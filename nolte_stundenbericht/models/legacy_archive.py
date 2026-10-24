import re

from odoo import _, api, fields, models


class NolteServiceLegacyArchive(models.Model):
    """A lightweight index for historical report PDFs already stored by Odoo.

    The document itself deliberately remains the original ``ir.attachment`` on
    the invoice.  This model only stores searchable metadata and a reference.
    """

    _name = "nolte.service.report.legacy.archive"
    _description = "Archivierter PDF-Bericht (bestehendes PDF)"
    _order = "service_date desc, id desc"

    name = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Kunde", required=True, index=True, ondelete="restrict")
    invoice_id = fields.Many2one("account.move", string="Rechnung", required=True, index=True, ondelete="restrict")
    attachment_id = fields.Many2one("ir.attachment", string="Vorhandenes PDF", required=True, index=True, ondelete="restrict")
    source_filename = fields.Char(string="PDF-Datei", related="attachment_id.name", readonly=True)
    service_date = fields.Date(string="Einsatzdatum", index=True)
    period_text = fields.Char(string="Zeitraum")
    technician_name = fields.Char(string="Servicetechniker")
    service_location = fields.Char(string="Einsatzort", index=True)
    machine_number = fields.Char(string="Maschinen-Nr.")
    machine_type = fields.Char(string="Maschinentyp")
    import_source = fields.Selection([
        ("invoice_pdf", "Rechnungsanhang"),
        ("manual", "Manuell"),
    ], default="invoice_pdf", required=True, readonly=True)
    imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)

    _attachment_unique = models.Constraint(
        "UNIQUE(attachment_id)",
        "Dieses PDF ist bereits im Stundenbericht-Archiv verlinkt.",
    )

    def action_open_pdf(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/nolte_stundenbericht/legacy-archive/%s/preview" % self.id,
            "target": "new",
        }

    def action_refresh_metadata(self):
        """Refresh searchable fields from the linked invoice without copying a PDF."""
        for record in self:
            values = self._metadata_from_invoice(record.invoice_id, record.attachment_id)
            record.write({key: values[key] for key in (
                "name", "service_date", "period_text", "technician_name",
                "service_location", "machine_number", "machine_type",
            )})
        return True

    @api.model
    def _is_candidate_filename(self, filename, keywords=None):
        filename = (filename or "").casefold()
        terms = keywords or ("stundenbericht", "servicebericht", "einsatzbericht", "arbeitsbericht")
        return any(term.casefold().strip() and term.casefold().strip() in filename for term in terms)

    @api.model
    def _invoice_note_text(self, invoice):
        """Return all invoice display lines, where legacy exports keep metadata."""
        return "\n".join(invoice.invoice_line_ids.filtered("display_type").mapped("name"))

    @api.model
    def _metadata_from_invoice(self, invoice, attachment):
        text = self._invoice_note_text(invoice)

        def find(labels):
            pattern = r"(?:^|\\n)\\s*(?:%s)\\s*:\\s*([^\\n]+)" % "|".join(labels)
            match = re.search(pattern, text, flags=re.IGNORECASE)
            return match.group(1).strip() if match else False

        period = find((r"einsatzzeitraum", r"zeitraum", r"period"))
        return {
            "name": attachment.name or invoice.name,
            "company_id": invoice.company_id.id,
            "partner_id": invoice.partner_id.commercial_partner_id.id,
            "invoice_id": invoice.id,
            "attachment_id": attachment.id,
            "service_date": invoice.invoice_date,
            "period_text": period,
            "technician_name": find((r"servicetechniker", r"service technician")),
            "service_location": find((r"einsatzort", r"ausf(?:ü|u)hrungsort", r"work site", r"service location")) or invoice.partner_shipping_id.display_name or False,
            "machine_number": find((r"maschinen(?:[- ]?nr\\.?| no\\.?)", r"machine(?:[- ]?no\\.?| number)?")),
            "machine_type": find((r"maschinentyp", r"machine type")),
        }

    @api.model
    def _attachment_invoice(self, attachment, invoice_cache):
        """Resolve a PDF attached directly to an invoice or to its chatter."""
        if attachment.res_model == "account.move" and str(attachment.res_id or "").isdigit():
            return invoice_cache.get(int(attachment.res_id))
        if attachment.res_model == "mail.message" and str(attachment.res_id or "").isdigit():
            message = self.env["mail.message"].sudo().browse(int(attachment.res_id)).exists()
            if message and message.model == "account.move" and str(message.res_id or "").isdigit():
                return invoice_cache.get(int(message.res_id))
        return self.env["account.move"]

    @api.model
    def candidate_attachments(self, company, keywords=None, date_from=False, date_to=False, limit=1000, include_all_pdfs=False):
        """Find invoice PDFs directly attached to invoices or their chatter.

        ``include_all_pdfs`` intentionally leaves broad matches unselected in
        the wizard. It is useful for older, generic names such as
        ``2026-014-AL.pdf`` that cannot be recognised from their filename.
        """
        domain = [("mimetype", "=", "application/pdf")]
        if not include_all_pdfs:
            terms = [term for term in (keywords or ("stundenbericht", "servicebericht", "einsatzbericht", "arbeitsbericht")) if term and term.strip()]
            if not terms:
                return []
            domain += ["|"] * (len(terms) - 1) + [("name", "ilike", term.strip()) for term in terms]
        attachments = self.env["ir.attachment"].sudo().search(
            domain,
            order="create_date desc, id desc",
            # A matching file may belong to another document (for example a
            # project task). Fetch a small buffer so the requested number of
            # invoice-backed PDFs is still available after that filtering.
            limit=limit * 10,
        )
        candidates = []
        invoice_ids = [int(item.res_id) for item in attachments if item.res_model == "account.move" and str(item.res_id or "").isdigit()]
        message_ids = [int(item.res_id) for item in attachments if item.res_model == "mail.message" and str(item.res_id or "").isdigit()]
        messages = self.env["mail.message"].sudo().browse(message_ids).exists()
        invoice_ids += [int(message.res_id) for message in messages if message.model == "account.move" and str(message.res_id or "").isdigit()]
        invoices = {invoice.id: invoice for invoice in self.env["account.move"].sudo().browse(invoice_ids).exists()}
        for attachment in attachments:
            invoice = self._attachment_invoice(attachment, invoices)
            if not invoice or invoice.company_id != company or invoice.move_type not in ("out_invoice", "out_refund"):
                continue
            if date_from and invoice.invoice_date and invoice.invoice_date < date_from:
                continue
            if date_to and invoice.invoice_date and invoice.invoice_date > date_to:
                continue
            if not include_all_pdfs and not self._is_candidate_filename(attachment.name, keywords):
                continue
            candidates.append((attachment, invoice, self._is_candidate_filename(attachment.name, keywords)))
            if len(candidates) >= limit:
                break
        return candidates

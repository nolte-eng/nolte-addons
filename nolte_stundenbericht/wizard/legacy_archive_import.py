from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NolteServiceLegacyArchiveImport(models.TransientModel):
    _name = "nolte.service.report.legacy.import"
    _description = "Historische Stundenberichte aus Rechnungsanhängen übernehmen"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, readonly=True)
    date_from = fields.Date(string="Rechnungsdatum ab")
    date_to = fields.Date(string="Rechnungsdatum bis")
    keywords = fields.Char(
        string="Dateinamen enthalten",
        required=True,
        default="stundenbericht, servicebericht, einsatzbericht, arbeitsbericht",
        help="Nur PDF-Anhänge mit einem dieser Begriffe im Dateinamen werden vorgeschlagen.",
    )
    include_all_invoice_pdfs = fields.Boolean(
        string="Alle PDF-Dateianhänge von Rechnungen prüfen",
        help="Auch PDF-Dateien mit allgemeinen Namen werden angezeigt. Diese werden nicht automatisch ausgewählt.",
    )
    max_candidates = fields.Integer(string="Maximale Treffer", default=1000, required=True)
    line_ids = fields.One2many("nolte.service.report.legacy.import.line", "wizard_id", string="Vorschau")
    scanned_at = fields.Datetime(readonly=True)

    def action_scan(self):
        self.ensure_one()
        if self.max_candidates < 1:
            raise UserError(_("Die maximale Trefferzahl muss mindestens 1 sein."))
        self.line_ids.unlink()
        archive = self.env["nolte.service.report.legacy.archive"]
        keywords = [item.strip() for item in self.keywords.split(",") if item.strip()]
        existing_ids = set(archive.sudo().search([]).mapped("attachment_id").ids)
        values = []
        for attachment, invoice, filename_matches in archive.candidate_attachments(
            self.company_id, keywords, self.date_from, self.date_to, self.max_candidates, self.include_all_invoice_pdfs,
        ):
            metadata = archive._metadata_from_invoice(invoice, attachment)
            already_linked = attachment.id in existing_ids
            values.append({
                "wizard_id": self.id,
                "selected": filename_matches and not already_linked,
                "status": "already_linked" if already_linked else ("ready" if filename_matches else "needs_review"),
                "attachment_id": attachment.id,
                "invoice_id": invoice.id,
                "partner_id": metadata["partner_id"],
                "service_date": metadata["service_date"],
                "period_text": metadata["period_text"],
                "technician_name": metadata["technician_name"],
                "service_location": metadata["service_location"],
                "machine_number": metadata["machine_number"],
                "machine_type": metadata["machine_type"],
            })
        self.env["nolte.service.report.legacy.import.line"].create(values)
        self.scanned_at = fields.Datetime.now()
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}

    def action_import_selected(self):
        self.ensure_one()
        archive = self.env["nolte.service.report.legacy.archive"]
        selected = self.line_ids.filtered(lambda line: line.selected and line.status in ("ready", "needs_review"))
        created = 0
        for line in selected:
            if archive.sudo().search_count([("attachment_id", "=", line.attachment_id.id)]):
                line.write({"status": "already_linked", "selected": False})
                continue
            values = archive._metadata_from_invoice(line.invoice_id, line.attachment_id)
            values.update({
                "service_date": line.service_date or values["service_date"],
                "period_text": line.period_text,
                "technician_name": line.technician_name,
                "service_location": line.service_location,
                "machine_number": line.machine_number,
                "machine_type": line.machine_type,
            })
            archive.create(values)
            line.write({"status": "imported", "selected": False})
            created += 1
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Archiv aktualisiert"), "message": _("%s PDF-Verweise wurden ohne Dateikopie ins Archiv aufgenommen.") % created, "type": "success", "sticky": False}}


class NolteServiceLegacyArchiveImportLine(models.TransientModel):
    _name = "nolte.service.report.legacy.import.line"
    _description = "Vorschau historischer Stundenberichte"
    _order = "service_date desc, id desc"

    wizard_id = fields.Many2one("nolte.service.report.legacy.import", required=True, ondelete="cascade")
    selected = fields.Boolean(default=True)
    status = fields.Selection([
        ("ready", "Bereit"),
        ("needs_review", "Bitte prüfen"),
        ("already_linked", "Bereits verlinkt"),
        ("imported", "Übernommen"),
    ], required=True, default="ready")
    attachment_id = fields.Many2one("ir.attachment", string="PDF", required=True, readonly=True)
    invoice_id = fields.Many2one("account.move", string="Rechnung", required=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Kunde", readonly=True)
    service_date = fields.Date(string="Einsatzdatum")
    period_text = fields.Char(string="Zeitraum")
    technician_name = fields.Char(string="Servicetechniker")
    service_location = fields.Char(string="Einsatzort")
    machine_number = fields.Char(string="Maschinen-Nr.")
    machine_type = fields.Char(string="Maschinentyp")

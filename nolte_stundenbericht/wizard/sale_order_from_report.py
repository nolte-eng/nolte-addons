from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NolteSaleOrderFromReportWizard(models.TransientModel):
    _name = "nolte.service.report.sale.order.wizard"
    _description = "Angebotsentwurf aus Stundenbericht erstellen"

    report_id = fields.Many2one("nolte.service.report", required=True, readonly=True)
    company_id = fields.Many2one(related="report_id.company_id", readonly=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Odoo-Kunde",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        report = self.env["nolte.service.report"].browse(self.env.context.get("active_id")).exists()
        if not report:
            return values
        if report.sale_order_id:
            raise UserError(_("Für diesen Stundenbericht ist bereits ein Auftrag hinterlegt."))
        if report.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill"):
            raise UserError(_("Ein Angebotsentwurf kann erst nach der Kundenbestätigung erstellt werden."))
        partner = report.partner_id.commercial_partner_id
        values.update({"report_id": report.id, "partner_id": partner.id or False})
        return values

    def action_create_sale_order(self):
        self.ensure_one()
        report = self.report_id
        if report.sale_order_id:
            raise UserError(_("Für diesen Stundenbericht ist inzwischen bereits ein Auftrag hinterlegt."))
        if report.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill"):
            raise UserError(_("Ein Angebotsentwurf kann erst nach der Kundenbestätigung erstellt werden."))
        if not self.partner_id or not self.partner_id.active:
            raise UserError(_("Bitte wählen Sie einen aktiven Odoo-Kunden aus."))

        partner = self.partner_id.commercial_partner_id
        if partner.company_id and partner.company_id != report.company_id:
            raise UserError(_("Der gewählte Kunde gehört zu einem anderen Unternehmen."))
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "company_id": report.company_id.id,
            "origin": report.name,
            "client_order_ref": report.name,
        })
        # Keep the service context on the quotation itself, like the note
        # block added by Nolte Überstunden to imported quotations.
        note_lines = ["Stundenbericht: %s" % report.name]
        location = report.service_location_name or report.service_location
        if location:
            note_lines.append("Einsatzort: %s" % location)
        technicians = report.member_ids.mapped("employee_id.name")
        if technicians:
            note_lines.append("Servicetechniker: %s" % ", ".join(dict.fromkeys(technicians)))
        if report.machine_type:
            note_lines.append("Maschinentyp: %s" % report.machine_type)
        if report.machine_number:
            note_lines.append("Maschinennummer: %s" % report.machine_number)
        dates = report.member_ids.mapped("service_date") or [report.service_date]
        dates = sorted(date for date in dates if date)
        if dates:
            date_text = dates[0].strftime("%d.%m.%Y")
            if dates[-1] != dates[0]:
                date_text += "–%s" % dates[-1].strftime("%d.%m.%Y")
            note_lines.append("Einsatzzeitraum: %s" % date_text)
        if report.work_description:
            note_lines.append("Arbeitsauftrag: %s" % report.work_description.strip())
        if report.public_note:
            note_lines.append("Notizen: %s" % report.public_note.strip())
        if note_lines:
            self.env["sale.order.line"].create({
                "order_id": order.id,
                "display_type": "line_note",
                "name": "\n".join(note_lines),
                "sequence": 1,
            })
        report.write({"sale_order_id": order.id})
        report.message_post(body=_("Angebotsentwurf %(order)s für %(customer)s erstellt und verknüpft.") % {
            "order": order.name,
            "customer": partner.display_name,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Stundenbericht"),
            "res_model": "nolte.service.report",
            "res_id": report.id,
            "view_mode": "form",
            "target": "current",
        }

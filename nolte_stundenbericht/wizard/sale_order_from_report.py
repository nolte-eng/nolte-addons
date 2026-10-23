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
        if report.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill"):
            raise UserError(_("Ein Angebotsentwurf kann erst nach der Kundenbestätigung erstellt werden."))
        if not self.partner_id or not self.partner_id.active:
            raise UserError(_("Bitte wählen Sie einen aktiven Odoo-Kunden aus."))
        report._ensure_sale_order(partner=self.partner_id)
        return {
            "type": "ir.actions.act_window",
            "name": _("Stundenbericht"),
            "res_model": "nolte.service.report",
            "res_id": report.id,
            "view_mode": "form",
            "target": "current",
        }

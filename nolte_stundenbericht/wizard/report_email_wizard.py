from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize


class ReportEmailWizard(models.TransientModel):
    _name = "nolte.service.report.email.wizard"
    _description = "E-Mail-Adresse für den Stundenbericht"

    report_id = fields.Many2one("nolte.service.report", required=True, readonly=True)
    customer_email = fields.Char(string="Kunden-E-Mail", required=True)
    purpose = fields.Selection([("pdf", "Bericht senden"), ("signature", "Unterschrift anfordern")], required=True, readonly=True)

    def action_continue(self):
        self.ensure_one()
        self.check_access("write")
        report = self.report_id
        report.check_access("write")
        address = email_normalize(self.customer_email)
        if not address:
            raise UserError(_("Bitte eine gültige Kunden-E-Mail-Adresse eingeben."))
        # Report-specific recipient only. Never change the customer master
        # or the signed PDF/snapshot when correcting the delivery address.
        report.write({"manual_contact_email": address})
        if self.purpose == "signature":
            return report.action_request_online_signature()
        return report.action_send_customer_pdf()

from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_l10n_german_template_data = fields.Binary(compute='_compute_german_template_data')
    x_l10n_german_document_title = fields.Char(compute='_compute_german_document_title')
    x_l10n_german_addresses = fields.Binary(compute='_compute_german_addresses', exportable=False)

    def _compute_german_template_data(self):
        for record in self:
            data = []
            if record.name:
                data.append(("Rechnungsnummer", record.name))
            if record.invoice_date:
                data.append(("Rechnungsdatum", record.invoice_date.strftime('%d.%m.%Y')))
            if record.invoice_date_due:
                data.append(("Fälligkeitsdatum", record.invoice_date_due.strftime('%d.%m.%Y')))
            if record.invoice_origin:
                data.append(("Quelle", record.invoice_origin))
            if record.ref:
                data.append(("Referenz", record.ref))
            if record.user_id:
                data.append(("Ansprechpartner", record.user_id.name or ""))
                if record.user_id.phone:
                    data.append(("Telefon", record.user_id.phone))
                if record.user_id.email:
                    data.append(("E-Mail", record.user_id.email))
            record.x_l10n_german_template_data = str(data).encode('utf-8')

    def _compute_german_document_title(self):
        for record in self:
            title = ""
            if record.move_type == 'out_invoice':
                title = "Rechnung" if record.state == 'posted' else "Rechnungsentwurf"
            elif record.move_type == 'out_refund':
                title = "Gutschrift"
            elif record.move_type == 'in_refund':
                title = "Eingangs-Gutschrift"
            elif record.move_type == 'in_invoice':
                title = "Eingangsrechnung"
            record.x_l10n_german_document_title = title

    def _compute_german_addresses(self):
        for record in self:
            addresses = []
            if record.partner_shipping_id == record.partner_id:
                addresses.append(("Rechnungs- und Lieferadresse", record.partner_shipping_id.name or ""))
            elif record.move_type in ("in_invoice", "in_refund") or not record.partner_shipping_id:
                addresses.append(("Rechnungsadresse", record.partner_id.name or ""))
            else:
                addresses.append(("Lieferadresse", record.partner_shipping_id.name or ""))
                addresses.append(("Rechnungsadresse", record.partner_id.name or ""))
            record.x_l10n_german_addresses = str(addresses).encode('utf-8')
from odoo import models, fields, _
from odoo.tools import format_date


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    l10n_german_template_data = fields.Binary(compute='_compute_l10n_german_template_data')
    l10n_german_document_title = fields.Char(compute='_compute_l10n_german_document_title')
    l10n_german_addresses = fields.Binary(compute='_compute_l10n_german_addresses', exportable=False)

    def _compute_l10n_german_template_data(self):
        for record in self:
            record.l10n_german_template_data = data = []
            if record.state in ('draft', 'sent'):
                if record.name:
                    data.append((_("Quotation No."), record.name))
                if record.date_order:
                    data.append((_("Quotation Date"), format_date(self.env, record.date_order)))
                if record.validity_date:
                    data.append((_("Expiration"), format_date(self.env, record.validity_date)))
            else:
                if record.name:
                    data.append((_("Order No."), record.name))
                if record.date_order:
                    data.append((_("Order Date"), format_date(self.env, record.date_order)))
            if record.client_order_ref:
                data.append((_('Customer Reference'), record.client_order_ref))
            if record.user_id:
                data.append((_("Salesperson"), record.user_id.name))
            if record.user_id.phone:
                data.append((_("Phone"), record.user_id.phone))
            if record.user_id.email:
                data.append((_("E-Mail"), record.user_id.email))
            if 'incoterm' in record._fields and record.incoterm:
                data.append((_("Incoterm"), record.incoterm.code))

    def _compute_l10n_german_document_title(self):
        for record in self:
            if self._context.get('proforma'):
                record.l10n_germsn_document_title = _('Pro Forma Invoice')
            elif record.state in ('draft', 'sent'):
                record.l10n_german_document_title = _('Quotation')
            else:
                record.l10n_german_document_title = _('Sales Order')

    def _compute_l10n_german_addresses(self):
        for record in self:
            record.l10n_german_addresses = data = []
            if record.partner_shipping_id == record.partner_invoice_id:
                data.append((_("Invoicing and Shipping Address:"), record.partner_shipping_id))
            else:
                data.append((_("Shipping Address:"), record.partner_shipping_id))
                data.append((_("Invoicing Address:"), record.partner_invoice_id))

    def check_field_access_rights(self, operation, field_names):
        field_names = super().check_field_access_rights(operation, field_names)
        return [field_name for field_name in field_names if field_name not in {
            'l10n_german_addresses',
        }]

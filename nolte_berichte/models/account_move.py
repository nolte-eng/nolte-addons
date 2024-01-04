from odoo import models, fields, _
from odoo.tools import format_date


class AccountMove(models.Model):
    _inherit = 'account.move'

    german_template_data = fields.Binary(compute='_compute_german_template_data')
    german_document_title = fields.Char(compute='_compute_german_document_title')

    def _compute_german_template_data(self):
        for record in self:
            record.german_template_data = data = []
            if record.name:
                data.append((_("Invoice No."), record.name))
            if record.invoice_date:
                data.append((_("Invoice Date"), format_date(self.env, record.invoice_date)))
            if record.invoice_date_due:
                data.append((_("Due Date"), format_date(self.env, record.invoice_date_due)))
            if record.invoice_origin:
                data.append((_("Source"), record.invoice_origin))
            if record.ref:
                data.append((_("Reference"), record.ref))
            if record.user_id:
                data.append((_("Contact person"), record.user_id.name))
            if record.user_id.phone:
                data.append((_("Phone"), record.user_id.phone))
            if record.user_id.email:
                data.append((_("E-Mail"), record.user_id.email))

    def _compute_german_document_title(self):
        for record in self:
            record.german_document_title = ''
            if record.move_type == 'out_invoice':
                if record.state == 'posted':
                    record.german_document_title = _('Invoice')
                elif record.state == 'draft':
                    record.german_document_title = _('Draft Invoice')
                elif record.state == 'cancel':
                    record.german_document_title = _('Cancelled Invoice')
            elif record.move_type == 'out_refund':
                record.german_document_title = _('Credit Note')
            elif record.move_type == 'in_refund':
                record.german_document_title = _('Vendor Credit Note')
            elif record.move_type == 'in_invoice':
                record.german_document_title = _('Vendor Bill')
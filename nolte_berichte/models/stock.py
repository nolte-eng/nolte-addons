from odoo import models, fields, _
from odoo.tools import format_date


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    german_template_data = fields.Binary(compute='_compute_german_template_data')
    german_addresses = fields.Binary(compute='_compute_german_addresses')

    def _compute_german_template_data(self):
        self.german_template_data = []

    def _compute_german_addresses(self):
        for record in self:
            record.german_addresses = data = []
            if record.partner_id:
                if record.picking_type_id.code == 'incoming':
                    data.append((_('Vendor Address:'), record.partner_id))
                if record.picking_type_id.code == 'internal':
                    data.append((_('Warehouse Address:'), record.partner_id))
                if record.picking_type_id.code == 'outgoing' and record.move_ids_without_package and record.move_ids_without_package[0].partner_id \
                        and record.move_ids_without_package[0].partner_id.id != record.partner_id.id:
                    data.append((_('Customer Address:'), record.partner_id))

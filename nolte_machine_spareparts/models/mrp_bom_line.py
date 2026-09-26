# -*- coding: utf-8 -*-
from odoo import fields, models

class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    qty_available = fields.Float(
        string="Bestand",
        related="product_id.qty_available",
        readonly=True,
    )

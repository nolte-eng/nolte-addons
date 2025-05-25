# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NolteEng(models.Model):
    _name = 'nolte.eng'
    _description = 'Nolte Engineering Data'

    name = fields.Char(string='Name')
    value = fields.Integer(string='Value')
    value2 = fields.Float(string='Computed Value', compute="_compute_value2", store=True)
    description = fields.Text(string='Description')

    @api.depends('value')
    def _compute_value2(self):
        for record in self:
            record.value2 = float(record.value) / 100

from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    ceo_title = fields.Char(string="CEO Titel")
    ceo_01 = fields.Char(string="Geschäftsführer 1")
    ceo_02 = fields.Char(string="Geschäftsführer 2")

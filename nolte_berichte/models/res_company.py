# -*- coding: utf-8 -*-


# Copyright 2021-Nolte engineering GmbH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    ceo_title = fields.Char('res.partner.title')
    ceo_01 = fields.Char('executive director')
    ceo_02 = fields.Char('executive director#2')
    com_fax = fields.Char('company_fax')

class BaseDocumentLayout(models.TransientModel):
    _inherit ='base.document.layout'
    # Those following fields are required as a company to create invoice report

    ceo_title = fields.Char('res.partner.title', readonly=True)
    ceo_01 = fields.Char('executive director')
    ceo_02 = fields.Char('executive director#2')
    com_fax = fields.Char('company_fax')
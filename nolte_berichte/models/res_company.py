# -*- coding: utf-8 -*-
# Copyright 2014-now Equitania Software GmbH - Pforzheim - Germany
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    ceo_title = fields.Char('res.partner.title')
    ceo_01 = fields.Char('executive director')
    ceo_02 = fields.Char('executive director#2')
    com_fax = fields.Char('company_fax')

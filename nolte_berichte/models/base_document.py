from odoo import models, fields, _
#from odoo.tools import format_date
l10n_de_template_data = fields.Binary(compute='_compute_l10n_de_template_data')

def _compute_l10n_de_template_data(self):
    self.l10n_de_template_data = [
        (_("Invoice No."), 'INV/2021/12345'),
        (_("Invoice Date"), format_date(self.env, fields.Date.today())),
        (_("Due Date"), format_date(self.env, fields.Date.add(fields.Date.today(), days=7))),
        (_("Reference"), 'SO/2021/45678'),
        (_("Your Contact"), 'John Doe'),
        (_("Phone"), '030-3000000'),
    ]
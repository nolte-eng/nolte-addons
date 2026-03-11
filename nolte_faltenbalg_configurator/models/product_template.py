from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_faltenbalg_configurator = fields.Boolean(
        string="Faltenbalg-Konfigurator aktiv",
        help="Zeigt auf der Website einen Button zum Faltenbalg-Konfigurator an.",
    )

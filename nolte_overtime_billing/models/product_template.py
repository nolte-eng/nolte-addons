from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Some databases (esp. during upgrades/migrations) contain a NOT NULL column `base_unit_count`
    # although the field may not be provided by installed addons in Community setups.
    # Defining it here prevents NOT NULL violations when creating products.
    base_unit_count = fields.Float(
        string="Base Unit Count",
        default=1.0,
        required=True,
        help="Internal helper to satisfy databases where this column is NOT NULL.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("base_unit_count", 1.0)
        return super().create(vals_list)

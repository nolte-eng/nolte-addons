from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    nolte_product_work_id = fields.Many2one("product.product", string="Work Time (Regular)",
        config_parameter="nolte_overtime_billing.product_work_id")
    nolte_product_travel_id = fields.Many2one("product.product", string="Travel Time (Regular)",
        config_parameter="nolte_overtime_billing.product_travel_id")

    nolte_product_work_ot30_id = fields.Many2one("product.product", string="Work Time Overtime 30%",
        config_parameter="nolte_overtime_billing.product_work_ot30_id")
    nolte_product_work_ot50_id = fields.Many2one("product.product", string="Work Time Overtime 50%",
        config_parameter="nolte_overtime_billing.product_work_ot50_id")
    nolte_product_travel_ot30_id = fields.Many2one("product.product", string="Travel Time Overtime 30%",
        config_parameter="nolte_overtime_billing.product_travel_ot30_id")
    nolte_product_travel_ot50_id = fields.Many2one("product.product", string="Travel Time Overtime 50%",
        config_parameter="nolte_overtime_billing.product_travel_ot50_id")

    nolte_product_km_id = fields.Many2one("product.product", string="Mileage Allowance",
        config_parameter="nolte_overtime_billing.product_km_id")
    nolte_product_overnight_id = fields.Many2one("product.product", string="Overnight Allowance ",
        config_parameter="nolte_overtime_billing.product_overnight_id")

    nolte_product_allowance_id = fields.Many2one("product.product", string="Daily Allowance",
        config_parameter="nolte_overtime_billing.product_allowance_id")

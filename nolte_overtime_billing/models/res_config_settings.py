from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    nolte_product_work_id = fields.Many2one("product.product", string="Arbeitszeit (normal)",
        config_parameter="nolte_overtime_billing.product_work_id")
    nolte_product_travel_id = fields.Many2one("product.product", string="Fahrzeit (normal)",
        config_parameter="nolte_overtime_billing.product_travel_id")

    nolte_product_work_ot30_id = fields.Many2one("product.product", string="Arbeitszeit Überstunden 30%",
        config_parameter="nolte_overtime_billing.product_work_ot30_id")
    nolte_product_work_ot50_id = fields.Many2one("product.product", string="Arbeitszeit Überstunden 50%",
        config_parameter="nolte_overtime_billing.product_work_ot50_id")
    nolte_product_travel_ot30_id = fields.Many2one("product.product", string="Fahrzeit Überstunden 30%",
        config_parameter="nolte_overtime_billing.product_travel_ot30_id")
    nolte_product_travel_ot50_id = fields.Many2one("product.product", string="Fahrzeit Überstunden 50%",
        config_parameter="nolte_overtime_billing.product_travel_ot50_id")

    nolte_product_km_id = fields.Many2one("product.product", string="Kilometerpauschale",
        config_parameter="nolte_overtime_billing.product_km_id")
    nolte_product_overnight_id = fields.Many2one("product.product", string="Übernachtungspauschale ",
        config_parameter="nolte_overtime_billing.product_overnight_id")

    nolte_product_allowance_id = fields.Many2one("product.product", string="Auslöse / pro Tag",
        config_parameter="nolte_overtime_billing.product_allowance_id")

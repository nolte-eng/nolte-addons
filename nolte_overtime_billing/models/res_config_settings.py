from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    nolte_product_work_id = fields.Many2one("product.product", string="Produkt Arbeitszeit (normal)",
        config_parameter="nolte_overtime_billing.product_work_id")
    nolte_product_travel_id = fields.Many2one("product.product", string="Produkt Fahrzeit (normal)",
        config_parameter="nolte_overtime_billing.product_travel_id")

    nolte_product_work_ot30_id = fields.Many2one("product.product", string="Produkt Arbeitszeit Überstunden 30%",
        config_parameter="nolte_overtime_billing.product_work_ot30_id")
    nolte_product_work_ot50_id = fields.Many2one("product.product", string="Produkt Arbeitszeit Überstunden 50%",
        config_parameter="nolte_overtime_billing.product_work_ot50_id")
    nolte_product_travel_ot30_id = fields.Many2one("product.product", string="Produkt Fahrzeit Überstunden 30%",
        config_parameter="nolte_overtime_billing.product_travel_ot30_id")
    nolte_product_travel_ot50_id = fields.Many2one("product.product", string="Produkt Fahrzeit Überstunden 50%",
        config_parameter="nolte_overtime_billing.product_travel_ot50_id")

    nolte_product_km_id = fields.Many2one("product.product", string="Produkt Kilometer (optional)",
        config_parameter="nolte_overtime_billing.product_km_id")
    nolte_product_overnight_id = fields.Many2one("product.product", string="Produkt Übernachtungspauschale (optional)",
        config_parameter="nolte_overtime_billing.product_overnight_id")

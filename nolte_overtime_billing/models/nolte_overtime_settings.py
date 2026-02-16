from odoo import api, fields, models


class NolteOvertimeSettings(models.TransientModel):
    """Standalone settings wizard.

    Using res.config.settings from a custom menu can behave inconsistently
    (values not applied/persisted) depending on the context/action.

    This wizard writes directly to ir.config_parameter, so values always stick.
    """

    _name = "nolte.overtime.settings"
    _description = "Nolte Überstunden – Einstellungen"

    # Normal
    product_work_id = fields.Many2one("product.product", string="Arbeitszeit (normal)")
    product_travel_id = fields.Many2one("product.product", string="Fahrzeit (normal)")

    # Overtime
    product_work_ot30_id = fields.Many2one("product.product", string="Arbeitszeit Überstunden 30 %")
    product_work_ot50_id = fields.Many2one("product.product", string="Arbeitszeit Überstunden 50 %")
    product_travel_ot30_id = fields.Many2one("product.product", string="Fahrzeit Überstunden 30 %")
    product_travel_ot50_id = fields.Many2one("product.product", string="Fahrzeit Überstunden 50 %")

    # Extras
    product_km_id = fields.Many2one("product.product", string="Kilometerpauschale")
    product_overnight_id = fields.Many2one("product.product", string="Übernachtungspauschale")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        icp = self.env["ir.config_parameter"].sudo()

        def _get_m2o(key: str):
            val = icp.get_param(key) or ""
            try:
                pid = int(val)
            except Exception:
                pid = 0
            return pid or False

        mapping = {
            "product_work_id": "nolte_overtime_billing.product_work_id",
            "product_travel_id": "nolte_overtime_billing.product_travel_id",
            "product_work_ot30_id": "nolte_overtime_billing.product_work_ot30_id",
            "product_work_ot50_id": "nolte_overtime_billing.product_work_ot50_id",
            "product_travel_ot30_id": "nolte_overtime_billing.product_travel_ot30_id",
            "product_travel_ot50_id": "nolte_overtime_billing.product_travel_ot50_id",
            "product_km_id": "nolte_overtime_billing.product_km_id",
            "product_overnight_id": "nolte_overtime_billing.product_overnight_id",
        }

        for field_name, key in mapping.items():
            if field_name in fields_list:
                res[field_name] = _get_m2o(key)
        return res

    def action_save(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()

        def _set(key: str, m2o):
            icp.set_param(key, str(m2o.id) if m2o else "")

        _set("nolte_overtime_billing.product_work_id", self.product_work_id)
        _set("nolte_overtime_billing.product_travel_id", self.product_travel_id)
        _set("nolte_overtime_billing.product_work_ot30_id", self.product_work_ot30_id)
        _set("nolte_overtime_billing.product_work_ot50_id", self.product_work_ot50_id)
        _set("nolte_overtime_billing.product_travel_ot30_id", self.product_travel_ot30_id)
        _set("nolte_overtime_billing.product_travel_ot50_id", self.product_travel_ot50_id)
        _set("nolte_overtime_billing.product_km_id", self.product_km_id)
        _set("nolte_overtime_billing.product_overnight_id", self.product_overnight_id)

        return {"type": "ir.actions.act_window_close"}

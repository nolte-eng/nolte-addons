# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def post_init_hook(cr, registry=None):
    """Post-init hook: accepts env (Odoo 18) or (cr, registry)."""
    env = cr if hasattr(cr, "cr") else api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"].sudo()
    key_overnight = "nolte_overtime_billing.product_overnight_id"
    key_allowance = "nolte_overtime_billing.product_allowance_id"

    # Default Overnight Allowance
    if not ICP.get_param(key_overnight):
        tmpl = env.ref("nolte_overtime_billing.product_template_overnight", raise_if_not_found=False)
        if tmpl:
            product = tmpl.sudo().product_variant_id
            if product:
                ICP.set_param(key_overnight, str(product.id))

    # Default Allowance
    if not ICP.get_param(key_allowance):
        tmpl_a = env.ref("nolte_overtime_billing.product_template_allowance", raise_if_not_found=False)
        if tmpl_a:
            prod_a = tmpl_a.sudo().product_variant_id
            if prod_a:
                ICP.set_param(key_allowance, str(prod_a.id))

# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    """Auto-map default 'Übernachtungspauschale' product if not configured yet."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"].sudo()
    key = "nolte_overtime_billing.product_overnight_id"
    if ICP.get_param(key):
        return
    prod = env.ref("nolte_overtime_billing.product_overnight", raise_if_not_found=False)
    if not prod:
        prod = env["product.product"].search([("name", "=", "Übernachtungspauschale")], limit=1)
    if prod:
        ICP.set_param(key, str(prod.id))

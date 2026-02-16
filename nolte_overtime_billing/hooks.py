# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID


def post_init_hook(env):
    """Odoo 18+ post-init hook: called with an Environment instance.

    Auto-map default 'Übernachtungspauschale' product (variant) if not configured yet.
    We create only the product.template in XML; Odoo creates the single variant automatically.
    """
    env = env(user=SUPERUSER_ID)
    ICP = env["ir.config_parameter"].sudo()
    key = "nolte_overtime_billing.product_overnight_id"
    if ICP.get_param(key):
        return

    tmpl = env.ref("nolte_overtime_billing.product_template_overnight", raise_if_not_found=False)
    prod = False
    if tmpl and getattr(tmpl, "product_variant_id", False):
        prod = tmpl.product_variant_id

    if not prod:
        prod = env["product.product"].search([("name", "=", "Übernachtungspauschale")], limit=1)

    if prod:
        ICP.set_param(key, str(prod.id))

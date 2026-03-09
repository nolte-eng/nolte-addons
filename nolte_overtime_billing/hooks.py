# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

def _ensure_product_template_base_unit_count_default_cr(cr):
    """Some local schemas add a NOT NULL column `product_template.base_unit_count`
    without an ORM field/default. XML product.template creation would then insert NULL and crash.

    We defensively backfill NULLs and set a DEFAULT before any data files are loaded.
    """
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'product_template'
           AND column_name = 'base_unit_count'
        LIMIT 1
        """
    )
    if cr.fetchone():
        cr.execute("UPDATE product_template SET base_unit_count = 1 WHERE base_unit_count IS NULL")
        cr.execute("ALTER TABLE product_template ALTER COLUMN base_unit_count SET DEFAULT 1")


def pre_init_hook(cr):
    """Pre-init hook: accepts env (Odoo 18) or cr (older signatures)."""
    cr = getattr(cr, "cr", cr)
    _ensure_product_template_base_unit_count_default_cr(cr)


def post_init_hook(cr, registry=None):
    """Post-init hook: accepts env (Odoo 18) or (cr, registry)."""
    env = cr if hasattr(cr, "cr") else api.Environment(cr, SUPERUSER_ID, {})
    cr = env.cr
    _ensure_product_template_base_unit_count_default_cr(cr)

    ICP = env["ir.config_parameter"].sudo()
    key_overnight = "nolte_overtime_billing.product_overnight_id"
    key_allowance = "nolte_overtime_billing.product_allowance_id"

    # Default Übernachtungspauschale
    if not ICP.get_param(key_overnight):
        tmpl = env.ref("nolte_overtime_billing.product_template_overnight", raise_if_not_found=False)
        if tmpl:
            product = tmpl.sudo().product_variant_id
            if product:
                ICP.set_param(key_overnight, str(product.id))

    # Default Auslöse
    if not ICP.get_param(key_allowance):
        tmpl_a = env.ref("nolte_overtime_billing.product_template_allowance", raise_if_not_found=False)
        if tmpl_a:
            prod_a = tmpl_a.sudo().product_variant_id
            if prod_a:
                ICP.set_param(key_allowance, str(prod_a.id))

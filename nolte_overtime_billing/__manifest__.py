# -*- coding: utf-8 -*-
{
    "name": "Nolte Overtime Billing (CSV → Sales Order)",
    "version": "19.0.1.5.6",
    "category": "Sales",
    "summary": "Import timesheet CSV, calculate overtime, and create a sales order (and invoice).",
    "author": "Nolte Engineering / Nolte Sales",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "product", "uom", "nolte_spesenbericht"],
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
    "data": [
        "data/product_data.xml",
        "security/ir_model.xml",
        "security/ir.model.access.csv",
        "views/overtime_import_wizard_views.xml",
        "views/nolte_overtime_settings_views.xml",
        "views/menu.xml",
        "views/sale_order_views.xml",
    ],
    "application": True,
    "installable": True,
}

# -*- coding: utf-8 -*-
{
    "name": "Nolte Overtime Billing (CSV → Sales Order)",
    "version": "18.0.1.6.7",
    "category": "Sales",
    "summary": "Import Stundenbericht-CSV, berechne Überstunden, erstelle Verkaufsauftrag (und daraus Rechnung).",
    "author": "Nolte Engineering / Nolte Sales",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "product", "uom"],
    "data": [
        "security/ir.model.access.csv",
        "data/product_data.xml",
                "views/overtime_import_wizard_views.xml",
        "views/menu.xml",
        "views/nolte_overtime_settings_views.xml",
        "views/sale_order_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": False,
    "installable": True,
}

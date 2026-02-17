# -*- coding: utf-8 -*-
{
    "name": "Nolte Overtime Billing (CSV → Sales Order)",
    "version": "18.0.1.7.0",
    "category": "Sales",
    "summary": "Import Stundenbericht-CSV, berechne Überstunden, erstelle Verkaufsauftrag (und daraus Rechnung).",
    "author": "Nolte Engineering / Nolte Sales",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "product", "uom"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/overtime_import_wizard_views.xml",
        "views/menu.xml",
        "views/sale_order_views.xml",
    ],
    "application": False,
    "installable": True,
}

{
    "name": "Nolte Spesenbericht",
    "version": "20.0.1.7.8",
    "category": "Human Resources/Expenses",
    "summary": "Monatliche Arbeitszeit- und Spesenerfassung als Odoo-Webseite",
    "author": "Nolte Engineering / Nolte Sales",
    "license": "LGPL-3",
    "depends": ["website", "mail", "hr", "hr_holidays", "hr_expense", "product"],
    "data": [
        "security/spesenbericht_security.xml",
        "security/ir.model.access.csv",
        "data/nolte.bmf.rate.csv",
        "views/spesenbericht_views.xml",
        "views/spesenbericht_templates.xml",
        "views/spesenbericht_reports.xml",
        "views/overtime_report.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "nolte_spesenbericht/static/src/scss/spesenbericht.scss",
            "nolte_spesenbericht/static/src/js/spesenbericht.js",
        ],
    },
    "application": True,
    "installable": True,
    "post_init_hook": "post_init_hook",
}

{
    "name": "Nolte Faltenbalg Konfigurator",
    "version": "18.0.4.2.0",
    "summary": "Schritt-für-Schritt Website-Konfigurator für Faltenbalg-Anfragen",
    "category": "Website/Website",
    "author": "OpenAI for Nolte Engineering",
    "license": "LGPL-3",
    "depends": ["website_sale", "mail", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "data/website_page_data.xml",
        "views/product_template_views.xml",
        "views/faltenbalg_inquiry_views.xml",
        "views/website_templates.xml"
    ],
    "assets": {
        "web.assets_frontend": [
            "nolte_faltenbalg_configurator/static/src/css/faltenbalg.css",
            "nolte_faltenbalg_configurator/static/src/js/faltenbalg_wizard.js"
        ]
    },
    "installable": True,
    "application": False
}

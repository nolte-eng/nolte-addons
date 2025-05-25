{
    "name": "Nolte Berichte",
    "version": "18.0.1.0.0",
    "category": "Localization",
    "license": "LGPL-3",
    "summary": "Deutsche Berichtsanpassungen für Verkauf, Einkauf, Rechnung und Lager",
    "description": "Anpassung der Odoo-Berichte an die deutsche DIN 5008 Formatierung",
    "author": "Nolte Engineering GmbH",
    "website": "http://www.nolte-eng.de",
    "depends": ["l10n_din5008"],
    "data": [

        "views/report_templates.xml",
        "views/res_company_view.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "nolte_berichte/static/src/scss/*.scss",
        ]
    },
    "installable": True,
    "application": 'Accounting/Localizations',
    "auto_install": False,
}
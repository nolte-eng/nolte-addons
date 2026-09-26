{
    "name": "Produktanfrage & Detailaktionen",
    "version": "20.0.2.0.5",
    "category": "Website/eCommerce",
    "summary": "Herstellerunabhängige Anfrage-, Detail- und Prospektaktionen im Shop",
    "author": "Nolte Sales UG",
    "license": "LGPL-3",
    "depends": ["website_sale", "website_crm"],
    "data": [
        "views/product_template_views.xml",
        "views/website_sale_templates.xml",
        "views/quote_request_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "comev_product_cta/static/src/scss/comev_product_cta.scss",
            "comev_product_cta/static/src/js/product_variant_quote.js",
        ],
    },
    "installable": True,
    "application": False,
}

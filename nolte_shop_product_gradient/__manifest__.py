{
    "name": "Nolte Shop Product Gradient",
    "summary": "Dezenter Hintergrundverlauf fuer Produktbilder im Shop-Raster",
    "version": "20.0.1.0.1",
    "category": "Website/eCommerce",
    "author": "Nolte Engineering GmbH",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "data": ["views/shop_search.xml", "views/product_price_link.xml"],
    "assets": {
        "web.assets_frontend": [
            "nolte_shop_product_gradient/static/src/scss/product_cards.scss",
            "nolte_shop_product_gradient/static/src/scss/product_detail.scss",
        ],
    },
    "installable": True,
    "application": False,
}

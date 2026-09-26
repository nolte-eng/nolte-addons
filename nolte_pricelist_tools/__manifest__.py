{
    "name": "Nolte Pricelist Tools",
    "version": "20.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Preislistenpositionen öffnen und Produktvarianten gesammelt hinzufügen",
    "author": "Nolte Sales UG (haftungsbeschränkt)",
    "license": "LGPL-3",
    "depends": ["product", "sale_management"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/pricelist_variant_wizard_views.xml",
        "views/product_pricelist_views.xml"
    ],
    "installable": True,
    "application": False,
}

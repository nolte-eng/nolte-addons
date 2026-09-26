# -*- coding: utf-8 -*-
{
    "name": "Nolte: Kundenmaschinen Ersatzteile & PDF-Katalog",
    "summary": (
        "Verknüpft Maintenance-Equipment mit Maschinenmodellen, zeigt deren "
        "Ersatzteile und erzeugt Angebote und PDF-Kataloge."
    ),
    "version": "20.0.1.0.0",
    "category": "Maintenance",
    "author": "Nolte Engineering GmbH",
    "license": "LGPL-3",
    "depends": ["stock", "sale", "maintenance", "mrp", "contacts", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/maintenance_equipment_views.xml",
        "report/spare_parts_report.xml",
    ],
    "installable": True,
    "application": False,
}

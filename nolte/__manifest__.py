# -*- coding: utf-8 -*-
{
    'name': "nolte",
    'summary': 'Erweiterungen zum Anpassen von Odoo für Nolte Engineering GmbH',
    'description': """
Erweiterungen für Nolte Engineering GmbH
========================================
-Anpassung des Kalenders
	- Besitzer wird  angezeigt
	- Standardansicht ist Monat
	- Zeige 10 Termine an einen Tag an
    """,
    'author': 'Lars Nolte',
    'website': 'http://www.nolte-eng.de',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '15.0.0.1',

    # Benötigten Module werden eingebunden
    'depends': ['base', 'calendar', 'crm'],

    # always loaded
    'data': [

    # 'security/ir.model.access.csv',

    # Ansicht auf Monat umstellen
    'views/calendar_month_view.xml',
    # Ansicht Erweitern um Besitzer
    'views/calendar_owner_view.xml',
    # Anzahl der Angezeigten Events
    'views/calendar_event_view.xml',
    # Kundenverwaltung Archiv button
    'views/crm_archive_button.xml'
    ],

}

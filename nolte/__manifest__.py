{
    'name': 'Nolte Addon',
        'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Customized Calendar and CRM Enhancements',
    'description': """This module extends the Calendar and CRM capabilities with custom views and functionalities.""",
    'depends': ['base', 'calendar', 'crm'],
    'data': [
        'views/calendar_owner_view.xml',
        'views/calendar_event_view.xml',
        'views/calendar_month_view.xml',
        'views/crm_archive_button.xml',
        'security/ir.model.access.csv',
        'data/demo.xml'
    ],
    'demo': ['data/demo.xml'],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
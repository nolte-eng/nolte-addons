# -*- coding: utf-8 -*-
{
    'name': "nolte_mail_template",

    'summary': """
        Vorlagen fuer Emails""",

    'description': """
        Benutzerdefinierte vorlagen für E-Mails
    """,

    'author': "Lars Nolte",
    'website': "http://www.nolte-eng.de",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '13.0.1',

    # any module necessary for this one to work correctly
    'depends': ['mail','sale'],

    # always loaded
    'data': [
        'views/mail_template.xml',
    ],
}

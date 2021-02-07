# -*- coding: utf-8 -*-
{
    'name': "Nolte Berichte",

    'summary': """
        Anpassung der Berichte für Deutsche Firmen
""",

    'description': """
        Anpassung der Berichte an die Deutsche Schreibweise
    """,
    'author': "Nolte Engineering GmbH",
    'website': "http://www.nolte-eng.de",
    'category': 'Uncategorized',
    'version': '14.0.0.1',

    # any module necessary for this one to work correctly
    #    'depends': ['base', 'account', 'web', 'sale_comment_template', 'partner_fax'],
    'depends': ['base', 'account', 'web', 'partner_fax', 'sale'],

    'data': [
        #    'security/ir.model.access.csv',
        'views/report_invoice_document.xml',
        'views/report_saleorder_document.xml',
        'views/address_layout.xml',
        'views/external_layout_german.xml',
        'views/company_footer.xml',
        'views/paper_format.xml',
        'views/res_company_view.xml',
        'data/report_layout.xml'
    ]
}

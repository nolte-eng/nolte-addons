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

        'report/external_layout_german.xml',
        'report/report_invoice_document.xml',
        'report/report_saleorder_document.xml',
        'report/report_purchaseorder_document.xml',

        'views/address_layout.xml',
        'views/company_footer.xml',
        'views/res_company_view.xml',

        'data/paper_format.xml',
        'data/report_layout.xml'
    ]
}

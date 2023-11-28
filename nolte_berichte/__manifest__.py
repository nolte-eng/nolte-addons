{
    'name':'Nolte Berichte',
    'version':'16.0.1.0.0',
    'category':'Uncategorized',
    'license':'GPL-2',
    'summary':"""Anpassung der Berichte für Deutsche Firmen""",
    'description':"""Anpassung der Berichte an die Deutsche Schreibweise""",
    'author:':"Nolte Engineering GmbH",
    'website':"http://www.nolte-eng.de",

    'depends':['base', 'account', 'web', 'sale'],

    'data':[

       # 'report/external_layout_german.xml',
        'report/xpath_invoice_document.xml',
        'report/xpath_din5008.xml',
      #  'report/report_invoice_document.xml',
       # 'report/german_din5008.xml',
        'report/german_invoice_document.xml',
        'views/report_templates.xml',
       # 'report/report_invoice_document.xml',
        # 'report/report_saleorder_document.xml',
        # 'report/report_purchaseorder_document.xml',
        #
        # 'views/address_layout.xml',
        # 'views/company_footer.xml',
           'views/res_company_view.xml',
        #
        # 'data/paper_format.xml',
       # 'data/report_layout.xml'

    ],
    'assets': {
        'web.report_assets_common': [
            'nolte_berichte/static/src/**/*',
       ],
    },
 }




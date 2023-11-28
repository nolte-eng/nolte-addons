{
    'name':'Nolte Berichte',
    'version':'15.0.1.0.0',
    'category':'Uncategorized',
    'license':'GPL-2',
    'summary':"""Anpassung der Berichte für Deutsche Firmen""",
    'description':"""Anpassung der Berichte an die Deutsche Schreibweise""",
    'author:':"Nolte Engineering GmbH",
    'website':"http://www.nolte-eng.de",

    'depends':['base', 'account', 'web', 'sale'],

    'data':[
        'report/german_invoice_document.xml',
        'views/report_templates.xml',
        'views/res_company_view.xml',
       
        'data/report_layout.xml'
    ],
    'assets': {
        'web.report_assets_common': [
            'nolte_berichte/static/src/**/*',
       ],
    },
 }



# -*- coding: utf-8 -*-
{
    'name': 'Construction Progress Invoice - Work Done % Billing',
    'summary': 'Construction and contracting progress billing: bill each invoice line by Work Done %, track Previous %, contract value and guarantee, and print a Construction Invoice. Switch between Labour Supply and Construction invoices.',
    'description': """
Construction Progress Invoice
=============================
Progress billing for construction, contracting, fit-out, MEP and labour supply
companies on Odoo 19 Community and Enterprise.

* Labour Supply Invoice / Construction Invoice switch on customer invoices
* Work Done % per invoice line: the line amount, taxes and journal entry are
  calculated on the work done, using Odoo's standard invoice logic
* Previous % (already billed), Contract Amount and Guarantee (Gtee) per line
* Contract Value total on the invoice
* Construction Invoice PDF with Contract Amount, Previous %, Work Done %, tax and totals
* Filters for Construction and Labour Supply invoices
* Depends only on Accounting (account)

Keywords: construction invoice, progress billing, progressive invoice, interim
invoice, percentage of completion, work done percentage, contracting invoice,
contractor billing, labour supply invoice, subcontractor invoice.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'Saaskul',
    'website': 'https://saaskul.com',
    'live_test_url': 'https://saaskul.com/contactus?name=Live%20Preview%20-%20Construction%20Progress%20Invoice',
    'support': 'info.cpabooks@gmail.com',
    'license': 'OPL-1',
    'price': 140.00,
    'currency': 'USD',
    'images': [
        'static/description/banner.png',
    ],
    'depends': [
        'account',
    ],
    'data': [
        'views/account_move_views.xml',
        'report/report_invoice.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

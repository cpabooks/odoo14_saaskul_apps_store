# -*- coding: utf-8 -*-
{
    'name': 'Financial Statements Report',
    'summary': 'IFRS-style financial statements, trial balance mapping and corporate tax filing',
    'description': """
Cpabooks Audited Financials
===========================
Self-contained financial statement pack for Odoo 19 Community:

* Statement of Profit or Loss
* Statement of Financial Position
* Changes in Equity, Cash Flow, PPE schedule and notes
* Chart of accounts mapping and corporate tax filing categories
* PDF, Excel and CSV export
* Country-aware print follows the company currency: NGN prints FGN / Nigerian Naira,
  AED keeps U.A.E. / Arab Emirates Dirhams, a currency used by one country prints
  that country. A shared or missing currency defaults to FGN / Nigeria.
  The company address is not used.
  Non-AED companies get L1 and L4 export only.
* Optional "Load ISO Chart of Accounts" wizard (ISOSYSTEMS, Nigeria): account groups,
  ledgers and AFG mapping.

Depends only on Accounting (account). No other custom module is required.
    """,
    'version': '19.0.1.0.267',
    'category': 'Accounting',
    'author': 'Saaskul',
    'website': 'https://saaskul.com',
    'live_test_url': 'https://saaskul.com/contactus?name=Live%20Preview%20-%20Financial%20Statements%20Report',
    'support': 'info.cpabooks@gmail.com',
    'license': 'OPL-1',
    'price': 400.00,
    'currency': 'USD',
    'images': [
        'static/description/banner_screenshot.jpg',
    ],
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/audited_financial_security.xml',
        'data/multico_client_actions.xml',
        'views/audited_financials_views.xml',
        'views/account_account_views.xml',
        'views/audited_financial_ledger_merge_views.xml',
        'views/audited_financial_l1_print_wizard_views.xml',
        'views/audited_financial_print_setup_wizard_views.xml',
        'views/afg_journal_items_views.xml',
        'views/audited_financial_iso_coa_wizard_views.xml',
        'views/res_company_views.xml',
        'report/afg_audit_report.xml',
        'data/menu_cleanup_legacy_statements.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'audited_financials_saaskul/static/lib/jquery.js',
            'audited_financials_saaskul/static/src/css/audited_financials_dashboard.css',
            'audited_financials_saaskul/static/src/css/audited_financial_app_shell.css',
            'audited_financials_saaskul/static/src/css/afg_map_list.css',
            'audited_financials_saaskul/static/src/xml/audited_financials_dashboard.xml',
            'audited_financials_saaskul/static/src/js/audited_financials_dashboard.js',
            'audited_financials_saaskul/static/src/js/afg_map_list.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
}

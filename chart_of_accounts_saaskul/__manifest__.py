# -*- coding: utf-8 -*-
{
    'name': 'IFRS Chart of Accounts',
    'summary': 'IFRS L1/L2/L3 chart structure, ledger coding, reset tools and opening balance',
    'description': """
IFRS Chart of Accounts
======================
Structure your Odoo chart with IFRS-style L1 types, L2 groups and L3 ledgers.
Reset and regenerate codes, merge or delete unused accounts, and post opening
balances — on Odoo 14 Community and Enterprise.
    """,
    'author': 'Saaskul',
    'website': 'https://saaskul.com',
    'live_test_url': 'https://saaskul.com/contactus?name=Live%20Preview%20-%20IFRS%20Chart%20of%20Accounts',
    'support': 'info.cpabooks@gmail.com',
    'category': 'Accounting',
    'version': '14.0.1.0.0',
    'license': 'OPL-1',
    'price': 19.50,
    'currency': 'USD',
    'images': [
        'static/description/banner.png',
    ],
    'depends': [
        'base',
        'mail',
        'account',
        'product',
        'purchase',
    ],
    'data': [
        'security/account_group_security.xml',
        'security/ir.model.access.csv',
        'data/coa_seed/load_group.xml',
        'data/data.xml',
        'data/disable_legacy_coa_views.xml',
        'data/initialize_coa_code_digits.xml',
        'views/coa_legacy/coa_create.xml',
        'views/coa_legacy/inherit_account_account.xml',
        'views/coa_bulk_actions_wizard.xml',
        'views/coa_legacy/account_account.xml',
        'views/coa_legacy/chart_of_account_list.xml',
        'views/coa_legacy/productTemplate.xml',
        'views/views.xml',
        'views/templates.xml',
        'views/coa_ifrs_coding_wizard.xml',
        'views/account_account_views.xml',
        'views/coa_setup_file_views.xml',
        'views/account_account_search_views.xml',
        'views/account_opening_balance_views.xml',
        'views/product_with_analytic_acc_config.xml',
        'views/account_move.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}

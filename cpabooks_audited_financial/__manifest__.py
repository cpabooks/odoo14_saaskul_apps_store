# -*- coding: utf-8 -*-
{
    'name': 'CPABooks Audited Financials (AFG)',
    'summary': 'IFRS/FTA-style management financial statements and TB mapping',
    'description': """
CPABooks Audited Financials (AFG)
=================================
From trial balance to the full pack: Profit or Loss, Financial Position,
Equity, Cash Flow, PPE schedule, notes and UAE Corporate Tax.
    """,
    'version': '14.0.1.0.225',
    'category': 'Accounting',
    'author': 'CPABooks',
    'website': 'https://www.cpabooks.co',
    'license': 'LGPL-3',
    'price': 15.00,
    'currency': 'USD',
    'support': 'support@cpabooks.co',
    'images': [
        'static/description/banner_screenshot.jpg',
        'static/description/feature_01_setup.jpg',
        'static/description/feature_02_reporting.jpg',
        'static/description/feature_03_structure.jpg',
    ],
    'depends': [
        'base',
        'account',
        'project_dashboard_odoo',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/audited_financial_security.xml',
        'data/multico_client_actions.xml',
        'views/audited_financials_views.xml',
        'views/afg_map_list_assets.xml',
        'views/account_account_views.xml',
        'views/audited_financial_ledger_merge_views.xml',
        'views/audited_financial_l1_print_wizard_views.xml',
        'views/audited_financial_print_setup_wizard_views.xml',
        'views/afg_journal_items_views.xml',
        'data/menu_cleanup_legacy_statements.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
}

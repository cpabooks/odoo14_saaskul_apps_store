# -*- coding: utf-8 -*-
{
    'name': 'Cancel & Delete Global - All Documents',
    'summary': 'One Cancel / Delete / Reverse / Reset to Draft action set for Sales, Purchase, Delivery, Invoice, Payment, Inventory Adjustment and Expense',
    'description': """
Cancel & Delete Global
======================
One consistent action set on Sales Orders, Purchase Orders, Transfers, Invoices
and Bills, Payments, Inventory Adjustments and Expenses: Cancel, Cancel lines,
Cancel linked documents, Delete, Delete linked documents, Reset to Draft,
Reverse and Confirm / Post. Works on Odoo 14 Community and Enterprise.
    """,
    'author': 'Saaskul',
    'website': 'https://saaskul.com',
    'live_test_url': 'https://saaskul.com/contactus?name=Live%20Preview%20-%20Cancel%20%26%20Delete%20Global',
    'support': 'info.cpabooks@gmail.com',
    'category': 'Extra Tools',
    'version': '14.0.1.0.0',
    'license': 'OPL-1',
    'price': 9.00,
    'currency': 'USD',
    'images': [
        'static/description/banner.png',
    ],
    'depends': [
        'base',
        'mail',
        'sale',
        'purchase',
        'stock',
        'account',
        'hr_expense',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/cpa_cd_confirm_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/stock_inventory_views.xml',
        'views/hr_expense_views.xml',
        'views/server_actions.xml',
        'views/assets.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}

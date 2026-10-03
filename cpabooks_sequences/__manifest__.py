# -*- coding: utf-8 -*-

{
    'name': 'CPA Books Re-Sequences',

    'summary': 'Manage and re-sequence document numbers across Odoo applications',

    'description': """
CPA Books Re-Sequences
======================

Manage and re-sequence document numbers across Accounting, Sales,
Purchase, Inventory, Project and CRM in Odoo 14.

Features:
---------
* Manage multiple document sequences from one place
* Reset sequence prefixes
* Configure yearly or monthly sequences
* Change sequence number digits
* Multi-company sequence management
* Bulk update multiple sequences
    """,

    'author': 'CPA Books',
    'website': 'https://www.cpabooks.co',

    'category': 'Productivity',
    'version': '14.0.1.53',
    'license': 'OPL-1',

    'depends': [
        'base',
        'account',
        'sale',
        'stock',
        'project',
        'crm',
        'sh_pdc',
    ],

    'data': [
        'views/views.xml',
        'views/templates.xml',
        'views/sequence_menu.xml',
        'views/account_move.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
        'views/stock_picking.xml',
        'views/set_company_prefix_vew.xml',
        'views/assets.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/create_sequences.xml',
    ],

    'demo': [
        'demo/demo.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}
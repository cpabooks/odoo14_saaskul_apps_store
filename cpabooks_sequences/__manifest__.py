# -*- coding: utf-8 -*-
{
    'name': "CPABooks Re-Sequences",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "S. M. Emrul Bahar",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '14.0.1.53',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'sale', 'stock', 'project', 'crm', 'sh_pdc'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/sequence_menu.xml',
        'views/account_move.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
        'views/stock_picking.xml',
        'views/set_company_prefix_vew.xml',
        'views/assets.xml',
        # 'views/helpdesk_ticket.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/create_sequences.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

# -*- coding: utf-8 -*-
{
    'name': 'Saaskul Re-Sequences - PDC Vouchers',
    'summary': 'Number Post Dated Cheque vouchers with Saaskul Re-Sequences',
    'description': """
Saaskul Re-Sequences - PDC Vouchers
===================================
Bridge between Saaskul Re-Sequences and Post Dated Cheque Management (sh_pdc).
Assigns PDC Receipt and PDC Payment voucher numbers from the Re-Sequences setup.
    """,
    'author': 'Saaskul',
    'website': 'https://www.saaskul.co',
    'category': 'Accounting',
    'version': '14.0.1.0.0',
    'license': 'OPL-1',
    'depends': [
        'saaskul_sequences',
        'sh_pdc',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': True,
}

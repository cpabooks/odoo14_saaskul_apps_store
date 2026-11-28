# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAccountType(models.Model):
    """Odoo 19 has no account.account.type; the IFRS L1 tools keep their own copy."""
    _name = 'account.account.type'
    _description = 'Account Type (IFRS L1)'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    type = fields.Selection([
        ('other', 'Regular'),
        ('receivable', 'Receivable'),
        ('payable', 'Payable'),
        ('liquidity', 'Liquidity'),
    ], required=True, default='other')
    internal_group = fields.Selection([
        ('equity', 'Equity'),
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('off_balance', 'Off Balance'),
    ], string='Internal Group')
    include_initial_balance = fields.Boolean()
    note = fields.Text()


class AccountAccountUserType(models.Model):
    _inherit = 'account.account'

    user_type_id = fields.Many2one('account.account.type', string='Type (IFRS L1)', index=True)

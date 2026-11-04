# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    cpabooks_opening_auto_re = fields.Boolean(
        string='Opening Balance Auto RE',
        copy=False,
        help='Automatically added retained earnings line that balances the opening entry.',
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE account_move_line
                ADD COLUMN IF NOT EXISTS cpabooks_opening_auto_re boolean DEFAULT false
            """
        )

    @api.onchange('debit', 'credit', 'account_id')
    def _onchange_cpabooks_opening_balance_line(self):
        move = self.move_id
        if not move.cpabooks_is_opening_balance or move.state != 'draft':
            return
        move._cpabooks_sync_opening_retained_earnings_line_onchange()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get('cpabooks_skip_opening_sync'):
            return lines
        moves = lines.mapped('move_id').filtered(
            lambda move: move.cpabooks_is_opening_balance and move.state == 'draft'
        )
        if moves:
            moves._cpabooks_sync_opening_retained_earnings_line()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('cpabooks_skip_opening_sync'):
            return res
        if {'debit', 'credit', 'account_id', 'cpabooks_opening_auto_re'} & set(vals):
            moves = self.mapped('move_id').filtered(
                lambda move: move.cpabooks_is_opening_balance and move.state == 'draft'
            )
            if moves:
                moves._cpabooks_sync_opening_retained_earnings_line()
        return res

    def unlink(self):
        moves = self.mapped('move_id').filtered(
            lambda move: move.cpabooks_is_opening_balance and move.state == 'draft'
        )
        res = super().unlink()
        if self.env.context.get('cpabooks_skip_opening_sync'):
            return res
        if moves:
            moves._cpabooks_sync_opening_retained_earnings_line()
        return res

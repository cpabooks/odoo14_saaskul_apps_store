# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    cpabooks_is_opening_balance = fields.Boolean(
        string='Opening Balance Entry',
        copy=False,
        help='Posted lines on this journal update the Opening Balance column on the chart of accounts.',
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE account_move
                ADD COLUMN IF NOT EXISTS cpabooks_is_opening_balance boolean DEFAULT false
            """
        )

    @api.model
    def _cpabooks_get_retained_earnings_account(self, company):
        company = company or self.env.company
        Account = self.env['account.account']
        equity_type = self.env.ref('account.data_account_type_equity', raise_if_not_found=False)
        domain = [('company_id', '=', company.id), ('deprecated', '=', False)]
        if equity_type:
            domain.append(('user_type_id', '=', equity_type.id))
        for label in ('retained earning', 'retained earnings', 'current year earning', 'undistributed'):
            acc = Account.search(domain + [('name', 'ilike', label)], limit=1)
            if acc:
                return acc
        return Account.search(domain, limit=1)

    def _cpabooks_opening_manual_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: not line.cpabooks_opening_auto_re)

    def _cpabooks_opening_retained_earnings_line(self):
        self.ensure_one()
        return self.line_ids.filtered('cpabooks_opening_auto_re')[:1]

    def _cpabooks_remove_extra_opening_auto_re_lines(self):
        Line = self.env['account.move.line']
        ctx = dict(self.env.context, cpabooks_skip_opening_sync=True)
        for move in self:
            auto_lines = move.line_ids.filtered('cpabooks_opening_auto_re').sorted('id')
            if len(auto_lines) > 1:
                auto_lines[1:].with_context(**ctx).unlink()

    def _cpabooks_opening_balance_diff(self):
        self.ensure_one()
        manual_lines = self._cpabooks_opening_manual_lines()
        total_debit = sum(manual_lines.mapped('debit'))
        total_credit = sum(manual_lines.mapped('credit'))
        return total_debit - total_credit

    def _cpabooks_opening_re_line_vals(self, re_account, diff):
        if diff > 0:
            return {
                'account_id': re_account.id,
                'debit': 0.0,
                'credit': diff,
                'name': _('Opening balance offset'),
                'cpabooks_opening_auto_re': True,
            }
        if diff < 0:
            return {
                'account_id': re_account.id,
                'debit': -diff,
                'credit': 0.0,
                'name': _('Opening balance offset'),
                'cpabooks_opening_auto_re': True,
            }
        return {
            'account_id': re_account.id,
            'debit': 0.0,
            'credit': 0.0,
            'name': _('Opening balance offset'),
            'cpabooks_opening_auto_re': True,
        }

    def _cpabooks_sync_opening_retained_earnings_line(self):
        for move in self.filtered(
            lambda m: m.cpabooks_is_opening_balance and m.state == 'draft'
        ):
            move._cpabooks_remove_extra_opening_auto_re_lines()
            re_account = move._cpabooks_get_retained_earnings_account(move.company_id)
            if not re_account:
                continue
            diff = move._cpabooks_opening_balance_diff()
            vals = move._cpabooks_opening_re_line_vals(re_account, diff)
            re_line = move._cpabooks_opening_retained_earnings_line()
            ctx = dict(self.env.context, cpabooks_skip_opening_sync=True)
            if re_line:
                if abs(diff) > 0.005:
                    re_line.with_context(**ctx).write(vals)
                else:
                    re_line.with_context(**ctx).unlink()
            elif abs(diff) > 0.005:
                vals['move_id'] = move.id
                self.env['account.move.line'].with_context(**ctx).create(vals)

    def _cpabooks_sync_opening_retained_earnings_line_onchange(self):
        """Update the auto retained-earnings line in the form without writing to the database."""
        self.ensure_one()
        if not self.cpabooks_is_opening_balance or self.state != 'draft':
            return
        auto_lines = self.line_ids.filtered('cpabooks_opening_auto_re').sorted('id')
        if len(auto_lines) > 1:
            self.line_ids -= auto_lines[1:]
        re_account = self._cpabooks_get_retained_earnings_account(self.company_id)
        if not re_account:
            return
        diff = self._cpabooks_opening_balance_diff()
        vals = self._cpabooks_opening_re_line_vals(re_account, diff)
        re_line = self._cpabooks_opening_retained_earnings_line()
        if re_line:
            re_line.update(vals)
        elif abs(diff) > 0.005:
            new_line = self.env['account.move.line'].new(dict(vals, move_id=self))
            self.line_ids += new_line
        elif re_line:
            self.line_ids -= re_line

    def _cpabooks_opening_entry_is_balanced(self):
        self.ensure_one()
        total_debit = sum(self.line_ids.mapped('debit'))
        total_credit = sum(self.line_ids.mapped('credit'))
        return abs(total_debit - total_credit) <= 0.005

    @api.onchange(
        'line_ids',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.account_id',
        'line_ids.cpabooks_opening_auto_re',
    )
    def _onchange_cpabooks_opening_balance_lines(self):
        if self.cpabooks_is_opening_balance:
            self._cpabooks_sync_opening_retained_earnings_line_onchange()

    @api.model
    def action_cpabooks_open_opening_balance_entry(self):
        company = self.env.company
        journal = self.env['account.journal'].search(
            [('company_id', '=', company.id), ('type', '=', 'general')],
            limit=1,
        )
        if not journal:
            raise UserError(
                _('Configure a miscellaneous journal for %s before entering opening balances.')
                % company.display_name
            )
        move = self.search(
            [
                ('company_id', '=', company.id),
                ('cpabooks_is_opening_balance', '=', True),
                ('state', '=', 'draft'),
            ],
            order='id desc',
            limit=1,
        )
        if not move:
            move = self.create(
                {
                    'move_type': 'entry',
                    'journal_id': journal.id,
                    'company_id': company.id,
                    'ref': _('Opening Balance'),
                    'cpabooks_is_opening_balance': True,
                }
            )
        return {
            'name': _('Opening Balance'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_cpabooks_is_opening_balance': True,
                'default_move_type': 'entry',
            },
        }

    def _cpabooks_invalidate_coa_balance_fields(self):
        accounts = self.mapped('line_ids.account_id')
        if accounts:
            accounts.invalidate_cache(
                ['cpabooks_opening_balance', 'cpabooks_ledger_balance']
            )

    def action_post(self):
        opening_moves = self.filtered('cpabooks_is_opening_balance')
        opening_moves.filtered(lambda m: m.state == 'draft')._cpabooks_sync_opening_retained_earnings_line()
        for move in opening_moves:
            if move.state != 'draft':
                continue
            if not move._cpabooks_opening_entry_is_balanced():
                raise UserError(
                    _('Opening balance entry %s is not balanced. '
                      'Enter opening amounts on your ledger lines; '
                      'the retained earnings offset line is updated automatically.')
                    % (move.name or move.ref or move.id)
                )
        res = super().action_post()
        if opening_moves:
            opening_moves._cpabooks_invalidate_coa_balance_fields()
        return res

    def button_draft(self):
        res = super().button_draft()
        opening_moves = self.filtered('cpabooks_is_opening_balance')
        if opening_moves:
            opening_moves._cpabooks_invalidate_coa_balance_fields()
        return res

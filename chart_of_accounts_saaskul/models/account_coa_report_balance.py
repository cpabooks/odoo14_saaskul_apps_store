# -*- coding: utf-8 -*-
from odoo import api, models, _


class AccountCoaReport(models.AbstractModel):
    """Accounting → Trial Balance (account.coa.report).

    CPABooks presentation: signed Net balances (golden rule), not separate Debit/Credit
    columns that only prove Dr=Cr. Convention:

      Assets / Expenses  → positive  (debit nature)
      Liabilities / Equity / Income → negative  (credit nature)

    When books are complete, column TOTAL Net is nil (0.00).
    """

    _inherit = 'account.coa.report'

    # Default UI: account.group hierarchy on, all groups expanded (Unfold All).
    filter_hierarchy = True
    filter_unfold_all = True

    @api.model
    def _get_columns(self, options):
        """One Net column per period (signed), so TOTAL can be nil."""
        header = [
            {'name': '', 'style': 'width:45%'},
            {'name': _('Opening'), 'class': 'number'},
        ]
        for period in reversed(options.get('comparison', {}).get('periods', [])):
            header.append({'name': period.get('string') or '', 'class': 'number'})
        header += [
            {'name': (options.get('date') or {}).get('string') or '', 'class': 'number'},
            {'name': _('Total'), 'class': 'number'},
        ]
        return [header]

    @api.model
    def _cpabooks_tb_net_cell(self, value, blank_if_zero=True):
        """Format a signed Net amount (debit − credit)."""
        return {
            'name': self.format_value(value, blank_if_zero=blank_if_zero),
            'class': 'number',
            'no_format_name': value,
            'no_format': value,
        }

    @api.model
    def _get_lines(self, options, line_id=None):
        # Same data source as standard CoA TB, but store signed Net instead of Debit|Credit pairs.
        # Include archived accounts — posted balances on inactive ledgers still affect the books
        # (excluding them makes TOTAL Net ≠ nil, e.g. archived bank with large credit balance).
        new_options = options.copy()
        new_options['unfold_all'] = True
        options_list = self._get_options_periods_list(new_options)
        gl = self.env['account.general.ledger'].with_context(active_test=False)
        accounts_results, _taxes_results = gl._do_query(
            options_list, fetch_lines=False
        )

        # Opening + one net per period + Total Net
        n_cols = len(options_list) + 2
        totals = [0.0] * n_cols
        lines = []

        for account, periods_results in accounts_results:
            sums = []
            account_balance = 0.0
            for i, period_values in enumerate(reversed(periods_results)):
                account_sum = period_values.get('sum', {})
                account_un_earn = period_values.get('unaffected_earnings', {})
                account_init_bal = period_values.get('initial_balance', {})

                if i == 0:
                    # Opening = signed balance (debit − credit) before first period
                    initial_balance = (
                        account_init_bal.get('balance', 0.0)
                        + account_un_earn.get('balance', 0.0)
                    )
                    sums.append(initial_balance)
                    account_balance += initial_balance

                # Period movement as signed Net (debit − credit)
                period_debit = account_sum.get('debit', 0.0) - account_init_bal.get('debit', 0.0)
                period_credit = account_sum.get('credit', 0.0) - account_init_bal.get('credit', 0.0)
                period_net = period_debit - period_credit
                sums.append(period_net)
                account_balance += period_net

            sums.append(account_balance)

            columns = []
            for idx, value in enumerate(sums):
                totals[idx] += value
                columns.append(self._cpabooks_tb_net_cell(value, blank_if_zero=True))

            name = account.name_get()[0][1]
            if len(name) > 40 and not self._context.get('print_mode'):
                name = name[:40] + '...'

            lines.append({
                'id': account.id,
                'name': name,
                'title_hover': name,
                'columns': columns,
                'unfoldable': False,
                'caret_options': 'account.account',
                'class': 'o_account_searchable_line o_account_coa_column_contrast',
            })

        currency = self.env.company.currency_id
        rounded_totals = [currency.round(t) for t in totals]
        # Always show TOTAL amounts (including 0.00) so "nil" is visible
        lines.append({
            'id': 'grouped_accounts_total',
            'name': _('TOTAL (Net — must be nil)'),
            'class': 'total o_account_coa_column_contrast',
            'columns': [
                self._cpabooks_tb_net_cell(total, blank_if_zero=False)
                for total in rounded_totals
            ],
            'level': 1,
        })

        # Final Total column imbalance (last Net)
        diff = rounded_totals[-1] if rounded_totals else 0.0
        if abs(diff) > 0.005:
            if 'account.account' in self.env:
                self.env['account.account']._cpabooks_ensure_unaffected_earnings_account(
                    self.env.company
                )
            short = _("Imbalance %(diff)s — Net TOTAL must be 0.00") % {
                'diff': self.format_value(diff),
            }
            detail = _(
                "Signed Net (Assets/Expenses +, Liabilities/Income −) is not nil. "
                "Usually open P&L not in Current Year Earnings, unposted journals, "
                "or a journal/analytic filter — not a journal missing debit=credit."
            )
            lines.append({
                'id': 'cpabooks_tb_imbalance',
                'name': short,
                'title_hover': detail,
                'class': 'o_account_report_line text-danger',
                'columns': [{'name': ''} for _c in rounded_totals],
                'level': 1,
            })

        return lines

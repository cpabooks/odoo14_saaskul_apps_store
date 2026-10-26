# -*- coding: utf-8 -*-
import json
import re
from itertools import groupby as itertools_groupby

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.sql import column_exists, create_column


class AccountAccount(models.Model):
    _name = 'account.account'
    _inherit = ['account.account', 'mail.thread', 'mail.activity.mixin']

    def _auto_init(self):
        cr = self.env.cr
        if not column_exists(cr, self._table, 'cpabooks_previous_code'):
            create_column(cr, self._table, 'cpabooks_previous_code', 'varchar')
        if not column_exists(cr, self._table, 'cpabooks_previous_name'):
            create_column(cr, self._table, 'cpabooks_previous_name', 'varchar')
        return super()._auto_init()

    @api.model
    def _cpabooks_disable_legacy_coa_views(self):
        """Keep the deprecated module installed without applying its stale UI."""
        self.env.cr.execute(
            """
            UPDATE ir_ui_view AS view
               SET arch_db = REPLACE(
                   REPLACE(
                       view.arch_db,
                       ' domain="[(''share'', ''='', False)]"',
                       ''
                   ),
                   ' domain="[(''share'',''='',False)]"',
                   ''
               )
              FROM ir_model_data AS data
             WHERE data.module = 'sh_pdc'
               AND data.name = 'sh_pdc_account_setting_inherit'
               AND data.model = 'ir.ui.view'
               AND data.res_id = view.id
               AND view.arch_db LIKE '%domain=%share%False%'
            """
        )
        patched_count = self.env.cr.rowcount
        self.env.cr.execute(
            """
            UPDATE ir_ui_view AS view
               SET active = FALSE
              FROM ir_model_data AS data
             WHERE data.module = 'cpabooks_chart_of_accounts'
               AND data.model = 'ir.ui.view'
               AND data.res_id = view.id
               AND view.active = TRUE
            RETURNING view.id
            """
        )
        disabled_ids = [row[0] for row in self.env.cr.fetchall()]
        if patched_count or disabled_ids:
            self.env['ir.ui.view'].clear_caches()
        return len(disabled_ids)

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        result = super().fields_view_get(
            view_id=view_id,
            view_type=view_type,
            toolbar=toolbar,
            submenu=submenu,
        )
        if view_type != 'tree' or not result.get('arch'):
            return result

        company = self.env.company.sudo()._cpabooks_ensure_coa_code_digits()
        selected_name = 'action_set_coa_%s_digits' % company.cpabooks_coa_code_digits
        arch = etree.fromstring(result['arch'].encode('utf-8'))
        changed = False
        for button in arch.iter('button'):
            name = button.get('name')
            if name not in ('action_set_coa_4_digits', 'action_set_coa_6_digits'):
                continue
            is_selected = name == selected_name
            label = 'COA %s Digits' % ('4' if name.endswith('4_digits') else '6')
            modifiers = json.loads(button.get('modifiers') or '{}')
            if is_selected:
                button.set('string', '%s (Selected)' % label)
                button.set('disabled', 'disabled')
                button.set('class', 'btn-secondary disabled m-2')
                button.set(
                    'title',
                    'Current company setting. Existing ledger codes are unchanged.',
                )
                modifiers['readonly'] = True
            else:
                button.set('string', label)
                button.attrib.pop('disabled', None)
                button.set('class', 'oe_highlight m-2')
                button.set(
                    'confirm',
                    'This will reset all ledger codes and groups for the current company. Continue?',
                )
                button.set(
                    'title',
                    'Reset this company to %s-digit ledger codes and matching groups.'
                    % ('4' if name.endswith('4_digits') else '6'),
                )
                modifiers.pop('readonly', None)
            button.set('modifiers', json.dumps(modifiers))
            changed = True
        if changed:
            result['arch'] = etree.tostring(arch, encoding='unicode')
        return result

    def _cpabooks_set_coa_code_digits(self, digits):
        if digits not in ('4', '6'):
            raise UserError(_('COA code digits must be 4 or 6.'))
        company = self.env.company.sudo()._cpabooks_ensure_coa_code_digits()
        if company.cpabooks_coa_code_digits == digits:
            return self.env.ref('account.action_account_form').sudo().read()[0]
        accounts = self.sudo().search([('company_id', '=', company.id)])
        if not accounts:
            raise UserError(_('No chart of accounts found for %s.') % company.display_name)
        return accounts.with_context(
            cpa_reset_code_options={
                'code_digits': int(digits),
                'company_code_mode': 'shared',
            },
        ).action_reset_code_digits()

    def action_set_coa_4_digits(self):
        return self._cpabooks_set_coa_code_digits('4')

    def action_set_coa_6_digits(self):
        return self._cpabooks_set_coa_code_digits('6')

    cpabooks_previous_code = fields.Char(
        string='Previous account code',
        copy=False,
        tracking=True,
        help='Former code kept when IFRS recoding is applied.',
    )
    cpabooks_previous_name = fields.Char(
        string='Previous ledger name',
        copy=False,
        help='Former name kept when an IFRS naming correction is accepted.',
    )
    cpabooks_ifrs_needs_name_review = fields.Boolean(
        string='IFRS name review',
        compute='_compute_cpabooks_ifrs_display',
        compute_sudo=True,
    )
    cpabooks_proposed_group_name = fields.Char(
        string='Proposed Group',
        compute='_compute_cpabooks_ifrs_display',
        compute_sudo=True,
        help='Suggested L2 IFRS group (helper only). Reporting uses Group.',
    )
    cpabooks_l1_type_code = fields.Char(
        string='Type Code',
        compute='_compute_cpabooks_ifrs_display',
        store=True,
        compute_sudo=True,
        readonly=True,
    )
    cpabooks_l1_type_label = fields.Char(
        string='L1 Type',
        compute='_compute_cpabooks_ifrs_display',
        store=True,
        compute_sudo=True,
        readonly=True,
    )
    cpabooks_bs_pl = fields.Selection(
        [('BS', 'BS'), ('PL', 'PL')],
        string='B/P',
        compute='_compute_cpabooks_ifrs_display',
        compute_sudo=True,
        help='BS = Balance Sheet, PL = Profit and Loss.',
    )

    create_asset = fields.Selection(
        [
            ('no', 'No'),
            ('draft', 'Create in draft'),
            ('validate', 'Create and validate'),
        ],
        default='no',
    )
    cpabooks_balance_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Balance Currency',
        readonly=True,
    )
    cpabooks_company_branch_code = fields.Char(
        string='Co.',
        compute='_compute_cpabooks_company_display',
        readonly=True,
    )
    cpabooks_company_display = fields.Char(
        string='Company / Branch',
        compute='_compute_cpabooks_company_display',
        readonly=True,
    )
    cpabooks_display_code = fields.Char(
        string='Ledger Code',
        compute='_compute_cpabooks_display_code',
        search='_search_cpabooks_display_code',
    )
    cpabooks_l1_type_display = fields.Char(
        string='L1-TCODE',
        compute='_compute_cpabooks_l1_type_display',
        readonly=True,
    )
    cpabooks_group_code = fields.Char(
        string='Group Code',
        compute='_compute_cpabooks_group_display',
        store=True,
        compute_sudo=True,
        readonly=True,
    )
    cpabooks_group_series_code = fields.Char(
        string='Legacy Group Series',
        compute='_compute_cpabooks_group_display',
        store=True,
        compute_sudo=True,
        readonly=True,
        help='Group search/reporting series code. Example: group 18 -> 1818.',
    )
    cpabooks_group_name = fields.Char(
        string='Group',
        compute='_compute_cpabooks_group_display',
        compute_sudo=True,
        readonly=True,
    )

    @api.depends(
        'name',
        'code',
        'cpabooks_previous_code',
        'user_type_id',
        'user_type_id.name',
        'internal_group',
        'internal_type',
        'company_id',
    )
    def _compute_cpabooks_ifrs_display(self):
        engine = self.env['coa.ifrs.coding']
        for account in self:
            account.cpabooks_ifrs_needs_name_review = engine.name_needs_ifrs_review(account.name)
            account.cpabooks_proposed_group_name = engine.resolve_l2_group(account)['display_name']
            account.cpabooks_l1_type_code = engine.l1_type_code(account)
            account.cpabooks_l1_type_label = engine.l1_type_label(account)
            account.cpabooks_bs_pl = engine.ledger_bs_pl(account)

    def name_get(self):
        engine = self.env['coa.ifrs.coding']
        result = []
        for account in self:
            code = engine.effective_ledger_code(account) or (account.code or '').strip()
            name = account.name or ''
            if code:
                display = '%s | %s' % (code, name)
            else:
                display = name
            result.append((account.id, display))
        return result

    @api.depends('company_id')
    def _compute_cpabooks_company_display(self):
        companies = self.env['res.company'].sudo().search([], order='id')
        digit_map = {
            company.id: str(index + 1)
            for index, company in enumerate(companies[:9])
        }
        for account in self:
            account.cpabooks_company_branch_code = digit_map.get(account.company_id.id, '')
            account.cpabooks_company_display = account.company_id.display_name or ''

    @api.model_create_multi
    def create(self, vals_list):
        # Keep user-entered codes; do not auto-rewrite to IFRS series on manual create.
        accounts = super().create(vals_list)
        accounts._cpabooks_schedule_ifrs_name_prompt()
        if not self.env.context.get('cpabooks_skip_ifrs_auto_setup'):
            # Only fill MISSING codes / sync groups — never force IFRS over a provided code.
            self.env['coa.ifrs.coding'].setup_ifrs_for_accounts(accounts, force_code=False)
        return accounts

    def _cpabooks_next_duplicate_code(self):
        """Unique code for Action → Duplicate; keep original style when possible."""
        self.ensure_one()
        base = (self.code or '').strip() or 'COPY'
        company_id = self.company_id.id
        Account = self.sudo()

        match = re.match(r'^(.*?)(\d+)$', base)
        if match:
            prefix, num_str = match.group(1), match.group(2)
            width = len(num_str)
            next_num = int(num_str) + 1
            for _ in range(10000):
                candidate = '%s%s' % (prefix, str(next_num).zfill(width))
                if not Account.search_count([
                    ('company_id', '=', company_id),
                    ('code', '=', candidate),
                ]):
                    return candidate
                next_num += 1

        seq = 1
        while True:
            candidate = '%s-C%s' % (base, seq)
            if not Account.search_count([
                ('company_id', '=', company_id),
                ('code', '=', candidate),
            ]):
                return candidate
            seq += 1

    def copy(self, default=None):
        """Duplicate ledger: new code, name ends with (copied), keep group/type."""
        self.ensure_one()
        default = dict(default or {})
        if 'code' not in default:
            default['code'] = self._cpabooks_next_duplicate_code()
        if 'name' not in default:
            base_name = (self.name or '').strip()
            if base_name.lower().endswith('(copied)'):
                default['name'] = base_name
            else:
                default['name'] = _('%s (copied)') % base_name
        if 'group_id' not in default and self.group_id:
            default['group_id'] = self.group_id.id
        # Skip IFRS auto remap on create — keeps the same group and avoids
        # account.group parent_path "Recursion Detected" during duplicate.
        return super(
            AccountAccount,
            self.with_context(
                cpabooks_skip_ifrs_auto_setup=True,
                cpabooks_skip_ifrs_name_wizard=True,
            ),
        ).copy(default)


    @api.onchange("user_type_id", "group_id")
    def _onchange_cpa_bank_cash_defaults(self):
        for account in self:
            type_name = (account.user_type_id.name or "").lower()
            if "bank" not in type_name and "cash" not in type_name:
                continue
            group = self.env["account.group"].search([
                ("company_id", "=", account.company_id.id or self.env.company.id),
                ("name", "=", "Cash & Cash Equivalents"),
            ], limit=1)
            afg = self.env["audited.financial.group"].search([("code", "=", "AFG_CASH")], limit=1)
            if group:
                account.group_id = group
            if afg and "afg_group_id" in account._fields:
                account.afg_group_id = afg
            if "ctf_category" in account._fields:
                account.ctf_category = "current_assets"

    def _cpa_apply_bank_cash_defaults(self):
        """Bank and Cash ledgers stay on Cash & Cash Equivalents, AFG_CASH, Current Assets."""
        if self.env.context.get("cpa_skip_bank_rule"):
            return
        if "audited.financial.group" not in self.env.registry:
            return
        Afg = self.env["audited.financial.group"].sudo()
        Group = self.env["account.group"].sudo()
        afg = Afg.search([("code", "=", "AFG_CASH")], limit=1)
        for account in self:
            type_name = (account.user_type_id.name or "").lower()
            if "bank" not in type_name and "cash" not in type_name:
                continue
            group = Group.search([
                ("company_id", "=", account.company_id.id),
                ("name", "=", "Cash & Cash Equivalents"),
            ], limit=1)
            if group and account.group_id.id != group.id:
                self.env.cr.execute(
                    "UPDATE account_account SET group_id = %s WHERE id = %s",
                    (group.id, account.id),
                )
            if "ctf_category" in account._fields and account.ctf_category != "current_assets":
                self.env.cr.execute(
                    "UPDATE account_account SET ctf_category = %s WHERE id = %s",
                    ("current_assets", account.id),
                )
            if afg and "afg_group_id" in account._fields and account.afg_group_id.id != afg.id:
                self.env.cr.execute(
                    "UPDATE account_account SET afg_group_id = %s WHERE id = %s",
                    (afg.id, account.id),
                )
                Line = self.env["audited.financial.group.line"].sudo().with_context(afg_skip_collapse=True)
                Line.search([("account_id", "=", account.id)]).unlink()
                Line.create({"group_id": afg.id, "account_id": account.id})
            if group:
                gvals = {}
                if "afg_group_id" in group._fields and afg and group.afg_group_id.id != afg.id:
                    gvals["afg_group_id"] = afg.id
                if "ctf_category" in group._fields and group.ctf_category != "current_assets":
                    gvals["ctf_category"] = "current_assets"
                if gvals:
                    group.with_context(cpa_skip_group_push=True, skip_prefix_constraint=True).write(gvals)
        self.invalidate_cache()

    def write(self, vals):
        # Manual create/edit: never block on IFRS series. Duplicates allowed.
        # Optional soft digit hint is onchange-only (see _onchange_cpabooks_code_digits).
        chosen_group = vals.get("group_id") if "group_id" in vals else None
        if self.env.context.get('cpabooks_skip_ifrs_name_wizard') or 'name' not in vals:
            result = super().write(vals)
            if chosen_group and self.ids and not self.env.context.get("cpa_skip_bank_rule"):
                self.env.cr.execute(
                    "UPDATE account_account SET group_id = %s WHERE id IN %s",
                    (chosen_group, tuple(self.ids)),
                )
                self.invalidate_cache(fnames=["group_id"])
            self._cpa_apply_bank_cash_defaults()
            return result
        old_names = {account.id: account.name for account in self}
        result = super().write(vals)
        flagged = self.filtered(
            lambda account: self.env['coa.ifrs.coding'].name_needs_ifrs_review(account.name)
        )
        if flagged:
            for account in flagged:
                if not account.cpabooks_previous_name and old_names.get(account.id):
                    account.with_context(cpabooks_skip_ifrs_name_wizard=True).write({
                        'cpabooks_previous_name': old_names[account.id],
                    })
            flagged._cpabooks_schedule_ifrs_name_prompt()
        if chosen_group and self.ids and not self.env.context.get("cpa_skip_bank_rule"):
            self.env.cr.execute(
                "UPDATE account_account SET group_id = %s WHERE id IN %s",
                (chosen_group, tuple(self.ids)),
            )
            self.invalidate_cache(fnames=["group_id"])
        self._cpa_apply_bank_cash_defaults()
        return result

    @api.onchange('code')
    def _onchange_cpabooks_code_digits(self):
        """Hint only: prefer 4 or 6 numeric digits. Never block save."""
        for account in self:
            code = (account.code or '').strip()
            if not code:
                continue
            digits = re.sub(r'\D+', '', code)
            if digits and len(digits) not in (4, 6):
                return {
                    'warning': {
                        'title': _('COA code length'),
                        'message': _(
                            'Code %(code)s has %(n)s digits. '
                            'Saaskul usually uses 4-digit or 6-digit codes. '
                            'You can still save this code (duplicates allowed; IFRS series not enforced).'
                        ) % {'code': code, 'n': len(digits)},
                    }
                }
        return None

    def _cpabooks_schedule_ifrs_name_prompt(self):
        if self.env.context.get('cpabooks_skip_ifrs_name_wizard'):
            return
        engine = self.env['coa.ifrs.coding']
        flagged = self.filtered(lambda account: engine.name_needs_ifrs_review(account.name))
        if not flagged:
            return
        if len(flagged) != 1:
            return
        account_id = flagged.id

        def open_wizard():
            account = self.env['account.account'].browse(account_id).exists()
            if account:
                self.env['coa.ifrs.name.suggestion.wizard'].create_from_account(account)

        self.env.cr.postcommit.add(open_wizard)

    def _cpabooks_log_ifrs_code_change(self, old_code, new_code):
        for account in self:
            if not old_code or old_code == new_code:
                continue
            account.message_post(
                body=_(
                    'IFRS account code changed from <b>%(old)s</b> to <b>%(new)s</b> '
                    '(previous code stored on the ledger). Journal entries are unchanged.'
                ) % {'old': old_code, 'new': new_code},
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def action_cpabooks_ifrs_name_review(self):
        self.ensure_one()
        engine = self.env['coa.ifrs.coding']
        if not engine.name_needs_ifrs_review(self.name):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('IFRS naming'),
                    'message': _('This ledger name does not require IFRS review.'),
                    'type': 'info',
                    'sticky': False,
                },
            }
        wizard = self.env['coa.ifrs.name.suggestion.wizard'].create({
            'account_id': self.id,
            'current_name': self.name,
            'suggested_name': engine.suggest_ifrs_name(self),
            'edited_name': engine.suggest_ifrs_name(self),
            'previous_name': self.cpabooks_previous_name or '',
            'message': _(
                'This ledger/group name may need IFRS naming correction. '
                'Do you want to update?'
            ),
        })
        return wizard.action_open()

    @api.depends('code', 'cpabooks_previous_code')
    def _compute_cpabooks_display_code(self):
        engine = self.env['coa.ifrs.coding']
        for account in self:
            account.cpabooks_display_code = (
                engine.effective_ledger_code(account) or (account.code or '')
            )

    @api.depends(
        'cpabooks_l1_type_code',
        'cpabooks_l1_type_label',
        'internal_group',
        'code',
        'cpabooks_previous_code',
    )
    def _compute_cpabooks_l1_type_display(self):
        engine = self.env['coa.ifrs.coding']
        for account in self:
            type_code = account.cpabooks_l1_type_code or engine.l1_type_code(account)
            type_label = account.cpabooks_l1_type_label or engine.l1_type_label(account)
            account.cpabooks_l1_type_display = '%s %s' % (type_code, type_label)

    @api.model
    def _search_cpabooks_display_code(self, operator, value):
        if operator in ('ilike', 'like', '=ilike', '=', '!=', 'not ilike'):
            return ['|', ('code', operator, value), ('cpabooks_previous_code', operator, value)]
        return [('code', operator, value)]

    @api.depends(
        'group_id',
        'group_id.code_prefix_start',
        'group_id.code_prefix_end',
        'group_id.name',
        'code',
        'company_id',
        'company_id.cpabooks_coa_code_digits',
    )

    def _adapt_accounts_for_account_groups(self, account_ids=None):
        """Keep a group set from the COA Setup File.

        Odoo reassigns every ledger by code prefix when a group is saved.
        A setup group such as Accounts Receivables (prefix 112) would otherwise
        be replaced by 101 Unallocated Group on ledger 101003.
        """
        if self.env.context.get("cpa_apply_setup_groups"):
            return True
        records = account_ids if account_ids is not None else self
        keep = {}
        for account in records:
            group = account.group_id
            if not group:
                continue
            if (group.name or "").strip().lower() == "unallocated group":
                continue
            keep[account.id] = group.id
        res = super(AccountAccount, self)._adapt_accounts_for_account_groups(account_ids)
        if keep:
            for account_id, group_id in keep.items():
                self.env.cr.execute(
                    "UPDATE account_account SET group_id = %s WHERE id = %s",
                    (group_id, account_id),
                )
            self.browse(list(keep)).invalidate_cache(fnames=["group_id"])
        return res

    def _compute_cpabooks_group_display(self):
        engine = self.env['coa.ifrs.coding']
        for account in self:
            group = account.group_id
            if not group:
                account.cpabooks_group_code = ''
                account.cpabooks_group_series_code = ''
                account.cpabooks_group_name = ''
                continue
            company = account.company_id.sudo()._cpabooks_ensure_coa_code_digits()
            expected_width = 2 if company.cpabooks_coa_code_digits == '4' else 3
            code = (group.code_prefix_start or group.code_prefix_end or '').strip()
            ledger_digits = re.sub(r'\D+', '', account.code or '')
            if (
                len(ledger_digits) >= expected_width
                and (
                    len(code) != expected_width
                    or not code.isdigit()
                    or (
                        expected_width == 3
                        and len(code) == 2
                        and code.isdigit()
                    )
                )
            ):
                code = ledger_digits[:expected_width]
            account.cpabooks_group_code = code
            account.cpabooks_group_series_code = (
                account.cpabooks_group_code * 2
                if len(account.cpabooks_group_code) == 2 and account.cpabooks_group_code.isdigit()
                else ''
            )
            group_name = engine._normalize_group_label(
                account.cpabooks_group_code, group.name,
            )
            if expected_width == 3 and len(ledger_digits) >= 3:
                group_name = engine._normalize_group_label(
                    ledger_digits[:3], group_name,
                )
            account.cpabooks_group_name = (
                '%s-%s' % (account.cpabooks_group_code, group_name)
                if account.cpabooks_group_code and group_name
                else group_name
            )

    @api.model
    def _cpabooks_repair_group_codes_for_digit_mode(self):
        """Align group prefixes/display with company 4/6-digit ledger mode."""
        companies = self.env['res.company'].sudo().search([])
        companies._cpabooks_ensure_coa_code_digits()
        repaired = 0
        for company in companies:
            code_digits = int(company.cpabooks_coa_code_digits or '6')
            accounts = self.sudo().search([('company_id', '=', company.id)])
            if not accounts:
                continue
            repaired += self._cpa_sync_groups_for_code_digits(accounts, code_digits)
            accounts._compute_cpabooks_group_display()
        return repaired
    cpabooks_opening_balance = fields.Monetary(
        string='Opening Balance',
        compute='_compute_cpabooks_opening_balance',
        currency_field='cpabooks_balance_currency_id',
        help='Posted balance from the opening balance journal entry only.',
    )
    cpabooks_ledger_balance = fields.Monetary(
        string='Closing Balance',
        compute='_compute_cpabooks_ledger_balance',
        currency_field='cpabooks_balance_currency_id',
        help=(
            'Posted balance: debit minus credit. '
            'Assets and expenses are typically positive; '
            'liabilities, equity, and income are typically negative. '
            'The column total should be zero.'
        ),
    )

    def _cpabooks_fetch_posted_balances(self, account_ids):
        if not account_ids:
            return {}
        self.env.cr.execute(
            """
            SELECT line.account_id, COALESCE(SUM(line.debit - line.credit), 0.0)
              FROM account_move_line line
              JOIN account_move move ON move.id = line.move_id
             WHERE line.account_id = ANY(%s)
               AND move.state = 'posted'
             GROUP BY line.account_id
            """,
            [account_ids],
        )
        return dict(self.env.cr.fetchall())

    def _cpabooks_fetch_opening_balances(self, account_ids):
        if not account_ids:
            return {}
        self.env.cr.execute(
            """
            SELECT line.account_id, COALESCE(SUM(line.debit - line.credit), 0.0)
              FROM account_move_line line
              JOIN account_move move ON move.id = line.move_id
             WHERE line.account_id = ANY(%s)
               AND move.state = 'posted'
               AND move.cpabooks_is_opening_balance = TRUE
             GROUP BY line.account_id
            """,
            [account_ids],
        )
        return dict(self.env.cr.fetchall())

    @api.depends('company_id')
    def _compute_cpabooks_opening_balance(self):
        account_ids = self.ids
        balances = self._cpabooks_fetch_opening_balances(account_ids)
        for account in self:
            account.cpabooks_opening_balance = balances.get(account.id, 0.0)

    @api.depends('company_id')
    def _compute_cpabooks_ledger_balance(self):
        account_ids = self.ids
        balances = self._cpabooks_fetch_posted_balances(account_ids)
        for account in self:
            account.cpabooks_ledger_balance = balances.get(account.id, 0.0)

    def action_cpabooks_add_opening_balance(self):
        return self.env['account.move'].action_cpabooks_open_opening_balance_entry()

    @api.model
    def _cpa_get_duplicate_code_records(self):
        self.env.cr.execute("""
            SELECT array_agg(id ORDER BY company_id, code, id)
              FROM account_account
             WHERE code IS NOT NULL AND code != '' AND company_id IS NOT NULL
             GROUP BY company_id, code
            HAVING count(*) > 1
        """)
        duplicate_ids = []
        for row in self.env.cr.fetchall():
            duplicate_ids.extend(row[0] or [])
        return self.sudo().browse(duplicate_ids)

    @api.model
    def _cpa_generate_unique_duplicate_code(self, account, sequence):
        base_code = (account.code or '').strip() or 'DUP'
        candidate = '%s-D%s' % (base_code, sequence)
        check_sequence = sequence
        while self.sudo().search_count([
            ('id', '!=', account.id),
            ('company_id', '=', account.company_id.id),
            ('code', '=', candidate),
        ]):
            check_sequence += 1
            candidate = '%s-D%s' % (base_code, check_sequence)
        return candidate

    @api.model
    def action_cpa_view_duplicate_codes(self):
        duplicate_accounts = self._cpa_get_duplicate_code_records()
        action = self.env.ref('account.action_account_form').sudo().read()[0]
        action.update({
            'name': _('Duplicate Account Codes'),
            'domain': [('id', 'in', duplicate_accounts.ids)],
        })
        return action

    def action_fix_duplicate_codes(self):
        return self.action_cpa_fix_duplicate_codes()

    def action_view_duplicate_codes(self):
        return self.action_cpa_view_duplicate_codes()

    @api.model
    def action_cpa_fix_duplicate_codes(self):
        duplicate_accounts = self._cpa_get_duplicate_code_records()
        if not duplicate_accounts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Duplicate Codes'),
                    'message': _('No duplicate account codes were found.'),
                    'type': 'success',
                    'sticky': False,
                },
            }

        renamed_accounts = []
        sorted_accounts = duplicate_accounts.sorted(
            key=lambda acc: (acc.company_id.id, acc.code or '', acc.id),
        )
        for _group_key, grouped_accounts in itertools_groupby(
            sorted_accounts,
            key=lambda acc: (acc.company_id.id, acc.code or ''),
        ):
            group_accounts = list(grouped_accounts)
            if len(group_accounts) < 2:
                continue
            for sequence, account in enumerate(group_accounts[1:], start=1):
                new_code = self._cpa_generate_unique_duplicate_code(account, sequence)
                account.sudo().write({'code': new_code})
                renamed_accounts.append(
                    '%s / %s -> %s' % (account.company_id.name, account.name, new_code)
                )

        message = _('Renamed %s duplicate account(s).') % len(renamed_accounts)
        if renamed_accounts:
            message = '%s %s' % (
                message,
                _('First duplicate kept original code in each company.'),
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Duplicate Codes Fixed'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

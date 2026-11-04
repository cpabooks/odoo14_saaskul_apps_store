import random
import re
from itertools import groupby
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from collections import defaultdict
import csv
import os
from odoo.exceptions import UserError
from odoo.release import product_name


class Account(models.Model):
    _inherit = 'account.account'

    def _register_hook(self):
        super()._register_hook()
        from odoo.addons.chart_of_accounts_saaskul.hooks import (
            _ensure_account_account_cpabooks_columns,
        )
        _ensure_account_account_cpabooks_columns(self.env.cr)

    get_previous = fields.Boolean('Get Value From Previous', default=True)
    previous = fields.Many2one('account.account', 'Choose Account')
    active = fields.Boolean('Active', default=True)
    qid = fields.Char('QID', reaonly=True)
    is_duplicate = fields.Boolean('Duplicate')
    is_show_code = fields.Boolean('Show-Code')
    cpabooks_default_seed_key = fields.Char(
        string='Default Ledger Key',
        copy=False,
        index=True,
        readonly=True,
    )
    cpabooks_default_manually_modified = fields.Boolean(
        string='Default Ledger Manually Modified',
        copy=False,
        default=False,
        readonly=True,
    )
    cpabooks_sync_name_all_companies = fields.Boolean(
        string='All companies',
        default=True,
        help='Kept in step with All companies on the ledger. '
             'Ticked: the name is saved on every company. Unticked: this company only.',
    )
    cpabooks_related_account_ids = fields.Many2many(
        'account.account',
        'account_account_cpabooks_related_rel',
        'account_id',
        'related_account_id',
        string='Related Ledgers',
        help='Link provision/accrual and expense ledgers. The reverse link is '
             'maintained automatically and is used by Tally CA vs. Exp.',
    )

    _CPABOOKS_DEFAULT_TRACKED_FIELDS = frozenset({
        'name', 'code', 'user_type_id', 'group_id', 'reconcile', 'currency_id',
        'tax_ids', 'tag_ids', 'allowed_journal_ids', 'deprecated',
        'create_asset', 'asset_model',
    })

# Neutralize core unique(code, company_id) so duplicate ledger codes are allowed.
    _sql_constraints = [
        ('code_company_uniq', 'CHECK(True)', 'The code of the account must be unique per company !'),
    ]

    @api.model
    def _is_valid_coa_seed_row(self, row):
        """Reject blank/footer CSV rows before they can create ledgers."""
        return bool(
            (row.get('code_auto') or '').strip()
            and (row.get('account_name_revise') or '').strip()
            and (row.get('type_revise') or '').strip()
        )

    def _get_duplicate_code_records(self):
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
        return self.browse(duplicate_ids)

    def _generate_unique_duplicate_code(self, account, sequence):
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

    def action_view_duplicate_codes(self):
        duplicate_accounts = self.sudo()._get_duplicate_code_records()
        action = self.env.ref('account.action_account_form').sudo().read()[0]
        action.update({
            'name': _('Duplicate Account Codes'),
            'domain': [('id', 'in', duplicate_accounts.ids)],
        })
        return action

    def action_fix_duplicate_codes(self):
        duplicate_accounts = self.sudo()._get_duplicate_code_records()
        if not duplicate_accounts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Duplicate Codes'),
                    'message': _('No duplicate account codes were found.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        renamed_accounts = []
        sorted_accounts = duplicate_accounts.sorted(key=lambda acc: (acc.company_id.id, acc.code or '', acc.id))
        for _, grouped_accounts in groupby(sorted_accounts, key=lambda acc: (acc.company_id.id, acc.code or '')):
            group_accounts = list(grouped_accounts)
            if len(group_accounts) < 2:
                continue
            for sequence, account in enumerate(group_accounts[1:], start=1):
                new_code = self._generate_unique_duplicate_code(account, sequence)
                account.sudo().write({'code': new_code})
                renamed_accounts.append('%s / %s -> %s' % (account.company_id.name, account.name, new_code))

        message = _('Renamed %s duplicate accounts.') % len(renamed_accounts)
        if renamed_accounts:
            message = '%s %s' % (message, _('First duplicate kept original code in each company.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Duplicate Codes Fixed'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.model
    def create(self, vals_list):
        res = super(Account, self).create(vals_list)
        if (
            isinstance(vals_list, dict)
            and vals_list.get('cpabooks_related_account_ids')
            and not self.env.context.get('cpabooks_skip_related_ledger_sync')
        ):
            res._cpabooks_sync_related_ledgers(
                {account.id: set() for account in res},
            )
        user_type_id = self.env['account.account.type'].search([
            ('name', 'ilike', 'Bank and Cash')
        ], limit=1, order='id asc')
        # if res.user_type_id == user_type_id:
        #     self._action_create_journal(res)
        return res

    def write(self, vals):
        vals = dict(vals)
        if (
            'afg_sync_same_name' in vals
            and 'cpabooks_sync_name_all_companies' in self._fields
            and 'cpabooks_sync_name_all_companies' not in vals
        ):
            vals['cpabooks_sync_name_all_companies'] = bool(vals.get('afg_sync_same_name'))
        old_related = {}
        if (
            'cpabooks_related_account_ids' in vals
            and not self.env.context.get('cpabooks_skip_related_ledger_sync')
        ):
            old_related = {
                account.id: set(account.cpabooks_related_account_ids.ids)
                for account in self
            }
        if (
            not self.env.context.get('cpabooks_default_seed_write')
            and self._CPABOOKS_DEFAULT_TRACKED_FIELDS.intersection(vals)
        ):
            # Mark user edits even when seed_key is not set yet — otherwise
            # upgrade / Reset All can treat renamed ledgers as factory defaults.
            to_flag = self.filtered(
                lambda account: not account.cpabooks_default_manually_modified
            )
            if to_flag:
                to_flag.with_context(cpabooks_default_seed_write=True).write({
                    'cpabooks_default_manually_modified': True,
                })
        old_names = {account.id: account.name for account in self} if 'name' in vals else {}
        res = super(Account, self).write(vals)
        if old_related:
            self._cpabooks_sync_related_ledgers(old_related)

        """Update the account journal's name if the user type is 'Bank and Cash'
         when the name field is modified."""

        if 'name' in vals:
            new_name = vals.get('name')
            for account in self:
                type_name = (account.user_type_id.name or '').lower()
                if type_name == 'bank and cash':
                    account_journal = self.env['account.journal'].search([
                        ('company_id', '=', account.company_id.id),
                        ('default_account_id', '=', account.id),
                    ], limit=1)
                    if account_journal:
                        account_journal.write({'name': new_name})
            if not self.env.context.get('cpabooks_skip_name_sync'):
                for account in self:
                    if 'afg_sync_same_name' in account._fields:
                        do_sync = bool(account.afg_sync_same_name)
                    elif hasattr(account, '_cpabooks_apply_to_all_companies'):
                        do_sync = account._cpabooks_apply_to_all_companies()
                    else:
                        do_sync = bool(account.cpabooks_sync_name_all_companies)
                    if not do_sync:
                        continue
                    if not new_name or new_name == old_names.get(account.id):
                        continue
                    account._cpabooks_sync_name_to_other_companies(
                        new_name, old_name=old_names.get(account.id),
                    )

        # Check if 'user_type_id' is being updated
        if 'user_type_id' in vals:
            user_type_id = self.env['account.account.type'].search([
                ('name', 'ilike', 'Bank and Cash')
            ], limit=1, order='id asc')

            # Loop through all records and trigger action if the user_type_id matches
            # for record in self:
            #     if record.user_type_id == user_type_id:
            #         self._action_create_journal(record)

        return res

    def _cpabooks_sync_related_ledgers(self, old_related):
        """Keep Related Ledgers reciprocal on add and remove."""
        for account in self:
            current_ids = set(account.cpabooks_related_account_ids.ids)
            if account.id in current_ids:
                account.with_context(
                    cpabooks_skip_related_ledger_sync=True,
                ).write({
                    'cpabooks_related_account_ids': [(3, account.id)],
                })
                current_ids.discard(account.id)
            previous_ids = set(old_related.get(account.id, set()))
            added_ids = current_ids - previous_ids
            removed_ids = previous_ids - current_ids
            if added_ids:
                self.browse(added_ids).with_context(
                    cpabooks_skip_related_ledger_sync=True,
                ).write({
                    'cpabooks_related_account_ids': [(4, account.id)],
                })
            if removed_ids:
                self.browse(removed_ids).with_context(
                    cpabooks_skip_related_ledger_sync=True,
                ).write({
                    'cpabooks_related_account_ids': [(3, account.id)],
                })

    def _cpabooks_sibling_accounts_for_name_sync(self, old_name=None):
        """Matching ledgers in other companies (identity / seed / code / old name)."""
        self.ensure_one()
        Account = self.env['account.account'].sudo()
        domain = [
            ('id', '!=', self.id),
            ('company_id', '!=', self.company_id.id),
        ]
        siblings = Account.browse()
        seed_key = self.cpabooks_default_seed_key
        if seed_key:
            siblings |= Account.search(domain + [
                ('cpabooks_default_seed_key', '=', seed_key),
            ])
        identity = (self.identity_code or '').strip()
        if identity and identity.lower() != 'new':
            siblings |= Account.search(domain + [
                ('identity_code', '=', identity),
            ])
        if self.code:
            siblings |= Account.search(domain + [
                ('code', '=', self.code),
            ])
        if not siblings and old_name:
            siblings = Account.search(domain + [
                ('name', '=', old_name),
            ])
        return siblings

    def _cpabooks_sync_name_to_other_companies(self, new_name, old_name=None):
        """Push Account Name to matching ledgers in other companies."""
        self.ensure_one()
        siblings = self._cpabooks_sibling_accounts_for_name_sync(old_name=old_name)
        to_update = siblings.filtered(lambda acc: acc.name != new_name)
        if not to_update:
            return
        to_update.with_context(
            cpabooks_skip_name_sync=True,
            cpabooks_skip_ifrs_name_wizard=True,
            cpabooks_skip_ifrs_auto_setup=True,
        ).write({'name': new_name})

    def _action_create_journal(self, coa):
        get_all_journal = self.env['account.journal'].sudo().search([])
        existing_journal = self.env['account.journal'].search([
            '|',
            ('default_account_id', '=', coa.id),
            ('payment_debit_account_id', '=', coa.id),
            ('payment_credit_account_id', '=', coa.id),
            ('company_id', '=', self.env.company.id)
        ], limit=1, order='id asc')

        name = coa.name
        words = name.split()
        code = ''.join((word[0] for word in words))

        journal_type = ''
        if 'bank' in coa.name.lower():
            journal_type = 'bank'
        elif 'cash' in coa.name.lower():
            journal_type = 'cash'
        else:
            journal_type = 'cash'

        if existing_journal in get_all_journal:
            print(f"The account {coa.name} is already linked to the journal: {existing_journal.name}")
            existing_journal.write({
                'name': coa.name,
                'type': journal_type,
                'code': code
            })

        else:
            journal = self.env['account.journal'].create({
                'name': coa.name,
                'type': journal_type,
                'default_account_id': coa.id,
                'code': code,
                'payment_debit_account_id': coa.id,
                'payment_credit_account_id': coa.id,
            })
            print(journal.name)

    def action_create_journals_from_coa(self):
        self.env['account.journal'].create_journals_from_coa()

    # @api.onchange('previous')
    # def get_default_values(self):
    #     for rec in self:
    #         if rec.previous:
    #             code = int(rec.previous.code) + 2
    #             check_code = self.env['account.account'].search([('code', '=', code)])
    #
    #             while check_code:
    #                 code += 1
    #                 check_code = self.env['account.account'].search([('code', '=', code)])
    #
    #             rec.update({
    #                 'name': False,
    #                 'code': code,
    #                 'company_id': rec.previous.company_id.id,
    #                 'user_type_id': rec.previous.user_type_id.id,
    #                 'cash_flow_category': rec.previous.cash_flow_category.id,
    #                 'group_id': rec.previous.group_id.id,
    #                 'tax_ids': rec.previous.tax_ids.ids or False,
    #                 'tag_ids': rec.previous.tag_ids.ids or False,
    #                 'allowed_journal_ids': rec.previous.allowed_journal_ids.ids or False,
    #                 'create_asset': rec.previous.create_asset,
    #                 'asset_model': rec.previous.asset_model.id,
    #                 'reconcile': rec.previous.reconcile,
    #                 'deprecated': rec.previous.deprecated,
    #             })

    @api.onchange('group_id')
    def get_code(self):
        """Keep a type that is already set. Fill an empty type from the same group."""
        if not self.group_id or self.user_type_id:
            return
        company_id = self.company_id.id or self.env.company.id
        sibling = self.env['account.account'].search([
            ('company_id', '=', company_id),
            ('group_id', '=', self.group_id.id),
            ('user_type_id', '!=', False),
            ('id', '!=', self._origin.id or 0),
        ], limit=1, order='id desc')
        if sibling.user_type_id:
            self.user_type_id = sibling.user_type_id

    def _load_group(self):
        companies = self.mapped('company_id') or self.env['res.company'].search([])
        group_model = self.env['account.group'].sudo()
        csv_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_rows = [
                row for row in csv.DictReader(csv_file)
                if self._is_valid_coa_seed_row(row)
                and (row.get('group') or '').strip()
            ]

        for company in companies:
            for row in csv_rows:
                group = (row.get('group') or '').strip()
                prefix = (row.get('From') or '').strip()
                suffix = (row.get('To') or '').strip()
                if not group:
                    continue

                group_id = group_model.search([
                    ('name', '=', group),
                    ('company_id', '=', company.id),
                ], limit=1)
                values = {
                    'name': group,
                    'company_id': company.id,
                    'code_prefix_start': prefix or False,
                    'code_prefix_end': suffix or False,
                }
                if not group_id:
                    group_model.with_context(skip_prefix_constraint=True).create(values)
                else:
                    if group_id.code_prefix_start != (prefix or False) or group_id.code_prefix_end != (suffix or False):
                        group_id.with_context(skip_prefix_constraint=True).write(values)

        self.env['account.group']._cpa_ensure_groups_on_all_companies()
        print('Executed _load_group()')
        return True

    def _get_group_mapping_by_prefix(self, company):
        mapping = {}
        group_model = self.env['account.group'].sudo()
        csv_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if not self._is_valid_coa_seed_row(row):
                    continue
                prefix = (row.get('From') or '').strip()
                group_name = (row.get('group') or '').strip()
                if not prefix or not group_name:
                    continue
                group = group_model.search([
                    ('name', '=', group_name),
                    ('company_id', '=', company.id),
                ], limit=1)
                if group:
                    mapping[prefix] = group
        return mapping

    def _get_company_group_by_name(self, company, names):
        group_model = self.env['account.group'].sudo()
        for name in names:
            group = group_model.search([
                ('name', '=', name),
                ('company_id', '=', company.id),
            ], limit=1)
            if group:
                return group
        return False

    def _find_group_from_account_code(self, account_code, prefix_map):
        if not account_code:
            return False
        normalized_code = str(account_code).strip()
        base_prefix = normalized_code.split('-')[0]
        if base_prefix in prefix_map:
            return prefix_map[base_prefix]

        digit_prefix = ''.join(ch for ch in normalized_code if ch.isdigit())
        if len(digit_prefix) >= 3 and digit_prefix[:3] in prefix_map:
            return prefix_map[digit_prefix[:3]]

        if len(digit_prefix) >= 2 and digit_prefix[:2] in prefix_map:
            return prefix_map[digit_prefix[:2]]

        return False


    def _cpa_group_from_account_type(self, account, company, name_lower, type_lower):
        """Type wins over a shared code prefix, so bank does not steal receivable or payable."""
        if (
            'bank and cash' in type_lower
            or any(keyword in name_lower for keyword in ('bank', 'cash', 'petty cash', 'outstanding receipt', 'outstanding payment'))
        ):
            return self._get_company_group_by_name(company, ['Cash & Cash Equivalents', 'Cash and Bank'])
        if 'receivable' in type_lower or any(keyword in name_lower for keyword in ('receivable', 'debtor')):
            return self._get_company_group_by_name(company, ['Accounts Receivables', 'Accounts Receivables - Others'])
        if 'payable' in type_lower or 'payable' in name_lower:
            return self._get_company_group_by_name(company, ['Accounts Payable', 'Provisions, Accruals & Other Payable'])
        return False


    def _cpa_clear_shadow_group_prefixes(self, companies):
        """Drop a duplicate group prefix when the seed group already owns it.

        Odoo otherwise keeps the lowest id, so Fixed Assets steals 112 from
        Accounts Receivables when a bank group save recomputes every ledger.
        """
        if not companies:
            return
        Group = self.env['account.group'].sudo()
        seed = {}
        csv_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv',
        ))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            for row in csv.DictReader(csv_file):
                prefix = (row.get('From') or '').strip()
                name = (row.get('group') or '').strip()
                if prefix and name:
                    seed[prefix] = name
        for company in companies:
            groups = Group.search([
                ('company_id', '=', company.id),
                ('code_prefix_start', '!=', False),
            ])
            by_prefix = {}
            for group in groups:
                by_prefix.setdefault(group.code_prefix_start, Group.browse())
                by_prefix[group.code_prefix_start] |= group
            for prefix, prefixed in by_prefix.items():
                if len(prefixed) < 2 or prefix not in seed:
                    continue
                keeper = prefixed.filtered(lambda group: group.name == seed[prefix])[:1]
                if not keeper:
                    continue
                shadows = prefixed - keeper
                if not shadows:
                    continue
                self.env.cr.execute(
                    "UPDATE account_account SET group_id = %s WHERE group_id IN %s",
                    (keeper.id, tuple(shadows.ids)),
                )
                self.env.cr.execute(
                    """
                    UPDATE account_group
                       SET code_prefix_start = NULL, code_prefix_end = NULL
                     WHERE id IN %s
                    """,
                    (tuple(shadows.ids),),
                )
        self.env['account.account'].invalidate_cache(fnames=['group_id'])
        self.env['account.group'].invalidate_cache(fnames=['code_prefix_start', 'code_prefix_end'])

    def _find_group_from_account(self, account, prefix_map):
        company = account.company_id
        name_lower = (account.name or '').strip().lower()
        type_lower = (account.user_type_id.name or '').strip().lower()
        typed = self._cpa_group_from_account_type(account, company, name_lower, type_lower)
        if typed:
            return typed

        target_group = self._find_group_from_account_code(account.code, prefix_map)
        if target_group:
            return target_group

        keyword_groups = []
        if (
            'bank and cash' in type_lower
            or any(keyword in name_lower for keyword in ('bank', 'cash', 'petty cash', 'outstanding receipt', 'outstanding payment'))
        ):
            keyword_groups.append(['Cash & Cash Equivalents', 'Cash and Bank'])
        if 'receivable' in type_lower or any(keyword in name_lower for keyword in ('receivable', 'debtor')):
            keyword_groups.append(['Accounts Receivables', 'Accounts Receivables - Others'])
        if 'payable' in type_lower or 'payable' in name_lower:
            keyword_groups.append(['Accounts Payable', 'Provisions, Accruals & Other Payable'])
        if 'prepayment' in type_lower or 'prepaid' in name_lower:
            keyword_groups.append(['Prepaid Expenses', 'Prepaid'])
        if 'fixed assets' in type_lower or 'fixed asset' in type_lower:
            keyword_groups.append(['Fixed Asset'])
        if 'depreciation' in type_lower or 'depn.' in name_lower or 'depreciation' in name_lower:
            keyword_groups.append(['Depreciations', 'Depreciation'])
        if 'cost of revenue' in type_lower or 'direct costs' in type_lower:
            keyword_groups.append(['Cost of Materials', 'Selling and Distribution Expenses'])
        if 'income' in type_lower:
            keyword_groups.append(['Sales Revenue', 'Other Income/ Exp'])
        if 'expenses' in type_lower:
            keyword_groups.append(['General & Admin Exp'])
        if 'current assets' in type_lower and any(keyword in name_lower for keyword in ('outstanding', 'interco', 'clearing')):
            keyword_groups.append(['Cash & Cash Equivalents', 'Accounts Receivables - Others'])
        for names in keyword_groups:
            found = self._cpa_group_loose(company, names)
            if found:
                return found

        covered = (
            self._cpa_group_from_afg(account, company)
            or self._cpa_group_from_same_name(account, company)
            or self._cpa_group_from_type_majority(account, company)
        )
        return covered or False

    _CPA_AFG_ACCOUNT_GROUP_NAMES = {
        "AFG_CASH": ["Cash & Cash Equivalents", "Cash and Bank"],
        "AFG_AR": ["Accounts Receivables", "Accounts Receivables - Others"],
        "AFG_PREP": ["Prepaid Expenses", "Deposits"],
        "AFG_PPE": ["Fixed Asset"],
        "AFG_INV": ["Inventories", "Inventory"],
        "AFG_AP": ["Accounts Payable"],
        "AFG_TAX": ["Taxes"],
        "AFG_EOS": ["Provisions, Accruals & Other Payable"],
    }

    def _cpa_group_loose(self, company, names):
        """Exact group name, then a name that contains it. Never Unallocated Group."""
        found = self._get_company_group_by_name(company, names)
        if found and (found.name or "").strip().lower() != "unallocated group":
            return found
        Group = self.env["account.group"].sudo()
        for name in names:
            group = Group.search([
                ("company_id", "=", company.id),
                ("name", "ilike", name),
            ], limit=1)
            if group and (group.name or "").strip().lower() != "unallocated group":
                return group
        return False

    def _cpa_group_from_afg(self, account, company):
        """AFG already on the ledger names the account group (Cash, Receivables, …)."""
        if "afg_group_id" not in account._fields or not account.afg_group_id:
            return False
        code = (account.afg_group_id.code or "").strip().upper()
        names = self._CPA_AFG_ACCOUNT_GROUP_NAMES.get(code)
        if not names:
            return False
        return self._cpa_group_loose(company, names)

    def _cpa_group_from_same_name(self, account, company):
        """Same ledger name in another company already has a group."""
        if not (account.name or "").strip():
            return False
        peers = self.sudo().search([
            ("id", "!=", account.id),
            ("name", "=", account.name),
            ("group_id", "!=", False),
            ("company_id", "!=", company.id),
        ], limit=8)
        for peer in peers:
            if (peer.group_id.name or "").strip().lower() == "unallocated group":
                continue
            local = self._cpa_group_loose(company, [peer.group_id.name])
            if local:
                return local
        return False

    def _cpa_group_from_type_majority(self, account, company):
        """When most ledgers of this type already share one group, use that group."""
        if not account.user_type_id:
            return False
        rows = self.read_group(
            [
                ("company_id", "=", company.id),
                ("user_type_id", "=", account.user_type_id.id),
                ("group_id", "!=", False),
                ("id", "!=", account.id),
            ],
            ["group_id"],
            ["group_id"],
            lazy=False,
        )
        if not rows:
            return False
        total = sum(row.get("__count") or row.get("group_id_count") or 0 for row in rows)
        best = max(rows, key=lambda row: row.get("__count") or row.get("group_id_count") or 0)
        count = best.get("__count") or best.get("group_id_count") or 0
        if total < 2 or count < 2 or count / float(total) < 0.6:
            return False
        group = self.env["account.group"].browse(best["group_id"][0])
        if not group or (group.name or "").strip().lower() == "unallocated group":
            return False
        return group

    @api.model
    def _cpa_fill_blank_account_groups(self):
        """Give a group to ledgers that still have none, using type, name, code, and AFG."""
        accounts = self.sudo().search([
            ("group_id", "=", False),
            ("company_id", "!=", False),
        ])
        by_company = {}
        for account in accounts:
            by_company.setdefault(account.company_id.id, self.browse())
            by_company[account.company_id.id] |= account
        Company = self.env["res.company"].sudo()
        for company in Company.browse(list(by_company)):
            prefix_map = self._get_group_mapping_by_prefix(company)
            for account in by_company[company.id]:
                group = account._find_group_from_account(account, prefix_map)
                if not group or (group.name or "").strip().lower() == "unallocated group":
                    continue
                account.with_context(cpa_apply_setup_groups=True).write({
                    "group_id": group.id,
                })
        return True

    def _load_coa(self):
        current_company = self.env.company
        csv_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if not self._is_valid_coa_seed_row(row):
                    continue
                name = row['account_name']
                revise_name = row['account_name_revise']
                auto_code = row['code_auto']
                user_type = row['type_revise']
                gen_code = f'{auto_code}'
                identity_code = row['code']

                user_type_id = self.env['account.account.type'].search([('name', 'like', user_type)], limit=1)
                coa_all = self.env['account.account'].search(
                    [('name', 'in', (name, revise_name)), ('company_id', '=', current_company.id)])
                coa = self.env['account.account']
                for data in coa_all:
                    if data.identity_code and identity_code == data.identity_code:
                        coa = data
                        break
                    elif not data.identity_code and data.code == identity_code:
                        coa = data
                        break

                # Check if an account with the generated code already exists in the company
                existing_account = self.env['account.account'].search(
                    [('code', '=', gen_code), ('company_id', '=', current_company.id)], limit=1)

                # if existing_account and existing_account.id != coa.id:
                #     # If the code is already taken by a different account, generate a new code or skip
                #     continue  # or handle differently, such as generating a new unique code

                if coa:
                    if coa.code != gen_code:
                        coa.write({
                            'code': gen_code,
                            'identity_code': identity_code if (
                                    coa.identity_code != identity_code and identity_code not in (
                                "new", "New", "NEW", False)) else coa.identity_code
                        })
                    else:
                        coa.write({
                            'identity_code': identity_code if (
                                    coa.identity_code != identity_code and identity_code not in (
                                "new", "New", "NEW", False)) else coa.identity_code
                        })

                if not coa:
                    reconcile = user_type_id.internal_group in ('asset', 'liability')
                    self.env['account.account'].create({
                        'code': gen_code,
                        'name': revise_name,
                        'user_type_id': user_type_id.id,
                        'reconcile': reconcile,
                        'identity_code': identity_code
                    })
        return True

    def reset_group(self):
        if not self:
            active_ids = self.env.context.get('active_ids') or []
            self = self.browse(active_ids).exists()
        if not self:
            raise UserError(_('Select the ledgers whose group should be reset.'))
        self._cpa_clear_shadow_group_prefixes(self.mapped('company_id'))
        self._load_group()
        account_model = self.env['account.account'].sudo()
        account_ids = self.ids
        accounts = account_model.browse(account_ids)
        for company in accounts.mapped('company_id'):
            prefix_map = self._get_group_mapping_by_prefix(company)
            company_accounts = account_model.search([('id', 'in', accounts.ids), ('company_id', '=', company.id)])
            for rec in company_accounts:
                target_group = self._find_group_from_account(rec, prefix_map)
                rec.with_context(cpa_apply_setup_groups=True).write({
                    'group_id': target_group.id if target_group else False,
                })

    def action_reset_groups_only(self):
        self.env['account.account'].sudo().search([('company_id', '!=', False)]).reset_group()
        return True

    def reset_type(self):
        csv_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))

        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)

            for row in csv_reader:
                if not self._is_valid_coa_seed_row(row):
                    continue
                user_type = row['type']
                user_type_revise = row['type_revise']
                # qid = row['qid']
                code = row['code_auto']

                user_type_id = self.env['account.account.type'].search([('name', 'ilike', user_type_revise)], limit=1)

                for rec in self:
                    if rec.code == code:
                        reconcile = user_type_id.internal_group in ('asset', 'liability')
                        rec.update({
                            'user_type_id': user_type_id.id,
                            'reconcile': reconcile
                        })

    def reset_partner(self):
        restore = getattr(
            self.env['res.partner'],
            'action_cpabooks_restore_partner_accounts',
            None,
        )
        if restore:
            return restore()

        all_partner_ids = self.env['res.partner'].search([])
        account_receivable = self.env['account.account'].search(
            [('name', '=', 'Accounts Receivable')], limit=1, order='id asc',
        )
        account_payable = self.env['account.account'].search(
            [('name', '=', 'Payables')], limit=1, order='id asc',
        )

        for partner_id in all_partner_ids:
            vals = {}
            partner_co = partner_id.with_company(
                partner_id.company_id or self.env.company,
            )
            if (
                not partner_co.property_account_receivable_id
                and account_receivable
            ):
                vals['property_account_receivable_id'] = account_receivable.id
            if (
                not partner_co.property_account_payable_id
                and account_payable
            ):
                vals['property_account_payable_id'] = account_payable.id
            if vals:
                partner_co.write(vals)

    @api.model
    def _cpabooks_default_seed_rows(self):
        csv_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'data', 'coa_seed',
            'account_group_type.csv',
        ))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            return [
                row for row in csv.DictReader(csv_file)
                if self._is_valid_coa_seed_row(row)
            ]

    @api.model
    def _cpabooks_seed_key(self, row):
        return 'qid:%s' % (row.get('qid') or row['code_auto']).strip()

    @api.model
    def _cpabooks_seed_code(self, row, company):
        digits = re.sub(r'\D+', '', row['code_auto'])
        if company.cpabooks_coa_code_digits == '4' and len(digits) >= 4:
            return '%s%s' % (digits[:2], digits[-2:])
        return digits[:6] if len(digits) >= 6 else row['code_auto'].strip()

    @api.model
    def _cpabooks_ensure_default_groups(self, company, rows):
        Group = self.env['account.group'].sudo()
        groups = {}
        for row in rows:
            name = (row.get('group') or '').strip()
            if not name or name in groups:
                continue
            group = Group.search([
                ('company_id', '=', company.id),
                ('name', '=', name),
            ], limit=1)
            if not group:
                group = Group.with_context(skip_prefix_constraint=True).create({
                    'name': name,
                    'company_id': company.id,
                    'code_prefix_start': (row.get('From') or '').strip() or False,
                    'code_prefix_end': (row.get('To') or '').strip() or False,
                })
            groups[name] = group
        return groups

    @api.model
    def _cpabooks_find_legacy_default(self, company, row, seed_code):
        Account = self.sudo().with_company(company)
        identity_code = (row.get('code') or '').strip()
        if identity_code.lower() not in ('', 'new'):
            candidates = Account.search([
                ('company_id', '=', company.id),
                ('identity_code', '=', identity_code),
                ('cpabooks_default_seed_key', '=', False),
            ], limit=2)
            if len(candidates) == 1:
                return candidates

        default_name = row['account_name_revise'].strip()
        raw_code = row['code_auto'].strip()
        candidates = Account.search([
            ('company_id', '=', company.id),
            ('cpabooks_default_seed_key', '=', False),
            ('name', 'in', tuple(filter(None, {
                default_name,
                (row.get('account_name') or '').strip(),
            }))),
            ('code', 'in', tuple(filter(None, {raw_code, seed_code}))),
        ], limit=2)
        if len(candidates) == 1:
            return candidates

        for domain in (
            [('code', 'in', tuple(filter(None, {raw_code, seed_code})))],
            [('name', '=', default_name)],
        ):
            candidates = Account.search(
                [('company_id', '=', company.id),
                 ('cpabooks_default_seed_key', '=', False)] + domain,
                limit=2,
            )
            if len(candidates) == 1:
                return candidates
        return Account.browse()

    @api.model
    def _cpabooks_seed_values(self, company, row, groups):
        original_type = (row.get('type_revise') or '').strip()
        type_aliases = {
            'cost of revenue': ['Cost of Revenue', 'Cost of Materials'],
            'cost of materials': ['Cost of Materials', 'Cost of Revenue'],
        }
        type_names = type_aliases.get(original_type.lower(), [original_type])
        account_type = self.env['account.account.type']
        for type_name in type_names:
            account_type = self.env['account.account.type'].sudo().search([
                ('name', '=ilike', type_name),
            ], limit=1)
            if account_type:
                break
        if not account_type:
            raise UserError(_(
                'Account type "%s" required by the Saaskul chart was not found.'
            ) % original_type)
        group = groups.get((row.get('group') or '').strip())
        identity_code = (row.get('code') or '').strip()
        return {
            'company_id': company.id,
            'name': row['account_name_revise'].strip(),
            'code': self._cpabooks_seed_code(row, company),
            'user_type_id': account_type.id,
            'group_id': group.id if group else False,
            'reconcile': account_type.internal_group in ('asset', 'liability'),
            'identity_code': (
                identity_code
                if identity_code.lower() not in ('', 'new')
                else False
            ),
            'cpabooks_default_seed_key': self._cpabooks_seed_key(row),
            'cpabooks_default_manually_modified': False,
        }

    @api.model
    def _cpabooks_seed_values_match(self, account, values):
        return (
            re.sub(r'\D+', '', account.code or '')
            == re.sub(r'\D+', '', values['code'] or '')
            and account.name == values['name']
            and account.user_type_id.id == values['user_type_id']
            and account.group_id.id == values['group_id']
            and account.reconcile == values['reconcile']
        )

    @api.model
    def _cpabooks_is_legacy_pdc_default(self, account, values):
        legacy_codes = {
            'qid:5': '100011',
            'qid:43': '100012',
        }
        expected_code = legacy_codes.get(values['cpabooks_default_seed_key'])
        return bool(
            expected_code
            and account.code == expected_code
            and account.name == values['name']
            and account.user_type_id.id == values['user_type_id']
        )

    @api.model
    def cpabooks_ensure_default_coa(self, company=None, force=False):
        """Restore missing defaults and update defaults.

        ``force=False`` (Reset All / module upgrade): create missing factory
        ledgers and refresh code/type/group — **never overwrite ledger name**.
        ``force=True`` (Factory Reset): overwrite all seed ledgers to factory
        values including name (explicit user action only).
        """
        company = (company or self.env.company).sudo()._cpabooks_ensure_coa_code_digits()
        rows = self._cpabooks_default_seed_rows()
        groups = self._cpabooks_ensure_default_groups(company, rows)
        Account = self.sudo().with_company(company).with_context(
            allowed_company_ids=[company.id],
            cpabooks_skip_ifrs_auto_setup=True,
            cpabooks_skip_ifrs_name_wizard=True,
            cpabooks_default_seed_write=True,
        )
        created = updated = preserved = 0
        for row in rows:
            values = self._cpabooks_seed_values(company, row, groups)
            account = Account.search([
                ('company_id', '=', company.id),
                ('cpabooks_default_seed_key', '=', values['cpabooks_default_seed_key']),
            ], limit=1)
            if not account:
                account = self._cpabooks_find_legacy_default(
                    company, row, values['code'],
                )
                if account:
                    manually_modified = bool(
                        account.cpabooks_default_manually_modified
                        or not (
                            self._cpabooks_seed_values_match(account, values)
                            or self._cpabooks_is_legacy_pdc_default(account, values)
                        )
                    )
                    account.with_context(cpabooks_default_seed_write=True).write({
                        'cpabooks_default_seed_key':
                            values['cpabooks_default_seed_key'],
                        'cpabooks_default_manually_modified': False if force else manually_modified,
                    })
            if not account:
                Account.create(values)
                created += 1
            elif account.cpabooks_default_manually_modified and not force:
                preserved += 1
            else:
                changes = {
                    field_name: value
                    for field_name, value in values.items()
                    if field_name != 'company_id'
                    and (
                        account[field_name].id
                        if account._fields[field_name].type == 'many2one'
                        else account[field_name]
                    ) != value
                }
                # Soft paths must never restore user/custom ledger names.
                if not force:
                    changes.pop('name', None)
                if force and account.cpabooks_default_manually_modified:
                    changes['cpabooks_default_manually_modified'] = False
                if force and account.deprecated:
                    changes['deprecated'] = False
                if changes:
                    account.write(changes)
                    updated += 1

        tax_ledgers = Account.search([
            ('company_id', '=', company.id),
            ('name', '=ilike', 'Corporate tax for the year'),
            ('group_id', '!=', False),
        ])
        if tax_ledgers:
            tax_ledgers.with_context(cpabooks_default_seed_write=True).write({
                'group_id': False,
            })

        company.ensure_pdc_accounts()
        self._cpabooks_ensure_unaffected_earnings_account(company)
        # Auto-fill Dynamic Reports Cash Flow type when that module is installed
        if 'cash_flow_category' in self._fields and hasattr(
                self.env['account.account'], 'ins_auto_set_cash_flow_categories'):
            try:
                self.env['account.account'].ins_auto_set_cash_flow_categories(company=company)
            except Exception:
                pass
        return {
            'created': created,
            'updated': updated,
            'preserved': preserved,
        }

    @api.model
    def _cpabooks_factory_protected_account_ids(self, company):
        """Accounts that must not be deleted (moves / journal / company properties / PDC)."""
        company = company.sudo()
        protected = set()
        self.env.cr.execute(
            """
            SELECT DISTINCT account_id
              FROM account_move_line
             WHERE company_id = %s
               AND account_id IS NOT NULL
            """,
            [company.id],
        )
        protected.update(row[0] for row in self.env.cr.fetchall())

        journal_selects = []
        Journal = self.env['account.journal']
        for field_name in (
            'default_account_id',
            'suspense_account_id',
            'payment_debit_account_id',
            'payment_credit_account_id',
            'profit_account_id',
            'loss_account_id',
        ):
            if field_name in Journal._fields:
                journal_selects.append(
                    "SELECT %s AS acc_id FROM account_journal "
                    "WHERE company_id = %%s AND %s IS NOT NULL" % (field_name, field_name)
                )
        if journal_selects:
            self.env.cr.execute(
                "SELECT DISTINCT acc_id FROM (%s) t" % (" UNION ALL ".join(journal_selects)),
                [company.id] * len(journal_selects),
            )
            protected.update(row[0] for row in self.env.cr.fetchall() if row[0])

        for field_name in (
            'transfer_account_id',
            'income_currency_exchange_account_id',
            'expense_currency_exchange_account_id',
            'account_journal_suspense_account_id',
            'default_cash_difference_income_account_id',
            'default_cash_difference_expense_account_id',
            'account_default_pos_receivable_account_id',
            'property_stock_account_input_categ_id',
            'property_stock_account_output_categ_id',
            'property_stock_valuation_account_id',
        ):
            if field_name in company._fields and company[field_name]:
                protected.add(company[field_name].id)
        if company.pdc_customer:
            protected.add(company.pdc_customer.id)
        if company.pdc_vendor:
            protected.add(company.pdc_vendor.id)

        # Asset models / FAR
        if 'account.asset' in self.env:
            Asset = self.env['account.asset']
            for field_name in (
                'account_asset_id',
                'account_depreciation_id',
                'account_depreciation_expense_id',
            ):
                if field_name in Asset._fields:
                    for asset in Asset.sudo().search([('company_id', '=', company.id)]):
                        if asset[field_name]:
                            protected.add(asset[field_name].id)

        # Taxes (repartition accounts)
        if 'account.tax' in self.env:
            Tax = self.env['account.tax'].sudo().search([('company_id', '=', company.id)])
            for tax in Tax:
                for line in (tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids):
                    if line.account_id:
                        protected.add(line.account_id.id)

        return protected

    @api.model
    def _cpabooks_scrub_dangling_account_refs(self, company=None):
        """Clear leftover M2O / property pointers after accounts were deleted."""
        cr = self.env.cr
        # ir.property → account.account,ID
        cr.execute(
            """
            UPDATE ir_property
               SET value_reference = NULL
             WHERE value_reference LIKE 'account.account,%%'
               AND split_part(value_reference, ',', 2) ~ '^[0-9]+$'
               AND split_part(value_reference, ',', 2)::int
                   NOT IN (SELECT id FROM account_account)
            """
        )
        cr.execute(
            """
            DELETE FROM ir_property
             WHERE res_id LIKE 'account.account,%%'
               AND split_part(res_id, ',', 2) ~ '^[0-9]+$'
               AND split_part(res_id, ',', 2)::int
                   NOT IN (SELECT id FROM account_account)
            """
        )
        # AFG mapping orphans (if FK did not cascade)
        cr.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                 WHERE table_name = 'audited_financial_group_line'
            )
            """
        )
        if cr.fetchone()[0]:
            cr.execute(
                """
                DELETE FROM audited_financial_group_line
                 WHERE account_id IS NOT NULL
                   AND account_id NOT IN (SELECT id FROM account_account)
                """
            )
        # AFG working lines + merged_leaf CSV (Char field — no FK cascade)
        if "audited.financial.version" in self.env:
            try:
                self.env["audited.financial.version"]._afg_scrub_orphan_account_refs()
            except Exception:
                pass
        # Null company PDC if account gone
        if company:
            company = company.sudo()
            vals = {}
            if company.pdc_customer and not company.pdc_customer.exists():
                vals['pdc_customer'] = False
            if company.pdc_vendor and not company.pdc_vendor.exists():
                vals['pdc_vendor'] = False
            if vals:
                company.write(vals)
        # Stored root_id can point at account.root view rows that vanished after code/deletes.
        self._cpabooks_recompute_account_roots(company)
        return True

    @api.model
    def _cpabooks_recompute_account_roots(self, company=None):
        """Refresh stored account.root_id so Chart of Accounts searchpanel never hits Missing Record.

        ``account.root`` is a SQL view derived from current codes. After Factory Reset / code
        changes, stale root_id values (e.g. 50048) remain on account.account while the view
        row is gone → Missing Record account.root(…).
        """
        cr = self.env.cr
        domain_sql = ""
        params = []
        if company:
            domain_sql = " AND company_id = %s"
            params.append(company.id)
        # Match account.account._compute_account_root: ASCII(c0)*1000 + ASCII(c1 or \\x00)
        cr.execute(
            """
            UPDATE account_account
               SET root_id = CASE
                    WHEN code IS NULL OR code = '' THEN NULL
                    WHEN length(code) = 1 THEN ascii(substr(code, 1, 1)) * 1000
                    ELSE ascii(substr(code, 1, 1)) * 1000 + ascii(substr(code, 2, 1))
               END
             WHERE TRUE
            """ + domain_sql,
            params or None,
        )
        self.invalidate_cache(fnames=['root_id'])
        return True

    @api.model
    def cpabooks_factory_reset_coa(self, company=None):
        """Hard Factory Reset: delete unused non-protected ledgers, force-restore seed + PDC.

        Unlike Reset All, this does **not** preserve user-edited / user-created ledgers
        (except accounts that still have journal items or are linked on journals/company).
        """
        company = (company or self.env.company).sudo()._cpabooks_ensure_coa_code_digits()
        Account = self.sudo().with_company(company).with_context(
            allowed_company_ids=[company.id],
            cpabooks_skip_ifrs_auto_setup=True,
            cpabooks_skip_ifrs_name_wizard=True,
            cpabooks_default_seed_write=True,
        )
        protected = self._cpabooks_factory_protected_account_ids(company)
        all_accounts = Account.search([('company_id', '=', company.id)])
        to_remove = all_accounts.filtered(lambda acc: acc.id not in protected)
        deleted_ids = []

        deleted = 0
        archived = 0
        for account in to_remove:
            acc_id = account.id
            try:
                with self.env.cr.savepoint():
                    account.unlink()
                deleted += 1
                deleted_ids.append(acc_id)
            except Exception:
                try:
                    with self.env.cr.savepoint():
                        account.write({'deprecated': True})
                    archived += 1
                except Exception:
                    pass

        self._cpabooks_scrub_dangling_account_refs(company)
        result = self.cpabooks_ensure_default_coa(company, force=True)
        # Re-scrub after recreate in case old property rows pointed at deleted ids
        self._cpabooks_scrub_dangling_account_refs(company)
        company.ensure_pdc_accounts()
        # Ensure searchpanel / group-by never references deleted account.root rows
        self._cpabooks_recompute_account_roots(company)
        result['deleted'] = deleted
        result['archived'] = archived
        result['kept_in_use'] = len(protected)
        result['deleted_ids'] = deleted_ids
        return result

    @api.model
    def _cpabooks_unaffected_earnings_type(self):
        """Odoo TB/GL requires at least one Current Year Earnings account per company."""
        ue_type = self.env.ref('account.data_unaffected_earnings', raise_if_not_found=False)
        if ue_type:
            return ue_type
        return self.env['account.account.type'].sudo().search([
            ('name', '=ilike', 'Current Year Earnings'),
        ], limit=1)

    @api.model
    def _cpabooks_ensure_unaffected_earnings_account(self, company):
        """Ensure Undistributed Profits/Losses uses Current Year Earnings (not Equity).

        Without this type, Accounting → Trial Balance cannot roll prior-year P&amp;L into
        unaffected earnings and Initial Balance Debit/Credit can disagree.
        """
        company = (company or self.env.company).sudo()
        ue_type = self._cpabooks_unaffected_earnings_type()
        if not ue_type:
            return self.browse()

        Account = self.sudo().with_company(company).with_context(
            allowed_company_ids=[company.id],
            cpabooks_skip_ifrs_auto_setup=True,
            cpabooks_skip_ifrs_name_wizard=True,
            cpabooks_default_seed_write=True,
        )
        existing = Account.search([
            ('company_id', '=', company.id),
            ('user_type_id', '=', ue_type.id),
            ('deprecated', '=', False),
        ], limit=1)
        if existing:
            return existing

        # Prefer Saaskul seeded / renamed Undistributed Profits ledger
        candidates = Account.search([
            ('company_id', '=', company.id),
            ('deprecated', '=', False),
            '|', '|', '|',
            ('identity_code', '=', '999999'),
            ('cpabooks_default_seed_key', '=', 'qid:65'),
            ('name', '=ilike', 'Undistributed Profits/Losses'),
            ('name', 'ilike', 'Undistributed Profit'),
        ], limit=5)
        account = candidates[:1]
        if account:
            if account.user_type_id != ue_type:
                account.write({'user_type_id': ue_type.id})
            return account

        # Create missing UE account (6-digit IFRS-style default when company uses 6 digits)
        digits = company.cpabooks_coa_code_digits or '6'
        code = '338164' if digits == '6' else '3301'
        # Avoid code collision
        if Account.search([('company_id', '=', company.id), ('code', '=', code)], limit=1):
            code = '999999' if digits == '6' else '9999'
        group = self.env['account.group'].sudo().search([
            ('company_id', '=', company.id),
            '|', ('code_prefix_start', '=', '338'), ('name', 'ilike', 'Capital'),
        ], limit=1)
        return Account.create({
            'company_id': company.id,
            'name': 'Undistributed Profits/Losses',
            'code': code,
            'user_type_id': ue_type.id,
            'group_id': group.id if group else False,
            'reconcile': False,
            'identity_code': '999999',
            'cpabooks_default_seed_key': 'qid:65',
            'cpabooks_default_manually_modified': False,
        })

    @api.model
    def cpabooks_ensure_unaffected_earnings_all_companies(self):
        companies = self.env['res.company'].sudo().search([])
        for company in companies:
            self._cpabooks_ensure_unaffected_earnings_account(company)
        return True

    @api.model
    def cpabooks_ensure_default_coa_all_companies(self):
        """Upgrade/reset helper: restore missing defaults, including PDC, per company."""
        companies = self.env['res.company'].sudo().search([])
        companies._cpabooks_ensure_coa_code_digits()
        totals = {'created': 0, 'updated': 0, 'preserved': 0}
        for company in companies:
            result = self.with_company(company).with_context(
                allowed_company_ids=[company.id],
            ).cpabooks_ensure_default_coa(company)
            for key in totals:
                totals[key] += result[key]
        return totals

    def set_pdc(self):
        companies = self.mapped('company_id') or self.env.company
        return companies.ensure_pdc_accounts()

    def _action_load_coa(self):
        all_coa_ids = self.env['account.account'].sudo().search([])
        current_company = self.env.company
        csv_file_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if not self._is_valid_coa_seed_row(row):
                    continue
                name = row['account_name']
                revise_name = row['account_name_revise']
                auto_code = row['code_auto']
                user_type = row['type_revise']
                identity_code = row['code']

                user_type_id = self.env['account.account.type'].search([('name', 'like', user_type)], limit=1)
                reconcile = user_type_id.internal_group in ('asset', 'liability')

                get_coa = self.env['account.account'].search([
                    '|', ('name', 'in', (name, revise_name)),
                    ('code', 'in', (auto_code, identity_code)),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)

                skip = dict(cpabooks_skip_ifrs_auto_setup=True)
                if get_coa in all_coa_ids and (
                        get_coa.code != auto_code or get_coa.name != revise_name or get_coa.user_type_id != user_type_id or get_coa.identity_code != identity_code):
                    get_coa.with_context(**skip).write({
                        'code': auto_code,
                        # 'name': revise_name,
                        'user_type_id': user_type_id.id,
                        'reconcile': reconcile,
                        'identity_code': identity_code
                    })
                if not get_coa in all_coa_ids:
                    self.env['account.account'].with_context(**skip).create({
                        'code': auto_code,
                        'name': revise_name,
                        'user_type_id': user_type_id.id,
                        'reconcile': reconcile,
                        'identity_code': identity_code
                    })

        return True

    def reset_all(self):
        """Soft reset: restore missing factory defaults; preserve user-edited ledgers."""
        company = self.env.company
        self.cpabooks_ensure_default_coa(company, force=False)
        company_accounts = self.sudo().search([
            ('company_id', '=', company.id),
        ])
        company_accounts.reset_partner()
        company_accounts._create_item()
        company_accounts.action_create_far_rules()
        create_sequences = getattr(
            self.env['ir.sequence'], 'action_create_sequence', None,
        )
        if create_sequences:
            create_sequences()
        if hasattr(self, "action_cpa_update_all_groups"):
            self.action_cpa_update_all_groups()
        return True

    @api.model
    def load_coa(self):
        self._load_qid()
        # self._load_coa()
        # self._load_group()

    # @api.constrains('name')
    # def _check_name(self):
    #     for rec in self:
    #         if rec.name:
    #             coa_rec = self.env['account.account'].search(
    #                 [('name', '=ilike', rec.name), ('id', '!=', rec.id),('company_id','=',self.env.company.id)])
    #             if coa_rec:
    #                 raise UserError(_('This Chart Of Account Already exists!'))
    #                 print(coa_rec.name)

    def delete_wizard(self):
        """Open Factory Reset wizard (coa.create). Tolerate missing xmlids on restored DBs."""
        action = self.env.ref(
            "chart_of_accounts_saaskul.coa_create_form_action",
            raise_if_not_found=False,
        )
        if action:
            return action.read()[0]

        Act = self.env["ir.actions.act_window"].sudo()
        orphan = Act.search(
            [("res_model", "=", "coa.create"), ("view_mode", "ilike", "form")],
            order="id",
            limit=1,
        )
        view = self.env["ir.ui.view"].sudo().search(
            [("model", "=", "coa.create"), ("type", "=", "form")],
            order="id",
            limit=1,
        )
        if orphan:
            self._cpabooks_ensure_xmlid(
                "chart_of_accounts_saaskul.coa_create_form_action",
                orphan,
            )
            result = orphan.read()[0]
        else:
            result = {
                "type": "ir.actions.act_window",
                "name": _("Factory Reset"),
                "res_model": "coa.create",
                "view_mode": "form",
                "target": "new",
                "context": {"default_company_id": self.env.company.id},
            }
        if view:
            self._cpabooks_ensure_xmlid(
                "chart_of_accounts_saaskul.coa_create_form",
                view,
            )
            result["view_id"] = view.id
            result["views"] = [(view.id, "form")]
            result["target"] = "new"
        return result

    @api.model
    def _cpabooks_ensure_xmlid(self, xmlid, record):
        """Bind module.xmlid → record when ir.model.data was lost (common after restores)."""
        if not record or not xmlid or "." not in xmlid:
            return
        module, name = xmlid.split(".", 1)
        Imd = self.env["ir.model.data"].sudo()
        existing = Imd.search([("module", "=", module), ("name", "=", name)], limit=1)
        if existing:
            if existing.res_id != record.id or existing.model != record._name:
                existing.write({"model": record._name, "res_id": record.id})
            return
        Imd.create({
            "module": module,
            "name": name,
            "model": record._name,
            "res_id": record.id,
            "noupdate": True,
        })

    def reset_coa(self):
        return True

    @api.onchange("identity_code")
    def duplicacy_identity_code_chk(self):
        for rec in self:
            if rec.identity_code not in ("new", "New", "NEW", False):
                get_code = self.env['account.account'].sudo().search(
                    [('identity_code', '=', rec.identity_code), ('company_id', '=', self.env.company.id)])
                for line in get_code:
                    raise ValidationError(_("Same Identity Code Found in : %s", line.name))

    def action_create_far_rules(self):
        if 'account.asset' not in self.env:
            return True
        asset = self.env['account.asset'].search([])
        print([i.name for i in asset])
        expense_id = self.env['account.account'].search([
            ('name', 'ilike', 'Depreciation Costs'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        print(expense_id)
        print(expense_id.name)

        journal_id = self.env['account.journal'].search([
            ('name', 'ilike', 'Miscellaneous Operations'),
        ], limit=1)

        # FAA - Leasehold Improvement
        leasehold = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Leasehold Improvement'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if leasehold:
            if 'create_asset' in leasehold._fields:
                leasehold.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Leasehold Improvement')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Leasehold 10 years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': leasehold.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Leasehold 10 years',
                    'method_number': 120,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': leasehold.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            leasehold.asset_model = asset_model.id

        # FAA - Furniture & Fixtures
        furniture_fixtures = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Furniture & Fixtures'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if furniture_fixtures:
            furniture_fixtures.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Furniture & Fixtures')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Furniture & Fustures 5 Years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': furniture_fixtures.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Furniture & Fustures 5 Years',
                    'method_number': 60,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': furniture_fixtures.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            furniture_fixtures.asset_model = asset_model.id

        # FAA - Computer Hardware & Software
        computer_hardware = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Computer Hardware & Software'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if computer_hardware:
            computer_hardware.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Furniture & Fixtures')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Computer Hardware & Fustures 5 Years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': computer_hardware.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,

                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Computer Hardware & Fustures 5 Years',
                    'method_number': 60,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': computer_hardware.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            computer_hardware.asset_model = asset_model.id

        # FAA - Motor Vehicle
        motor = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Motor Vehicle'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if motor:
            motor.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Motor Vehicle')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Motor 10 years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': motor.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Motor 10 years',
                    'method_number': 120,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': motor.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            motor.asset_model = asset_model.id

        # FAA - Equipment & Machineries
        equipment = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Equipment & Machineries'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if equipment:
            equipment.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Equipment & Machineries')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Equipment & Fustures 5 Years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': equipment.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Equipment & Fustures 5 Years',
                    'method_number': 60,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': equipment.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            equipment.asset_model = asset_model.id

        # FAA - Tools & Office Equipment
        tools = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Tools & Office Equipment'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if tools:
            tools.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Tools & Office Equipment')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Tools & Fustures 5 Years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': tools.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Tools & Fustures 5 Years',
                    'method_number': 60,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': tools.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            tools.asset_model = asset_model.id

        # FAA - Building
        building = self.env['account.account'].search([
            ('name', 'ilike', 'FAA - Building'),
            ('user_type_id.name', 'in', ('Fixed Assets', 'Current Assets'))
        ], limit=1)
        if building:
            building.create_asset = 'draft'

            depreciation_account_id = self.env['account.account'].search([
                ('name', 'ilike', 'Acc. Depn. - Building')
            ], limit=1)
            asset_model = self.env['account.asset'].search([
                ('name', 'ilike', 'Building 15 Years')
            ], limit=1)
            if asset_model:
                asset_model.write({
                    'asset_type': 'purchase',
                    'display_account_asset_id': True,
                    'account_depreciation_expense_id': expense_id.id,
                    'state': 'model',
                    'account_asset_id': building.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                })
            else:
                asset_model = self.env['account.asset'].create({
                    'name': 'Building 15 Years',
                    'method_number': 180,
                    'method_period': '1',
                    'prorata': True,
                    'account_asset_id': building.id,
                    'account_depreciation_id': depreciation_account_id.id if depreciation_account_id else False,
                    'account_depreciation_expense_id': expense_id.id,
                    'journal_id': journal_id.id,
                    'asset_type': 'purchase',
                    'state': 'model',
                    'display_account_asset_id': True,
                })
            building.asset_model = asset_model.id

    def action_view_rules(self):
        if 'account.asset' not in self.env:
            raise UserError(_(
                'Fixed Asset rules require the account_asset module '
                '(Enterprise). Install it to open Assets.'
            ))
        tree = self.env.ref(
            'account_asset.view_account_asset_model_purchase_tree',
            raise_if_not_found=False,
        )
        form = self.env.ref(
            'account_asset.view_account_asset_form',
            raise_if_not_found=False,
        )
        views = []
        if tree:
            views.append((tree.id, 'tree'))
        if form:
            views.append((form.id, 'form'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assets',
            'res_model': 'account.asset',
            'view_mode': 'tree,form',
            'views': views or False,
            'target': 'current',
            'context': self.env.context,
            'domain': [('asset_type', '=', 'purchase'), ('state', '=', 'model')],
        }

    def create_category(self):
        parent_category_id = self.env['product.category'].search([
            ('name', 'ilike', 'All')
        ], limit=1, order='id asc')
        category = self.env['product.category'].search([
            ('name', 'ilike', 'COA')
        ], limit=1, order='id asc')

        if not category:
            self.env['product.category'].create({
                'name': 'COA',
                'parent_id': parent_category_id.id,
            })
        return True

    def _create_item(self):
        print('executed _create_item')
        if self.create_category():
            category_id = self.env['product.category'].search([
                ('name', 'ilike', 'COA')
            ], limit=1, order='id asc')

            all_product_ids = self.env['product.template'].search([])

            current_company = self.env.company
            csv_file_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))
            with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                for row in csv_reader:
                    if not self._is_valid_coa_seed_row(row):
                        continue
                    name = row['account_name']
                    revise_name = row['account_name_revise']
                    auto_code = row['code_auto']
                    user_type = row['type_revise']
                    identity_code = row['code']
                    create_items = row['create_item']
                    link_item_coa = row['link_item_coa']

                    if create_items.lower() == 'yes':
                        income_account_id = self.env['account.account'].search([
                            ('code', '=', auto_code)
                        ], limit=1, order="id asc")

                        # check if product already exists or not

                        product_id = self.env['product.template'].search([
                            '|', ('name', '=', revise_name),
                            ('coa_code', '=', auto_code),
                            ('company_id', '=', self.env.company.id)
                        ], limit=1)

                        if product_id in all_product_ids:
                            product_id.write({
                                'coa_code': auto_code,
                                'property_account_expense_id': income_account_id.id,
                                # 'property_account_income_id': income_account_id.id,
                                'company_id': self.env.company.id,
                                'categ_id': category_id.id,
                                'type': 'product' if user_type == 'Cost of Revenue' else 'service',
                            })

                        else:
                            product_id = self.env['product.template'].create({
                                'name': revise_name,
                                'coa_code': auto_code,
                                'categ_id': category_id.id,
                                'company_id': self.env.company.id,
                                # 'property_account_income_id': income_account_id.id,
                                'property_account_expense_id': income_account_id.id,
                                'type': 'product' if user_type == 'Cost of Revenue' else 'service',
                            })

                        if link_item_coa.lower() == 'yes':
                            product_id.write({
                                'property_account_expense_id': income_account_id.id
                            })
                        else:
                            print(f"link coa is 'no'")
                    else:
                        print(f"Product won't create for '{revise_name}' because create_items: '{create_items}'")

    def action_remove_group(self):
        all_coa = self.env['account.account'].sudo().search([])
        all_coa.group_id = False

    def create_deferred_expense_model(self):
        get_all_coa = self.env['account.account'].sudo().search([])
        get_all_asset = self.env['account.asset'].sudo().search([])

        prepaid_coa_ids = self.env['account.account'].search([
            ('user_type_id.name', 'ilike', 'Prepayments'),
            # ('company_id', '=', self.env.company.id)
        ])
        print(f'pre_coa {[i.name for i in prepaid_coa_ids]}')

        for i in prepaid_coa_ids:
            cleaned_name = re.sub(r'[\s-]*\(?prepaid\)?[\s-]*$', '', i.name, flags=re.IGNORECASE)
            print(f'cleaned {cleaned_name}')
            if cleaned_name != i.name:  # Only proceed if something was removed
                expense_coa_id = self.env['account.account'].search([
                    ('name', 'ilike', cleaned_name),
                    ('user_type_id.name', 'ilike', 'Expenses'),
                    # ('company_id', '=', self.env.company.id)
                ], limit=1)
                print(f'expense {expense_coa_id}')
                journal_id = self.env['account.journal'].search([
                    ('company_id', '=', self.env.company.id),
                    ('name', '=ilike', 'Miscellaneous Operations')
                ], limit=1, order="id asc")
                print(journal_id)

                # Create deferred asset models
                if expense_coa_id in get_all_coa:
                    i.create_asset = 'draft'
                    print(expense_coa_id.name)
                    for months in [12, 6, 3]:
                        model_name = f'{cleaned_name} {months} Months.'
                        model = self.env['account.asset'].search([
                            ('name', 'ilike', model_name),
                            ('company_id', '=', self.env.company.id),
                            ('account_depreciation_id', '=', i.id)
                        ], limit=1)
                        print(f'model {model}')

                        if not model or model not in get_all_asset:
                            model = self.env['account.asset'].create({
                                'name': model_name,
                                'asset_type': 'expense',
                                'state': 'model',
                                'account_depreciation_id': i.id,
                                'account_depreciation_expense_id': expense_coa_id.id,
                                'journal_id': journal_id.id,
                                'prorata': True,
                                'method_number': months,
                                'method_period': '1',
                            })
                        if model in get_all_asset:
                            model.write({
                                'state': 'model',
                                'account_depreciation_id': i.id,
                                'account_depreciation_expense_id': expense_coa_id.id,
                                'journal_id': journal_id.id,
                                'prorata': True,
                            })

                        # Assign asset_model to the first created model (12 months)
                        if months == 12 and not i.asset_model:
                            i.asset_model = model.id

    @api.model
    def default_get(self, fields_list):
        get_last = self.env['account.account'].search([], limit=1, order="id desc")
        self.is_show_code = get_last.is_show_code
        return super(Account, self).default_get(fields_list)

    def action_toggle_code(self):
        get_all_coa_ids = self.env['account.account'].search([])
        for coa in get_all_coa_ids:
            coa.is_show_code = True if not coa.is_show_code else False

    def action_show_code_true(self):
        self.env['account.account'].sudo().search([]).is_show_code = True

    def name_get(self):
        result = []
        for rec in self:
            if rec.is_show_code:
                result.append((rec.id, '%s - %s' % (rec.code, rec.name)))

            else:
                result.append((rec.id, '%s' % (rec.name)))
        return result

    def action_update_selected(self):
        csv_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv'))

        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)

            for row in csv_reader:
                if not self._is_valid_coa_seed_row(row):
                    continue
                auto_code = row['code_auto']
                user_type = row['type_revise']
                revise_name = row['account_name_revise']
                name = row['account_name']
                identity_code = row['code']

                user_type_id = user_type_id = self.env['account.account.type'].search([
                    ('name', 'like', user_type)
                ], limit=1, order="id asc")
                reconcile = user_type_id.internal_group in ('asset', 'liability')
                for rec in self:
                    if rec.name in (revise_name, name):
                        print(row)
                        rec.write({
                            'code': auto_code,
                            'name': revise_name,
                            'user_type_id': user_type_id.id,
                            'reconcile': reconcile,
                            'identity_code': identity_code
                        })

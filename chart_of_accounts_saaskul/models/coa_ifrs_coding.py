# -*- coding: utf-8 -*-
import csv
import logging
import re
from collections import defaultdict

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_resource

_logger = logging.getLogger(__name__)

from .coa_l_structure_data import (
    COA_STRUCTURE_HELP,
    L1_BY_INTERNAL_GROUP,
    L1_TYPE_CODES,
    L2_CATALOG,
    L2_DEFAULT_BY_TYPE,
    MAX_BRANCH_COMPANIES,
)

PROPOSED_GROUP_BY_INTERNAL = {
    'asset': 'Assets',
    'liability': 'Liabilities',
    'equity': 'Equity',
    'income': 'Income',
    'expense': 'Expenses',
    'off_balance': 'Off-Balance Sheet',
}

PROPOSED_GROUP_BY_TYPE = {
    'liquidity': 'Cash and Cash Equivalents',
    'receivable': 'Trade and Other Receivables',
    'payable': 'Trade and Other Payables',
    'equity': 'Equity',
}

NON_IFRS_NAME_MARKERS = (
    r'\btest\b',
    r'\btodo\b',
    r'\bdummy\b',
    r'\bxxx\b',
    r'\btbd\b',
)

IFRS_RANGE_HELP = COA_STRUCTURE_HELP

IFRS_UNALLOCATED_GROUP_CODE = '99'
IFRS_UNALLOCATED_GROUP_LABEL = 'Unallocated Group'
IFRS_TEMP_CODE_MARKERS = ('__ifrs_code_', '__ifrs_tmp_', '__reset_digits_')


class CoaIfrsCoding(models.AbstractModel):
    _name = 'coa.ifrs.coding'
    _description = 'COA L1/L2/L3 structure (Type / IFRS Group / Ledger code)'

    @api.model
    def _ifrs_range_help_text(self):
        return IFRS_RANGE_HELP

    @api.model
    def branch_companies(self, company_ids=None):
        if not company_ids:
            raise UserError(_('Select at least one company for IFRS branch coding.'))
        if len(company_ids) > MAX_BRANCH_COMPANIES:
            raise UserError(
                _('IFRS branch coding supports up to %(max)s companies (branch digit 1–%(max)s).')
                % {'max': MAX_BRANCH_COMPANIES}
            )
        companies = self.env['res.company'].search(
            [('id', 'in', company_ids)], order='id', limit=MAX_BRANCH_COMPANIES,
        )
        if not companies:
            raise UserError(_('Select at least one company for IFRS branch coding.'))
        return companies

    @api.model
    def branch_companies_for_accounts(self, accounts, preferred_company_ids=None):
        """Build branch list from ledger companies (not only the active company switcher)."""
        account_companies = accounts.mapped('company_id').sorted('id')
        if preferred_company_ids:
            preferred = self.env['res.company'].browse(preferred_company_ids).exists().sorted('id')
            account_companies = (preferred | account_companies).sorted('id')
        company_ids = account_companies.ids[:MAX_BRANCH_COMPANIES]
        if len(account_companies) > MAX_BRANCH_COMPANIES:
            names = ', '.join(account_companies.mapped('name'))
            raise UserError(
                _('IFRS branch coding supports up to %(max)s companies. Found: %(names)s')
                % {'max': MAX_BRANCH_COMPANIES, 'names': names}
            )
        return self.branch_companies(company_ids)

    @api.model
    def branch_company_digit_map(self, branch_companies):
        branch_companies = branch_companies.sorted('id')
        return {company.id: str(index + 1) for index, company in enumerate(branch_companies)}

    @api.model
    def company_branch_digit(self, company, branch_companies):
        digit_map = self.branch_company_digit_map(branch_companies)
        digit = digit_map.get(company.id)
        if not digit:
            raise UserError(
                _('Company %(company)s is not in the branch list (digits 1–%(max)s by company ID order).')
                % {'company': company.display_name, 'max': MAX_BRANCH_COMPANIES}
            )
        return digit

    @api.model
    def _normalize_name(self, name):
        return re.sub(r'\s+', ' ', (name or '').strip().lower())

    @api.model
    def _ifrs_range_bucket(self, account):
        """Return (range_start, range_end, bucket_key, preferred_first_base)."""
        name = self._normalize_name(account.name)
        ig = account.internal_group
        it = account.internal_type
        utype_name = (account.user_type_id.name or '').lower() if account.user_type_id else ''

        if ig == 'off_balance' or re.search(r'suspense|clearing', name):
            return (900, 999, 'special', 900)
        if re.search(r'\btax\b|\bvat\b|withholding', name):
            return (900, 999, 'tax', 901)

        if ig == 'income':
            return (500, 599, 'revenue', 440)
        if ig == 'equity':
            return (400, 499, 'equity', 401)
        if ig == 'expense':
            if re.search(r'salary|payroll|wage|ctc|gratuity', name):
                return (600, 899, 'payroll', 603)
            if re.search(r'audit|professional fee|consult', name):
                return (600, 899, 'expense_prof', 760)
            if re.search(r'cost of sales|cogs|cost of goods', name):
                return (600, 899, 'cogs', 610)
            if re.search(r'deprec|amort', name):
                return (600, 899, 'depreciation', 680)
            return (600, 899, 'expense', 601)

        if ig == 'liability':
            if re.search(r'accru|provision', name):
                return (300, 399, 'accrual', 236)
            if it == 'payable' or re.search(r'payable|creditor', name):
                return (300, 399, 'payable', 301)
            return (300, 399, 'liability', 310)

        if ig == 'asset':
            if it == 'liquidity' or re.search(r'bank|cash|cheque|petty', name):
                return (100, 199, 'cash_bank', 110)
            if it == 'receivable' or re.search(r'receivable|debtor', name):
                return (100, 199, 'receivable', 120)
            if re.search(r'inventory|stock', name):
                return (200, 299, 'inventory', 210)
            if re.search(r'prepaid|prepayment|advance', name) or 'prepayment' in utype_name:
                return (200, 299, 'prepaid', 220)
            if re.search(r'accum|deprec', name):
                return (100, 199, 'accum_depr', 105)
            if re.search(r'fixed asset|ppe|furniture|vehicle|equipment', name) or 'fixed' in utype_name:
                return (100, 199, 'fixed_asset', 101)
            return (200, 299, 'current_asset', 201)

        return (900, 999, 'special', 900)

    @api.model
    def proposed_group_name(self, account):
        if account.user_type_id and account.user_type_id.type in PROPOSED_GROUP_BY_TYPE:
            return PROPOSED_GROUP_BY_TYPE[account.user_type_id.type]
        return PROPOSED_GROUP_BY_INTERNAL.get(account.internal_group, account.user_type_id.name or '')

    @api.model
    def account_grouping_key(self, account):
        """Group mirrored ledgers across companies (same XXX, different C)."""
        identity = ''
        if 'identity_code' in account._fields:
            identity = (account.identity_code or '').strip().lower()
            if identity and identity not in ('new', 'false', '0'):
                return ('identity', identity)
        return (
            'name_type',
            self._normalize_name(account.name),
            account.user_type_id.id or 0,
            self._ifrs_range_bucket(account)[2],
        )

    @api.model
    def name_needs_ifrs_review(self, name):
        text = (name or '').strip()
        if not text or len(text) < 3:
            return True
        lowered = text.lower()
        for pattern in NON_IFRS_NAME_MARKERS:
            if re.search(pattern, lowered):
                return True
        if lowered.startswith('ic ') or lowered == 'ic':
            return True
        if 'interco' in lowered and 'intercompany' not in lowered:
            return True
        return False

    @api.model
    def suggest_ifrs_name(self, account):
        current = (account.name or '').strip()
        seed = self._seed_structure_for_account(account)
        seed_name = (seed.get('account_name_revise') or seed.get('account_name') or '').strip()
        if seed_name and seed_name.lower() != 'new' and self.name_needs_ifrs_review(current):
            return seed_name
        proposed_group = self.proposed_group_name(account)
        company = account.company_id.display_name if account.company_id else ''
        if account.internal_type == 'liquidity':
            return _('%(group)s - %(company)s') % {'group': proposed_group, 'company': company}
        if account.internal_type in ('receivable', 'payable'):
            if company and company.lower() not in current.lower():
                return _('%(base)s - %(company)s') % {'base': proposed_group, 'company': company}
            return proposed_group
        if self.name_needs_ifrs_review(current):
            return proposed_group or current
        return current

    @api.model
    def ledger_bs_pl(self, account):
        if account.internal_group in ('income', 'expense'):
            return 'PL'
        return 'BS'

    @api.model
    def is_temp_ifrs_code(self, code):
        code = (code or '').strip()
        return any(code.startswith(marker) for marker in IFRS_TEMP_CODE_MARKERS)

    @api.model
    def effective_ledger_code(self, account):
        code = (account.code or '').strip()
        if self.is_temp_ifrs_code(code):
            prev = ''
            if 'cpabooks_previous_code' in account._fields:
                prev = (account.cpabooks_previous_code or '').strip()
            if prev and not self.is_temp_ifrs_code(prev):
                return prev
            return ''
        return code

    @api.model
    def l1_type_code(self, account):
        code = self.effective_ledger_code(account)
        if code and len(code) == 4 and code[0] in L1_BY_INTERNAL_GROUP.values():
            return code[0]
        return L1_BY_INTERNAL_GROUP.get(account.internal_group, '1')

    @api.model
    def l1_type_label(self, account):
        code = self.l1_type_code(account)
        labels = {tc: lbl for _ig, (tc, lbl) in L1_TYPE_CODES.items()}
        return labels.get(code, _('Assets'))

    @api.model
    def ledger_first_digit(self, account):
        return self.l1_type_code(account)

    @api.model
    def _normalize_group_label(self, two_digit_code, label):
        """Strip leading group code from label (name field must not include the code)."""
        label = (label or IFRS_UNALLOCATED_GROUP_LABEL).strip()
        prefix = (two_digit_code or '').strip()
        if not prefix:
            return label
        while label.startswith(prefix):
            label = label[len(prefix):].lstrip(' -')
        return label or IFRS_UNALLOCATED_GROUP_LABEL

    @api.model
    def ifrs_group_display_name(self, two_digit_code, label):
        """Full label for helpers/wizards (code + name). Not stored on account.group.name."""
        clean = self._normalize_group_label(two_digit_code, label)
        return '%s %s' % (two_digit_code, clean)

    @api.model
    def repair_ifrs_group_names(self, company_ids=None):
        """Fix groups whose name still embeds the 2-digit prefix (duplicate in name_get)."""
        Group = self.env['account.group'].sudo()
        domain = []
        if company_ids:
            domain.append(('company_id', 'in', company_ids))
        ctx = self._group_skip_context()
        repaired = 0
        for group in Group.search(domain):
            code = (group.code_prefix_start or '').strip()
            if len(code) != 2 or not code.isdigit():
                continue
            clean = self._normalize_group_label(code, group.name)
            if group.name != clean:
                group.with_context(**ctx).write({'name': clean})
                repaired += 1
        return repaired

    @tools.ormcache('self.env.cr.dbname')
    def _seed_structure_rows(self):
        path = get_module_resource(
            'chart_of_accounts_saaskul',
            'data',
            'coa_seed',
            'account_group_type.csv',
        )
        if not path:
            return []
        rows = []
        with open(path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                rows.append({
                    key: (value or '').strip()
                    for key, value in row.items()
                })
        return rows

    @api.model
    def _seed_structure_for_account(self, account):
        rows = self._seed_structure_rows()
        identity = ''
        if 'identity_id' in account._fields and account.identity_id:
            identity = str(account.identity_id).strip().lower()
        current_code = (self.effective_ledger_code(account) or account.code or '').strip().lower()
        account_name = self._normalize_name(account.name)

        if identity:
            for row in rows:
                if (row.get('code') or '').strip().lower() == identity:
                    return row
        if current_code:
            for row in rows:
                seed_code = (row.get('code') or '').strip().lower()
                seed_auto = (row.get('code_auto') or '').split('-')[0].strip().lower()
                if current_code in (seed_code, seed_auto):
                    return row
        if account_name:
            for row in rows:
                names = (
                    row.get('account_name_revise'),
                    row.get('account_name'),
                )
                if any(self._normalize_name(name) == account_name for name in names if name):
                    return row
        return {}

    @api.model
    def _match_l2_from_seed(self, account, type_code):
        row = self._seed_structure_for_account(account)
        if not row:
            return None
        seed_text = ' '.join(filter(None, (
            row.get('group'),
            row.get('type_revise'),
            row.get('account_name_revise'),
            row.get('account_name'),
        )))
        normalized = self._normalize_name(seed_text)
        if not normalized:
            return None
        for group_code, label, patterns in L2_CATALOG.get(type_code, []):
            for pattern in patterns:
                if re.search(pattern, normalized):
                    return group_code, label
        return None

    @api.model
    def _match_l2_from_account(self, account, type_code):
        seed_match = self._match_l2_from_seed(account, type_code)
        if seed_match:
            return seed_match
        name = self._normalize_name(account.name)
        utype = self._normalize_name(account.user_type_id.name if account.user_type_id else '')
        text = '%s %s' % (name, utype)
        for group_code, label, patterns in L2_CATALOG.get(type_code, []):
            for pattern in patterns:
                if re.search(pattern, text):
                    return group_code, label
        default_code = L2_DEFAULT_BY_TYPE.get(type_code, '99')
        for group_code, label, _patterns in L2_CATALOG.get(type_code, []):
            if group_code == default_code:
                return group_code, label
        return default_code, IFRS_UNALLOCATED_GROUP_LABEL

    @api.model
    def resolve_l2_group(self, account):
        type_code = self.l1_type_code(account)
        group_code, label = self._match_l2_from_account(account, type_code)
        return {
            'code': group_code,
            'label': label,
            'display_name': self.ifrs_group_display_name(group_code, label),
        }

    @api.model
    def build_ifrs_two_digit_group_plan(self, accounts):
        """L2: fixed 2-digit IFRS group from Type + catalog (independent of ledger code)."""
        plan = {}
        for account in accounts.filtered('company_id'):
            plan[account.id] = self.resolve_l2_group(account)
        return plan

    build_l2_group_plan = build_ifrs_two_digit_group_plan

    @api.model
    def parse_ledger_code(self, code):
        code = (code or '').strip()
        if len(code) != 4 or not code.isdigit():
            return {}
        return {
            'group_code': code[:2],
            'sequence': int(code[2:4]),
        }

    @api.model
    def ledger_code_is_valid(self, account, code=None):
        code = (code if code is not None else account.code) or ''
        code = code.strip()
        if self.is_temp_ifrs_code(code):
            return False
        if len(code) != 4 or not code.isdigit():
            return False
        parsed = self.parse_ledger_code(code)
        if not parsed:
            return False
        group_code = (self.resolve_l2_group(account).get('code') or '').strip()
        return (
            parsed['group_code'] == group_code
            and 1 <= parsed['sequence'] <= 99
        )

    @api.model
    def ledger_code_is_valid_for_branches(self, account, branch_companies, code=None):
        return self.ledger_code_is_valid(account, code=code)

    @api.model
    def preferred_l3_ledger_code(self, account, branch_companies=None):
        """Preferred L3-LC prefix: L2 group code + sequence, company kept separate."""
        group_info = self.resolve_l2_group(account)
        group_code = (group_info.get('code') or '').strip()
        if len(group_code) != 2 or not group_code.isdigit():
            return ''
        return '%s01' % group_code

    @api.model
    def _ledger_code_is_available(self, account, code, exclude_account_ids=None):
        exclude_ids = list(exclude_account_ids or []) + [account.id]
        return not self.env['account.account'].sudo().search_count([
            ('company_id', '=', account.company_id.id),
            ('code', '=', code),
            ('id', 'not in', exclude_ids),
        ])

    @api.model
    def allocate_group_based_ledger_code(
        self, account, branch_companies=None, exclude_account_ids=None, reserved_codes=None,
    ):
        reserved_codes = set(reserved_codes or [])
        return self.allocate_next_ledger_code(
            account,
            exclude_account_ids=exclude_account_ids,
            reserved_codes=reserved_codes,
        )

    @api.model
    def _collect_used_ledger_sequences(self, company, group_code, exclude_account_ids=None):
        exclude_account_ids = set(exclude_account_ids or [])
        used = set()
        accounts = self.env['account.account'].sudo().search([
            ('company_id', '=', company.id),
            ('code', '=like', '%s__' % group_code),
        ])
        for acc in accounts:
            if acc.id in exclude_account_ids:
                continue
            code = (acc.code or '').strip()
            parsed = self.parse_ledger_code(code)
            if parsed and parsed['group_code'] == group_code:
                used.add(parsed['sequence'])
        return used

    @api.model
    def allocate_next_ledger_code(self, account, exclude_account_ids=None, reserved_codes=None):
        account = account.exists()
        if not account.company_id:
            raise UserError(_('Select a company before generating a ledger code.'))
        reserved_codes = set(reserved_codes or [])
        group_code = (self.resolve_l2_group(account).get('code') or '').strip()
        if len(group_code) != 2 or not group_code.isdigit():
            raise UserError(_('No valid IFRS group code found for %s.') % account.display_name)
        used = self._collect_used_ledger_sequences(account.company_id, group_code, exclude_account_ids)
        used |= {
            int(code[2:4])
            for code in reserved_codes
            if len(code) == 4 and code.isdigit() and code[:2] == group_code
        }
        sequence = 1
        if used:
            sequence = max(used) + 1
        while sequence in used:
            sequence += 1
        if sequence > 99:
            raise UserError(
                _('No available ledger sequence for group %(group)s in %(company)s.')
                % {'group': group_code, 'company': account.company_id.display_name}
            )
        candidate = '%s%02d' % (group_code, sequence)
        while self.env['account.account'].sudo().search_count([
            ('company_id', '=', account.company_id.id),
            ('code', '=', candidate),
            ('id', 'not in', list(exclude_account_ids or []) + [account.id]),
        ]) or candidate in reserved_codes:
            sequence += 1
            if sequence > 99:
                raise UserError(_('No unique ledger code available for this type and company.'))
            candidate = '%s%02d' % (group_code, sequence)
        return candidate

    @api.model
    def suggest_ledger_code_for_account(self, account):
        if self.ledger_code_is_valid(account):
            return (account.code or '').strip()
        return self.allocate_next_ledger_code(account)

    @api.model
    def _group_skip_context(self):
        return dict(
            cpabooks_skip_group_prefix_constraint=True,
            skip_prefix_constraint=True,
        )

    @api.model
    def _account_count_for_group(self, group_id):
        if not group_id:
            return 0
        self.env.cr.execute(
            "SELECT COUNT(*) FROM account_account WHERE group_id = %s",
            (group_id,),
        )
        return self.env.cr.fetchone()[0]

    @api.model
    def _reassign_all_accounts_from_group(self, group_from, group_to):
        if not group_from or not group_to or group_from == group_to:
            return 0
        Account = self.env['account.account'].sudo().with_context(active_test=False)
        ctx = self._group_skip_context()
        accounts = Account.search([('group_id', '=', group_from.id)])
        if not accounts:
            return 0
        accounts.with_context(**ctx).write({'group_id': group_to.id})
        Account.flush(['group_id'])
        return len(accounts)

    @api.model
    def _safe_unlink_account_group(self, group, reassign_to=None):
        """Unlink account.group only when no account.account row references it."""
        group = group.exists()
        if not group:
            return False
        if reassign_to:
            self._reassign_all_accounts_from_group(group, reassign_to)
        if self._account_count_for_group(group.id):
            _logger.info(
                'Skip unlink account.group %s (%s): still linked to account(s)',
                group.id,
                group.display_name,
            )
            return False
        ctx = self._group_skip_context()
        try:
            with self.env.cr.savepoint():
                group.with_context(**ctx).unlink()
            return True
        except Exception:
            _logger.exception(
                'Could not unlink account.group %s (%s)',
                group.id,
                group.display_name,
            )
            return False

    @api.model
    def _get_or_create_ifrs_group(self, company, two_digit_code, label):
        Group = self.env['account.group'].sudo()
        group_name = self._normalize_group_label(two_digit_code, label)
        code_domain = [
            ('company_id', '=', company.id),
            ('code_prefix_start', '=', two_digit_code),
            ('code_prefix_end', '=', two_digit_code),
        ]
        groups = Group.search(code_domain)
        ctx = self._group_skip_context()
        if groups:
            group = groups.filtered(
                lambda rec: self._normalize_group_label(two_digit_code, rec.name) == group_name
            )[:1] or groups[:1]
            if group.name != group_name:
                group.with_context(**ctx).write({'name': group_name})
            return group

        same_name_groups = Group.search([('company_id', '=', company.id)])
        group = same_name_groups.filtered(
            lambda rec: self._normalize_group_label(
                rec.code_prefix_start or rec.code_prefix_end or two_digit_code, rec.name,
            ) == group_name
        )[:1]
        if group:
            values = {}
            if group.code_prefix_start != two_digit_code:
                values['code_prefix_start'] = two_digit_code
            if group.code_prefix_end != two_digit_code:
                values['code_prefix_end'] = two_digit_code
            if values:
                group.with_context(**ctx).write(values)
            return group

        return Group.with_context(**ctx).create({
            'name': group_name,
            'code_prefix_start': two_digit_code,
            'code_prefix_end': two_digit_code,
            'company_id': company.id,
        })

    @api.model
    def sync_ifrs_groups_for_accounts(self, accounts):
        accounts = accounts.exists().filtered('company_id')
        if not accounts:
            return 0
        plan = self.build_ifrs_two_digit_group_plan(accounts)
        linked_group_ids = set()
        for account in accounts:
            info = plan.get(account.id)
            if not info:
                info = {
                    'code': IFRS_UNALLOCATED_GROUP_CODE,
                    'label': IFRS_UNALLOCATED_GROUP_LABEL,
                    'display_name': self.ifrs_group_display_name(
                        IFRS_UNALLOCATED_GROUP_CODE, IFRS_UNALLOCATED_GROUP_LABEL,
                    ),
                }
            group = self._get_or_create_ifrs_group(
                account.company_id, info['code'], info['label'],
            )
            if account.group_id != group:
                account.with_context(cpabooks_skip_ifrs_name_wizard=True).write({
                    'group_id': group.id,
                })
            linked_group_ids.add(group.id)

        company_ids = accounts.mapped('company_id').ids
        self._deduplicate_ifrs_groups(company_ids)
        self.repair_ifrs_group_names(company_ids)
        self._cleanup_orphan_non_ifrs_groups(
            company_ids, keep_group_ids=linked_group_ids,
        )
        return len(linked_group_ids)

    @api.model
    def _deduplicate_ifrs_groups(self, company_ids):
        Group = self.env['account.group'].sudo()
        domain = [('company_id', 'in', company_ids)] if company_ids else []
        buckets = defaultdict(list)
        for group in Group.search(domain, order='company_id, code_prefix_start, id'):
            code = (group.code_prefix_start or group.code_prefix_end or '').strip()
            if len(code) != 2 or not code.isdigit():
                continue
            key = (
                group.company_id.id,
                code,
                self._normalize_group_label(code, group.name).lower(),
            )
            buckets[key].append(group)
        for groups in buckets.values():
            if len(groups) < 2:
                continue
            keep = groups[0]
            for duplicate in groups[1:]:
                self._reassign_all_accounts_from_group(duplicate, keep)
                self._safe_unlink_account_group(duplicate)

    @api.model
    def _reassign_accounts_on_legacy_groups(self, company_ids):
        Account = self.env['account.account'].sudo()
        domain = [('company_id', 'in', company_ids)] if company_ids else []
        legacy_accounts = Account.search(domain).filtered(
            lambda acc: not acc.group_id
            or len((acc.group_id.code_prefix_start or '').strip()) != 2
            or not (acc.group_id.code_prefix_start or '').strip().isdigit()
        )
        if legacy_accounts:
            self.sync_ifrs_groups_for_accounts(legacy_accounts)

    @api.model
    def _cleanup_orphan_non_ifrs_groups(self, company_ids, keep_group_ids=None):
        """Remove empty legacy groups that are not 2-digit IFRS groups."""
        self._reassign_accounts_on_legacy_groups(company_ids)
        Group = self.env['account.group'].sudo()
        keep_group_ids = set(keep_group_ids or [])
        domain = [('company_id', 'in', company_ids)] if company_ids else []
        for group in Group.search(domain):
            if group.id in keep_group_ids:
                continue
            start = (group.code_prefix_start or '').strip()
            if len(start) == 2 and start.isdigit():
                continue
            if self._account_count_for_group(group.id):
                continue
            self._safe_unlink_account_group(group)

    @api.model
    def assign_ifrs_codes_for_accounts(self, accounts, force=False):
        """Assign L3 ledger codes only when missing/invalid (never when group changes)."""
        accounts = accounts.exists().filtered('company_id')
        if not accounts:
            return 0
        updated = 0
        skip = dict(cpabooks_skip_ifrs_name_wizard=True)
        for account in accounts:
            if not force and self.ledger_code_is_valid(account):
                continue
            new_code = self.allocate_next_ledger_code(account)
            old_code = (account.code or '').strip()
            if old_code == new_code:
                continue
            vals = {'code': new_code}
            if (
                'cpabooks_previous_code' in account._fields
                and old_code
                and old_code != new_code
                and not self.is_temp_ifrs_code(old_code)
                and not account.cpabooks_previous_code
            ):
                vals['cpabooks_previous_code'] = old_code
            account.with_context(**skip).write(vals)
            if old_code != new_code:
                account._cpabooks_log_ifrs_code_change(old_code, new_code)
            updated += 1
        return updated

    @api.model
    def recover_stuck_temp_ifrs_codes(self, accounts=None):
        Account = self.env['account.account'].sudo()
        if accounts is None:
            domain = ['|', '|']
            domain.extend(
                ('code', '=like', '%s%%' % marker) for marker in IFRS_TEMP_CODE_MARKERS
            )
            accounts = Account.search(domain)
        else:
            accounts = accounts.filtered(
                lambda rec: self.is_temp_ifrs_code(rec.code),
            )
        if not accounts:
            return 0
        return self.assign_ifrs_codes_for_accounts(accounts)

    @api.model
    def setup_ifrs_for_accounts(self, accounts, force_code=False):
        """Set missing codes only; never overwrite a user-entered ledger code."""
        accounts = accounts.exists()
        self.recover_stuck_temp_ifrs_codes(accounts.filtered(
            lambda rec: self.is_temp_ifrs_code(rec.code),
        ))
        code_accounts = accounts
        if not force_code:
            # Preserve any existing code (4/6 digit, dashed, duplicate — user choice).
            # Only auto-fill when code is blank or a stuck TEMP placeholder.
            code_accounts = accounts.filtered(
                lambda rec: not (rec.code or '').strip() or self.is_temp_ifrs_code(rec.code)
            )
        self.assign_ifrs_codes_for_accounts(code_accounts, force=force_code)
        self.sync_ifrs_groups_for_accounts(accounts)
        return len(accounts)

    @api.model
    def migrate_coa_structure_all_companies(self):
        """Silent migration: reassign legacy groups, sync IFRS groups, fix invalid codes."""
        companies = self.env['res.company'].sudo().search([])
        accounts = self.env['account.account'].sudo().search([
            ('company_id', 'in', companies.ids),
        ])
        self._reassign_accounts_on_legacy_groups(companies.ids)
        self.assign_ifrs_codes_for_accounts(
            accounts.filtered(lambda acc: not self.ledger_code_is_valid(acc)),
        )
        self.sync_ifrs_groups_for_accounts(accounts)
        self.repair_ifrs_group_names(companies.ids)
        Group = self.env['account.group'].sudo()
        for company in companies:
            keep_ids = set(Group.search([
                ('company_id', '=', company.id),
            ]).filtered(
                lambda g: len((g.code_prefix_start or '').strip()) == 2
                and (g.code_prefix_start or '').strip().isdigit()
            ).ids)
            self._cleanup_orphan_non_ifrs_groups(
                [company.id], keep_group_ids=keep_ids,
            )
        return len(accounts)

    @api.model
    def format_xxxc_code(self, base_num, branch_digit=None):
        """Legacy wrapper: ledger code is now group code + sequence; BC is separate."""
        text = str(base_num or '').strip()
        if len(text) >= 4 and text[-4:].isdigit():
            return text[-4:]
        if len(text) >= 2 and text[-2:].isdigit():
            return '%s01' % text[-2:]
        return ''

    @api.model
    def build_account_code_plan(self, accounts, branch_companies, force_regenerate=False):
        """L3-LC plan: L2 group code + 2-digit ledger sequence; company is separate."""
        if hasattr(branch_companies, 'mapped'):
            branch_companies = self.branch_companies_for_accounts(
                accounts, preferred_company_ids=branch_companies.ids,
            )
        plan = {}
        issues = {}
        assigned_account_ids = defaultdict(set)
        assigned_codes = defaultdict(set)

        for account in accounts.filtered(lambda rec: rec.company_id in branch_companies).sorted(
            lambda rec: (
                rec.company_id.id,
                (self.resolve_l2_group(rec).get('code') or ''),
                rec.id,
            )
        ):
            group_code = (self.resolve_l2_group(account).get('code') or '').strip()
            if (
                not force_regenerate
                and self.ledger_code_is_valid(account)
                and (account.code or '').strip() not in assigned_codes[account.company_id.id]
            ):
                plan[account.id] = (account.code or '').strip()
                assigned_codes[account.company_id.id].add((account.code or '').strip())
                issues[account.id] = 'ok'
                continue
            if len(group_code) != 2 or not group_code.isdigit():
                issues[account.id] = 'name_review'
                continue
            try:
                proposed = self.allocate_group_based_ledger_code(
                    account,
                    exclude_account_ids=assigned_account_ids[(account.company_id.id, group_code)],
                    reserved_codes=assigned_codes[account.company_id.id],
                )
            except UserError:
                issues[account.id] = 'name_review'
                continue
            assigned_account_ids[(account.company_id.id, group_code)].add(account.id)
            assigned_codes[account.company_id.id].add(proposed)
            plan[account.id] = proposed
            issue = 'code_change' if (account.code or '').strip() != proposed else 'ok'
            if self.name_needs_ifrs_review(account.name):
                issue = 'code_change_name_review' if issue == 'code_change' else 'name_review'
            issues[account.id] = issue
        return plan, issues

    @api.model
    def build_group_code_plan(self, groups, branch_companies):
        """Legacy wrapper — maps group.id → 2-digit IFRS group code."""
        accounts = self.env['account.account'].search([('group_id', 'in', groups.ids)])
        account_plan = self.build_ifrs_two_digit_group_plan(accounts)
        plan = {}
        for group in groups:
            sample = accounts.filtered(lambda rec: rec.group_id == group)[:1]
            if sample and sample.id in account_plan:
                plan[group.id] = account_plan[sample.id]['code']
        return plan

    @api.model
    def preview_lines(self, accounts, branch_companies, update_groups=False, force_regenerate=False):
        if hasattr(branch_companies, 'ids'):
            branch_company_ids = branch_companies.ids
        else:
            branch_company_ids = branch_companies or []
        branch_companies = self.branch_companies_for_accounts(
            accounts, preferred_company_ids=branch_company_ids or None,
        )
        code_plan, issues = self.build_account_code_plan(
            accounts, branch_companies, force_regenerate=force_regenerate,
        )
        digit_map = self.branch_company_digit_map(branch_companies)
        ifrs_group_plan = self.build_ifrs_two_digit_group_plan(accounts)

        lines = []
        for account in accounts.filtered(lambda rec: rec.company_id in branch_companies).sorted(
            lambda rec: (rec.company_id.name or '', rec.code or '', rec.name or '', rec.id)
        ):
            proposed_code = code_plan.get(account.id, account.code)
            display_code = self.effective_ledger_code(account) or (account.code or '')
            needs_name = self.name_needs_ifrs_review(account.name)
            suggested = self.suggest_ifrs_name(account) if needs_name else ''
            group = account.group_id
            group_info = ifrs_group_plan.get(account.id, {})
            proposed_group_code = group_info.get('code', '')
            lines.append({
                'account_id': account.id,
                'group_id': group.id if group else False,
                'current_code': display_code,
                'proposed_code': proposed_code,
                'branch_digit': digit_map.get(account.company_id.id, ''),
                'branch_code': 'BC%s' % digit_map.get(account.company_id.id, ''),
                'name': account.name,
                'company_id': account.company_id.id,
                'user_type_id': account.user_type_id.id,
                'bs_pl': self.ledger_bs_pl(account),
                'ifrs_group_name': group.name if group else '',
                'proposed_group_name': group_info.get('display_name') or self.proposed_group_name(account),
                'proposed_group_code': proposed_group_code,
                'proposed_series_code': proposed_group_code * 2 if proposed_group_code else '',
                'name_needs_review': needs_name,
                'suggested_name': suggested,
                'previous_name': account.cpabooks_previous_name if 'cpabooks_previous_name' in account._fields else '',
                'issue': issues.get(account.id, 'ok'),
                'name_action': 'skip',
            })
        return lines

    @api.model
    def apply_plan(self, preview_lines, update_groups=False):
        accounts = preview_lines.mapped('account_id')
        skip = dict(
            cpabooks_skip_ifrs_name_wizard=True,
            cpabooks_ifrs_apply_approved=True,
        )

        for line in preview_lines:
            account = line.account_id.with_context(**skip)
            if line.name_action == 'accept' and line.suggested_name and line.name != line.suggested_name:
                vals = {'name': line.suggested_name}
                if 'cpabooks_previous_name' in account._fields:
                    vals['cpabooks_previous_name'] = line.name
                account.write(vals)
            elif line.name_action == 'edit' and line.edited_name:
                vals = {'name': line.edited_name}
                if 'cpabooks_previous_name' in account._fields and line.name != line.edited_name:
                    vals['cpabooks_previous_name'] = line.name
                account.write(vals)

        for line in preview_lines:
            account = line.account_id.with_context(**skip)
            proposed = (line.proposed_code or '').strip()
            if not proposed:
                continue
            old_code = (account.code or '').strip()
            if proposed == old_code or self.is_temp_ifrs_code(proposed):
                continue
            vals = {'code': proposed}
            if (
                'cpabooks_previous_code' in account._fields
                and old_code
                and old_code != proposed
                and not self.is_temp_ifrs_code(old_code)
                and not account.cpabooks_previous_code
            ):
                vals['cpabooks_previous_code'] = old_code
            account.write(vals)
            if old_code != proposed:
                account._cpabooks_log_ifrs_code_change(old_code, proposed)

        self.sync_ifrs_groups_for_accounts(accounts)
        return len(accounts)

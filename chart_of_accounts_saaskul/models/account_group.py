# -*- coding: utf-8 -*-
import csv
import os
import re

from odoo import api, fields, models
from odoo.osv import expression

# Account Groups screen kept on 2026-09-29. Reset and Factory restore this.
# 548 and 764 are the free +2 codes: 546 is Cost of Materials, 760 sits inside 756-760.
CPA_GROUP_PORTRAIT = (
    ('Cash & Cash Equivalents', '110', '110', 'AFG_CASH', 'current_assets', ''),
    ('Accounts Receivables', '112', '112', 'AFG_AR', 'nca_other', 'Other non-current assets (AED)'),
    ('Accounts Receivables - Others', '114', '114', 'AFG_AR', 'current_assets', ''),
    ('Deposits', '118', '118', 'AFG_PREP', 'current_assets', 'Total current assets (AED)'),
    ('Advance (Asset)', '120', '120', 'AFG_PREP', 'current_assets', 'Total current assets (AED)'),
    ('Inventories', '122', '122', 'AFG_INV', 'current_assets', 'Total current assets (AED)'),
    ('Prepaid Expenses', '124', '124', 'AFG_PREP', 'current_assets', 'Total current assets (AED)'),
    ('Fixed Asset', '126', '126', 'AFG_PPE', 'ppe', 'Property, plant and equipment (AED)'),
    ('Accounts Payable', '228', '228', 'AFG_AP', 'current_liab', 'Total current liabilities (AED)'),
    ('Tax Payable', '230', '230', 'AFG_AP', 'current_liab', 'Total current liabilities (AED)'),
    ('Loan (Liabilities)', '232', '232', 'AFG_AP', 'current_liab', 'Total current liabilities (AED)'),
    ('Employee Liabilities', '234', '234', 'AFG_AP', 'current_liab', ''),
    ('Provisions, Accruals & Other Payable', '236', '236', 'AFG_AP', 'current_liab', 'Total current liabilities (AED)'),
    ('Capital & Equities', '338', '338', 'AFG_EQ', 'other_equity', 'Other equity (AED)'),
    ('Sales Revenue', '440', '440', 'AFG_GNA', 'other_exp', ''),
    ('Other Income/ Exp', '442', '442', 'AFG_GNA', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Cost of Materials', '546', '546', 'AFG_COR', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Selling and Distribution Expenses', '548', '548', 'AFG_COR', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Employee CTC - Cash', '750', '750', 'AFG_PAYROLL', 'salaries', 'Salaries, wages and related charges (AED)'),
    ('Employee CTC - Directors', '752', '752', 'AFG_PAYROLL', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Employee CTC - Others', '754', '754', 'AFG_PAYROLL', 'salaries', ''),
    ('General & Admin Exp', '756', '760', 'AFG_EQ_CHG', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Vehicle Expenses', '762', '762', 'AFG_GNA', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Bad Debts Write Off', '764', '764', 'AFG_GNA', 'cogs', 'Expenditure incurred in deriving operating revenue (AED)'),
    ('Depreciations', '864', '864', 'AFG_DEPR_PL', 'depreciation', 'Depreciation and amortisation (AED)'),
    ('Income Taxes', '968', '968', 'AFG_GNA', 'cogs', ''),
)

# COA setup type_revise, folded into the order used on the Account Groups list.
CPA_GROUP_SECTION = {
    'Sales Revenue': '1_sales',
    'Other Income/ Exp': '1_sales',
    'Cost of Materials': '2_cost',
    'Selling and Distribution Expenses': '2_cost',
    'Employee CTC - Cash': '3_expense',
    'Employee CTC - Directors': '3_expense',
    'Employee CTC - Others': '3_expense',
    'General & Admin Exp': '3_expense',
    'Vehicle Expenses': '3_expense',
    'Bad Debts Write Off': '3_expense',
    'Depreciations': '3_expense',
    'Income Taxes': '3_expense',
    'Cash & Cash Equivalents': '4_assets',
    'Accounts Receivables': '4_assets',
    'Accounts Receivables - Others': '4_assets',
    'Deposits': '4_assets',
    'Advance (Asset)': '4_assets',
    'Inventories': '4_assets',
    'Prepaid Expenses': '4_assets',
    'Fixed Asset': '4_assets',
    'Accounts Payable': '5_liabilities',
    'Tax Payable': '5_liabilities',
    'Loan (Liabilities)': '5_liabilities',
    'Employee Liabilities': '5_liabilities',
    'Provisions, Accruals & Other Payable': '5_liabilities',
    'Capital & Equities': '6_equity',
}


class AccountGroup(models.Model):
    _inherit = 'account.group'

    def name_get(self):
        """Clubbed chart rows show the group name only. The code stays in Group Code."""
        result = []
        for group in self:
            name = (group.name or '').strip()
            prefix = (group.code_prefix_start or '').strip()
            if prefix and name.startswith(prefix):
                name = name[len(prefix):].lstrip(' -')
            result.append((group.id, name or group.name or ''))
        return result

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        """Switcher companies only. Super-admin skips ir.rules, so the same group name showed once per company."""
        args = list(args or [])
        if not self.env.su and not self.env.context.get('cpabooks_group_all_companies'):
            company_ids = []
            for cid in (self.env.context.get('allowed_company_ids') or self.env.companies.ids):
                try:
                    company_ids.append(int(cid))
                except (TypeError, ValueError):
                    continue
            if company_ids:
                args = expression.AND([args, [('company_id', 'in', company_ids)]])
        return super(AccountGroup, self)._search(
            args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid,
        )

    def _cpabooks_should_skip_prefix_overlap(self):
        ctx = self.env.context
        if ctx.get('cpabooks_skip_group_prefix_constraint') or ctx.get(
            'skip_prefix_constraint',
        ):
            return True
        # l10n_qa account.group.csv reload clashes with CPABooks IFRS groups on KCS DBs.
        if ctx.get('install_module') == 'l10n_qa':
            return True
        install_fn = (ctx.get('install_filename') or '').replace('\\', '/')
        if ctx.get('module') == 'l10n_qa' and 'account.group' in install_fn:
            return True
        return False

    def _cpabooks_with_skip_prefix_overlap(self):
        if self._cpabooks_should_skip_prefix_overlap():
            return self.with_context(cpabooks_skip_group_prefix_constraint=True)
        return self

    @api.model_create_multi
    def create(self, vals_list):
        return super(
            AccountGroup, self._cpabooks_with_skip_prefix_overlap(),
        ).create(vals_list)

    def write(self, vals):
        return super(
            AccountGroup, self._cpabooks_with_skip_prefix_overlap(),
        ).write(vals)

    def _adapt_parent_account_group(self):
        """Rebuild group parents without Odoo's whole-company parent_path check.

        Core calls ``_parent_store_update`` on every group in the company. That
        check treats the first child's ancestors as a cycle and raises
        Recursion Detected on Reset Groups.
        """
        if self.env.context.get('cpabooks_skip_parent_rebuild') or not self:
            return
        for company in self.mapped("company_id"):
            self._cpa_rebuild_group_parents(company)

    def _cpa_rebuild_group_parents(self, company):
        cr = self.env.cr
        self.env["account.group"].flush()
        cr.execute(
            """
            UPDATE account_group agroup SET parent_id = (
                SELECT parent.id FROM account_group parent
                WHERE char_length(parent.code_prefix_start) < char_length(agroup.code_prefix_start)
                AND parent.code_prefix_start <= LEFT(agroup.code_prefix_start, char_length(parent.code_prefix_start))
                AND parent.code_prefix_end >= LEFT(agroup.code_prefix_end, char_length(parent.code_prefix_end))
                AND parent.id != agroup.id
                AND parent.company_id = %(company_id)s
                ORDER BY char_length(parent.code_prefix_start) DESC LIMIT 1
            ) WHERE agroup.company_id = %(company_id)s
            """,
            {"company_id": company.id},
        )
        cr.execute(
            """
            UPDATE account_group
               SET parent_path = NULL
             WHERE company_id = %s
            """,
            (company.id,),
        )
        cr.execute(
            """
            UPDATE account_group
               SET parent_path = id::text || '/'
             WHERE company_id = %s
               AND parent_id IS NULL
            """,
            (company.id,),
        )
        for _index in range(30):
            cr.execute(
                """
                UPDATE account_group child
                   SET parent_path = parent.parent_path || child.id::text || '/'
                  FROM account_group parent
                 WHERE child.company_id = %s
                   AND child.parent_id = parent.id
                   AND parent.parent_path IS NOT NULL
                   AND child.parent_path IS NULL
                   AND strpos(parent.parent_path, '/' || child.id::text || '/') = 0
                """,
                (company.id,),
            )
            if not cr.rowcount:
                break
        cr.execute(
            """
            UPDATE account_group
               SET parent_id = NULL,
                   parent_path = id::text || '/'
             WHERE company_id = %s
               AND parent_path IS NULL
            """,
            (company.id,),
        )
        self.env["account.group"].invalidate_cache(fnames=["parent_id", "parent_path"])
        return True

    @api.constrains('code_prefix_start', 'code_prefix_end')
    def _constraint_prefix_overlap(self):
        if self._cpabooks_should_skip_prefix_overlap():
            return
        parent = getattr(super(AccountGroup, self), '_constraint_prefix_overlap', None)
        if parent:
            return parent()


    def _cpa_setup_catalog(self):
        """COA setup file is the only account-group list. Prefix steps by 2 from 110."""
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv',
        ))
        by_code = {}
        by_name = {}
        prefix_counts = {}
        name_prefixes = {}
        if not os.path.isfile(path):
            return by_code, by_name, {}, {}
        with open(path, mode='r', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                name = (row.get('group') or '').strip()
                if not name or name.lower() == 'unallocated group':
                    continue
                start = (row.get('From') or '').strip()
                code_auto = (row.get('code_auto') or '').strip()
                revise = (row.get('account_name_revise') or '').strip().lower()
                digits = re.sub(r'\D+', '', code_auto)
                if digits:
                    by_code[digits] = name
                if code_auto:
                    by_code[code_auto] = name
                if revise and revise != 'new':
                    by_name[revise] = name
                if start:
                    prefix_counts.setdefault(start, {})
                    prefix_counts[start][name] = prefix_counts[start].get(name, 0) + 1
                    name_prefixes.setdefault(name, set()).add(start)
        primary = {}
        for start, names in prefix_counts.items():
            primary[start] = max(names, key=names.get)
        spans = {}
        for name, prefixes in name_prefixes.items():
            ordered = sorted(prefixes)
            if not ordered:
                continue
            if (
                len(ordered) > 1
                and all(len(item) == len(ordered[0]) and item.isdigit() for item in ordered)
                and int(ordered[-1]) - int(ordered[0]) <= 4
                and all(primary.get(item) == name for item in ordered)
            ):
                spans[name] = (ordered[0], ordered[-1])
            else:
                owned = [item for item in ordered if primary.get(item) == name]
                if owned:
                    spans[name] = (owned[0], owned[0])
                else:
                    spans[name] = (False, False)
        for name, start, end, _afg, _ctf, _ctf_name in CPA_GROUP_PORTRAIT:
            spans[name] = (start, end)
        return by_code, by_name, spans, primary

    @api.model
    def _cpa_ensure_groups_on_all_companies(self):
        """Create the setup groups on every company. One name, one prefix."""
        Group = self.sudo().with_context(
            cpabooks_group_all_companies=True,
            skip_prefix_constraint=True,
            cpabooks_skip_group_prefix_constraint=True,
            cpabooks_skip_parent_rebuild=True,
            cpa_apply_setup_groups=True,
        )
        _by_code, _by_name, spans, _primary = self._cpa_setup_catalog()
        companies = self.env['res.company'].sudo().search([])
        created = 0
        for company in companies:
            for name, (start, end) in spans.items():
                found = Group.search([
                    ('company_id', '=', company.id),
                    ('name', '=', name),
                ], limit=1)
                vals = {
                    'name': name,
                    'code_prefix_start': start or False,
                    'code_prefix_end': end or start or False,
                    'cpa_coa_section': CPA_GROUP_SECTION.get(name) or False,
                }
                if 'cpabooks_all_companies' in Group._fields:
                    vals['cpabooks_all_companies'] = True
                if found:
                    to_write = {}
                    if found.code_prefix_start != vals['code_prefix_start']:
                        to_write['code_prefix_start'] = vals['code_prefix_start']
                    if found.code_prefix_end != vals['code_prefix_end']:
                        to_write['code_prefix_end'] = vals['code_prefix_end']
                    if vals.get('cpa_coa_section') and found.cpa_coa_section != vals['cpa_coa_section']:
                        to_write['cpa_coa_section'] = vals['cpa_coa_section']
                    if to_write:
                        found.write(to_write)
                    continue
                donor = Group.search([
                    ('name', '=', name),
                    ('company_id', '!=', company.id),
                ], limit=1)
                if donor and 'afg_group_id' in Group._fields and donor.afg_group_id:
                    afg = donor.afg_group_id
                    if not afg.company_id or afg.company_id.id == company.id:
                        vals['afg_group_id'] = afg.id
                if donor and 'ctf_group_id' in Group._fields and donor.ctf_group_id:
                    vals['ctf_group_id'] = donor.ctf_group_id.id
                if donor and 'ctf_category' in Group._fields and donor.ctf_category:
                    vals['ctf_category'] = donor.ctf_category
                vals['company_id'] = company.id
                Group.create(vals)
                created += 1
        self._cpa_apply_group_portrait_links()
        return created

    @api.model
    def _cpa_assign_ledgers_from_setup(self):
        """Point each ledger at the setup group. Ledger names stay as they are."""
        by_code, by_name, _spans, primary = self._cpa_setup_catalog()
        Account = self.env['account.account'].sudo().with_context(
            cpa_apply_setup_groups=True,
            cpabooks_skip_name_sync=True,
            afg_skip_same_name_sync=True,
        )
        Group = self.sudo().with_context(cpabooks_group_all_companies=True)
        cache = {}
        updated = 0
        for account in Account.search([]):
            digits = re.sub(r'\D+', '', account.code or '')
            group_name = by_code.get(account.code or '') or by_code.get(digits)
            if not group_name:
                group_name = by_name.get((account.name or '').strip().lower())
            if not group_name and len(digits) >= 3:
                group_name = primary.get(digits[:3])
            if not group_name:
                current = (account.group_id.name or '').strip().lower()
                if current == 'unallocated group':
                    account.write({'group_id': False})
                    updated += 1
                continue
            key = (account.company_id.id, group_name)
            group = cache.get(key)
            if group is None:
                group = Group.search([
                    ('company_id', '=', account.company_id.id),
                    ('name', '=', group_name),
                ], limit=1)
                cache[key] = group
            if group and account.group_id.id != group.id:
                account.write({'group_id': group.id})
                updated += 1
        return updated

    @api.model
    def _cpa_drop_extra_groups(self):
        """Unallocated and any group outside the setup list do not belong here."""
        _by_code, _by_name, spans, _primary = self._cpa_setup_catalog()
        allowed = set(spans)
        Group = self.sudo().with_context(
            cpabooks_group_all_companies=True,
            cpabooks_skip_parent_rebuild=True,
        )
        Account = self.env['account.account'].sudo().with_context(
            cpa_apply_setup_groups=True,
        )
        removed = 0
        companies = self.env['res.company'].sudo().search([])
        for company in companies:
            for name in allowed:
                found = Group.search([
                    ('company_id', '=', company.id),
                    ('name', '=', name),
                ])
                if len(found) < 2:
                    continue
                start = spans[name][0] or False
                ranked = sorted(
                    found,
                    key=lambda group: (
                        (group.code_prefix_start or False) == start,
                        Account.search_count([('group_id', '=', group.id)]),
                    ),
                    reverse=True,
                )
                keep = ranked[0]
                for extra in ranked[1:]:
                    Account.search([('group_id', '=', extra.id)]).write({'group_id': keep.id})
                    self.env.cr.execute(
                        "UPDATE account_group SET parent_id = NULL WHERE parent_id = %s OR id = %s",
                        (extra.id, extra.id),
                    )
                    extra.unlink()
                    removed += 1
        for group in list(Group.search([])):
            name = (group.name or '').strip()
            if name in allowed and name.lower() != 'unallocated group':
                continue
            Account.search([('group_id', '=', group.id)]).with_context(
                cpa_apply_setup_groups=True,
            ).write({'group_id': False})
            self.env.cr.execute(
                "UPDATE account_group SET parent_id = NULL WHERE parent_id = %s OR id = %s",
                (group.id, group.id),
            )
            group.unlink()
            removed += 1
        return removed

    def action_cpa_reset_account_groups(self):
        """Add missing setup groups and move ledgers onto them. Ledger names stay."""
        created = self._cpa_ensure_groups_on_all_companies()
        moved = self._cpa_assign_ledgers_from_setup()
        removed = self._cpa_drop_extra_groups()
        self._cpa_apply_group_portrait_links()
        self._cpa_mark_all_company_ticks()
        Group = self.sudo().with_context(cpabooks_skip_parent_rebuild=False, cpabooks_group_all_companies=True)
        Group.search([])._adapt_parent_account_group()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Reset Groups",
                "message": "Setup groups are on every company. Added %s, moved %s ledgers, removed %s extra groups. Ledger names were not changed." % (created, moved, removed),
                "type": "success",
                "sticky": False,
            },
        }

    def action_cpa_reset_account_groups_factory(self):
        """Erase every account group and rebuild the setup list."""
        Group = self.sudo().with_context(
            cpabooks_group_all_companies=True,
            cpabooks_skip_parent_rebuild=True,
            skip_prefix_constraint=True,
        )
        self.env.cr.execute("UPDATE account_account SET group_id = NULL")
        self.env.cr.execute("UPDATE account_group SET parent_id = NULL")
        Group.search([]).unlink()
        self.env['account.account'].invalidate_cache(fnames=['group_id'])
        created = self._cpa_ensure_groups_on_all_companies()
        moved = self._cpa_assign_ledgers_from_setup()
        self._cpa_apply_group_portrait_links()
        self._cpa_mark_all_company_ticks()
        Group.with_context(cpabooks_skip_parent_rebuild=False).search([])._adapt_parent_account_group()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Reset Groups (Factory)",
                "message": "Rebuilt %s setup groups and linked %s ledgers. Ledger names were not changed." % (created, moved),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def _cpa_mark_all_company_ticks(self):
        from odoo.tools.sql import column_exists

        cr = self.env.cr
        if column_exists(cr, 'account_group', 'cpabooks_all_companies'):
            cr.execute(
                """
                UPDATE account_group
                   SET cpabooks_all_companies = TRUE
                 WHERE cpabooks_all_companies IS DISTINCT FROM TRUE
                """
            )
        if 'afg_sync_same_name' in self.env['account.account']._fields:
            cr.execute(
                """
                UPDATE account_account
                   SET afg_sync_same_name = TRUE
                 WHERE afg_sync_same_name IS DISTINCT FROM TRUE
                """
            )
        if not column_exists(cr, 'account_account', 'cpabooks_sync_name_all_companies'):
            return
        cr.execute(
            """
            UPDATE account_account
               SET cpabooks_sync_name_all_companies = TRUE
             WHERE cpabooks_sync_name_all_companies IS DISTINCT FROM TRUE
            """
        )
        return True

    @api.model
    def _cpa_apply_group_portrait_links(self):
        """Put the saved AFG, CTFG and COA type back. Never write an empty value."""
        Group = self.sudo().with_context(
            cpabooks_group_all_companies=True,
            cpabooks_skip_parent_rebuild=True,
            cpa_skip_group_cross_company=True,
            skip_prefix_constraint=True,
        )
        has_afg = 'afg_group_id' in self._fields
        Afg = self.env['audited.financial.group'].sudo() if has_afg else None
        Ctf = self.env['audited.financial.ctf.group'].sudo() if 'ctf_group_id' in self._fields else None
        companies = self.env['res.company'].sudo().search([])
        for company in companies:
            for name, _start, _end, afg_code, ctf_cat, ctf_name in CPA_GROUP_PORTRAIT:
                group = Group.search([
                    ('company_id', '=', company.id),
                    ('name', '=', name),
                ], limit=1)
                if not group:
                    continue
                vals = {}
                if has_afg and afg_code:
                    afg = Afg.search([
                        ('code', '=', afg_code),
                        '|', ('company_id', '=', False), ('company_id', '=', company.id),
                    ], limit=1)
                    afg_id = False
                    if afg:
                        mapper = getattr(group, '_cpa_afg_id_for_company', None)
                        if mapper:
                            afg_id = mapper(afg, company)
                        elif not afg.company_id or afg.company_id.id == company.id:
                            afg_id = afg.id
                    if afg_id and group.afg_group_id.id != afg_id:
                        vals['afg_group_id'] = afg_id
                if (
                    ctf_cat
                    and 'ctf_category' in group._fields
                    and group.ctf_category != ctf_cat
                ):
                    vals['ctf_category'] = ctf_cat
                if ctf_name and Ctf is not None and 'ctf_group_id' in group._fields:
                    ctf = Ctf.search([('name', '=', ctf_name)], limit=1)
                    if ctf and group.ctf_group_id.id != ctf.id:
                        vals['ctf_group_id'] = ctf.id
                section = CPA_GROUP_SECTION.get(name)
                if (
                    section
                    and 'cpa_coa_section' in group._fields
                    and group.cpa_coa_section != section
                ):
                    vals['cpa_coa_section'] = section
                if vals:
                    group.with_context(cpa_skip_group_push=True).write(vals)
        return True

    cpa_coa_section = fields.Selection(
        [
            ('1_sales', 'Sales'),
            ('2_cost', 'Cost of Revenue'),
            ('3_expense', 'Expense'),
            ('4_assets', 'Assets'),
            ('5_liabilities', 'Liabilities'),
            ('6_equity', 'Equity'),
        ],
        string='COA Type',
        index=True,
        group_expand='_expand_cpa_coa_section',
    )

    def _expand_cpa_coa_section(self, sections, domain, order):
        return [key for key, _label in self._fields['cpa_coa_section'].selection]

    cpa_ctg_label = fields.Char(string="CTFG", compute="_compute_cpa_ctg_label")

    def _compute_cpa_ctg_label(self):
        selection = {}
        try:
            from odoo.addons.cpabooks_audited_financial.models.account_account import CTF_CATEGORY_SELECTION
            selection = dict(CTF_CATEGORY_SELECTION)
        except Exception:
            try:
                from odoo.addons.audited_financials_saaskul.models.account_account import CTF_CATEGORY_SELECTION
                selection = dict(CTF_CATEGORY_SELECTION)
            except Exception:
                selection = {}
        for group in self:
            value = group.ctf_category if "ctf_category" in group._fields else False
            if not value and "ctf_group_id" in group._fields and group.ctf_group_id:
                value = group.ctf_group_id.ctf_category
            group.cpa_ctg_label = selection.get(value, "") or ""

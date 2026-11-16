# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.sql import column_exists, create_column

from .audited_financials_presets import _account_match_code

_AFG_UNGRP_CODES = ("AFG_UNGRP_PL", "AFG_UNGRP_BS")

CTF_CATEGORY_SELECTION = [
    ("op_rev", "Operating Revenue"),
    ("cogs", "Expenditure incurred in deriving operating revenue"),
    ("salaries", "Salaries, wages and related charges"),
    ("depreciation", "Depreciation and amortisation"),
    ("fines", "Fines and Penalties"),
    ("donations", "Donations"),
    ("entertainment", "Client entertainment expenses"),
    ("other_exp", "Other expenses"),
    ("dividends", "Dividends received"),
    ("other_nor", "Other non-operating revenue"),
    ("interest_inc", "Interest Income"),
    ("interest_exp", "Interest Expenditure"),
    ("interest", "Net Interest Income / (Expense)"),
    ("disposal_gain", "Gains on Disposal of Assets"),
    ("disposal_loss", "Losses on Disposal of Assets"),
    ("disposal", "Net gains / (losses) on disposal of assets"),
    ("fx_gain", "Foreign exchange gains"),
    ("fx_loss", "Foreign exchange losses"),
    ("fx", "Net Gains/(losses) on foreign exchange"),
    ("tax", "Less: Corporate Tax"),
    ("ppe", "Property, plant and equipment"),
    ("intangible", "Intangible assets"),
    ("financial_nca", "Financial assets"),
    ("nca_other", "Other non-current assets"),
    ("current_assets", "Current Assets"),
    ("current_liab", "Total current liabilities"),
    ("ncl", "Total non-current liabilities"),
    ("share_capital", "Share capital"),
    ("retained_earnings", "Retained earnings"),
    ("other_equity", "Other equity"),
]

# Odoo 19 account types (selection) mirrored as records so AFG can still
# store a CT Filing / AFG group on a type. Community has no account.account.type.
AFG_ACCOUNT_TYPES = (
    # code, name, internal_group, legacy type, include_initial_balance
    ("asset_receivable", "Receivable", "asset", "receivable", True),
    ("asset_cash", "Bank and Cash", "asset", "liquidity", True),
    ("asset_current", "Current Assets", "asset", "other", True),
    ("asset_non_current", "Non-current Assets", "asset", "other", True),
    ("asset_prepayments", "Prepayments", "asset", "other", True),
    ("asset_fixed", "Fixed Assets", "asset", "other", True),
    ("liability_payable", "Payable", "liability", "payable", True),
    ("liability_credit_card", "Credit Card", "liability", "other", True),
    ("liability_current", "Current Liabilities", "liability", "other", True),
    ("liability_non_current", "Non-current Liabilities", "liability", "other", True),
    ("equity", "Equity", "equity", "other", True),
    ("equity_unaffected", "Current Year Earnings", "equity", "other", True),
    ("income", "Income", "income", "other", False),
    ("income_other", "Other Income", "income", "other", False),
    ("expense", "Expenses", "expense", "other", False),
    ("expense_depreciation", "Depreciation", "expense", "other", False),
    ("expense_direct_cost", "Cost of Revenue", "expense", "other", False),
    ("off_balance", "Off-Balance Sheet", "off", "other", False),
)


class AccountAccount(models.Model):
    _inherit = "account.account"

    afg_group_id = fields.Many2one(
        "audited.financial.group",
        string="AFG group",
        compute="_compute_afg_group_id",
        inverse="_inverse_afg_group_id",
        store=True,
        readonly=False,
        help="Maps this ledger on Audited Financials. Empty = ungrouped / needs review.",
        domain="[('code', 'not in', ['AFG_UNGRP_PL', 'AFG_UNGRP_BS']),"
               " '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    ctf_category = fields.Selection(
        CTF_CATEGORY_SELECTION,
        string="CT Filing",
        help="Corporate Tax Filing (FTA) category for this ledger. "
             "Used on Audited Financials → CORPORATE TAX FILING- FTA.",
    )
    afg_sync_same_name = fields.Boolean(
        string="All companies",
        default=True,
        help="Ticked: saving this ledger also updates the same ledger in every "
             "other company (name, account group, AFG, CTFG, account type). "
             "Unticked: this company only.",
    )
    # Odoo 19 dropped company_id / user_type_id / deprecated. These fields keep
    # the AFG mapping code working on a shared chart (company_ids + account_type).
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        compute="_compute_afg_company_id",
        search="_search_afg_company_id",
    )
    user_type_id = fields.Many2one(
        "account.account.type",
        string="AFG account type",
        compute="_compute_afg_user_type_id",
        inverse="_inverse_afg_user_type_id",
        store=True,
        readonly=False,
    )
    deprecated = fields.Boolean(
        string="Deprecated",
        compute="_compute_afg_deprecated",
        inverse="_inverse_afg_deprecated",
        store=True,
    )

    @api.depends("company_ids")
    @api.depends_context("allowed_company_ids", "company")
    def _compute_afg_company_id(self):
        current = self.env.company
        for acc in self:
            companies = acc.company_ids
            if current and current in companies:
                acc.company_id = current
            elif companies:
                acc.company_id = companies[0]
            else:
                acc.company_id = False

    def _search_afg_company_id(self, operator, value):
        return [("company_ids", operator, value)]

    # Core group_id is computed from the code prefix and not searchable; AFG
    # filters ledgers by account group, so match on the computed value.
    group_id = fields.Many2one(search="_search_afg_group_id")

    def _search_afg_group_id(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            raise UserError("Unsupported operator %s on account group." % operator)
        if hasattr(value, "ids"):
            values = list(value.ids) or [False]
        elif value is None or isinstance(value, (bool, int, str)):
            values = [value]
        else:
            values = list(value)
        group_ids = {int(v) for v in values if v}
        want_empty = any(not v for v in values)
        accounts = self.with_context(active_test=False, afg_unique_ledgers=False).search([])
        matched = accounts.filtered(
            lambda a: (a.group_id.id in group_ids) if a.group_id else want_empty
        )
        return [("id", "in" if operator in ("=", "in") else "not in", matched.ids)]

    @api.depends("account_type")
    def _compute_afg_user_type_id(self):
        Type = self.env["account.account.type"].sudo()
        Type._afg_ensure_standard_types()
        by_code = {t.code: t for t in Type.search([])}
        for acc in self:
            acc.user_type_id = by_code.get(acc.account_type, Type).id if acc.account_type in by_code else False

    def _inverse_afg_user_type_id(self):
        for acc in self:
            code = acc.user_type_id.code
            if code and acc.account_type != code:
                acc.account_type = code

    @api.depends("active")
    def _compute_afg_deprecated(self):
        for acc in self:
            acc.deprecated = not acc.active

    def _inverse_afg_deprecated(self):
        for acc in self:
            acc.active = not acc.deprecated

    def _auto_init(self):
        cr = self.env.cr
        if not column_exists(cr, "account_account", "ctf_category"):
            create_column(cr, "account_account", "ctf_category", "varchar")
        if not column_exists(cr, "account_account", "afg_group_id"):
            create_column(cr, "account_account", "afg_group_id", "int4")
        if not column_exists(cr, "account_account", "afg_sync_same_name"):
            create_column(cr, "account_account", "afg_sync_same_name", "boolean")
            cr.execute(
                "UPDATE account_account SET afg_sync_same_name = TRUE WHERE afg_sync_same_name IS NULL"
            )
        return super()._auto_init()

    def _afg_mapping_lines(self):
        self.ensure_one()
        return self.env["audited.financial.group.line"].with_context(
            afg_skip_collapse=True
        ).search([("account_id", "=", self.id)])

    def _afg_suggested_group(self):
        """Preset match when we are sure (not Ungrouped)."""
        self.ensure_one()
        code = _account_match_code(self)
        if not code or code in _AFG_UNGRP_CODES:
            return self.env["audited.financial.group"]
        Group = self.env["audited.financial.group"]
        grp = Group.search([("code", "=", code), ("company_id", "=", False)], limit=1)
        return grp or Group.search([("code", "=", code)], limit=1)

    def _afg_real_group_lines(self, accounts):
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        if not accounts:
            return Line.browse()
        lines = Line.search([("account_id", "in", accounts.ids)])
        return lines.filtered(lambda l: (l.group_id.code or "") not in _AFG_UNGRP_CODES)

    def _compute_afg_group_id(self):
        for acc in self:
            real = acc._afg_real_group_lines(acc)
            if not real and acc.afg_sync_same_name:
                real = acc._afg_real_group_lines(acc._afg_same_name_peers())
            if real:
                acc.afg_group_id = real[0].group_id
            else:
                acc.afg_group_id = acc._afg_suggested_group()

    def _inverse_afg_group_id(self):
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        Version = self.env["audited.financial.version"]
        Account = self.env["account.account"]
        for acc in self:
            peers = acc
            if acc.afg_sync_same_name and not self.env.context.get("afg_skip_same_name_sync"):
                peers |= acc._afg_same_name_peers()
            Line.search([("account_id", "in", peers.ids)]).unlink()
            grp = acc.afg_group_id
            if grp:
                for peer in peers:
                    Line.create({"group_id": grp.id, "account_id": peer.id})
        Version._afg_rebuild_after_coa_map(self)


    def _afg_same_name_peers(self):
        """Other companies' ledgers with this same unique ledger name."""
        self.ensure_one()
        Version = self.env["audited.financial.version"]
        key = Version._afg_pl_unique_ledger_key(self)
        if not key:
            return self.browse()
        Account = self.env["account.account"].sudo()
        peers = Account.browse()
        for other in Account.search([("id", "!=", self.id), ("name", "ilike", key)]):
            if Version._afg_pl_unique_ledger_key(other) == key:
                peers |= other
        return peers

    def _afg_group_for_company(self, group, company):
        if not group:
            return False
        if not company or not group.company_id or group.company_id.id == company.id:
            return group.id
        Group = self.env["account.group"].sudo()
        found = Group.search([
            ("company_id", "=", company.id),
            ("name", "=", group.name),
        ], limit=1)
        if not found and group.code_prefix_start:
            found = Group.search([
                ("company_id", "=", company.id),
                ("code_prefix_start", "=", group.code_prefix_start),
            ], limit=1)
        return found.id or False

    def _cpa_type_ctf_category(self, user_type):
        """CT Filing category stored on the account type. Empty when the type has no CTF."""
        group = user_type.ctf_group_id if user_type else False
        if not group:
            return False
        return group.ctf_category or False

    def _cpa_group_ctf_category(self, account_group):
        group = account_group.ctf_group_id if account_group else False
        if not group:
            return False
        return group.ctf_category or False

    def _cpa_forced_ctf_category(self, user_type, account_group):
        """Type CTF wins. Account group CTF applies when the type has none."""
        return self._cpa_type_ctf_category(user_type) or self._cpa_group_ctf_category(account_group)

    @api.model
    def _cpa_apply_saved_ctf(self):
        """Copy CTF already saved on types and account groups onto their ledgers.

        Account group first, then type, so a type allocation replaces the group.
        """
        # group_id is computed from the code prefix in Odoo 19 (not a column).
        Account = self.sudo().with_context(active_test=False, afg_skip_same_name_sync=True, cpa_skip_type_ctf=True)
        for acc in Account.search([]):
            cat = acc._cpa_group_ctf_category(acc.group_id)
            if cat and acc.ctf_category != cat:
                acc.write({"ctf_category": cat})
        cr = self.env.cr
        cr.execute(
            """
            UPDATE account_group ag
               SET ctf_category = cg.ctf_category
              FROM audited_financial_ctf_group cg
             WHERE cg.id = ag.ctf_group_id
               AND cg.ctf_category IS NOT NULL
               AND ag.ctf_category IS DISTINCT FROM cg.ctf_category
            """
        )
        cr.execute(
            """
            UPDATE account_account aa
               SET ctf_category = cg.ctf_category
              FROM account_account_type t
              JOIN audited_financial_ctf_group cg ON cg.id = t.ctf_group_id
             WHERE aa.user_type_id = t.id
               AND cg.ctf_category IS NOT NULL
               AND aa.ctf_category IS DISTINCT FROM cg.ctf_category
            """
        )
        cr.execute(
            """
            UPDATE account_account_type t
               SET ctf_category = cg.ctf_category
              FROM audited_financial_ctf_group cg
             WHERE cg.id = t.ctf_group_id
               AND cg.ctf_category IS NOT NULL
               AND t.ctf_category IS DISTINCT FROM cg.ctf_category
            """
        )
        self.invalidate_recordset(fnames=["ctf_category"])
        return True

    @api.model_create_multi
    def create(self, vals_list):
        Type = self.env["account.account.type"]
        Type._afg_ensure_standard_types()
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            # Odoo 19 derives account.group from the code prefix.
            vals.pop("group_id", None)
            type_id = vals.get("user_type_id")
            if type_id:
                user_type = Type.browse(type_id)
                if user_type.code and not vals.get("account_type"):
                    vals["account_type"] = user_type.code
                if user_type.afg_group_id and not vals.get("afg_group_id"):
                    vals["afg_group_id"] = user_type.afg_group_id.id
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        vals.pop("group_id", None)
        # A type that already has an AFG covers every ledger moved onto that type.
        if vals.get("user_type_id") and "afg_group_id" not in vals:
            user_type = self.env["account.account.type"].browse(vals["user_type_id"])
            if user_type.afg_group_id:
                vals = dict(vals, afg_group_id=user_type.afg_group_id.id)
        # Type CTF wins. If the type has none, the account group CTF wins.
        # Only when type or group changed. Every other save was rewriting CTF
        # and copying it to the same ledger in every company.
        if (
            not self.env.context.get("cpa_skip_type_ctf")
            and self
            and {"user_type_id", "group_id"} & set(vals)
        ):
            Type = self.env["account.account.type"]
            Group = self.env["account.group"]
            buckets = {}
            free = self.browse()
            for acc in self:
                if "user_type_id" in vals:
                    ut = Type.browse(vals["user_type_id"]) if vals.get("user_type_id") else Type
                else:
                    ut = acc.user_type_id
                if "group_id" in vals:
                    ag = Group.browse(vals["group_id"]) if vals.get("group_id") else Group
                else:
                    ag = acc.group_id
                cat = acc._cpa_forced_ctf_category(ut, ag)
                if cat:
                    buckets.setdefault(cat, self.browse())
                    buckets[cat] |= acc
                else:
                    free |= acc
            if buckets:
                res = True
                if free:
                    res = free.with_context(cpa_skip_type_ctf=True).write(vals) and res
                for cat, accs in buckets.items():
                    payload = dict(vals)
                    payload["ctf_category"] = cat
                    res = accs.with_context(cpa_skip_type_ctf=True).write(payload) and res
                return res
        sync_keys = {"ctf_category", "group_id", "user_type_id"} & set(vals)
        res = super(AccountAccount, self).write(vals)
        if not sync_keys or self.env.context.get("afg_skip_same_name_sync"):
            return res
        for acc in self:
            if not acc.afg_sync_same_name:
                continue
            peers = acc._afg_same_name_peers()
            if not peers:
                continue
            for peer in peers:
                payload = {}
                if "ctf_category" in vals:
                    payload["ctf_category"] = vals["ctf_category"]
                if "user_type_id" in vals:
                    payload["user_type_id"] = vals["user_type_id"]
                if "group_id" in vals:
                    grp = self.env["account.group"].browse(vals["group_id"]) if vals["group_id"] else False
                    payload["group_id"] = acc._afg_group_for_company(grp, peer.company_id)
                if payload:
                    peer.sudo().with_context(afg_skip_same_name_sync=True).write(payload)
        return res

    def _afg_dedupe_unique_ledgers(self):
        """One CoA row per unique ledger name; prefer the current company."""
        Version = self.env["audited.financial.version"]
        prefer = self.env.company.id if self.env.company else False
        by_key = {}
        for acc in self:
            key = Version._afg_pl_unique_ledger_key(acc) or ("id:%s" % acc.id)
            prev = by_key.get(key)
            if not prev:
                by_key[key] = acc
                continue
            if prefer and acc.company_id.id == prefer and prev.company_id.id != prefer:
                by_key[key] = acc
        return self.browse([a.id for a in by_key.values()])

    def _afg_unique_ledger_label(self):
        self.ensure_one()
        Version = self.env["audited.financial.version"]
        label = (self.name or "").strip()
        label = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", label)
        return label or Version._afg_pl_unique_ledger_key(self) or self.code or str(self.id)

    @api.depends("name", "code")
    @api.depends_context("afg_unique_ledgers")
    def _compute_display_name(self):
        if not self.env.context.get("afg_unique_ledgers"):
            return super()._compute_display_name()
        for acc in self:
            acc.display_name = acc._afg_unique_ledger_label()

    def _afg_map_company_domain(self):
        # Switcher cids only. Never fall back to user.company_ids (all companies).
        ctx_cids = self.env.context.get("allowed_company_ids") or []
        cids = [int(x) for x in ctx_cids if x]
        if not cids and self.env.company:
            cids = [self.env.company.id]
        if cids and "company_id" in self._fields:
            return [("company_id", "in", cids)]
        return []

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        domain = list(domain or [])
        if self.env.context.get("afg_map_list"):
            extra = self._afg_map_company_domain()
            if extra:
                domain = Domain.AND([domain, extra])
        return super()._search(
            domain, offset=offset, limit=limit, order=order,
            active_test=active_test, bypass_access=bypass_access,
        )

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        domain = list(domain or [])
        if not self.env.context.get("afg_unique_ledgers"):
            return super().search(domain, offset=offset, limit=limit, order=order)
        recs = super(AccountAccount, self.with_context(afg_unique_ledgers=False)).search(
            domain, offset=0, limit=None, order=order
        )
        recs = recs._afg_dedupe_unique_ledgers()
        if offset:
            recs = recs[offset:]
        if limit:
            recs = recs[: int(limit)]
        return recs

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        if not self.env.context.get("afg_unique_ledgers"):
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        args = list(domain or [])
        if name:
            args = ["|", ("name", operator, name), ("code", operator, name)] + args
        recs = super(AccountAccount, self.with_context(afg_unique_ledgers=False)).search(
            args, limit=None
        )
        recs = recs._afg_dedupe_unique_ledgers()
        if limit:
            recs = recs[: int(limit)]
        return [(a.id, a._afg_unique_ledger_label()) for a in recs]

    def action_remove_from_ctf(self):
        self.write({"ctf_category": False})
        return True

    def action_remove_from_coa_group(self):
        self.write({"group_id": False})
        return True

    def _afg_keyword_ctf(self):
        self.ensure_one()
        blob = " ".join([self.name or "", self.code or ""]).lower()
        rules = (
            ("dividend", "dividends"),
            ("fine", "fines"),
            ("penalt", "fines"),
            ("donation", "donations"),
            ("interest income", "interest_inc"),
            ("interest exp", "interest_exp"),
            ("interest", "interest"),
            ("gain on disposal", "disposal_gain"),
            ("loss on disposal", "disposal_loss"),
            ("disposal", "disposal"),
            ("exchange gain", "fx_gain"),
            ("exchange loss", "fx_loss"),
            ("foreign exchange", "fx"),
            ("forex", "fx"),
            ("corporate tax", "tax"),
            ("income tax", "tax"),
            ("intangible", "intangible"),
            ("financial asset", "financial_nca"),
            ("client entertain", "entertainment"),
            ("entertainment", "entertainment"),
        )
        for needle, cat in rules:
            if needle in blob:
                if cat == "entertainment" and any(
                    k in blob for k in ("cash", "bank", "receivable", "payable")
                ):
                    continue
                return cat
        return False

    def _afg_ctf_from_afg_code(self, code):
        mapping = {
            "AFG_REV": "op_rev",
            "AFG_COR": "cogs",
            "AFG_PAYROLL": "salaries",
            "AFG_DEPR_PL": "depreciation",
            "AFG_SELL": "other_exp",
            "AFG_GNA": "other_exp",
            "AFG_PPE": "ppe",
            "AFG_FIXED": "ppe",
            "AFG_INV": "current_assets",
            "AFG_AR": "current_assets",
            "AFG_PREP": "current_assets",
            "AFG_CASH": "current_assets",
            "AFG_EQ": "retained_earnings",
            "AFG_EQ_CHG": "other_equity",
            "AFG_EOS": "ncl",
            "AFG_AP": "current_liab",
            "AFG_TAX": "tax",
            "AFG_REL": "current_liab",
        }
        return mapping.get((code or "").strip().upper()) or False

    @api.model
    def action_afg_ensure_ctf_map(self):
        Ctf = self.env["audited.financial.ctf.group"]
        if Ctf._name in self.env:
            Ctf._setup_default_ctf_groups()
        for acc in self.search([("ctf_category", "=", "entertainment")]):
            blob = (acc.name or "").lower()
            if any(k in blob for k in ("cash", "bank", "receivable")):
                acc.ctf_category = "current_assets"
        accounts = self.search([("ctf_category", "=", False)])
        for acc in accounts:
            cat = acc._afg_keyword_ctf()
            if not cat:
                grp = acc.afg_group_id or acc._afg_suggested_group()
                cat = acc._afg_ctf_from_afg_code(grp.code if grp else "")
            if cat:
                acc.ctf_category = cat
        return True

    @api.model
    def action_afg_map_popup_ctf(self, category):
        cat = (category or "").strip()
        if not cat:
            raise UserError("Select a CT Filing group.")
        accounts = self.search([("ctf_category", "=", cat)])
        wiz = self.env["audited.financial.ctf.ledgers"].create({
            "category": cat,
            "account_ids": [(6, 0, accounts.ids)],
        })
        view = self.env.ref(
            "audited_financials_saaskul.view_audited_financial_ctf_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Add / remove ledgers",
            "res_model": "audited.financial.ctf.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }

    def _cpa_reset_ledger_buckets(self):
        """All ledgers grouped by the same unique ledger name."""
        Version = self.env["audited.financial.version"]
        buckets = {}
        for acc in self.sudo().search([]):
            key = Version._afg_pl_unique_ledger_key(acc) or ("id:%s" % acc.id)
            buckets.setdefault(key, []).append(acc)
        return buckets

    def _cpa_reset_majority(self, values):
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return max(counts, key=lambda value: (counts[value], -int(value) if str(value).isdigit() else 0))

    def action_cpa_reset_afg(self):
        """Copy an existing AFG group onto every company with the same ledger name."""
        ungrouped = {"AFG_UNGRP_PL", "AFG_UNGRP_BS"}
        Line = self.env["audited.financial.group.line"].sudo().with_context(
            afg_skip_collapse=True
        )
        updated = 0
        for recs in self._cpa_reset_ledger_buckets().values():
            donors = [
                acc for acc in recs
                if acc.afg_group_id and (acc.afg_group_id.code or "") not in ungrouped
            ]
            if not donors:
                continue
            group_id = self._cpa_reset_majority([acc.afg_group_id.id for acc in donors])
            missing_line = not Line.search_count([
                ("account_id", "in", [acc.id for acc in recs]),
                ("group_id", "=", group_id),
            ])
            if missing_line:
                Line.create({
                    "group_id": group_id,
                    "account_id": donors[0].id,
                })
            for acc in recs:
                if acc.afg_group_id.id == group_id:
                    continue
                self.env.cr.execute(
                    "UPDATE account_account SET afg_group_id = %s WHERE id = %s",
                    (group_id, acc.id),
                )
                updated += 1
        if updated:
            self.invalidate_recordset(fnames=["afg_group_id"])
        return True

    def action_cpa_reset_ctf(self):
        """Copy an existing CT Filing category onto every company with the same ledger name."""
        updated = 0
        for recs in self._cpa_reset_ledger_buckets().values():
            categories = [acc.ctf_category for acc in recs if acc.ctf_category]
            if not categories:
                continue
            category = self._cpa_reset_majority(categories)
            ids = [acc.id for acc in recs if acc.ctf_category != category]
            if not ids:
                continue
            self.browse(ids).with_context(afg_skip_same_name_sync=True).write({
                "ctf_category": category,
            })
            updated += len(ids)
        return True


class AccountGroup(models.Model):
    _inherit = "account.group"

    afg_group_id = fields.Many2one(
        "audited.financial.group",
        string="AFG",
        domain="[('code', 'not in', ['AFG_UNGRP_PL', 'AFG_UNGRP_BS']),"
               " '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Sets this Audited Financial group on every ledger in this account group.",
    )
    ctf_group_id = fields.Many2one(
        "audited.financial.ctf.group",
        string="CTF",
        domain="[('allocate', '=', True)]",
        help="Sets this CT Filing group on every ledger in this account group.",
    )
    ctf_category = fields.Selection(
        CTF_CATEGORY_SELECTION,
        string="CTF category",
    )
    cpabooks_all_companies = fields.Boolean(
        string="All companies",
        default=True,
        help="Ticked: saving this account group also updates the same group "
             "in every other company (name, AFG, CTFG). Unticked: this company only.",
    )

    def _auto_init(self):
        cr = self.env.cr
        if not column_exists(cr, "account_group", "afg_group_id"):
            create_column(cr, "account_group", "afg_group_id", "int4")
        if not column_exists(cr, "account_group", "ctf_group_id"):
            create_column(cr, "account_group", "ctf_group_id", "int4")
        if not column_exists(cr, "account_group", "ctf_category"):
            create_column(cr, "account_group", "ctf_category", "varchar")
        if not column_exists(cr, "account_group", "cpabooks_all_companies"):
            create_column(cr, "account_group", "cpabooks_all_companies", "bool")
            cr.execute(
                """
                UPDATE account_group
                   SET cpabooks_all_companies = TRUE
                 WHERE cpabooks_all_companies IS NULL
                """
            )
        return super()._auto_init()

    def write(self, vals):
        old_keys = {
            group.id: (group.name, group.code_prefix_start, group.company_id.id)
            for group in self
        }
        res = super().write(vals)
        if self.env.context.get("cpa_skip_group_push"):
            if not self.env.context.get("cpa_skip_group_cross_company"):
                self._cpa_share_group_to_other_companies(vals, old_keys)
            return res
        if "afg_group_id" in vals or "ctf_category" in vals or "ctf_group_id" in vals:
            self._cpa_push_afg_ctf_to_ledgers(vals)
        if not self.env.context.get("cpa_skip_group_cross_company"):
            self._cpa_share_group_to_other_companies(vals, old_keys)
        return res

    def _cpa_group_applies_to_all_companies(self, vals):
        self.ensure_one()
        if "cpabooks_all_companies" in vals:
            return bool(vals.get("cpabooks_all_companies"))
        if "cpabooks_all_companies" in self._fields:
            return bool(self.cpabooks_all_companies)
        return True

    def _cpa_afg_id_for_company(self, afg, company):
        if not afg:
            return False
        if not afg.company_id or not company or afg.company_id.id == company.id:
            return afg.id
        Group = afg.sudo()
        shared = Group.search([
            ("code", "=", afg.code),
            ("company_id", "=", False),
        ], limit=1)
        if shared:
            return shared.id
        own = Group.search([
            ("code", "=", afg.code),
            ("company_id", "=", company.id),
        ], limit=1)
        return own.id or False

    def _cpa_share_group_to_other_companies(self, vals, old_keys):
        """All companies ticked: same account group name gets this AFG, CTFG, and name."""
        share_keys = (
            "name", "code_prefix_start", "code_prefix_end",
            "afg_group_id", "ctf_group_id", "ctf_category",
        )
        if not any(key in vals for key in share_keys):
            return
        Group = self.with_context(cpabooks_group_all_companies=True).sudo()
        for group in self:
            if not group._cpa_group_applies_to_all_companies(vals):
                continue
            old_name, old_prefix, company_id = old_keys.get(
                group.id, (group.name, group.code_prefix_start, group.company_id.id),
            )
            if not old_prefix or not old_name:
                continue
            siblings = Group.search([
                ("id", "!=", group.id),
                ("company_id", "!=", company_id),
                ("code_prefix_start", "=", old_prefix),
                ("name", "=", old_name),
            ])
            for sibling in siblings:
                if (
                    "cpabooks_all_companies" in sibling._fields
                    and not sibling.cpabooks_all_companies
                ):
                    continue
                payload = {}
                for key in share_keys:
                    if key not in vals or key not in sibling._fields:
                        continue
                    if key == "afg_group_id":
                        afg = group.afg_group_id
                        payload[key] = group._cpa_afg_id_for_company(afg, sibling.company_id)
                    else:
                        payload[key] = vals.get(key)
                if payload:
                    sibling.with_context(cpa_skip_group_cross_company=True).write(payload)

    @api.model
    def _cpa_fill_blank_shared_afg(self):
        """Copy AFG and CTFG onto the same account group where another company already has them."""
        Group = self.with_context(cpabooks_group_all_companies=True).sudo()
        blanks = Group.search([
            ("afg_group_id", "=", False),
            ("code_prefix_start", "!=", False),
            ("name", "!=", False),
        ])
        for blank in blanks:
            if (
                "cpabooks_all_companies" in blank._fields
                and blank.cpabooks_all_companies is False
            ):
                continue
            src = Group.search([
                ("id", "!=", blank.id),
                ("company_id", "!=", blank.company_id.id),
                ("code_prefix_start", "=", blank.code_prefix_start),
                ("name", "=", blank.name),
                ("afg_group_id", "!=", False),
            ], limit=1)
            if not src:
                continue
            afg_id = blank._cpa_afg_id_for_company(src.afg_group_id, blank.company_id)
            if not afg_id:
                continue
            payload = {"afg_group_id": afg_id}
            if not blank.ctf_group_id and src.ctf_group_id:
                payload["ctf_group_id"] = src.ctf_group_id.id
            if not blank.ctf_category and src.ctf_category:
                payload["ctf_category"] = src.ctf_category
            blank.with_context(cpa_skip_group_cross_company=True).write(payload)
        return True

    def _cpa_push_afg_ctf_to_ledgers(self, vals):
        Account = self.env["account.account"].sudo()
        Line = self.env["audited.financial.group.line"].sudo().with_context(
            afg_skip_collapse=True
        )
        for group in self:
            accounts = Account.search([("group_id", "=", group.id)])
            if not accounts:
                continue
            if "ctf_group_id" in vals:
                category = group.ctf_group_id.ctf_category or False
                if group.ctf_category != category:
                    group.with_context(cpa_skip_group_push=True).write({
                        "ctf_category": category,
                    })
                accounts.with_context(afg_skip_same_name_sync=True).write({
                    "ctf_category": category,
                })
            elif "ctf_category" in vals:
                accounts.with_context(afg_skip_same_name_sync=True).write({
                    "ctf_category": vals.get("ctf_category") or False,
                })
            if "afg_group_id" not in vals:
                continue
            gid = vals.get("afg_group_id") or False
            # Group AFG replaces whatever was reset onto the ledger before.
            Line.search([("account_id", "in", accounts.ids)]).unlink()
            if gid:
                for acc in accounts:
                    Line.create({"group_id": gid, "account_id": acc.id})
                self.env.cr.execute(
                    "UPDATE account_account SET afg_group_id = %s WHERE id IN %s",
                    (gid, tuple(accounts.ids)),
                )
            else:
                self.env.cr.execute(
                    "UPDATE account_account SET afg_group_id = NULL WHERE id IN %s",
                    (tuple(accounts.ids),),
                )
            accounts.invalidate_recordset(fnames=["afg_group_id"])

    def _afg_code_prefix(self):
        self.ensure_one()
        if "code_prefix_start" in self._fields:
            return (self.code_prefix_start or "").strip()
        if "code_prefix" in self._fields:
            return (self.code_prefix or "").strip()
        return ""

    def afg_map_fetch_children(self):
        self.ensure_one()
        Account = self.env["account.account"]
        extra = Account._afg_map_company_domain()
        domain = [("group_id", "=", self.id)] + extra
        accounts = Account.search(domain, order="code, name")
        prefix = self._afg_code_prefix()
        if not accounts and prefix:
            domain = [("code", "=like", prefix + "%")] + extra
            child_prefixes = []
            for child in self.search([("parent_id", "=", self.id)]):
                p = child._afg_code_prefix()
                if p and len(p) > len(prefix):
                    child_prefixes.append(p)
            recs = Account.search(domain, order="code, name")
            keep = Account.browse()
            for acc in recs:
                code = acc.code or ""
                if any(code.startswith(p) for p in child_prefixes):
                    continue
                keep |= acc
            if keep:
                accounts = keep
        return [{
            "id": acc.id,
            "line_id": acc.id,
            "code": acc.code or "",
            "name": acc.name or "",
        } for acc in accounts]

    def afg_map_fetch_children_multi(self):
        return {str(g.id): g.afg_map_fetch_children() for g in self}

    def action_afg_map_popup(self):
        self.ensure_one()
        accounts = self.env["account.account"].search([("group_id", "=", self.id)])
        wiz = self.env["audited.financial.coa.group.ledgers"].create({
            "account_group_id": self.id,
            "account_ids": [(6, 0, accounts.ids)],
        })
        view = self.env.ref(
            "audited_financials_saaskul.view_audited_financial_coa_group_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Add / remove ledgers",
            "res_model": "audited.financial.coa.group.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": dict(self.env.context),
        }


class AuditedFinancialCoaGroupLedgers(models.TransientModel):
    _name = "audited.financial.coa.group.ledgers"
    _description = "Account group ledgers"

    account_group_id = fields.Many2one("account.group", required=True, readonly=True)
    account_ids = fields.Many2many(
        "account.account",
        "afg_coa_group_ledgers_rel",
        "wizard_id",
        "account_id",
        string="Ledgers",
    )

    def action_remove_from_group(self):
        self.ensure_one()
        self.account_ids.write({"group_id": False})
        self.account_ids = [(5, 0, 0)]
        return True

    def action_open_add(self):
        self.ensure_one()
        wiz = self.env["audited.financial.group.add.ledgers"].create({
            "coa_target_group_id": self.account_group_id.id,
        })
        wiz._afg_load_pick_lines()
        view = self.env.ref(
            "audited_financials_saaskul.view_audited_financial_group_add_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Add ledgers",
            "res_model": "audited.financial.group.add.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }


class AccountAccountType(models.Model):
    """Stand-in for the Odoo 14 account type model, keyed by Odoo 19 account_type."""

    _name = "account.account.type"
    _description = "Account Type"
    _order = "name, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    internal_group = fields.Selection(
        [
            ("asset", "Asset"),
            ("liability", "Liability"),
            ("equity", "Equity"),
            ("income", "Income"),
            ("expense", "Expense"),
            ("off", "Off Balance"),
        ],
        string="Internal Group",
    )
    type = fields.Selection(
        [
            ("receivable", "Receivable"),
            ("payable", "Payable"),
            ("liquidity", "Liquidity"),
            ("other", "Regular"),
        ],
        string="Legacy type",
        default="other",
    )
    include_initial_balance = fields.Boolean(string="Bring Balance Forward")
    ctf_group_id = fields.Many2one(
        "audited.financial.ctf.group",
        string="CTF",
        domain="[('allocate', '=', True)]",
        help="Sets this CT Filing group on every ledger of this type.",
    )
    ctf_category = fields.Selection(CTF_CATEGORY_SELECTION, string="CTF category")
    afg_group_id = fields.Many2one(
        "audited.financial.group",
        string="AFG",
        domain="[('code', 'not in', ['AFG_UNGRP_PL', 'AFG_UNGRP_BS'])]",
        help="Sets this Audited Financial group on every ledger of this type.",
    )

    _code_uniq = models.Constraint("unique(code)", "Account type code must be unique.")

    def _auto_init(self):
        res = super()._auto_init()
        self._afg_ensure_standard_types()
        return res

    @api.model
    def _afg_ensure_standard_types(self):
        existing = {rec.code: rec for rec in self.sudo().search([])}
        if len(existing) >= len(AFG_ACCOUNT_TYPES) and all(code in existing for code, *_rest in AFG_ACCOUNT_TYPES):
            return True
        for code, name, internal_group, legacy, initial in AFG_ACCOUNT_TYPES:
            if code in existing:
                continue
            self.sudo().create({
                "code": code,
                "name": name,
                "internal_group": internal_group,
                "type": legacy,
                "include_initial_balance": initial,
            })
        return True

    def write(self, vals):
        before = {
            rec.id: (
                rec.ctf_group_id.id,
                rec.ctf_category,
                rec.afg_group_id.id,
            )
            for rec in self
        }
        res = super().write(vals)
        if self.env.context.get("cpa_skip_type_push"):
            return res
        if not any(key in vals for key in ("ctf_group_id", "ctf_category", "afg_group_id")):
            return res
        Account = self.env["account.account"].sudo()
        for rec in self:
            prev = before.get(rec.id)
            if prev and (
                rec.ctf_group_id.id,
                rec.ctf_category,
                rec.afg_group_id.id,
            ) == prev:
                continue
            payload = {}
            if "ctf_group_id" in vals or "ctf_category" in vals:
                if "ctf_group_id" in vals:
                    category = rec.ctf_group_id.ctf_category or False
                    if rec.ctf_category != category:
                        rec.with_context(cpa_skip_type_push=True).write({"ctf_category": category})
                else:
                    category = vals.get("ctf_category") or False
                payload["ctf_category"] = category
            if "afg_group_id" in vals:
                payload["afg_group_id"] = rec.afg_group_id.id or False
            accounts = Account.search([("user_type_id", "=", rec.id)])
            if accounts and payload:
                accounts.with_context(
                    afg_skip_same_name_sync=True,
                    cpa_skip_type_ctf=True,
                ).write(payload)
        return res


class AccountAccountTypePopup(models.Model):
    _inherit = "account.account"

    cpa_type_ctf_group_id = fields.Many2one(
        related="user_type_id.ctf_group_id",
        string="Set CTF",
        readonly=False,
        help="Saved on this account type. Every ledger of the type gets this CT Filing group.",
    )
    cpa_type_afg_group_id = fields.Many2one(
        related="user_type_id.afg_group_id",
        string="Set AFG",
        readonly=False,
        help="Saved on this account type. Every ledger of the type gets this AFG group.",
    )

    def action_cpa_open_account_type(self):
        self.ensure_one()
        if not self.user_type_id:
            raise UserError("Set a type on this ledger first.")
        view = self.env.ref("audited_financials_saaskul.view_account_type_ctf_popup")
        return {
            "type": "ir.actions.act_window",
            "name": "Type",
            "res_model": "account.account.type",
            "res_id": self.user_type_id.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }


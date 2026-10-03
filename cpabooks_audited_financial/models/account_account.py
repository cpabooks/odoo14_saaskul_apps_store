# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
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

    def _auto_init(self):
        cr = self.env.cr
        if not column_exists(cr, "account_account", "ctf_category"):
            create_column(cr, "account_account", "ctf_category", "varchar")
        if not column_exists(cr, "account_account", "afg_group_id"):
            create_column(cr, "account_account", "afg_group_id", "int4")
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

    def _compute_afg_group_id(self):
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        for acc in self:
            lines = Line.search([("account_id", "=", acc.id)])
            real = lines.filtered(lambda l: (l.group_id.code or "") not in _AFG_UNGRP_CODES)
            if real:
                acc.afg_group_id = real[0].group_id
            else:
                acc.afg_group_id = acc._afg_suggested_group()

    def _inverse_afg_group_id(self):
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        Version = self.env["audited.financial.version"]
        Account = self.env["account.account"]
        for acc in self:
            key = Version._afg_pl_unique_ledger_key(acc)
            peers = acc
            if key:
                cids = list(self.env.context.get("allowed_company_ids") or [])
                if not cids:
                    cids = list(self.env.companies.ids or [])
                if acc.company_id:
                    cids = list(set(cids) | {acc.company_id.id})
                domain = [("company_id", "in", cids)] if cids else []
                for other in Account.search(domain):
                    if Version._afg_pl_unique_ledger_key(other) == key:
                        peers |= other
            Line.search([("account_id", "in", peers.ids)]).unlink()
            grp = acc.afg_group_id
            if grp:
                grp._afg_add_unique_accounts(peers)
        Version._afg_rebuild_after_coa_map(self)

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

    def name_get(self):
        if self.env.context.get("afg_unique_ledgers"):
            Version = self.env["audited.financial.version"]
            res = []
            for a in self:
                label = (a.name or "").strip()
                label = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", label)
                label = label or Version._afg_pl_unique_ledger_key(a) or a.code or str(a.id)
                res.append((a.id, label))
            return res
        return super().name_get()

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
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = list(args or [])
        if self.env.context.get("afg_map_list"):
            extra = self._afg_map_company_domain()
            if extra:
                args = expression.AND([args, extra])
        return super(AccountAccount, self)._search(
            args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid,
        )

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = list(domain or [])
        if self.env.context.get("afg_map_list"):
            extra = self._afg_map_company_domain()
            if extra:
                domain = expression.AND([domain, extra])
        return super(AccountAccount, self).read_group(
            domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy
        )

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        args = list(args or [])
        if not self.env.context.get("afg_unique_ledgers") or count:
            return super().search(args, offset=offset, limit=limit, order=order, count=count)
        recs = super(AccountAccount, self.with_context(afg_unique_ledgers=False)).search(
            args, offset=0, limit=None, order=order, count=False
        )
        recs = recs._afg_dedupe_unique_ledgers()
        if offset:
            recs = recs[offset:]
        if limit:
            recs = recs[: int(limit)]
        return recs

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        if not self.env.context.get("afg_unique_ledgers"):
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        args = list(args or [])
        if name:
            args = ["|", ("name", operator, name), ("code", operator, name)] + args
        recs = super(AccountAccount, self.with_context(afg_unique_ledgers=False)).search(
            args, limit=None
        )
        recs = recs._afg_dedupe_unique_ledgers()
        if limit:
            recs = recs[: int(limit)]
        return recs.name_get()

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
            "cpabooks_audited_financial.view_audited_financial_ctf_ledgers_form"
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


class AccountGroup(models.Model):
    _inherit = "account.group"

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
            "cpabooks_audited_financial.view_audited_financial_coa_group_ledgers_form"
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
            "cpabooks_audited_financial.view_audited_financial_group_add_ledgers_form"
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

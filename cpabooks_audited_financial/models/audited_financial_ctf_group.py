# -*- coding: utf-8 -*-
"""CT Filing (L1) groups — same hierarchy as CTF P&L / SOFP report."""

from odoo import api, fields, models

from .account_account import CTF_CATEGORY_SELECTION

# code, name, parent_code, sequence, section, ctf_category, allocate
CTF_GROUP_PRESETS = [
    ("ctf_pl", "Statement of Profit & Loss Account - CTF Format", False, 10, "pl", False, False),
    ("op_rev", "Operating Revenue (AED)", "ctf_pl", 11, "pl", "op_rev", True),
    ("cogs", "Expenditure incurred in deriving operating revenue (AED)", "ctf_pl", 12, "pl", "cogs", True),
    ("gross", "Gross Profit / Loss (AED)", "ctf_pl", 13, "pl", False, False),
    ("noe_h", "Non-operating Expense", "ctf_pl", 20, "pl", False, False),
    ("salaries", "Salaries, wages and related charges (AED)", "noe_h", 21, "pl", "salaries", True),
    ("depreciation", "Depreciation and amortisation (AED)", "noe_h", 22, "pl", "depreciation", True),
    ("fines", "Fines and Penalties (AED)", "noe_h", 23, "pl", "fines", True),
    ("donations", "Donations (AED)", "noe_h", 24, "pl", "donations", True),
    ("entertainment", "Client entertainment expenses (AED)", "noe_h", 25, "pl", "entertainment", True),
    ("other_exp", "Other expenses (AED)", "noe_h", 26, "pl", "other_exp", True),
    ("noe_tot", "Non-operating Expense (Excluding others item Listed below) (AED)", "ctf_pl", 27, "pl", False, False),
    ("nor_h", "Non-operating Revenue", "ctf_pl", 30, "pl", False, False),
    ("dividends", "Dividends received (AED)", "nor_h", 31, "pl", "dividends", True),
    ("other_nor", "Other non-operating revenue (AED)", "nor_h", 32, "pl", "other_nor", True),
    ("oi_h", "Other items", "ctf_pl", 40, "pl", False, False),
    ("interest_inc", "Interest Income (AED)", "oi_h", 41, "pl", "interest_inc", True),
    ("interest_exp", "Interest Expenditure (AED)", "oi_h", 42, "pl", "interest_exp", True),
    ("interest", "Net Interest Income / (Expense) (AED)", "oi_h", 43, "pl", "interest", True),
    ("disposal_gain", "Gains on Disposal of Assets (AED)", "oi_h", 44, "pl", "disposal_gain", True),
    ("disposal_loss", "Losses on Disposal of Assets (AED)", "oi_h", 45, "pl", "disposal_loss", True),
    ("disposal", "Net gains / (losses) on disposal of assets (AED)", "oi_h", 46, "pl", "disposal", True),
    ("fx_gain", "Foreign exchange gains (AED)", "oi_h", 47, "pl", "fx_gain", True),
    ("fx_loss", "Foreign exchange losses (AED)", "oi_h", 48, "pl", "fx_loss", True),
    ("fx", "Net Gains/(losses) on foreign exchange (AED)", "oi_h", 49, "pl", "fx", True),
    ("net", "Net profit/(loss) (AED)", "ctf_pl", 50, "pl", False, False),
    ("tax", "Less: Corporate Tax", "ctf_pl", 51, "pl", "tax", True),
    ("net_after", "Net profit/(loss) (AED) after corporate tax", "ctf_pl", 52, "pl", False, False),
    ("ctf_bs", "Statement of Financial Position - CTF Format", False, 100, "bs", False, False),
    ("assets_h", "Assets", "ctf_bs", 101, "bs", False, False),
    ("current_assets", "Total current assets (AED)", "assets_h", 102, "bs", "current_assets", True),
    ("ppe", "Property, plant and equipment (AED)", "assets_h", 103, "bs", "ppe", True),
    ("intangible", "Intangible assets (AED)", "assets_h", 104, "bs", "intangible", True),
    ("financial_nca", "Financial assets (AED)", "assets_h", 105, "bs", "financial_nca", True),
    ("nca_other", "Other non-current assets (AED)", "assets_h", 106, "bs", "nca_other", True),
    ("nca_tot", "Total non-current assets (AED)", "assets_h", 107, "bs", False, False),
    ("total_asset", "Total Asset", "assets_h", 108, "bs", False, False),
    ("liab_h", "Liabilities", "ctf_bs", 120, "bs", False, False),
    ("current_liab", "Total current liabilities (AED)", "liab_h", 121, "bs", "current_liab", True),
    ("ncl", "Total non-current liabilities (AED)", "liab_h", 122, "bs", "ncl", True),
    ("total_liab", "Total liabilities (AED)", "liab_h", 123, "bs", False, False),
    ("eq_h", "Equity", "ctf_bs", 140, "bs", False, False),
    ("share_capital", "Share capital (AED)", "eq_h", 141, "bs", "share_capital", True),
    ("retained_earnings", "Retained earnings (AED)", "eq_h", 142, "bs", "retained_earnings", True),
    ("other_equity", "Other equity (AED)", "eq_h", 143, "bs", "other_equity", True),
    ("total_eq", "Total equity (AED)", "eq_h", 144, "bs", False, False),
    ("tel", "Total equity and liabilities (AED)", "ctf_bs", 160, "bs", False, False),
]


class AuditedFinancialCtfGroup(models.Model):
    _name = "audited.financial.ctf.group"
    _description = "CT Filing ledger group (L1)"
    _parent_name = "parent_id"
    _parent_store = False
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(index=True, required=True)
    parent_id = fields.Many2one(
        "audited.financial.ctf.group",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many(
        "audited.financial.ctf.group",
        "parent_id",
        string="Subgroups",
    )
    sequence = fields.Integer(default=10)
    report_section = fields.Selection(
        [("pl", "Profit or Loss"), ("bs", "Financial Position")],
        required=True,
        default="pl",
    )
    ctf_category = fields.Selection(CTF_CATEGORY_SELECTION, string="CT Filing")
    allocate = fields.Boolean(default=False)
    has_ledgers = fields.Boolean(compute="_compute_has_ledgers", string="Has ledgers")
    indent_name = fields.Char(compute="_compute_indent_name", string="Description")

    _sql_constraints = [
        ("ctf_group_code_uniq", "unique(code)", "CTF group code must be unique."),
    ]

    def _ctf_depth(self):
        self.ensure_one()
        depth = 0
        p = self.parent_id
        while p and depth < 8:
            depth += 1
            p = p.parent_id
        return depth

    def _compute_indent_name(self):
        for rec in self:
            rec.indent_name = ("%s%s" % ("    " * rec._ctf_depth(), rec.name or "")).rstrip()

    def _compute_has_ledgers(self):
        Account = self.env["account.account"]
        for rec in self:
            if not rec.allocate or not rec.ctf_category:
                rec.has_ledgers = False
                continue
            rec.has_ledgers = bool(Account.search_count([
                ("ctf_category", "=", rec.ctf_category),
            ]))

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if not self.env.context.get("afg_skip_ctf_setup") and not count:
            self.with_context(afg_skip_ctf_setup=True)._setup_default_ctf_groups()
        return super().search(args, offset=offset, limit=limit, order=order, count=count)

    @api.model
    def action_setup_default_ctf_groups(self):
        return self._setup_default_ctf_groups()

    @api.model
    def _setup_default_ctf_groups(self):
        existing = {
            g.code: g
            for g in self.with_context(afg_skip_ctf_setup=True).search([])
        }
        for code, name, parent_code, seq, section, cat, allocate in CTF_GROUP_PRESETS:
            vals = {
                "name": name,
                "code": code,
                "sequence": seq,
                "report_section": section,
                "ctf_category": cat or False,
                "allocate": bool(allocate),
                "parent_id": existing[parent_code].id if parent_code and parent_code in existing else False,
            }
            rec = existing.get(code)
            if rec:
                rec.write(vals)
            else:
                rec = self.create(vals)
                existing[code] = rec
        return True

    @api.model
    def get_label_map(self):
        self.action_setup_default_ctf_groups()
        return {
            g.code: g.name
            for g in self.with_context(afg_skip_ctf_setup=True).search([])
        }

    def afg_map_fetch_children(self):
        self.ensure_one()
        Account = self.env["account.account"]
        if not self.allocate or not self.ctf_category:
            return []
        self.env["account.account"].action_afg_ensure_ctf_map()
        cids = list(self.env.context.get("allowed_company_ids") or self.env.companies.ids or [])
        domain = [("ctf_category", "=", self.ctf_category)]
        if cids:
            domain.append(("company_id", "in", cids))
        accounts = Account.search(domain, order="code, name")
        Version = self.env["audited.financial.version"]
        rows = []
        seen = set()
        for acc in accounts:
            key = Version._afg_pl_unique_ledger_key(acc) or acc.id
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "id": acc.id,
                "line_id": acc.id,
                "code": acc.code or "",
                "name": acc.name or "",
            })
        return rows

    def afg_map_fetch_children_multi(self):
        return {str(g.id): g.afg_map_fetch_children() for g in self}

    def action_afg_map_popup(self):
        self.ensure_one()
        if not self.allocate or not self.ctf_category:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "CT Filing",
                    "message": "This line is a total / heading. Allocate ledgers on the subgroups.",
                    "type": "warning",
                    "sticky": False,
                },
            }
        return self.env["account.account"].action_afg_map_popup_ctf(self.ctf_category)

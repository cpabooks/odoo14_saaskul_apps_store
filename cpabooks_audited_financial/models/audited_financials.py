# -*- coding: utf-8 -*-
"""Audited Financial Groups (AFG) — trial balance to IFRS/FTA-style working papers."""

import base64
import calendar
import csv
import html as html_lib
import io
import re
from collections import OrderedDict, defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import logging

from odoo import _, api, fields, models
from odoo.exceptions import MissingError, UserError

from .account_account import CTF_CATEGORY_SELECTION
from .audited_financials_presets import AFG_PRESET_GROUPS, _account_match_code

_logger = logging.getLogger(__name__)

# Keep these tokens uppercase in Proper Case labels (VAT → VAT, not Vat).
_AFG_ACRONYMS = frozenset({
    "VAT", "IFRS", "FTA", "AED", "USD", "EUR", "GBP", "UAE", "GCC",
    "EBITDA", "COGS", "NBV", "PPE", "EOS", "ITC", "GST", "WHT", "CPA",
    "P&L", "TB", "BS", "PL", "ROI", "ERP", "FY", "YTD", "AP", "AR",
    "COS", "COGS", "SG&A", "EBIT", "EPS", "FX", "OCI", "SOCE",
})

_AFG_MONTH_ABBR = (
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


AFG_SENSITIVITY = [
    ("none", "Not sensitive"),
    ("revenue", "Revenue"),
    ("cost_of_revenue", "Cost of revenue"),
    ("depreciation", "Depreciation"),
    ("fixed_assets", "Fixed assets"),
    ("owner_current_account", "Owner current account"),
    ("retained_earnings", "Retained earnings"),
    ("related_party", "Related party balances"),
    ("tax_losses", "Tax losses"),
    ("tax_payable", "Tax payable / receivable"),
    ("eos_benefits", "Employees' end of service benefits"),
    ("cash_bank", "Cash and bank"),
    ("trade_receivables_payables", "Trade receivables / payables"),
]

AFG_REPORT_SECTION = [
    ("pl", "Statement of Profit or Loss"),
    ("bs", "Statement of Financial Position"),
    ("equity", "Statement of Changes in Equity"),
    ("cashflow", "Statement of Cash Flows"),
    ("notes", "Notes to the Financial Statements"),
    ("fixed_assets", "Property, Plant and Equipment"),
    ("review", "Validation & Review"),
]

# Chart-of-accounts type roll-ups shown above AFG (level 0) on the dashboard.
AFG_PL_COA_TYPES = OrderedDict([
    ("sales", {"label": "Total Sales", "sequence": 10}),
    ("cost_of_revenue", {"label": "Cost of Materials", "sequence": 20}),
    ("expenses", {"label": "Expenses Total", "sequence": 30}),
    ("net_profit", {
        "label": "Profit for the Year",
        "sequence": 40,
        "computed_from": ("sales", "cost_of_revenue", "expenses"),
    }),
])
AFG_BS_COA_TYPES = OrderedDict([
    ("asset", {"label": "Assets", "sequence": 10}),
    ("total_assets", {"label": "Total Assets", "sequence": 15, "computed_from": ("asset",)}),
    ("liability", {"label": "Liabilities", "sequence": 20}),
    ("total_liabilities", {"label": "Total Liabilities", "sequence": 25, "computed_from": ("liability",)}),
    ("equity", {"label": "Equity", "sequence": 30}),
    ("total_equity_liabilities", {
        "label": "Total Equity and Liabilities",
        "sequence": 40,
        "computed_from": ("liability", "equity"),
    }),
])
AFG_CODE_BS_TYPE = {
    "AFG_PPE": "asset",
    "AFG_INV": "asset",
    "AFG_AR": "asset",
    "AFG_PREP": "asset",
    "AFG_CASH": "asset",
    "AFG_AP": "liability",
    "AFG_TAX": "liability",
    "AFG_EOS": "liability",
    # AFG_REL omitted: related-party mix of AR/AP — split by account.internal_group
    "AFG_EQ": "equity",
    "AFG_EQ_CHG": "equity",
}
AFG_SECTION_COA_TYPES = {
    "pl": AFG_PL_COA_TYPES,
    "bs": AFG_BS_COA_TYPES,
    "equity": OrderedDict([
        ("equity", {"label": "Statement of Changes in Equity", "sequence": 10}),
    ]),
    "cashflow": OrderedDict([
        ("cashflow", {"label": "Cash flows", "sequence": 10}),
    ]),
    "fixed_assets": OrderedDict([
        ("fixed_assets", {"label": "Property, plant and equipment", "sequence": 10}),
    ]),
}
AFG_SECTIONS_WITH_COA_TYPE = tuple(AFG_SECTION_COA_TYPES.keys())

# Statement face presentation: Odoo signed balances → natural IFRS figures
# (sales/liabilities/equity shown positive; P&L net = sales − costs − expenses).
AFG_PL_FACE_NEGATE_TYPES = frozenset({"sales"})
AFG_BS_FACE_NEGATE_TYPES = frozenset({
    "liability", "total_liabilities", "equity", "total_equity_liabilities",
})


def _afg_default_period_vals():
    """Prior column = two calendar years back from today; current = last full calendar year (e.g. in 2026 → 2024 / 2025)."""
    yc = fields.Date.today().year - 1
    yp = yc - 1
    return {
        "period_preset": "years",
        "year_prior": yp,
        "year_current": yc,
        "date_from_prior": fields.Date.from_string("%s-01-01" % yp),
        "date_to_prior": fields.Date.from_string("%s-12-31" % yp),
        "date_from_current": fields.Date.from_string("%s-01-01" % yc),
        "date_to_current": fields.Date.from_string("%s-12-31" % yc),
    }


def _afg_month_start_end(year, month):
    """Return (date_from, date_to) for a calendar month."""
    last = calendar.monthrange(int(year), int(month))[1]
    return (
        fields.Date.from_string("%04d-%02d-01" % (int(year), int(month))),
        fields.Date.from_string("%04d-%02d-%02d" % (int(year), int(month), last)),
    )


def _afg_last_complete_month(today=None):
    """Last fully closed calendar month relative to today."""
    today = fields.Date.to_date(today or fields.Date.today())
    first_this = today.replace(day=1)
    last_end = first_this - timedelta(days=1)
    return last_end.replace(day=1), last_end


def _afg_format_period_label(date_from, date_to):
    """Short column caption: full year → '2025'; same month → 'Jun 2026'."""
    df = fields.Date.to_date(date_from)
    dt = fields.Date.to_date(date_to)
    if not df or not dt:
        return ""
    if df.month == 1 and df.day == 1 and dt.month == 12 and dt.day == 31 and df.year == dt.year:
        return str(df.year)
    if df.year == dt.year and df.month == dt.month:
        return "%s %s" % (_AFG_MONTH_ABBR[df.month], df.year)
    return "%s %s–%s %s" % (
        _AFG_MONTH_ABBR[df.month], df.year, _AFG_MONTH_ABBR[dt.month], dt.year,
    )


def _afg_period_preset_vals(preset, today=None):
    """Build version write vals for a dashboard period preset."""
    preset = (preset or "years").strip()
    today = fields.Date.to_date(today or fields.Date.today())
    if preset == "years":
        return _afg_default_period_vals()
    cur_start, cur_end = _afg_last_complete_month(today)
    if preset == "mom":
        # Prior = month before last; current = last complete month (e.g. Jun / Jul 2026).
        prior_end = cur_start - timedelta(days=1)
        prior_start = prior_end.replace(day=1)
        return {
            "period_preset": "mom",
            "year_prior": prior_start.year,
            "year_current": cur_start.year,
            "date_from_prior": prior_start,
            "date_to_prior": prior_end,
            "date_from_current": cur_start,
            "date_to_current": cur_end,
        }
    if preset == "yoy_month":
        # Prior = same month last year; current = last complete month (e.g. Jul 2025 / Jul 2026).
        py, pm = cur_start.year - 1, cur_start.month
        prior_start, prior_end = _afg_month_start_end(py, pm)
        return {
            "period_preset": "yoy_month",
            "year_prior": py,
            "year_current": cur_start.year,
            "date_from_prior": prior_start,
            "date_to_prior": prior_end,
            "date_from_current": cur_start,
            "date_to_current": cur_end,
        }
    return _afg_default_period_vals()


def _afg_period_presets_catalog(today=None, version=None):
    """UI cards: yearly / MoM / YoY / Custom (yearly remains default)."""
    today = fields.Date.to_date(today or fields.Date.today())
    specs = [
        ("years", _("Last 2 years"), _("Full calendar years (default)")),
        ("mom", _("Last 2 months"), _("Last month vs month before")),
        ("yoy_month", _("Same month YoY"), _("Last month vs same month last year")),
    ]
    out = []
    for key, title, hint in specs:
        vals = _afg_period_preset_vals(key, today)
        lab_p = _afg_format_period_label(vals["date_from_prior"], vals["date_to_prior"])
        lab_c = _afg_format_period_label(vals["date_from_current"], vals["date_to_current"])
        out.append({
            "key": key,
            "title": title,
            "hint": hint,
            "label_prior": lab_p,
            "label_current": lab_c,
            "caption": "%s → %s" % (lab_p, lab_c),
            "is_default": key == "years",
        })
    custom_caption = _("Pick dates…")
    custom_prior = custom_current = ""
    if version is not None:
        try:
            custom_prior = version._afg_period_label_prior()
            custom_current = version._afg_period_label_current()
            if version.period_preset == "custom" and custom_prior and custom_current:
                custom_caption = "%s → %s" % (custom_prior, custom_current)
        except Exception:
            pass
    out.append({
        "key": "custom",
        "title": _("Custom period"),
        "hint": _("Choose prior & current date ranges"),
        "label_prior": custom_prior,
        "label_current": custom_current,
        "caption": custom_caption,
        "is_default": False,
    })
    return out


# Show N years / months (dashboard + print comparative columns)
AFG_PERIOD_SPAN_KEYS = (
    "1y", "2y", "3y", "4y", "5y",
    "1m", "2m", "3m", "4m",
)


def _afg_normalize_period_span(span):
    s = (span or "2y").strip().lower()
    return s if s in AFG_PERIOD_SPAN_KEYS else "2y"


def _afg_parse_period_span(span):
    s = _afg_normalize_period_span(span)
    return int(s[:-1]), s[-1]


def _afg_period_span_label(span):
    n, unit = _afg_parse_period_span(span)
    if unit == "y":
        return _("1 year") if n == 1 else _("%s years") % n
    return _("1 month") if n == 1 else _("%s months") % n


def _afg_shift_month(year, month, delta):
    """Shift calendar month by delta (may be negative). Return (year, month)."""
    idx = int(year) * 12 + (int(month) - 1) + int(delta)
    return idx // 12, (idx % 12) + 1


def _afg_period_span_vals(span, today=None):
    """Write vals: oldest window → prior fields, newest → current (N=1 → same window)."""
    n, unit = _afg_parse_period_span(span)
    today = fields.Date.to_date(today or fields.Date.today())
    if unit == "y":
        yc = today.year - 1
        yp = yc if n <= 1 else yc - (n - 1)
        return {
            "period_preset": "years",
            "year_prior": yp,
            "year_current": yc,
            "date_from_prior": fields.Date.from_string("%s-01-01" % yp),
            "date_to_prior": fields.Date.from_string("%s-12-31" % yp),
            "date_from_current": fields.Date.from_string("%s-01-01" % yc),
            "date_to_current": fields.Date.from_string("%s-12-31" % yc),
        }
    cur_start, cur_end = _afg_last_complete_month(today)
    oldest_y, oldest_m = _afg_shift_month(cur_start.year, cur_start.month, -(n - 1))
    prior_start, prior_end = _afg_month_start_end(oldest_y, oldest_m)
    return {
        "period_preset": "mom",
        "year_prior": prior_start.year,
        "year_current": cur_start.year,
        "date_from_prior": prior_start,
        "date_to_prior": prior_end,
        "date_from_current": cur_start,
        "date_to_current": cur_end,
    }


def _afg_period_span_catalog():
    """UI options for Show periods card."""
    out = []
    for key in AFG_PERIOD_SPAN_KEYS:
        n, unit = _afg_parse_period_span(key)
        out.append({
            "key": key,
            "title": _afg_period_span_label(key),
            "hint": (
                _("Full calendar years ending last year")
                if unit == "y"
                else _("Complete calendar months ending last month")
            ),
            "is_default": key == "2y",
        })
    return out


def _afg_windows_for_span(span, today=None):
    """Oldest→newest window list for a span key (independent of version dates)."""
    n, unit = _afg_parse_period_span(span)
    today = fields.Date.to_date(today or fields.Date.today())
    windows = []
    if unit == "y":
        yc = today.year - 1
        for offset in range(n - 1, -1, -1):
            y = yc - offset
            df = fields.Date.from_string("%s-01-01" % y)
            dt = fields.Date.from_string("%s-12-31" % y)
            windows.append({
                "key": "y%s" % y,
                "label": str(y),
                "date_from": df,
                "date_to": dt,
            })
        return windows
    cur_start, cur_end = _afg_last_complete_month(today)
    for offset in range(n - 1, -1, -1):
        yy, mm = _afg_shift_month(cur_start.year, cur_start.month, -offset)
        df, dt = _afg_month_start_end(yy, mm)
        windows.append({
            "key": "m%04d%02d" % (yy, mm),
            "label": _afg_format_period_label(df, dt),
            "date_from": df,
            "date_to": dt,
        })
    return windows


class AuditedFinancialGroup(models.Model):
    _name = "audited.financial.group"
    _description = "Audited Financial Group (AFG)"
    _order = "report_section, sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(string="Code", index=True)
    report_section = fields.Selection(AFG_REPORT_SECTION, string="Report section", required=True, index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        help="Leave empty to map one unique ledger name across companies in the switcher "
             "(amounts are summed). Set a company only when this group is for that company.",
        ondelete="cascade",
    )
    sensitivity_category = fields.Selection(AFG_SENSITIVITY, string="IFRS sensitivity", default="none")
    line_ids = fields.One2many(
        "audited.financial.group.line",
        "group_id",
        string="Account mappings",
        domain=lambda self: self._afg_line_ids_company_domain(),
    )
    note = fields.Text()

    _sql_constraints = [
        (
            "audited_financial_group_code_company_uniq",
            "unique(code, company_id)",
            "AFG code must be unique per company (or once for shared templates).",
        ),
    ]

    @api.model
    def _afg_line_ids_company_domain(self):
        """AFG presets are shared; mapping lines must follow the company switcher."""
        cids = list(self.env.context.get("allowed_company_ids") or [])
        if not cids:
            cids = list(self.env.companies.ids) if self.env.companies else []
        if not cids and self.env.company:
            cids = [self.env.company.id]
        return [("company_id", "in", cids)] if cids else [("id", "=", False)]

    @api.model
    def _setup_default_afg_presets(self):
        Group = self.env["audited.financial.group"].sudo()
        for code, name, section, seq, sens in AFG_PRESET_GROUPS:
            if Group.search([("code", "=", code), ("company_id", "=", False)], limit=1):
                continue
            Group.create({
                "code": code,
                "name": name,
                "report_section": section,
                "sequence": seq,
                "sensitivity_category": sens,
                "company_id": False,
            })

    def name_get(self):
        result = []
        for group in self:
            if group.code:
                result.append((group.id, "%s — %s" % (group.code, group.name or "")))
            else:
                result.append((group.id, group.name or ""))
        return result

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = list(args or [])
        domain = list(args)
        if name:
            domain = ["|", ("code", operator, name), ("name", operator, name)] + domain
        return self.search(domain, limit=limit).name_get()

    def _afg_collapse_duplicate_mapping(self):
        """Keep one mapping line per unique ledger name (prefer current company)."""
        Version = self.env["audited.financial.version"]
        prefer = self.env.company.id if self.env.company else False
        Line = self.env["audited.financial.group.line"]
        for group in self:
            drop = Line.browse()
            seen = {}
            lines = group.line_ids.sorted(
                key=lambda l: (0 if l.company_id.id == prefer else 1, l.id)
            )
            for line in lines:
                if not line.account_id:
                    continue
                key = Version._afg_pl_unique_ledger_key(line.account_id)
                if not key:
                    continue
                if key in seen:
                    drop |= line
                else:
                    seen[key] = line
            if drop:
                drop.unlink()
        return True

    def read(self, fields=None, load="_classic_read"):
        if self.ids and not self.env.context.get("bin_size"):
            try:
                self._afg_collapse_duplicate_mapping()
            except Exception:
                _logger.debug("AFG mapping unique-ledger collapse skipped", exc_info=True)
        return super().read(fields=fields, load=load)

    def _afg_add_unique_accounts(self, accounts):
        """Create mapping lines for unique ledger names; skip names already mapped."""
        Version = self.env["audited.financial.version"]
        Line = self.env["audited.financial.group.line"]
        accounts = accounts.exists()
        for group in self:
            existing = {
                Version._afg_pl_unique_ledger_key(l.account_id)
                for l in Line.with_context(afg_skip_collapse=True).search(
                    [("group_id", "=", group.id)]
                )
            }
            seen = set(k for k in existing if k)
            for acc in accounts:
                key = Version._afg_pl_unique_ledger_key(acc)
                if not key or key in seen:
                    continue
                seen.add(key)
                Line.create({"group_id": group.id, "account_id": acc.id})
        return True

    def action_open_add_ledgers(self):
        self.ensure_one()
        wiz = self.env["audited.financial.group.add.ledgers"].create({
            "group_id": self.id,
        })
        wiz._afg_load_pick_lines()
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_group_add_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Add ledgers"),
            "res_model": "audited.financial.group.add.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": dict(self.env.context, afg_unique_ledgers=1),
        }

    def _afg_map_company_ids(self):
        cids = list(self.env.context.get("allowed_company_ids") or [])
        if not cids:
            cids = list(self.env.companies.ids or [])
        return cids

    def afg_map_fetch_children(self):
        """CoA ledgers under this AFG group (mapping lines + standard keyword match)."""
        self.ensure_one()
        Version = self.env["audited.financial.version"]
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        lines = Line.search([("group_id", "=", self.id)])
        if not lines:
            self.action_afg_ensure_standard_map()
            lines = Line.search([("group_id", "=", self.id)])
        rows = []
        seen = set()
        to_link = self.env["account.account"]

        def add_acc(acc, line=None):
            if not acc:
                return
            key = Version._afg_pl_unique_ledger_key(acc) or acc.id
            if key in seen:
                return
            seen.add(key)
            rows.append({
                "id": acc.id,
                "line_id": line.id if line else acc.id,
                "code": acc.code or "",
                "name": (line.ledger_caption if line else acc.name) or acc.name or "",
            })

        for line in lines:
            add_acc(line.account_id, line)
        cids = self._afg_map_company_ids()
        domain = [("company_id", "in", cids)] if cids else []
        code = (self.code or "").strip()
        if code:
            for acc in self.env["account.account"].search(domain, order="code, name"):
                if _account_match_code(acc) == code:
                    if acc.id not in set(lines.mapped("account_id").ids):
                        to_link |= acc
                    add_acc(acc)
        if to_link:
            self._afg_add_unique_accounts(to_link)
        return rows

    def afg_map_fetch_children_multi(self):
        return {str(g.id): g.afg_map_fetch_children() for g in self}

    def action_afg_map_popup(self):
        self.ensure_one()
        self.afg_map_fetch_children()
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_group_ledgers_popup"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Add / remove ledgers"),
            "res_model": "audited.financial.group",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": dict(
                self.env.context,
                form_view_initial_mode="edit",
                afg_skip_collapse=True,
            ),
        }

    @api.model
    def action_afg_ensure_standard_map(self):
        """Allocate unmapped CoA to preset AFG groups (same rules as working paper)."""
        self._setup_default_afg_presets()
        Version = self.env["audited.financial.version"]
        ver = Version.search([], limit=1, order="id desc")
        if ver:
            ver.action_auto_map_chart()
            ver._afg_mirror_schedule_mappings()
            return True
        groups = self.search([("company_id", "=", False), ("code", "!=", False)])
        code_to_group = {g.code: g for g in groups if g.code}
        ungrp = {"AFG_UNGRP_PL", "AFG_UNGRP_BS"}
        cids = list(self.env.context.get("allowed_company_ids") or self.env.companies.ids or [])
        domain = [("company_id", "in", cids)] if cids else []
        Account = self.env["account.account"].search(domain)
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        mapped = set(Line.search([("account_id", "in", Account.ids)]).mapped("account_id").ids)
        for acc in Account:
            if acc.id in mapped:
                continue
            code = _account_match_code(acc)
            target = code_to_group.get(code)
            if not target or (target.code or "") in ungrp:
                continue
            target._afg_add_unique_accounts(acc)
            mapped.add(acc.id)
        return True


class AuditedFinancialGroupAddLedgers(models.TransientModel):
    _name = "audited.financial.group.add.ledgers"
    _description = "AFG add unique ledgers"

    group_id = fields.Many2one(
        "audited.financial.group",
        ondelete="cascade",
    )
    ctf_category = fields.Selection(CTF_CATEGORY_SELECTION, string="CT Filing")
    coa_target_group_id = fields.Many2one(
        "account.group",
        string="Account group",
        ondelete="cascade",
    )
    search_ledger = fields.Char(
        string="Search",
        help="Filter by ledger name or account code (partial match).",
    )
    filter_type_id = fields.Many2one(
        "account.account.type",
        string="Type",
        help="Show only this account type.",
    )
    filter_group_id = fields.Many2one(
        "account.group",
        string="Group",
        help="Show only this COA group.",
    )
    select_all = fields.Boolean(string="Select all")
    selected_account_ids = fields.Many2many(
        "account.account",
        "afg_add_ledgers_wiz_selected_rel",
        "wizard_id",
        "account_id",
        string="Picked",
    )
    line_ids = fields.One2many(
        "audited.financial.group.add.ledgers.line",
        "wizard_id",
        string="Ledgers",
    )

    def _afg_remember_selected_accounts(self):
        self.ensure_one()
        kept = set(self.selected_account_ids.ids)
        visible = self.line_ids
        kept -= set(visible.filtered(lambda l: not l.selected).mapped("account_id").ids)
        kept |= set(visible.filtered("selected").mapped("account_id").ids)
        self.selected_account_ids = [(6, 0, list(kept))]
        return kept

    def _afg_load_pick_lines(self):
        self.ensure_one()
        kept = self._afg_remember_selected_accounts()
        self.line_ids.unlink()
        Account = self.env["account.account"].with_context(afg_unique_ledgers=1)
        domain = list(self.env["audited.financial.group"]._afg_line_ids_company_domain() or [])
        needle = (self.search_ledger or "").strip()
        if needle:
            domain.extend([
                "|",
                ("name", "ilike", needle),
                ("code", "ilike", needle),
            ])
        if self.filter_type_id:
            domain.append(("user_type_id", "=", self.filter_type_id.id))
        if self.filter_group_id:
            domain.append(("group_id", "=", self.filter_group_id.id))
        recs = Account.search(domain, order="user_type_id, group_id, name")
        Version = self.env["audited.financial.version"]
        mapped = set()
        if self.ctf_category:
            mapped = {
                Version._afg_pl_unique_ledger_key(acc)
                for acc in Account.search([("ctf_category", "=", self.ctf_category)])
            }
        elif self.coa_target_group_id:
            mapped = {
                Version._afg_pl_unique_ledger_key(acc)
                for acc in Account.search([("group_id", "=", self.coa_target_group_id.id)])
            }
        elif self.group_id:
            mapped = {
                Version._afg_pl_unique_ledger_key(l.account_id)
                for l in self.env["audited.financial.group.line"].with_context(
                    afg_skip_collapse=True
                ).search([("group_id", "=", self.group_id.id)])
            }
        cmds = []
        for acc in recs:
            key = Version._afg_pl_unique_ledger_key(acc)
            if key and key in mapped:
                continue
            cmds.append((0, 0, {
                "account_id": acc.id,
                "ledger_name": (acc.name or "").strip(),
                "user_type_id": acc.user_type_id.id,
                "coa_group_id": acc.group_id.id if acc.group_id else False,
                "selected": acc.id in kept,
            }))
        self.select_all = bool(cmds) and all(c[2].get("selected") for c in cmds)
        self.write({"line_ids": cmds, "select_all": self.select_all})
        return True

    def action_apply_ledger_filter(self):
        self.ensure_one()
        self._afg_load_pick_lines()
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_group_add_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Add ledgers"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }

    def action_clear_ledger_filter(self):
        self.ensure_one()
        self.write({
            "search_ledger": False,
            "filter_type_id": False,
            "filter_group_id": False,
        })
        return self.action_apply_ledger_filter()

    @api.onchange("select_all")
    def _onchange_select_all(self):
        for line in self.line_ids:
            line.selected = bool(self.select_all)

    def action_add(self):
        self.ensure_one()
        kept = self._afg_remember_selected_accounts()
        picked = self.env["account.account"].browse(list(kept)).exists()
        if not picked:
            raise UserError(_("Tick at least one ledger, then Add."))
        if self.ctf_category:
            picked.write({"ctf_category": self.ctf_category})
        elif self.coa_target_group_id:
            picked.write({"group_id": self.coa_target_group_id.id})
        elif self.group_id:
            self.group_id._afg_add_unique_accounts(picked)
        else:
            raise UserError(_("No AFG group, CT Filing category, or account group to add ledgers to."))
        return {"type": "ir.actions.act_window_close"}


class AuditedFinancialGroupAddLedgersLine(models.TransientModel):
    _name = "audited.financial.group.add.ledgers.line"
    _description = "AFG add ledger pick line"
    _order = "user_type_id, ledger_name, id"

    wizard_id = fields.Many2one(
        "audited.financial.group.add.ledgers",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string=" ")
    account_id = fields.Many2one("account.account", required=True, ondelete="cascade")
    ledger_code = fields.Char(
        related="account_id.code",
        string="Code",
        readonly=True,
    )
    ledger_name = fields.Char(string="Ledger")
    user_type_id = fields.Many2one("account.account.type", string="Type", readonly=True)
    coa_group_id = fields.Many2one("account.group", string="Group", readonly=True)


class AuditedFinancialCtfLedgers(models.TransientModel):
    _name = "audited.financial.ctf.ledgers"
    _description = "CT Filing category ledgers"

    category = fields.Selection(CTF_CATEGORY_SELECTION, required=True, readonly=True)
    account_ids = fields.Many2many(
        "account.account",
        "afg_ctf_ledgers_wiz_rel",
        "wizard_id",
        "account_id",
        string="Ledgers",
    )

    def action_remove_from_category(self):
        self.ensure_one()
        self.account_ids.write({"ctf_category": False})
        self.account_ids = [(5, 0, 0)]
        return True

    def action_open_add(self):
        self.ensure_one()
        wiz = self.env["audited.financial.group.add.ledgers"].create({
            "ctf_category": self.category,
        })
        wiz._afg_load_pick_lines()
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_group_add_ledgers_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Add ledgers"),
            "res_model": "audited.financial.group.add.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }


class AuditedFinancialGroupLine(models.Model):
    _name = "audited.financial.group.line"
    _description = "AFG Account Mapping Line"
    _order = "group_id, id"

    group_id = fields.Many2one("audited.financial.group", required=True, ondelete="cascade")
    group_code = fields.Char(related="group_id.code", string="Group code", store=True, readonly=True)
    account_id = fields.Many2one(
        "account.account",
        required=True,
        ondelete="cascade",
        domain=lambda self: self.env["audited.financial.group"]._afg_line_ids_company_domain(),
    )
    ledger_caption = fields.Char(
        string="Ledger",
        compute="_compute_ledger_caption",
        help="Ledger name only (no CoA code, no company).",
    )
    company_id = fields.Many2one(related="account_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Amount",
        compute="_compute_mapping_amount",
        currency_field="currency_id",
        help="Posted balance for the current AFG year "
             "(balance sheet: closing; P&amp;L: period movement). "
             "Use this to prioritise reclassifying ungrouped ledgers that still have amounts.",
    )
    target_group_id = fields.Many2one(
        "audited.financial.group",
        string="Target / correct group",
        help="Pick the AFG group this ungrouped account should belong to. "
             "Saving moves the mapping off Ungrouped.",
        ondelete="set null",
        copy=False,
    )

    def action_remove_from_afg_group(self):
        self.unlink()
        return True

    _sql_constraints = [
        (
            "audited_group_account_uniq",
            "unique(group_id, account_id)",
            "Each account can only appear once per AFG group.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        Version = self.env["audited.financial.version"]
        Account = self.env["account.account"]
        filtered = []
        keys_by_group = {}
        for vals in vals_list:
            gid = vals.get("group_id")
            aid = vals.get("account_id")
            if gid and aid:
                if gid not in keys_by_group:
                    keys_by_group[gid] = {
                        Version._afg_pl_unique_ledger_key(l.account_id)
                        for l in self.with_context(afg_skip_collapse=True).search(
                            [("group_id", "=", gid)]
                        )
                    }
                key = Version._afg_pl_unique_ledger_key(Account.browse(aid))
                if key and key in keys_by_group[gid]:
                    continue
                if key:
                    keys_by_group[gid].add(key)
            filtered.append(vals)
        if not filtered:
            return self.browse()
        return super().create(filtered)

    @api.depends("account_id", "account_id.name")
    def _compute_ledger_caption(self):
        Version = self.env["audited.financial.version"]
        for line in self:
            acc = line.account_id
            if not acc:
                line.ledger_caption = ""
                continue
            raw = (acc.name or "").strip()
            raw = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", raw)
            line.ledger_caption = raw or Version._afg_pl_unique_ledger_key(acc) or acc.code or ""

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if count or self.env.context.get("afg_skip_collapse"):
            return super().search(
                args, offset=offset, limit=limit, order=order, count=count
            )
        recs = super().search(args, offset=0, limit=None, order=order, count=False)
        groups = recs.mapped("group_id")
        if groups:
            groups.sudo().with_context(afg_skip_collapse=True)._afg_collapse_duplicate_mapping()
        return super().search(
            args, offset=offset, limit=limit, order=order, count=False
        )

    @api.model
    def _afg_ungrouped_codes(self):
        return ("AFG_UNGRP_PL", "AFG_UNGRP_BS")

    def _afg_mapping_period_for_company(self, company_id):
        """Return (date_from, date_to) for mapping Amount — prefer that company's AFG version."""
        Version = self.env["audited.financial.version"]
        ver = Version.search(
            [("company_id", "=", company_id)],
            limit=1,
            order="write_date desc, id desc",
        )
        if not ver:
            ver = Version.search(
                [("company_ids", "in", [company_id])],
                limit=1,
                order="write_date desc, id desc",
            )
        if ver:
            return ver.date_from_current, ver.date_to_current
        dv = _afg_default_period_vals()
        return dv["date_from_current"], dv["date_to_current"]

    def _afg_mapping_scope_cids(self, line):
        """Companies to summarise: group.company_id, else the company switcher."""
        group = line.group_id
        if group and group.company_id:
            return [int(group.company_id.id)]
        cids = list(self.env.context.get("allowed_company_ids") or [])
        if not cids:
            cids = list(self.env.companies.ids) if self.env.companies else []
        if not cids and line.company_id:
            cids = [int(line.company_id.id)]
        return [int(c) for c in cids if c]

    @api.depends("account_id", "group_id", "group_id.report_section", "group_id.company_id", "company_id")
    def _compute_mapping_amount(self):
        """One mapping line = unique ledger; amount is TB sum in scope companies."""
        for line in self:
            line.amount = 0.0
        lines = self.filtered(lambda l: l.account_id and l.account_id.exists())
        if not lines:
            return

        Version = self.env["audited.financial.version"]
        ver_proxy = Version.search([], limit=1) or Version.new({})
        by_bucket = defaultdict(list)
        for line in lines:
            cids = tuple(self._afg_mapping_scope_cids(line))
            section = (line.group_id.report_section if line.group_id else "bs") or "bs"
            use_closing = section in ("bs", "equity", "fixed_assets")
            by_bucket[(cids, use_closing)].append(line)

        for (cids, use_closing), bucket in by_bucket.items():
            if not cids:
                continue
            date_from, date_to = self._afg_mapping_period_for_company(cids[0])
            cid_list = list(cids)
            if use_closing:
                tb = ver_proxy._fetch_tb_coa_stock(date_to, cid_list, fy_anchor_date=date_from)
            else:
                tb = ver_proxy._fetch_tb(date_from, date_to, cid_list)
            for line in bucket:
                aids = ver_proxy._tb_account_ids_for_group_line(line, cid_list)
                line.amount = sum(float(tb.get(aid, 0.0) or 0.0) for aid in aids)

    def _afg_apply_target_group(self, target_group):
        """Move this mapping line onto ``target_group`` (used from Ungrouped review)."""
        self.ensure_one()
        if not target_group:
            return True
        if target_group.id == self.group_id.id:
            return self.write({"target_group_id": False})
        if target_group.code in self._afg_ungrouped_codes():
            raise UserError(_(
                "Choose a real AFG group (not Ungrouped) for account %s."
            ) % (self.account_id.display_name or self.account_id.name or ""))
        Line = self.env["audited.financial.group.line"]
        existing = Line.search([
            ("group_id", "=", target_group.id),
            ("account_id", "=", self.account_id.id),
            ("id", "!=", self.id),
        ], limit=1)
        if existing:
            # Already on the correct group — drop the ungrouped duplicate
            return self.unlink()
        return super(AuditedFinancialGroupLine, self).write({
            "group_id": target_group.id,
            "target_group_id": False,
        })

    def write(self, vals):
        vals = dict(vals or {})
        if "target_group_id" not in vals:
            return super().write(vals)
        target_id = vals.pop("target_group_id")
        Target = self.env["audited.financial.group"]
        target_rec = Target.browse(int(target_id)) if target_id else Target.browse()
        for line in self:
            if target_rec:
                line._afg_apply_target_group(target_rec)
            else:
                super(AuditedFinancialGroupLine, line).write({"target_group_id": False})
        if vals:
            return super().write(vals)
        return True


class AuditedFinancialVersion(models.Model):
    _name = "audited.financial.version"
    _description = "Audited Financials Working Version"
    _order = "write_date desc, id desc"

    def _afg_ctf_label(self, code, fallback):
        Group = self.env["audited.financial.ctf.group"].sudo()
        labels = Group.get_label_map() if hasattr(Group, "get_label_map") else {}
        return labels.get(code) or fallback

    name = fields.Char(required=True, default=lambda self: _("Draft %s") % fields.Date.context_today(self))
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    branch_company_id = fields.Many2one(
        "res.company",
        string="Branch (company filter)",
        help="When set, trial balance is restricted to this company. For multi-company books, pick the reporting entity.",
    )
    company_ids = fields.Many2many(
        "res.company",
        "audited_financial_version_company_rel",
        "version_id",
        "company_id",
        string="Consolidated companies",
        help="Include posted moves from all listed companies (leave empty to use primary company only).",
    )
    report_column_company_ids = fields.Many2many(
        "res.company",
        "audited_financial_version_report_col_rel",
        "version_id",
        "company_id",
        string="Companies on statement columns",
        help="Advanced: which companies appear as extra columns in some exports or form views. "
        "The dashboard shows two year columns (prior and current) for the active company only.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.ref("base.AED", raise_if_not_found=False) or self.env.company.currency_id,
    )
    year_current = fields.Integer(
        string="Current year",
        required=True,
        default=lambda self: _afg_default_period_vals()["year_current"],
    )
    year_prior = fields.Integer(
        string="Prior year",
        required=True,
        default=lambda self: _afg_default_period_vals()["year_prior"],
    )
    period_preset = fields.Selection(
        [
            ("years", "Last 2 calendar years"),
            ("mom", "Last 2 months"),
            ("yoy_month", "Same month year-over-year"),
            ("custom", "Custom period"),
        ],
        string="Period preset",
        default="years",
        required=True,
        help="Dashboard comparative window. Default stays last two full calendar years.",
    )
    date_from_current = fields.Date(string="Current period start", required=True)
    date_to_current = fields.Date(string="Current period end", required=True)
    date_from_prior = fields.Date(string="Prior period start", required=True)
    date_to_prior = fields.Date(string="Prior period end", required=True)
    data_state = fields.Selection(
        [
            ("empty", "No posted journal data"),
            ("posted", "Loaded from posted journals"),
            ("sample", "Sample preview data"),
        ],
        string="Data source",
        default="empty",
        readonly=True,
    )
    state = fields.Selection([("draft", "Draft"), ("saved", "Saved")], default="draft", index=True)
    edit_mode = fields.Boolean(string="Edit mode", default=False)
    print_max_level = fields.Integer(
        string="Report level (L1–L4)",
        default=3,
        help="Report pack: 1=Official (types+AFG), 2=Management with Type (type→ledger), "
             "3=Detailed with Group (AFG→account.group→ledger), 4=Working Papers (AFG→ledger + TB). "
             "Controls dashboard/PDF visibility only — one reporting engine. "
             "Legacy hierarchy depths 0–5 are migrated to packs on read.",
    )
    print_years_descending = fields.Boolean(
        string="Export year columns descending",
        default=False,
        help="When True, amount columns show current year first. "
             "Default False = prior then current (e.g. 2024 then 2025), matching AFG Column ascending.",
    )
    internal_action_notes = fields.Text(
        string="Internal notes / actions",
        help="Working-paper checklist: missing items and next actions. Not printed on L1 Official PDF.",
    )
    print_page_setup = fields.Selection(
        [
            ("default", "Default"),
            ("skip_empty", "Skip empty pages"),
            ("compact", "Compact header/footer + skip empty"),
        ],
        string="Page setup",
        default="default",
        help="Print layout: skip blank statement pages; compact tightens header/footer spacing.",
    )
    print_company_name = fields.Char(
        string="Print company name",
        help="Overrides company name on PDF / Excel / Word headers. Empty = legal company name.",
    )
    print_show_page_numbers = fields.Boolean(
        string="Show page numbers",
        default=False,
        help="When False (default), PDF has no page numbers. Toggle from Print Setup.",
    )
    print_exclude_keys = fields.Char(
        string="Print exclude page keys",
        help="Comma-separated chapter keys to skip (e.g. fta). Empty = include all pages.",
    )
    line_ids = fields.One2many("audited.financial.line", "version_id", string="Lines")
    note_ids = fields.One2many("audited.financial.note", "version_id", string="Notes")
    alert_ids = fields.One2many("audited.financial.alert", "version_id", string="Alerts")
    log_ids = fields.One2many("audited.financial.edit.log", "version_id", string="Edit log", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        dv = _afg_default_period_vals()
        for key, val in dv.items():
            res.setdefault(key, val)
        return res

    @api.onchange("year_current", "year_prior")
    def _onchange_years_set_dates(self):
        for rec in self:
            if rec.year_current:
                rec.date_from_current = fields.Date.from_string("%s-01-01" % rec.year_current)
                rec.date_to_current = fields.Date.from_string("%s-12-31" % rec.year_current)
            if rec.year_prior:
                rec.date_from_prior = fields.Date.from_string("%s-01-01" % rec.year_prior)
                rec.date_to_prior = fields.Date.from_string("%s-12-31" % rec.year_prior)
            rec.period_preset = "years"

    def _afg_period_label_prior(self):
        self.ensure_one()
        return _afg_format_period_label(self.date_from_prior, self.date_to_prior) or str(self.year_prior or "")

    def _afg_period_label_current(self):
        self.ensure_one()
        return _afg_format_period_label(self.date_from_current, self.date_to_current) or str(self.year_current or "")

    def _afg_switchboard_short_name_enabled(self):
        self.env.user.company_ids  # touch ACL
        return self.env["ir.config_parameter"].sudo().get_param(
            "cpabooks_settings_extend.show_short_name_in_switchboard",
        ) == "True"

    def _afg_company_column_header(self, company):
        """Compact header for company columns (multi-co report short name first)."""
        company = company.sudo()
        if hasattr(company, "cpabooks_multico_report_column_label"):
            return company.cpabooks_multico_report_column_label()
        multico = (getattr(company, "cpabooks_multico_report_short_name", None) or "").strip()
        if multico:
            return multico
        if self._afg_switchboard_short_name_enabled() and getattr(
            company, "cpabooks_show_in_switchboard", False
        ):
            short = (getattr(company, "switchboard_name", None) or "").strip()
            if short:
                return short
        name = (company.name or "").strip()
        return (name[:10] if name else "") or (company.display_name or "")

    def _afg_company_title_label(self, company):
        """Subtitle next to report title — follows per-company switchboard setting."""
        company = company.sudo()
        if hasattr(company, "cpabooks_switchboard_display_name"):
            return company.cpabooks_switchboard_display_name()
        return company.display_name or ""

    def _afg_column_company_order(self):
        self.ensure_one()
        full = [int(x) for x in self._tb_company_ids()]
        if not full:
            return []
        allowed = set(full)
        cols = [int(c) for c in self.report_column_company_ids.ids if int(c) in allowed]
        # Empty selection = show every branch in TB order (all companies selected by default).
        return cols if cols else list(full)

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_afg_col_sync"):
            return res
        if "company_ids" in vals:
            for ver in self:
                allowed = set(ver.company_ids.ids)
                cur = [int(c) for c in ver.report_column_company_ids.ids if int(c) in allowed]
                ver.with_context(skip_afg_col_sync=True).write({
                    "report_column_company_ids": [(6, 0, cur)],
                })
        return res

    @api.model
    def _afg_allowed_company_ids_from_context(self):
        """Parse ``allowed_company_ids`` from env.context (list, tuple, int, or comma-separated string).

        Some RPC paths send a string like ``"1,2,3"``; iterating it as a list of ints fails and
        would otherwise fall back to a single company.
        """
        user_ok = set(self.env.user.company_ids.ids)
        raw = self.env.context.get("allowed_company_ids")
        if raw in (None, False, ""):
            return []
        candidates = []
        if isinstance(raw, (list, tuple)):
            candidates.extend(raw)
        elif isinstance(raw, int):
            candidates.append(raw)
        elif isinstance(raw, str):
            chunk = raw.replace("[", "").replace("]", "").strip()
            for part in chunk.split(","):
                p = part.strip()
                if not p:
                    continue
                try:
                    candidates.append(int(p))
                except ValueError:
                    continue
        else:
            try:
                candidates.append(int(raw))
            except (TypeError, ValueError):
                return []
        out = []
        for x in candidates:
            try:
                cid = int(x)
            except (TypeError, ValueError):
                continue
            if cid in user_ok:
                out.append(cid)
        return sorted(set(out))

    def _tb_company_ids(self):
        """Companies that drive TB / rebuild.

        Order: branch filter → active ``allowed_company_ids`` (systray) →
        version *Consolidated companies* → primary ``company_id``.

        Switcher context wins so multi-select updates amounts without being
        narrowed by a stale single-company ``company_ids`` list.
        """
        self.ensure_one()
        if self.branch_company_id:
            return [int(self.branch_company_id.id)]

        user_cos = set(self.env.user.company_ids.ids)
        ctx_list = self.env["audited.financial.version"]._afg_allowed_company_ids_from_context()
        if ctx_list:
            return ctx_list

        if self.company_ids:
            base = [int(c) for c in self.company_ids.ids if c in user_cos]
            if base:
                return base
        if self.company_id:
            return [int(self.company_id.id)]
        return []

    @api.model
    def _afg_mirror_schedule_mappings(self):
        """Copy global AFG mappings so schedule-only sections receive accounts.

        Auto-map assigns each account to a single primary group; PPE goes to the
        balance sheet group but not to *Fixed assets register* / *Cash flow* /
        *Equity changes* unless we mirror mappings.
        """
        Group = self.env["audited.financial.group"].sudo()
        Line = self.env["audited.financial.group.line"].sudo()

        def group_by_code(code):
            return Group.search([("code", "=", code), ("company_id", "=", False)], limit=1)

        def copy_accounts(src_code, dst_code):
            src_g = group_by_code(src_code)
            dst_g = group_by_code(dst_code)
            if not src_g or not dst_g:
                return
            existing = set(Line.search([("group_id", "=", dst_g.id)]).mapped("account_id").ids)
            for gl in Line.search([("group_id", "=", src_g.id)]):
                aid = gl.account_id.id
                if not aid or aid in existing:
                    continue
                Line.create({"group_id": dst_g.id, "account_id": aid})
                existing.add(aid)

        copy_accounts("AFG_PPE", "AFG_FIXED")
        copy_accounts("AFG_EQ", "AFG_EQ_CHG")
        # Working cash-flow classification: key working-capital and BS drivers
        cf_dest = group_by_code("AFG_CF")
        if cf_dest:
            existing_cf = set(Line.search([("group_id", "=", cf_dest.id)]).mapped("account_id").ids)
            for code in (
                "AFG_CASH",
                "AFG_AR",
                "AFG_AP",
                "AFG_EQ",
                "AFG_INV",
                "AFG_PREP",
                "AFG_PPE",
                "AFG_TAX",
                "AFG_REL",
                "AFG_EOS",
            ):
                src_g = group_by_code(code)
                if not src_g:
                    continue
                for gl in Line.search([("group_id", "=", src_g.id)]):
                    aid = gl.account_id.id
                    if not aid or aid in existing_cf:
                        continue
                    Line.create({"group_id": cf_dest.id, "account_id": aid})
                    existing_cf.add(aid)

    def _afg_account_label(self, account):
        """Label without multicompany suffix (display_name often appends company)."""
        account.ensure_one()
        code = (account.code or "").strip()
        name = (account.name or "").strip()
        if code and name:
            return "%s %s" % (code, name)
        return name or code or _("(no name)")

    def _afg_ledger_name_is_placeholder(self, name):
        n = (name or "").strip()
        if not n:
            return True
        if re.match(r"^x{2,}$", n, flags=re.I):
            return True
        return n.lower() in ("n/a", "na", "test", "dummy", "tbd", "-", "xx", "xxx", "xxxx")

    def _afg_pick_l3_representative(self, aids, Account=None):
        """Prefer a real CoA name over placeholder names (XXXX) when codes merge."""
        Account = Account or self._afg_account_sudo()
        recs = Account.browse([int(a) for a in (aids or []) if a]).exists()
        if not recs:
            return Account.browse()
        prefer = self.env.company.id if self.env.company else 0

        def _score(acc):
            name = (acc.name or "").strip()
            real = 0 if self._afg_ledger_name_is_placeholder(name) else 1
            return (real, 1 if acc.company_id.id == prefer else 0, len(name), acc.id)

        return max(list(recs), key=_score)

    def _afg_group_label(self, group):
        if not group:
            return _("Ungrouped ledgers")
        group.ensure_one()
        return (group.name or "").strip() or (group.display_name or _("Account group"))

    def _afg_odoo_group_code_prefix(self, group):
        """Short code label for account.group (CoA range prefix)."""
        if not group:
            return ""
        if group.code_prefix_start:
            if group.code_prefix_end and group.code_prefix_end != group.code_prefix_start:
                return "%s-%s" % (group.code_prefix_start, group.code_prefix_end)
            return group.code_prefix_start or ""
        return ""

    def _afg_line_branch_codes(self, line):
        """Structured codes/captions for dashboard toggles (group vs ledger)."""
        res = {
            "group_code": "",
            "group_caption": "",
            "ledger_code": "",
            "ledger_caption": "",
            "drill_account_ids": [],
            "report_section": line.report_section or "pl",
        }
        if line.level == 2:
            res["group_caption"] = (line.label or "").strip()
            if line.odoo_group_id:
                res["group_code"] = self._afg_odoo_group_code_prefix(line.odoo_group_id.sudo())
        elif line.level == 3:
            acc_ids = self._line_leaf_account_ids(line)
            res["drill_account_ids"] = acc_ids
            pick_ids = list(acc_ids or [])
            if line.account_id:
                pick_ids.append(line.account_id.id)
            acc = self._afg_pick_l3_representative(pick_ids)
            if acc:
                res["ledger_code"] = (acc.code or "").strip()
                res["ledger_caption"] = (acc.name or "").strip()
        return res

    def _afg_normalized_ledger_name(self, account):
        """Lowercase ledger name with whitespace collapsed (aligned with multicompany P&amp;L aml merge)."""
        account.ensure_one()
        return self._afg_normalize_caption(account.name)

    def _afg_pl_unique_ledger_key(self, account):
        """Same unique-ledger key as P&amp;L Default View (name only; strip trailing (Type))."""
        if not account:
            return ""
        name = (account.name or "").strip()
        name = re.sub(r"^[|\s]+", "", name)
        name = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", name)
        name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
        name = re.sub(r"\s+", " ", name)
        return name.lower()

    def _afg_pl_unique_ledger_buckets(self, tb_prior, tb_curr, company_ids):
        """One bucket per Default P&L unique ledger name (all companies summed)."""
        Account = self._afg_account_sudo()
        tb_prior = tb_prior or {}
        tb_curr = tb_curr or {}
        prefer = int(self.env.company.id) if self.env.company else 0
        buckets = {}
        aids = set()
        for raw in list(tb_prior.keys()) + list(tb_curr.keys()):
            try:
                aids.add(int(raw))
            except (TypeError, ValueError):
                continue
        for aid in aids:
            acc = Account.browse(aid)
            if not acc.exists():
                continue
            ig = (acc.internal_group or "").strip()
            if not ig and acc.user_type_id:
                ig = (acc.user_type_id.internal_group or "").strip()
            if ig not in ("income", "expense"):
                continue
            key = self._afg_pl_unique_ledger_key(acc) or ("id:%s" % aid)
            b = buckets.get(key)
            if not b:
                b = {
                    "key": key,
                    "aids": [],
                    "prior": 0.0,
                    "curr": 0.0,
                    "rep": acc,
                }
                buckets[key] = b
            if aid not in b["aids"]:
                b["aids"].append(aid)
            b["prior"] += float(tb_prior.get(aid, 0.0) or 0.0)
            b["curr"] += float(tb_curr.get(aid, 0.0) or 0.0)
            if acc.company_id.id == prefer and b["rep"].company_id.id != prefer:
                b["rep"] = acc
        out = []
        for b in buckets.values():
            if abs(b["prior"]) < 0.005 and abs(b["curr"]) < 0.005:
                continue
            name = (b["rep"].name or "").strip()
            name = re.sub(r"^[|\s]+", "", name)
            name = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", name)
            b["label"] = name or self._afg_account_label(b["rep"])
            out.append(b)
        return out

    def _afg_group_for_pl_bucket(self, bucket, code_to_group, ungrp_pl):
        """Map one unique P&L ledger onto an AFG group (mapping, then prefix/keyword)."""
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        ungrp = set(Line._afg_ungrouped_codes())
        lines = Line.search([("account_id", "in", bucket["aids"])])
        real = lines.filtered(
            lambda l: l.group_id
            and (l.group_id.code or "") not in ungrp
            and (l.group_id.report_section or "") == "pl"
        )
        if real:
            return real[0].group_id
        acc = bucket.get("rep")
        code = _account_match_code(acc) if acc else None
        grp = code_to_group.get(code) if code else None
        return grp or ungrp_pl

    def _afg_build_pl_ledger_key_map(self, company_ids):
        """account.account ids keyed like P&amp;L unique ledger names.

        Include foreign-company CoA rows if this company's journal items posted
        on them (BRB P&amp;L Sub-Contractor Cost uses ABDUL HASEEB ledger 5338).
        """
        company_ids = [int(c) for c in (company_ids or []) if c]
        mapping = defaultdict(list)
        if not company_ids:
            return {}
        Account = self._afg_account_sudo()
        seen = set()
        for acc in Account.search([("company_id", "in", company_ids)]):
            seen.add(acc.id)
            key = self._afg_pl_unique_ledger_key(acc)
            if key:
                mapping[key].append(acc.id)
        self.env.cr.execute(
            """
            SELECT DISTINCT aml.account_id
              FROM account_move_line aml
             WHERE aml.company_id IN %s
               AND aml.account_id IS NOT NULL
            """,
            (tuple(company_ids),),
        )
        extra_ids = [int(row[0]) for row in self.env.cr.fetchall() if row and row[0]]
        extra_ids = [i for i in extra_ids if i not in seen]
        for acc in Account.browse(extra_ids).exists():
            key = self._afg_pl_unique_ledger_key(acc)
            if key:
                mapping[key].append(acc.id)
        return dict(mapping)

    def _afg_normalize_caption(self, text):
        """Collapse whitespace / case for multicompany same-name merges."""
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _afg_bucket_l3_leaf_accounts(self, aids_merged, Account, merge_same_ledger_name_multicompany=False):
        """Split L2 account ids into L3 buckets (one export/dashboard ledger row each).

        Critical: **never** merge two different ``account.account`` rows of the *same*
        company just because they share a code (CPABooks charts often reuse codes
        like 1103 / 5470 for unrelated ledgers). That double-counted P&amp;L/BS vs Odoo.

        Cross-company merge on identical code is only for true multicompany charts
        (one ledger per code per company).
        """
        if not aids_merged:
            return []
        aids_merged = Account.browse(aids_merged).exists().ids
        if not aids_merged:
            return []

        def _one_per_account(aids):
            return [[aid] for aid in sorted(set(aids))]

        # Bucket by code (or name when code empty)
        by_code = defaultdict(list)
        for aid in aids_merged:
            acc = Account.browse(aid)
            code = (acc.code or "").strip()
            if code:
                by_code[("code", code)].append(aid)
            else:
                by_code[("name", self._afg_normalized_ledger_name(acc))].append(aid)

        merged_groups = []
        for _key, aids in sorted(by_code.items(), key=lambda kv: kv[0]):
            aids = sorted(set(aids))
            if not aids:
                continue
            by_company = defaultdict(list)
            for aid in aids:
                by_company[Account.browse(aid).company_id.id].append(aid)

            if len(by_company) <= 1:
                # Same company: always one L3 per account id (duplicate codes stay separate)
                merged_groups.extend(_one_per_account(aids))
                continue

            # Multiple companies sharing this code/name
            conflict = any(len(set(v)) > 1 for v in by_company.values())
            if conflict:
                # A company has two accounts with the same code — never fold them
                merged_groups.extend(_one_per_account(aids))
                continue

            # One account per company → single multicompany L3 line
            cross = sorted({aid for v in by_company.values() for aid in v})
            if merge_same_ledger_name_multicompany or len(cross) > 1:
                merged_groups.append(cross)
            else:
                merged_groups.extend(_one_per_account(cross))

        # Fold same normalized *name* across different codes (multi-company charts).
        # One account per company with that name → single L3. Same-company duplicate
        # names with different codes stay separate (never fold same-company conflicts).
        if merge_same_ledger_name_multicompany and len(merged_groups) > 1:
            by_norm = defaultdict(list)
            for grp in merged_groups:
                acc0 = Account.browse(grp[0])
                by_norm[self._afg_normalized_ledger_name(acc0)].append(grp)
            folded = []
            for _nm, grps in by_norm.items():
                if len(grps) == 1:
                    folded.extend(grps)
                    continue
                all_aids = [a for g in grps for a in g]
                by_company = defaultdict(list)
                for aid in all_aids:
                    by_company[Account.browse(aid).company_id.id].append(aid)
                if any(len(set(v)) > 1 for v in by_company.values()):
                    folded.extend(grps)
                elif len(by_company) > 1:
                    folded.append(sorted(set(all_aids)))
                else:
                    folded.extend(grps)
            merged_groups = folded

        # Same unique name as P&L Default View — one L3 even in one company.
        by_pl = defaultdict(list)
        for grp in merged_groups:
            acc0 = Account.browse(grp[0])
            pl_key = self._afg_pl_unique_ledger_key(acc0)
            by_pl[pl_key or ("__id__", grp[0])].append(grp)
        folded_pl = []
        for _pk, grps in by_pl.items():
            if len(grps) == 1:
                folded_pl.append(grps[0])
            else:
                folded_pl.append(sorted(set(a for g in grps for a in g)))
        merged_groups = folded_pl

        merged_groups.sort(
            key=lambda aids: (
                (Account.browse(aids[0]).code or "").strip(),
                Account.browse(aids[0]).name or "",
                aids[0],
            )
        )
        return merged_groups

    def _tb_account_ids_for_group_line(self, group_line, company_ids):
        """Map one configured account into TB companies.

        Same company: use the exact mapped account only (duplicate CoA codes like two
        ``1103`` rows must not pull each other — that double-counted Petty Cash into AR).
        Other companies: match by code for multicompany consolidation.
        """
        Account = self._afg_account_sudo()
        acc = group_line.account_id
        company_ids = list(company_ids or [])
        if not acc:
            return []
        acc = Account.browse(acc.id)
        if not acc.exists() or not company_ids:
            return []
        result = []
        if acc.company_id and acc.company_id.id in company_ids:
            result.append(acc.id)
        elif not acc.company_id:
            result.append(acc.id)
        if acc.code and acc.company_id:
            others = Account.search([
                ("company_id", "in", company_ids),
                ("company_id", "!=", acc.company_id.id),
                ("code", "=", acc.code),
            ])
            result.extend(others.ids)
        # P&L Default View merges every ledger with the same unique name
        # (same company, different codes). Pull those in automatically.
        pl_key = self._afg_pl_unique_ledger_key(acc)
        by_key = self.env.context.get("afg_pl_ledger_ids_by_key")
        if pl_key and by_key is not None:
            result.extend(by_key.get(pl_key) or [])
        elif pl_key:
            for aid in (self._afg_build_pl_ledger_key_map(company_ids).get(pl_key) or []):
                result.append(aid)
        return sorted(set(int(x) for x in result if x))

    def _fetch_tb(self, date_from, date_to, company_ids):
        """Posted journal balances by account — period movement (sum in date range)."""
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids or not date_from or not date_to:
            return {}
        domain = [
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("parent_state", "=", "posted"),
            ("company_id", "in", company_ids),
        ]
        MoveLine = self.env["account.move.line"].with_context(allowed_company_ids=company_ids)
        groups = MoveLine.read_group(domain, ["balance"], ["account_id"], lazy=False)
        result = {}
        for row in groups:
            acc = row.get("account_id")
            if not acc:
                continue
            aid = acc[0]
            result[aid] = float(row.get("balance") or 0.0)
        return result

    def _fetch_tb_closing(self, date_to, company_ids):
        """Closing balance per account at date_to (cumulative posted, date &lt;= date_to). For BS / SOFP."""
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids or not date_to:
            return {}
        domain = [
            ("date", "<=", date_to),
            ("parent_state", "=", "posted"),
            ("company_id", "in", company_ids),
        ]
        MoveLine = self.env["account.move.line"].with_context(allowed_company_ids=company_ids)
        groups = MoveLine.read_group(domain, ["balance"], ["account_id"], lazy=False)
        result = {}
        for row in groups:
            acc = row.get("account_id")
            if not acc:
                continue
            aid = acc[0]
            result[aid] = float(row.get("balance") or 0.0)
        return result

    def _tb_fiscalyear_start(self, company, as_of_date):
        """Fiscal-year start for ``as_of_date`` (same helper Accounting GL / CoA TB uses)."""
        company = company.exists() and company or self.env.company
        as_of = fields.Date.to_date(as_of_date)
        return company.compute_fiscalyear_dates(as_of)["date_from"]

    def _fetch_tb_unaffected_earnings(self, fy_date_from, company_ids):
        """P&L before FY start — Accounting ``account.general.ledger`` unaffected earnings.

        Domain matches ``_get_options_unaffected_earnings``:
        date &lt;= fy_date_from - 1 on accounts with ``include_initial_balance`` = False.
        """
        company_ids = [int(c) for c in (company_ids or []) if c]
        fy_date_from = fields.Date.to_date(fy_date_from)
        if not company_ids or not fy_date_from:
            return {}
        date_to = fy_date_from - timedelta(days=1)
        domain = [
            ("date", "<=", date_to),
            ("parent_state", "=", "posted"),
            ("company_id", "in", company_ids),
            ("account_id.user_type_id.include_initial_balance", "=", False),
        ]
        MoveLine = self.env["account.move.line"].with_context(allowed_company_ids=company_ids)
        groups = MoveLine.read_group(domain, ["balance"], ["company_id"], lazy=False)
        result = {}
        for row in groups:
            cid = row.get("company_id")
            if not cid:
                continue
            result[int(cid[0] if isinstance(cid, (list, tuple)) else cid)] = float(
                row.get("balance") or 0.0
            )
        return result

    def _tb_unaffected_earnings_account_ids(self, company_ids):
        """First Current Year Earnings account per company (GL CoA injection target)."""
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids:
            return {}
        try:
            ue_type = self.env.ref("account.data_unaffected_earnings")
        except ValueError:
            return {}
        Account = self._afg_account_sudo()
        accounts = Account.search(
            [
                ("user_type_id", "=", ue_type.id),
                ("company_id", "in", company_ids),
            ],
            order="company_id, id",
        )
        by_cid = {}
        for acc in accounts:
            cid = int(acc.company_id.id)
            if cid not in by_cid:
                by_cid[cid] = int(acc.id)
        return by_cid

    def _fetch_tb_coa_stock(self, date_to, company_ids, fy_anchor_date=None):
        """Per-account stock matching Accounting → Trial Balance (``account.coa.report``).

        Uses the same rules as ``account.general.ledger`` ``_do_query`` sums:
        - BS (``include_initial_balance``): all posted lines with date &lt;= date_to
        - P&L (not include_initial_balance): only lines in [FY start, date_to]
        - Unaffected earnings (P&L before FY) injected onto Current Year Earnings
        """
        company_ids = [int(c) for c in (company_ids or []) if c]
        date_to = fields.Date.to_date(date_to)
        if not company_ids or not date_to:
            return {}
        fy_anchor = fields.Date.to_date(fy_anchor_date or date_to)
        result = {}
        MoveLine = self.env["account.move.line"].with_context(allowed_company_ids=company_ids)
        Company = self.env["res.company"]

        for cid in company_ids:
            company = Company.browse(cid)
            fy_start = self._tb_fiscalyear_start(company, fy_anchor)
            # Balance-sheet / equity stock accounts
            groups_bs = MoveLine.read_group(
                [
                    ("date", "<=", date_to),
                    ("parent_state", "=", "posted"),
                    ("company_id", "=", cid),
                    ("account_id.user_type_id.include_initial_balance", "=", True),
                ],
                ["balance"],
                ["account_id"],
                lazy=False,
            )
            for row in groups_bs:
                acc = row.get("account_id")
                if not acc:
                    continue
                result[acc[0]] = float(result.get(acc[0], 0.0)) + float(row.get("balance") or 0.0)
            # P&L within the fiscal year only (Opening on income/expense stays nil)
            if fy_start <= date_to:
                groups_pnl = MoveLine.read_group(
                    [
                        ("date", ">=", fy_start),
                        ("date", "<=", date_to),
                        ("parent_state", "=", "posted"),
                        ("company_id", "=", cid),
                        ("account_id.user_type_id.include_initial_balance", "=", False),
                    ],
                    ["balance"],
                    ["account_id"],
                    lazy=False,
                )
                for row in groups_pnl:
                    acc = row.get("account_id")
                    if not acc:
                        continue
                    result[acc[0]] = float(result.get(acc[0], 0.0)) + float(
                        row.get("balance") or 0.0
                    )

        # Per-company unaffected earnings → Current Year Earnings (GL / CoA TB)
        ue_target = self._tb_unaffected_earnings_account_ids(company_ids)
        for cid in company_ids:
            company = Company.browse(cid)
            fy_start = self._tb_fiscalyear_start(company, fy_anchor)
            ue_map = self._fetch_tb_unaffected_earnings(fy_start, [cid])
            ue_bal = float(ue_map.get(cid, 0.0) or 0.0)
            if abs(ue_bal) < 1e-9:
                continue
            aid = ue_target.get(cid)
            if not aid:
                continue
            result[aid] = float(result.get(aid, 0.0)) + ue_bal
        return result

    def _tb_coa_maps_by_cid(self, cids):
        """Opening / closing_prior / closing_current maps — Accounting CoA Trial Balance rules."""
        self.ensure_one()
        cids = [int(c) for c in (cids or []) if c]
        opening_date = self._tb_opening_date()
        maps = {"opening": {}, "closing_prior": {}, "closing_current": {}}
        for cid in cids:
            maps["opening"][cid] = self._fetch_tb_coa_stock(
                opening_date, [cid], fy_anchor_date=self.date_from_prior
            )
            maps["closing_prior"][cid] = self._fetch_tb_coa_stock(
                self.date_to_prior, [cid], fy_anchor_date=self.date_from_prior
            )
            maps["closing_current"][cid] = self._fetch_tb_coa_stock(
                self.date_to_current, [cid], fy_anchor_date=self.date_from_current
            )
        return maps

    def _section_uses_closing_balance(self, section):
        return section in ("bs", "equity", "fixed_assets")

    def _tb_prior_curr_per_company(self, use_closing):
        """Return (two dicts: company_id -> account_id -> balance) for prior & current dates.

        Closing / SOFP / equity use Accounting CoA stock (``include_initial_balance`` +
        unaffected earnings on Current Year Earnings) so Undistributed / UE is not left at 0.
        """
        self.ensure_one()
        cids = self._tb_company_ids()
        if not cids:
            return {}, {}
        if use_closing:
            return (
                {
                    int(cid): self._fetch_tb_coa_stock(
                        self.date_to_prior, [cid], fy_anchor_date=self.date_from_prior
                    )
                    for cid in cids
                },
                {
                    int(cid): self._fetch_tb_coa_stock(
                        self.date_to_current, [cid], fy_anchor_date=self.date_from_current
                    )
                    for cid in cids
                },
            )
        return (
            {int(cid): self._fetch_tb(self.date_from_prior, self.date_to_prior, [cid]) for cid in cids},
            {int(cid): self._fetch_tb(self.date_from_current, self.date_to_current, [cid]) for cid in cids},
        )

    def _line_leaf_account_ids(self, line):
        self.ensure_one()
        if line.level == 3:
            raw = []
            # Guard: account may have been deleted (Factory Reset) while line still points at it
            if line.account_id and line.account_id.exists():
                raw.append(line.account_id.id)
            extra = (line.merged_leaf_account_ids or "").strip()
            if extra:
                for x in extra.split(","):
                    x = x.strip()
                    if x.isdigit():
                        raw.append(int(x))
            if not raw:
                return []
            return sorted(self.env["account.account"].browse(raw).exists().ids)
        ids = []
        for ch in line.child_ids.sorted(lambda s: (s.sequence, s.id)):
            ids.extend(self._line_leaf_account_ids(ch))
        return ids

    @api.model
    def _afg_scrub_orphan_account_refs(self):
        """Remove AFG mapping / working lines that still point at deleted account.account rows.

        After COA Factory Reset, stale account ids (e.g. 5382) can break Audited Financials
        open with Missing Record.
        """
        cr = self.env.cr
        # Mapping lines (shared AFG presets)
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
        # Working paper leaf accounts
        cr.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                 WHERE table_name = 'audited_financial_line'
            )
            """
        )
        if cr.fetchone()[0]:
            cr.execute(
                """
                UPDATE audited_financial_line
                   SET account_id = NULL
                 WHERE account_id IS NOT NULL
                   AND account_id NOT IN (SELECT id FROM account_account)
                """
            )
            # Clean comma-separated merged leaf ids
            cr.execute(
                """
                SELECT id, merged_leaf_account_ids
                  FROM audited_financial_line
                 WHERE merged_leaf_account_ids IS NOT NULL
                   AND merged_leaf_account_ids <> ''
                """
            )
            for line_id, merged in cr.fetchall():
                parts = []
                for token in (merged or "").split(","):
                    token = token.strip()
                    if token.isdigit():
                        parts.append(int(token))
                if not parts:
                    continue
                cr.execute(
                    "SELECT id FROM account_account WHERE id = ANY(%s)",
                    [parts],
                )
                keep = {row[0] for row in cr.fetchall()}
                cleaned = ",".join(str(i) for i in parts if i in keep)
                if cleaned != (merged or "").strip():
                    cr.execute(
                        """
                        UPDATE audited_financial_line
                           SET merged_leaf_account_ids = %s
                         WHERE id = %s
                        """,
                        [cleaned or None, line_id],
                    )
        # Flush pending ORM writes first — clear() otherwise reloads stale DB rows and
        # drops in-flight period preset / date changes from the dashboard.
        Version = self.env["audited.financial.version"]
        Line = self.env["audited.financial.line"]
        GLine = self.env["audited.financial.group.line"]
        if hasattr(Version, "flush"):
            Version.flush()
            Line.flush()
            GLine.flush()
        self.env.clear()
        return True

    def _sum_accounts_company_tb(self, tb_by_company, company_id, account_ids):
        tmap = tb_by_company.get(int(company_id)) or {}
        return sum(float(tmap.get(aid, 0.0)) for aid in account_ids)

    def _afg_branch_has_balance(self, prior, current, co_prior=None, co_curr=None, tb_amounts=None):
        """True if any amount column is non-zero (dashboard hide rule)."""
        if tb_amounts:
            return any(abs(float(v or 0.0)) > 1e-9 for v in tb_amounts)
        if abs(float(prior or 0.0)) > 1e-9 or abs(float(current or 0.0)) > 1e-9:
            return True
        for seq in (co_prior or []):
            if abs(float(seq or 0.0)) > 1e-9:
                return True
        for seq in (co_curr or []):
            if abs(float(seq or 0.0)) > 1e-9:
                return True
        return False

    def _tb_signed_balance(self, raw_balance, internal_group=None):
        """Odoo move-line balance as-is (debit − credit). Sum of all accounts is nil when books balance.

        Do not flip by account type — that broke TOTAL nil and disagreed with Accounting → Trial Balance.
        ``internal_group`` kept for call-site compatibility only.
        """
        return float(raw_balance or 0.0)

    def _afg_account_sudo(self):
        """Chart accounts including archived — posted moves on inactive ledgers still affect Odoo reports."""
        return self.env["account.account"].sudo().with_context(active_test=False)

    def _tb_opening_date(self):
        self.ensure_one()
        start = fields.Date.to_date(self.date_from_prior)
        return start - timedelta(days=1)

    def _tb_otc_width(self):
        """TB amount width: Opening + (Transactions + Closing) × 2 periods.

        Closing of period N is the bridge opening into period N+1 (no duplicate
        Opening column for the second year/month).
        """
        return 5

    def _tb_face_otc(self, amounts):
        """Section-total face: |Opening|/|Closing|; Transactions = Closing − Opening."""
        w = self._tb_otc_width()
        a = [float(v or 0.0) for v in (amounts or [])]
        while len(a) < w:
            a.append(0.0)
        a = a[:w]
        if w < 5:
            return [abs(v) for v in a]
        op, cl_p, cl_c = abs(a[0]), abs(a[2]), abs(a[4])
        return [op, cl_p - op, cl_p, cl_c - cl_p, cl_c]

    def _afg_attach_opening_amounts(self, nodes, column_order=None):
        """Attach node['opening'] (books/TB opening stock) for SOFP bookend column."""
        self.ensure_one()
        cids = [
            int(c)
            for c in (column_order or self._afg_column_company_order() or self._tb_company_ids() or [])
        ]
        if not cids or not nodes:
            return nodes
        opening_date = self._tb_opening_date()
        maps_by_cid = {
            "opening": {int(cid): self._fetch_tb_closing(opening_date, [cid]) for cid in cids},
            "closing_prior": {
                int(cid): self._fetch_tb_closing(self.date_to_prior, [cid]) for cid in cids
            },
            "closing_current": {
                int(cid): self._fetch_tb_closing(self.date_to_current, [cid]) for cid in cids
            },
        }
        enriched = self._afg_enrich_tree_with_tb_amounts(nodes, maps_by_cid, cids)

        def _merge(face_list, enr_list):
            enr_by_id = {e.get("id"): e for e in (enr_list or []) if e.get("id") is not None}
            for idx, f in enumerate(face_list or []):
                e = enr_by_id.get(f.get("id"))
                if e is None and idx < len(enr_list or []):
                    e = enr_list[idx]
                tb = (e or {}).get("tb_amounts") or []
                f["opening"] = float(tb[0] or 0.0) if tb else float(f.get("prior") or 0.0)
                _merge(f.get("children") or [], (e or {}).get("children") or [])

        _merge(nodes, enriched)
        return nodes

    def _tb_pack_otc(self, opening, closing_prior, closing_current):
        """Build [op, tr_yp, cl_yp, tr_yc, cl_yc] — no duplicate Opening for year 2."""
        op = float(opening or 0.0)
        cp = float(closing_prior or 0.0)
        cc = float(closing_current or 0.0)
        return [op, cp - op, cp, cc - cp, cc]

    def _tb_pack_otc_pnl(self, prior_pnl, current_pnl):
        """P&L-style year results: opening nil; transactions = closing = year result."""
        p = float(prior_pnl or 0.0)
        c = float(current_pnl or 0.0)
        return [0.0, p, p, c, c]

    def _tb_resync_otc(self, tb):
        """Rebuild transactions after closing columns change (supports 4/5/6 legacy widths)."""
        tb = list(tb or [])
        if len(tb) == 4:
            # Legacy [op, cl_yp, op_yc, cl_yc]
            return self._tb_pack_otc(tb[0], tb[1], tb[3])
        if len(tb) >= 6:
            # Legacy duplicated opening_current (= closing_prior)
            return self._tb_pack_otc(tb[0], tb[2], tb[5])
        while len(tb) < 5:
            tb.append(0.0)
        op = float(tb[0] or 0.0)
        cp = float(tb[2] or 0.0)
        cc = float(tb[4] or 0.0)
        return [op, cp - op, cp, cc - cp, cc]

    def _tb_closing_indices(self):
        """Indices of prior/current closing columns inside tb_amounts."""
        return 2, 4

    def _tb_period_column_meta(self):
        """Opening | Transactions {period} | Closing | Transactions {period} | Closing.

        Year/month label only on Transactions. Opening/Closing stay bare so the
        bridge Closing (end of period N) doubles as opening into period N+1.
        """
        self.ensure_one()
        yp = self._afg_period_label_prior()
        yc = self._afg_period_label_current()
        return [
            {"key": "opening", "label": _("Opening"), "year": "", "role": "opening"},
            {"key": "trans_prior", "label": _("Transactions"), "year": yp, "role": "transactions"},
            {"key": "closing_prior", "label": _("Closing"), "year": "", "role": "closing"},
            {"key": "trans_current", "label": _("Transactions"), "year": yc, "role": "transactions"},
            {"key": "closing_current", "label": _("Closing"), "year": "", "role": "closing"},
        ]

    def _tb_period_column_labels_flat(self):
        """Flat labels for Excel/Word (year only on Transactions columns)."""
        labels = []
        for col in self._tb_period_column_meta():
            lab = col.get("label") or ""
            year = col.get("year") or ""
            if year:
                labels.append("%s %s" % (lab, year))
            else:
                labels.append(str(lab))
        return labels

    def _tb_account_period_amounts(self, acc, maps_by_cid, cids):
        """Return [op, tr_yp, cl_yp, tr_yc, cl_yc] signed TB amounts.

        Use AML company maps (not ``account.company_id``) so cross-company
        posted lines on a foreign chart account still hit the TB — same as CoA.
        """
        ig = acc.internal_group or "asset"
        opening = closing_prior = closing_current = 0.0
        for cid in cids:
            cid = int(cid)
            opening += self._tb_signed_balance(
                float((maps_by_cid.get("opening") or {}).get(cid, {}).get(acc.id, 0.0)), ig)
            closing_prior += self._tb_signed_balance(
                float((maps_by_cid.get("closing_prior") or {}).get(cid, {}).get(acc.id, 0.0)), ig)
            closing_current += self._tb_signed_balance(
                float((maps_by_cid.get("closing_current") or {}).get(cid, {}).get(acc.id, 0.0)), ig)
        return self._tb_pack_otc(opening, closing_prior, closing_current)

    def _afg_sum_tb_amounts(self, nodes):
        nodes = nodes or []
        width = self._tb_otc_width()
        if nodes and nodes[0].get("tb_amounts"):
            width = len(nodes[0]["tb_amounts"])
        return [
            sum(float((n.get("tb_amounts") or [0.0] * width)[i] or 0.0) for n in nodes)
            for i in range(width)
        ]
    def _trial_balance_rows_data(self):
        """Trial balance as hierarchical tree (CoA type → group → ledger) with prior/current."""
        self.ensure_one()
        forced = self.env.context.get("afg_tb_column_ids")
        if forced is not None and list(forced):
            try:
                cids = [int(x) for x in forced]
            except (TypeError, ValueError):
                cids = []
            if not cids:
                forced = None
        if forced is None or not list(forced):
            col_subset = self._afg_column_company_order()
            cids = col_subset if col_subset else self._tb_company_ids()
        tb_env = self.with_context(allowed_company_ids=cids)
        Company = self.env["res.company"]
        columns = []
        for c in cids:
            cid = int(c)
            if len(cids) == 1:
                columns.append({"id": cid, "name": _("Year %s") % (self.year_current,)})
            else:
                columns.append({"id": cid, "name": self._afg_company_column_header(Company.browse(cid))})
        if not cids:
            return {
                "columns": self._tb_period_column_meta(),
                "five_column": True,
                "tb_account_mode": True,
                "tb_split_panels": True,
                "rows": [],
                "roots": [],
                "panels": [],
                "balance_ok": True,
                "balance_diff": 0.0,
                "as_of": fields.Date.to_string(self.date_to_current),
            }
        # Same stock rules as Accounting → Trial Balance (account.coa.report)
        maps_by_cid = self._tb_coa_maps_by_cid(cids)
        Account = self._afg_account_sudo().with_context(allowed_company_ids=cids)
        AccountGroup = self.env["account.group"].sudo()
        # Include archived accounts: Odoo BS/TB still carry their posted balances
        accounts = Account.search([("company_id", "in", cids)], order="company_id, code")
        # Cross-company chart accounts that still have AML under these companies (CoA parity)
        map_aids = set()
        for _key, by_cid in (maps_by_cid or {}).items():
            for cid in cids:
                map_aids.update((by_cid or {}).get(int(cid), {}) or {})
        orphan_ids = [aid for aid in map_aids if aid not in set(accounts.ids)]
        if orphan_ids:
            accounts |= Account.browse(orphan_ids).exists()
        ig_labels = OrderedDict([
            ("asset", _("Assets")),
            ("liability", _("Liabilities")),
            ("equity", _("Equity")),
            ("income", _("Income")),
            ("expense", _("Expenses")),
        ])
        type_buckets = OrderedDict((k, {"groups": OrderedDict()}) for k in ig_labels.keys())

        flat_rows = []
        for acc in accounts:
            tb_amounts = self._tb_account_period_amounts(acc, maps_by_cid, cids)
            if not self._afg_branch_has_balance(0, 0, tb_amounts=tb_amounts):
                continue
            idx_p, idx_c = self._tb_closing_indices()
            closing_prior = tb_amounts[idx_p]
            closing_current = tb_amounts[idx_c]
            ig = acc.internal_group or "asset"
            if ig not in type_buckets:
                ig = "asset"
            gkey = acc.group_id.id if acc.group_id else 0
            bucket = type_buckets[ig]["groups"]
            if gkey not in bucket:
                og = acc.group_id
                bucket[gkey] = {
                    "label": self._afg_group_label(og) if og else _("Ungrouped ledgers"),
                    "group_code": self._afg_odoo_group_code_prefix(og) if og else "",
                    "accounts": [],
                }
            bucket[gkey]["accounts"].append({
                "acc": acc,
                "tb_amounts": tb_amounts,
                "prior": closing_prior,
                "current": closing_current,
            })
            flat_rows.append({
                "code": acc.code or "",
                "name": acc.name or "",
                "group": acc.group_id.display_name if acc.group_id else "",
                "tb_amounts": tb_amounts,
                "total": closing_current,
            })

        roots = []
        seq_type = 0
        for ig_key, ig_label in ig_labels.items():
            groups = type_buckets[ig_key]["groups"]
            if not groups:
                continue
            seq_type += 1
            group_children = []
            for gkey in sorted(groups.keys(), key=lambda k: (k == 0, groups[k]["label"].lower())):
                gdata = groups[gkey]
                ledger_children = []
                for row in sorted(gdata["accounts"], key=lambda r: (r["acc"].code or "", r["acc"].id)):
                    acc = row["acc"]
                    tb_amt = row["tb_amounts"]
                    ledger_children.append({
                        "id": "tb-%s" % acc.id,
                        "label": self._afg_account_label(acc),
                        "note": "",
                        "level": 2,
                        "is_ledger": True,
                        "account_id": acc.id,
                        "prior": row["prior"],
                        "current": row["current"],
                        "tb_amounts": tb_amt,
                        "internal_group": acc.internal_group or "asset",
                        "group_code": gdata["group_code"],
                        "group_caption": gdata["label"],
                        "ledger_code": (acc.code or "").strip(),
                        "ledger_caption": (acc.name or "").strip(),
                        "children": [],
                    })
                if not ledger_children:
                    continue
                gp, gc, gco_p, gco_c = self._afg_sum_branch_nodes(ledger_children)
                gtb = self._afg_sum_tb_amounts(ledger_children)
                group_children.append({
                    "id": "tb-gr-%s-%s" % (ig_key, gkey),
                    "label": gdata["label"],
                    "note": "",
                    "level": 1,
                    "prior": gp,
                    "current": gc,
                    "tb_amounts": gtb,
                    "co_prior": gco_p,
                    "co_curr": gco_c,
                    "internal_group": ig_key,
                    "group_code": gdata["group_code"],
                    "group_caption": gdata["label"],
                    "ledger_code": "",
                    "ledger_caption": "",
                    "children": ledger_children,
                })
            if not group_children:
                continue
            group_children = self._afg_consolidate_branch_tree(group_children)
            if not group_children:
                continue
            tp, tc, tco_p, tco_c = self._afg_sum_branch_nodes(group_children)
            ttb = self._afg_sum_tb_amounts(group_children)
            roots.append({
                "id": "tb-type-%s" % ig_key,
                "type_key": ig_key,
                "label": ig_label,
                "note": "",
                "level": 0,
                "prior": tp,
                "current": tc,
                "tb_amounts": ttb,
                "co_prior": tco_p,
                "co_curr": tco_c,
                "internal_group": ig_key,
                "is_computed": False,
                "children": group_children,
            })

        # Split panels like AFG UI, but ledgers = full CoA (Accounting → Trial Balance).
        # Do NOT fold Income/Expense into a synthetic Profit/(Loss) — that line is not on
        # Accounting TB and breaks nil when AFG mapping ≠ full books.
        by_key = {r.get("type_key"): r for r in roots}
        asset_root = by_key.get("asset")
        other_roots = []
        for key in ("liability", "equity", "income", "expense"):
            if by_key.get(key):
                other_roots.append(by_key[key])

        def _section_total(label, nodes, tid, nature="asset"):
            ttb = self._afg_sum_tb_amounts(nodes)
            while len(ttb) < self._tb_otc_width():
                ttb.append(0.0)
            idx_p, idx_c = self._tb_closing_indices()
            return {
                "id": tid,
                "type_key": "section_total",
                "label": label,
                "note": "",
                "level": 0,
                "prior": float(ttb[idx_p] or 0.0),
                "current": float(ttb[idx_c] or 0.0),
                "tb_amounts": list(ttb),
                "internal_group": nature,
                "is_computed": True,
                "is_tb_section_total": True,
                "children": [],
            }

        panels = []
        asset_nodes = [asset_root] if asset_root else []
        if asset_nodes:
            panels.append({
                "key": "assets",
                "title": _("ASSETS"),
                "roots": asset_nodes + [
                    _section_total(_("TOTAL ASSETS"), asset_nodes, "tb-total-assets", "asset"),
                ],
            })
        if other_roots:
            panels.append({
                "key": "liabilities_equity",
                "title": _("LIABILITIES, EQUITY, INCOME & EXPENSES"),
                "roots": other_roots + [
                    _section_total(
                        _("TOTAL LIABILITIES, EQUITY, INCOME & EXPENSES"),
                        other_roots,
                        "tb-total-liabilities",
                        "liability",
                    ),
                ],
            })

        # Balancing check — every OTC column (Accounting CoA Net TOTAL must be nil)
        width = self._tb_otc_width()
        idx_p, idx_c = self._tb_closing_indices()
        asset_tb = list((asset_root or {}).get("tb_amounts") or [0.0] * width)
        while len(asset_tb) < width:
            asset_tb.append(0.0)
        other_tb = list(
            self._afg_sum_tb_amounts(other_roots) if other_roots else [0.0] * width
        )
        while len(other_tb) < width:
            other_tb.append(0.0)
        # Signed equation: Assets + Liabilities + Equity + Income + Expense ≈ 0
        diffs = []
        for i in range(width):
            raw = float(asset_tb[i] or 0.0) + float(other_tb[i] or 0.0)
            if self.currency_id:
                raw = self.currency_id.round(raw)
            diffs.append(raw)
        diff = diffs[idx_c] if diffs else 0.0
        if panels:
            panels[-1]["roots"].append({
                "id": "tb-type-difference",
                "type_key": "difference",
                "label": _("TOTAL (Net — must be nil)"),
                "note": "",
                "level": 0,
                "prior": diffs[idx_p] if len(diffs) > idx_p else 0.0,
                "current": diff,
                "tb_amounts": list(diffs),
                "is_computed": True,
                "is_tb_difference": True,
                "is_tb_section_total": True,
                "children": [],
            })

        # Keep flat roots for backward compatibility (legacy single-tree consumers)
        compat_roots = []
        for panel in panels:
            compat_roots.extend([
                r for r in panel["roots"]
                if not r.get("is_tb_section_total") and not r.get("is_tb_difference")
            ])

        return {
            "columns": self._tb_period_column_meta(),
            "five_column": True,
            "tb_account_mode": True,
            "tb_split_panels": True,
            "rows": flat_rows,
            "roots": compat_roots,
            "panels": panels,
            "balance_ok": all(abs(d) <= 0.005 for d in diffs),
            "balance_diff": diff,
            "balance_diffs": diffs,
            "as_of": fields.Date.to_string(self.date_to_current),
        }

    def _afg_leaf_account_ids_from_node(self, node):
        """Collect chart account ids under an AFG dashboard tree node."""
        ids = []
        if node.get("account_id"):
            try:
                ids.append(int(node["account_id"]))
            except (TypeError, ValueError):
                pass
        for raw in node.get("drill_account_ids") or []:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        for ch in node.get("children") or []:
            ids.extend(self._afg_leaf_account_ids_from_node(ch))
        return list({i for i in ids if i})

    def _afg_tb_amounts_for_account_ids(self, acc_ids, maps_by_cid, cids):
        """Sum period TB columns for a set of accounts (Odoo signed, then caller may face-scale)."""
        Acc = self._afg_account_sudo()
        width = self._tb_otc_width()
        totals = [0.0] * width
        if not acc_ids:
            return totals
        for acc in Acc.browse([int(a) for a in acc_ids if a]).exists():
            row = self._tb_account_period_amounts(acc, maps_by_cid, cids)
            for i in range(width):
                totals[i] += float(row[i] or 0.0) if i < len(row) else 0.0
        return totals

    def _afg_nature_from_type_key(self, type_key):
        """Map AFG / CoA type_key → Odoo internal_group for TB nature display."""
        tk = str(type_key or "").strip().lower()
        if tk in ("asset", "liability", "equity", "income", "expense"):
            return tk
        if tk in ("sales", "other_income", "revenue", "income"):
            return "income"
        if tk in ("expenses", "cost_of_revenue", "cogs", "expense"):
            return "expense"
        return False

    def _afg_infer_node_internal_group(self, node, parent_ig=None):
        if not node:
            return parent_ig or "asset"
        ig = node.get("internal_group")
        if ig:
            return str(ig)
        mapped = self._afg_nature_from_type_key(node.get("type_key"))
        if mapped:
            return mapped
        aids = self._afg_leaf_account_ids_from_node(node)
        if aids:
            Acc = self.env["account.account"].browse(aids[0])
            if Acc.exists():
                return Acc.internal_group or parent_ig or "asset"
        return parent_ig or "asset"

    def _afg_enrich_tree_with_tb_amounts(self, nodes, maps_by_cid, cids, parent_ig=None):
        """Deep-copy AFG statement tree and attach tb_amounts (OTC × years).

        Ledger lines use posted AML closings (same source as Accounting Trial Balance Totals).
        Computed lines (Retained Earnings roll, Profit/(Loss), plugs) keep SOFP amounts so
        AFG TB stays data-aligned with the statement and does not zero-out IFRS rolls.
        """
        import copy

        width = self._tb_otc_width()
        idx_p, idx_c = self._tb_closing_indices()
        out = []
        for node in nodes or []:
            n = copy.deepcopy(node)
            ig = self._afg_infer_node_internal_group(n, parent_ig)
            n["internal_group"] = ig
            stmt_prior = float(n.get("prior") or 0.0)
            stmt_current = float(n.get("current") or 0.0)
            kids = self._afg_enrich_tree_with_tb_amounts(
                n.get("children") or [], maps_by_cid, cids, parent_ig=ig
            )
            n["children"] = kids
            scale = float(n.get("face_scale") if n.get("face_scale") is not None else 1.0)
            if self.env.context.get("afg_tb_signed"):
                # AFG Trial Balance: keep Odoo signed balances (nil identity).
                scale = 1.0
            preserve_stmt = bool(
                n.get("is_computed")
                or n.get("type_key") in ("retained_earnings", "cy_pnl", "bs_diff")
                or self._afg_node_looks_like_retained_earnings(n)
                or self._afg_node_looks_like_cy_pnl(n)
                or self._afg_node_looks_like_bs_diff(n)
            )
            # TB must match Accounting CoA — do not re-apply SOFP RE / CY presentation plugs
            if self.env.context.get("afg_tb_signed"):
                preserve_stmt = False
            if kids:
                raw = list(self._afg_sum_tb_amounts(kids))
                while len(raw) < width:
                    raw.append(0.0)
                # Children already face-scaled in their tb_amounts — do not re-scale.
                # Re-apply SOFP-only deltas (e.g. prior P&L rolled into RE) not in child AML.
                if preserve_stmt:
                    delta_p = stmt_prior - float(raw[idx_p] or 0.0)
                    delta_c = stmt_current - float(raw[idx_c] or 0.0)
                    if abs(delta_p) > 0.005 or abs(delta_c) > 0.005:
                        raw[idx_p] = float(raw[idx_p] or 0.0) + delta_p
                        raw[idx_c] = float(raw[idx_c] or 0.0) + delta_c
                        raw = self._tb_resync_otc(raw)
                n["tb_amounts"] = raw
            else:
                acc_ids = self._afg_leaf_account_ids_from_node(n)
                if acc_ids:
                    raw = self._afg_tb_amounts_for_account_ids(acc_ids, maps_by_cid, cids)
                    n["tb_amounts"] = [float(v or 0.0) * scale for v in raw]
                    if preserve_stmt:
                        tb = list(n["tb_amounts"])
                        while len(tb) < width:
                            tb.append(0.0)
                        delta_p = stmt_prior - float(tb[idx_p] or 0.0)
                        delta_c = stmt_current - float(tb[idx_c] or 0.0)
                        if abs(delta_p) > 0.005 or abs(delta_c) > 0.005:
                            tb[idx_p] = float(tb[idx_p] or 0.0) + delta_p
                            tb[idx_c] = float(tb[idx_c] or 0.0) + delta_c
                            n["tb_amounts"] = self._tb_resync_otc(tb)
                else:
                    # Computed / caption leaf with no ledger ids
                    if self.env.context.get("afg_tb_signed"):
                        # Accounting TB has no SOFP-only captions — keep nil identity
                        n["tb_amounts"] = [0.0] * width
                    else:
                        p = stmt_prior
                        c = stmt_current
                        if n.get("type_key") == "cy_pnl" or self._afg_node_looks_like_cy_pnl(n):
                            n["tb_amounts"] = self._tb_pack_otc_pnl(p, c)
                        else:
                            # RE / equity stock captions
                            n["tb_amounts"] = self._tb_pack_otc(p, p, c)
            tb = n.get("tb_amounts") or [0.0] * width
            while len(tb) < width:
                tb.append(0.0)
            n["prior"] = float(tb[idx_p] or 0.0)
            n["current"] = float(tb[idx_c] or 0.0)
            out.append(n)
        return out

    def _afg_tb_is_computed_cy_pnl_plug(self, node):
        """SOFP IFRS Profit/(Loss) plug (no CoA leaf) — not a real ledger."""
        if not node:
            return False
        nid = str(node.get("id") or "")
        if nid in ("bs-cy-pnl", "tb2-type-cy-pnl", "tb-type-cy-pnl"):
            return True
        if node.get("type_key") == "cy_pnl" and (
            node.get("is_computed") or not self._afg_leaf_account_ids_from_node(node)
        ):
            return True
        if self._afg_node_looks_like_cy_pnl(node) and (
            node.get("is_computed") or not self._afg_leaf_account_ids_from_node(node)
        ):
            return True
        return False

    def _afg_tb_strip_computed_cy_pnl(self, nodes):
        """Drop SOFP Profit/(Loss) plugs and re-sum parents (TB folds P&L once)."""
        width = self._tb_otc_width()
        idx_p, idx_c = self._tb_closing_indices()

        def scrub(node):
            kids = []
            for ch in node.get("children") or []:
                if self._afg_tb_is_computed_cy_pnl_plug(ch):
                    continue
                scrub(ch)
                kids.append(ch)
            node["children"] = kids
            if kids:
                ttb = list(self._afg_sum_tb_amounts(kids))
                while len(ttb) < width:
                    ttb.append(0.0)
                node["tb_amounts"] = ttb
                node["prior"] = float(ttb[idx_p] or 0.0)
                node["current"] = float(ttb[idx_c] or 0.0)
            return node

        out = []
        for n in nodes or []:
            if self._afg_tb_is_computed_cy_pnl_plug(n):
                continue
            scrub(n)
            out.append(n)
        return out

    def _afg_tb_collect_mapped_account_ids(self, nodes):
        """Account ids already present under AFG statement trees."""
        ids = set()
        for n in nodes or []:
            ids.update(self._afg_leaf_account_ids_from_node(n))
        return {int(i) for i in ids if i}

    def _afg_tb_unmapped_coa_type_roots(self, coa_data, mapped_ids):
        """CoA type roots containing only ledgers not mapped to AFG (keeps TB nil)."""
        import copy

        mapped_ids = {int(i) for i in (mapped_ids or set()) if i}
        out = []
        for root in (coa_data or {}).get("roots") or []:
            r = copy.deepcopy(root)
            tk = str(r.get("type_key") or "")
            if tk in ("section_total", "difference", "cy_pnl"):
                continue
            new_groups = []
            for grp in r.get("children") or []:
                ledgers = []
                for led in grp.get("children") or []:
                    try:
                        aid = int(led.get("account_id") or 0)
                    except (TypeError, ValueError):
                        aid = 0
                    if aid and aid in mapped_ids:
                        continue
                    ledgers.append(led)
                if not ledgers:
                    continue
                g = copy.deepcopy(grp)
                g["children"] = ledgers
                g["id"] = "tb-ungrouped-%s-%s" % (tk, g.get("id") or "x")
                g["label"] = _("Ungrouped (CoA) — %s") % (g.get("label") or _("Ledgers"))
                g["group_caption"] = g["label"]
                ttb = self._afg_sum_tb_amounts(ledgers)
                g["tb_amounts"] = ttb
                idx_p, idx_c = self._tb_closing_indices()
                g["prior"] = float(ttb[idx_p] or 0.0) if ttb else 0.0
                g["current"] = float(ttb[idx_c] or 0.0) if ttb else 0.0
                new_groups.append(g)
            if not new_groups:
                continue
            r["children"] = new_groups
            ttb = self._afg_sum_tb_amounts(new_groups)
            r["tb_amounts"] = ttb
            idx_p, idx_c = self._tb_closing_indices()
            r["prior"] = float(ttb[idx_p] or 0.0) if ttb else 0.0
            r["current"] = float(ttb[idx_c] or 0.0) if ttb else 0.0
            r["id"] = "tb-afg-unmapped-%s" % (tk or "x")
            out.append(r)
        return out

    def _afg_tb_merge_type_root(self, primary, extras):
        """Attach extra L1 groups under an existing type root (or return extras as new root)."""
        import copy

        if not extras:
            return primary
        if not primary:
            if len(extras) == 1:
                return extras[0]
            # Bundle multiple unmapped type pieces
            kids = []
            for e in extras:
                kids.extend(list(e.get("children") or []))
            if not kids:
                return False
            root = copy.deepcopy(extras[0])
            root["children"] = kids
            ttb = self._afg_sum_tb_amounts(kids)
            root["tb_amounts"] = ttb
            idx_p, idx_c = self._tb_closing_indices()
            root["prior"] = float(ttb[idx_p] or 0.0) if ttb else 0.0
            root["current"] = float(ttb[idx_c] or 0.0) if ttb else 0.0
            return root
        primary = copy.deepcopy(primary)
        kids = list(primary.get("children") or [])
        for e in extras:
            kids.extend(list(e.get("children") or []))
        primary["children"] = kids
        ttb = self._afg_sum_tb_amounts(kids)
        primary["tb_amounts"] = ttb
        idx_p, idx_c = self._tb_closing_indices()
        primary["prior"] = float(ttb[idx_p] or 0.0) if ttb else 0.0
        primary["current"] = float(ttb[idx_c] or 0.0) if ttb else 0.0
        return primary

    def _afg_trial_balance2_data(self, face_bs, face_pl, column_order=None):
        """AFG-shaped Trial Balance (PL/BS grouping + colors) with CoA coverage for nil.

        - Hierarchy / look: same as Statement of Financial Position & P&L (AFG L1 + ledgers)
        - Ledgers: mapped AFG accounts + any unmapped CoA accounts (Accounting TB parity)
        - No synthetic Profit/(Loss) plug
        """
        self.ensure_one()
        cids = [int(c) for c in (column_order or self._afg_column_company_order() or self._tb_company_ids())]
        width = self._tb_otc_width()
        empty = {
            "columns": self._tb_period_column_meta(),
            "five_column": True,
            "tb_account_mode": True,
            "tb_split_panels": True,
            "afg_style": True,
            "rows": [],
            "roots": [],
            "panels": [],
            "balance_ok": True,
            "balance_diff": 0.0,
            "as_of": fields.Date.to_string(self.date_to_current),
        }
        if not cids:
            return empty

        ctx = {}
        if column_order is not None:
            ctx["afg_tb_column_ids"] = column_order
        coa_data = self.with_context(**ctx)._trial_balance_rows_data() if ctx else self._trial_balance_rows_data()

        # Accounting CoA stock (include_initial_balance + unaffected earnings) — not SOFP plugs
        maps_by_cid = self._tb_coa_maps_by_cid(cids)
        # Same-name ledger fold for multi-company (also when TB2 built from already-faced trees)
        face_bs = list(face_bs or [])
        face_pl = list(face_pl or [])
        if len(cids) > 1:
            face_bs = self._afg_consolidate_branch_tree(face_bs)
            face_pl = self._afg_consolidate_branch_tree(face_pl)
        bs_enr = self.with_context(afg_tb_signed=True)._afg_enrich_tree_with_tb_amounts(
            face_bs, maps_by_cid, cids
        )
        bs_enr = self._afg_tb_strip_computed_cy_pnl(bs_enr)
        pl_enr = self.with_context(afg_tb_signed=True)._afg_enrich_tree_with_tb_amounts(
            face_pl, maps_by_cid, cids
        )
        if len(cids) > 1:
            bs_enr = self._afg_consolidate_branch_tree(bs_enr)
            pl_enr = self._afg_consolidate_branch_tree(pl_enr)

        mapped_ids = self._afg_tb_collect_mapped_account_ids(bs_enr + pl_enr)
        unmapped = self._afg_tb_unmapped_coa_type_roots(coa_data, mapped_ids)
        unmapped_by = {str(n.get("type_key") or ""): n for n in unmapped}

        by_bs = {str(n.get("type_key") or ""): n for n in (bs_enr or []) if n.get("type_key")}
        asset_root = self._afg_tb_merge_type_root(
            by_bs.get("asset"),
            [unmapped_by["asset"]] if unmapped_by.get("asset") else [],
        )
        liab_root = self._afg_tb_merge_type_root(
            by_bs.get("liability"),
            [unmapped_by["liability"]] if unmapped_by.get("liability") else [],
        )
        equity_root = self._afg_tb_merge_type_root(
            by_bs.get("equity"),
            [unmapped_by["equity"]] if unmapped_by.get("equity") else [],
        )

        # P&L AFG trees (sales / COGS / expenses) — real Income & Expense ledgers, not CY plug
        pl_roots = list(pl_enr or [])
        if unmapped_by.get("income"):
            pl_roots.append(unmapped_by["income"])
        if unmapped_by.get("expense"):
            pl_roots.append(unmapped_by["expense"])

        def _section_total(label, nodes, tid, nature="asset"):
            ttb = self._afg_sum_tb_amounts(nodes)
            while len(ttb) < width:
                ttb.append(0.0)
            idx_p, idx_c = self._tb_closing_indices()
            return {
                "id": tid,
                "type_key": "section_total",
                "label": label,
                "note": "",
                "level": 0,
                "prior": float(ttb[idx_p] or 0.0),
                "current": float(ttb[idx_c] or 0.0),
                "tb_amounts": list(ttb),
                "internal_group": nature,
                "is_computed": True,
                "is_tb_section_total": True,
                "children": [],
            }

        asset_nodes = [asset_root] if asset_root else []
        other_roots = []
        for n in (liab_root, equity_root):
            if n:
                other_roots.append(n)
        other_roots.extend(pl_roots)

        panels = []
        if asset_nodes:
            panels.append({
                "key": "assets",
                "title": _("ASSETS"),
                "roots": asset_nodes + [
                    _section_total(_("TOTAL ASSETS"), asset_nodes, "tb2-total-assets", "asset"),
                ],
            })
        if other_roots:
            panels.append({
                "key": "liabilities_equity",
                "title": _("LIABILITIES, EQUITY, INCOME & EXPENSES"),
                "roots": other_roots + [
                    _section_total(
                        _("TOTAL LIABILITIES, EQUITY, INCOME & EXPENSES"),
                        other_roots,
                        "tb2-total-liabilities",
                        "liability",
                    ),
                ],
            })

        asset_tb = list((asset_root or {}).get("tb_amounts") or [0.0] * width)
        while len(asset_tb) < width:
            asset_tb.append(0.0)
        other_tb = list(
            self._afg_sum_tb_amounts(other_roots) if other_roots else [0.0] * width
        )
        while len(other_tb) < width:
            other_tb.append(0.0)
        diffs = []
        for i in range(width):
            raw = float(asset_tb[i] or 0.0) + float(other_tb[i] or 0.0)
            if self.currency_id:
                raw = self.currency_id.round(raw)
            diffs.append(raw)
        idx_p, idx_c = self._tb_closing_indices()
        diff = diffs[idx_c] if diffs else 0.0
        if panels:
            panels[-1]["roots"].append({
                "id": "tb2-net-total",
                "type_key": "difference",
                "label": _("TOTAL (Net — must be nil)"),
                "note": "",
                "level": 0,
                "prior": diffs[idx_p] if len(diffs) > idx_p else 0.0,
                "current": diff,
                "tb_amounts": list(diffs),
                "is_computed": True,
                "is_tb_difference": True,
                "is_tb_section_total": True,
                "children": [],
            })

        compat_roots = []
        for panel in panels:
            compat_roots.extend([
                r for r in panel["roots"]
                if not r.get("is_tb_section_total") and not r.get("is_tb_difference")
            ])

        return {
            "columns": self._tb_period_column_meta(),
            "five_column": True,
            "tb_account_mode": True,
            "tb_split_panels": True,
            "afg_style": True,
            "rows": (coa_data or {}).get("rows") or [],
            "roots": compat_roots,
            "panels": panels,
            "balance_ok": all(abs(d) <= 0.505 for d in diffs),
            "balance_diff": diff,
            "balance_diffs": diffs,
            "as_of": fields.Date.to_string(self.date_to_current),
        }

    def _groups_for_mapping(self):
        self.ensure_one()
        dom = ["|", ("company_id", "=", False), ("company_id", "=", self.company_id.id)]
        return self.env["audited.financial.group"].search(dom, order="report_section, sequence, id")

    def _ensure_afg_presets(self):
        self.env["audited.financial.group"]._setup_default_afg_presets()

    def _posted_moves_exist(self, date_from, date_to, company_ids):
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids or not date_from or not date_to:
            return 0
        return self.env["account.move.line"].search_count([
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("parent_state", "=", "posted"),
            ("company_id", "in", company_ids),
        ])

    def _posted_moves_exist_upto(self, date_to, company_ids):
        """Any posted journal line on/before date_to (BS closing existence)."""
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids or not date_to:
            return 0
        return self.env["account.move.line"].search_count([
            ("date", "<=", date_to),
            ("parent_state", "=", "posted"),
            ("company_id", "in", company_ids),
        ])

    def _afg_posted_years(self, company_ids):
        """Distinct calendar years that have posted journal items (newest first)."""
        company_ids = [int(c) for c in (company_ids or []) if c]
        if not company_ids:
            return []
        self.env.cr.execute(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM aml.date)::int AS y
              FROM account_move_line aml
             WHERE aml.parent_state = 'posted'
               AND aml.company_id IN %s
             ORDER BY y DESC
            """,
            (tuple(company_ids),),
        )
        return [int(row[0]) for row in self.env.cr.fetchall() if row and row[0]]

    def _afg_snap_years_to_posted_data(self):
        """Align prior/current years to posted activity when the version window is empty.

        Default AFG years are last two full calendar years (e.g. in 2026 → 2024/2025).
        Companies whose books only exist in 2026 (or only one year) otherwise show
        empty PL/BS after Load default data.
        Never snap month presets (mom / yoy_month) — user chose that window.
        """
        self.ensure_one()
        if (self.period_preset or "years") not in ("years",):
            return False
        cids = self._tb_company_ids()
        years = self._afg_posted_years(cids)
        if not years:
            return False
        yc = years[0]
        yp = years[1] if len(years) > 1 else (yc - 1)
        if yp > yc:
            yp, yc = yc, yp
        if self.year_prior == yp and self.year_current == yc:
            return False
        self.with_context(skip_afg_audit=True).write({
            "period_preset": "years",
            "year_prior": yp,
            "year_current": yc,
            "date_from_prior": fields.Date.from_string("%s-01-01" % yp),
            "date_to_prior": fields.Date.from_string("%s-12-31" % yp),
            "date_from_current": fields.Date.from_string("%s-01-01" % yc),
            "date_to_current": fields.Date.from_string("%s-12-31" % yc),
        })
        return True

    def action_auto_map_chart(self):
        """Map every chart account in scope to exactly one AFG preset (L1) using keyword rules."""
        Group = self.env["audited.financial.group"]
        Line = self.env["audited.financial.group.line"]
        Account = self._afg_account_sudo()
        for ver in self:
            ver._ensure_afg_presets()
            cids = ver._tb_company_ids()
            groups = Group.search([("company_id", "=", False), ("code", "!=", False)])
            code_to_group = {g.code: g for g in groups if g.code}
            if not code_to_group:
                continue
            accounts = Account.search([("company_id", "in", cids)])
            mapped_lines_all = Line.with_context(afg_skip_collapse=True).search(
                [("account_id", "in", accounts.ids)]
            )
            ungrp = set(self.env["audited.financial.group.line"]._afg_ungrouped_codes())
            mapped_real = set(
                mapped_lines_all.filtered(
                    lambda l: (l.group_id.code or "") not in ungrp
                ).mapped("account_id").ids
            )
            existing = {gl.account_id.id: gl for gl in mapped_lines_all}
            for acc in accounts:
                if acc.id in mapped_real:
                    continue
                code = _account_match_code(acc)
                target = code_to_group.get(code)
                if not target or (target.code or "") in ungrp:
                    continue
                gl = existing.get(acc.id)
                if gl:
                    if gl.group_id.id != target.id:
                        gl.group_id = target.id
                    mapped_real.add(acc.id)
                    continue
                existing[acc.id] = Line.create({"group_id": target.id, "account_id": acc.id})
                mapped_real.add(acc.id)
            # Same unique ledger name → same AFG group. Real groups beat Ungrouped.
            key_to_group = {}
            mapped_lines = Line.search([("account_id", "in", accounts.ids)])
            for gl in mapped_lines:
                k = ver._afg_pl_unique_ledger_key(gl.account_id)
                if not k:
                    continue
                code = (gl.group_id.code or "")
                if code in ungrp:
                    key_to_group.setdefault(k, gl.group_id)
                else:
                    key_to_group[k] = gl.group_id
            existing = {gl.account_id.id: gl for gl in mapped_lines}
            for acc in accounts:
                k = ver._afg_pl_unique_ledger_key(acc)
                target = key_to_group.get(k)
                if not target:
                    continue
                gl = existing.get(acc.id)
                if gl:
                    if gl.group_id.id != target.id:
                        gl.group_id = target.id
                else:
                    existing[acc.id] = Line.create({
                        "group_id": target.id,
                        "account_id": acc.id,
                    })
            ver._afg_ensure_cost_of_sales_on_cor()
        self._afg_mirror_schedule_mappings()
        return True

    def _afg_reclass_ungrouped_by_keywords(self):
        """Move Ungrouped mapping onto a real AFG group when keyword rules are sure."""
        self.ensure_one()
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        Group = self.env["audited.financial.group"]
        ungrp_codes = tuple(Line._afg_ungrouped_codes())
        ungrp_groups = Group.search([("code", "in", ungrp_codes)])
        if not ungrp_groups:
            return False
        code_to_group = {
            g.code: g
            for g in Group.search([("company_id", "=", False), ("code", "!=", False)])
            if g.code and g.code not in ungrp_codes
        }
        changed = False
        for line in Line.search([("group_id", "in", ungrp_groups.ids)]):
            acc = line.account_id
            if not acc:
                continue
            code = _account_match_code(acc)
            target = code_to_group.get(code)
            if not target:
                continue
            line.group_id = target
            changed = True
        cids = self._tb_company_ids()
        if cids:
            Account = self._afg_account_sudo()
            accounts = Account.search([("company_id", "in", cids)])
            have = set(
                Line.search([("account_id", "in", accounts.ids)]).mapped("account_id").ids
            )
            for acc in accounts:
                if acc.id in have:
                    continue
                code = _account_match_code(acc)
                target = code_to_group.get(code)
                if not target:
                    continue
                Line.create({"group_id": target.id, "account_id": acc.id})
                have.add(acc.id)
                changed = True
        return changed

    def _afg_align_unique_ledger_groups(self):
        """If any account of a unique ledger is on a real AFG group, move siblings off Ungrouped."""
        self.ensure_one()
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        Account = self._afg_account_sudo()
        cids = self._tb_company_ids()
        if not cids:
            return False
        ungrp = set(self.env["audited.financial.group.line"]._afg_ungrouped_codes())
        accounts = Account.search([("company_id", "in", cids)])
        mapped_lines = Line.search([("account_id", "in", accounts.ids)])
        key_to_group = {}
        for gl in mapped_lines:
            k = self._afg_pl_unique_ledger_key(gl.account_id)
            if not k:
                continue
            code = (gl.group_id.code or "")
            if code in ungrp:
                key_to_group.setdefault(k, gl.group_id)
            else:
                key_to_group[k] = gl.group_id
        existing = {gl.account_id.id: gl for gl in mapped_lines}
        for acc in accounts:
            k = self._afg_pl_unique_ledger_key(acc)
            target = key_to_group.get(k)
            if not target or (target.code or "") in ungrp:
                continue
            gl = existing.get(acc.id)
            if gl:
                if gl.group_id.id != target.id:
                    gl.group_id = target.id
            else:
                existing[acc.id] = Line.create({
                    "group_id": target.id,
                    "account_id": acc.id,
                })
        return True

    def _afg_ensure_cost_of_sales_on_cor(self):
        """Map every CoA Cost of Sales type onto AFG_COR (skip SAD- selling prefix)."""
        self.ensure_one()
        Group = self.env["audited.financial.group"]
        Line = self.env["audited.financial.group.line"]
        cor = Group.search([("code", "=", "AFG_COR"), ("company_id", "=", False)], limit=1)
        if not cor:
            cor = Group.search([("code", "=", "AFG_COR")], limit=1)
        if not cor:
            return False
        type_ids = [i for i in self._afg_cost_revenue_type_ids() if i]
        if not type_ids:
            return False
        Account = self._afg_account_sudo()
        cids = self._tb_company_ids()
        if not cids:
            return False
        accounts = Account.search([
            ("company_id", "in", cids),
            ("user_type_id", "in", type_ids),
        ])
        changed = False
        for acc in accounts:
            hay = ("%s %s" % (acc.code or "", acc.name or "")).lower()
            if "sad -" in hay or hay.startswith("sad "):
                continue
            lines = Line.with_context(afg_skip_collapse=True).search([
                ("account_id", "=", acc.id),
            ])
            cor_lines = lines.filtered(lambda l: l.group_id.id == cor.id)
            other = lines - cor_lines
            if other:
                other.unlink()
                changed = True
            if not cor_lines.exists():
                Line.create({"group_id": cor.id, "account_id": acc.id})
                changed = True
        return changed

    def _rebuild_line_hierarchy_from_tb(self):
        """Build L1 AFG / L2 Odoo account.group / L3 ledger lines from posted moves."""
        self.ensure_one()
        try:
            self._afg_reclass_ungrouped_by_keywords()
        except Exception:
            _logger.debug("AFG ungrouped keyword reclass skipped", exc_info=True)
        try:
            self._afg_align_unique_ledger_groups()
        except Exception:
            _logger.debug("AFG unique-ledger group align skipped", exc_info=True)
        cids = self._tb_company_ids()
        ctx = dict(self.env.context)
        if cids:
            ctx["allowed_company_ids"] = cids
        ctx["afg_pl_ledger_ids_by_key"] = self._afg_build_pl_ledger_key_map(cids)
        self = self.with_context(**ctx)
        Line = self.env["audited.financial.line"].with_context(skip_afg_audit=True)
        Account = self._afg_account_sudo()
        AccountGroup = self.env["account.group"].sudo()

        notes_by_gid = {}
        for ol in self.line_ids:
            if ol.level == 1 and ol.group_id:
                notes_by_gid[ol.group_id.id] = ol.note or ""

        posted_prior = self._posted_moves_exist(self.date_from_prior, self.date_to_prior, cids)
        posted_curr = self._posted_moves_exist(self.date_from_current, self.date_to_current, cids)
        # BS uses closing balances: activity before the window still feeds SOFP columns.
        posted_closing = self._posted_moves_exist_upto(self.date_to_current, cids)
        if posted_prior == 0 and posted_curr == 0 and posted_closing == 0:
            self.line_ids.unlink()
            self.write({"data_state": "empty"})
            return False

        tb_prior_pl = self._fetch_tb(self.date_from_prior, self.date_to_prior, cids)
        tb_curr_pl = self._fetch_tb(self.date_from_current, self.date_to_current, cids)
        # CoA stock (not raw AML closing) so Current Year Earnings / Undistributed gets UE
        tb_prior_bs = self._fetch_tb_coa_stock(
            self.date_to_prior, cids, fy_anchor_date=self.date_from_prior
        )
        tb_curr_bs = self._fetch_tb_coa_stock(
            self.date_to_current, cids, fy_anchor_date=self.date_from_current
        )
        self.line_ids.unlink()

        def bal(tb, aid):
            return float(tb.get(aid, 0.0))

        Group = self.env["audited.financial.group"]
        ungrp_pl = Group.search([("code", "=", "AFG_UNGRP_PL"), ("company_id", "=", False)], limit=1)
        if not ungrp_pl:
            ungrp_pl = Group.search([("code", "=", "AFG_UNGRP_PL")], limit=1)
        code_to_group = {
            g.code: g
            for g in Group.search([("company_id", "=", False), ("code", "!=", False)])
            if g.code
        }
        pl_buckets = self._afg_pl_unique_ledger_buckets(tb_prior_pl, tb_curr_pl, cids)
        pl_by_gid = defaultdict(list)
        for buck in pl_buckets:
            grp = self._afg_group_for_pl_bucket(buck, code_to_group, ungrp_pl)
            if grp:
                pl_by_gid[grp.id].append(buck)

        seq = 10
        for afg in self._groups_for_mapping():
            if afg.report_section == "pl":
                items = pl_by_gid.get(afg.id) or []
                if not items:
                    continue
                prior1 = sum(float(it["prior"] or 0.0) for it in items)
                curr1 = sum(float(it["curr"] or 0.0) for it in items)
                l1 = Line.create({
                    "version_id": self.id,
                    "group_id": afg.id,
                    "parent_id": False,
                    "level": 1,
                    "sequence": seq,
                    "label": afg.name,
                    "report_section": "pl",
                    "note": notes_by_gid.get(afg.id, ""),
                    "amount_prior": prior1,
                    "amount_current": curr1,
                    "source_amount_prior": prior1,
                    "source_amount_current": curr1,
                })
                seq += 10
                l2 = Line.create({
                    "version_id": self.id,
                    "group_id": afg.id,
                    "parent_id": l1.id,
                    "level": 2,
                    "sequence": 10,
                    "label": afg.name,
                    "report_section": "pl",
                    "amount_prior": prior1,
                    "amount_current": curr1,
                    "source_amount_prior": prior1,
                    "source_amount_current": curr1,
                })
                leaf_seq = 10
                for it in sorted(items, key=lambda x: (x.get("label") or "").lower()):
                    aids = [int(a) for a in (it.get("aids") or []) if a]
                    acc_rep = it.get("rep") or self._afg_pick_l3_representative(aids, Account)
                    if not acc_rep:
                        continue
                    rest = ",".join(str(a) for a in aids if a != acc_rep.id) or False
                    Line.create({
                        "version_id": self.id,
                        "group_id": afg.id,
                        "parent_id": l2.id,
                        "level": 3,
                        "account_id": acc_rep.id,
                        "merged_leaf_account_ids": rest,
                        "sequence": leaf_seq,
                        "label": it.get("label") or self._afg_account_label(acc_rep),
                        "report_section": "pl",
                        "amount_prior": it["prior"],
                        "amount_current": it["curr"],
                        "source_amount_prior": it["prior"],
                        "source_amount_current": it["curr"],
                    })
                    leaf_seq += 10
                continue
            if self._section_uses_closing_balance(afg.report_section):
                tb_prior = tb_prior_bs
                tb_curr = tb_curr_bs
            else:
                tb_prior = tb_prior_pl
                tb_curr = tb_curr_pl
            acc_ids = set()
            for gl in afg.line_ids:
                for aid in self._tb_account_ids_for_group_line(gl, cids):
                    acc_ids.add(aid)
            if not acc_ids:
                continue
            prior1 = sum(bal(tb_prior, aid) for aid in acc_ids)
            curr1 = sum(bal(tb_curr, aid) for aid in acc_ids)
            l1 = Line.create({
                "version_id": self.id,
                "group_id": afg.id,
                "parent_id": False,
                "level": 1,
                "sequence": seq,
                "label": afg.name,
                "report_section": afg.report_section,
                "note": notes_by_gid.get(afg.id, ""),
                "amount_prior": prior1,
                "amount_current": curr1,
                "source_amount_prior": prior1,
                "source_amount_current": curr1,
            })
            seq += 10
            by_og = defaultdict(list)
            cid_set = set(int(c) for c in cids)
            pl_key_to_local_og = {}
            for aid in acc_ids:
                acc = Account.browse(aid)
                if acc.company_id.id in cid_set:
                    pk = self._afg_pl_unique_ledger_key(acc)
                    if pk and acc.group_id:
                        pl_key_to_local_og.setdefault(pk, acc.group_id.id)
            for aid in acc_ids:
                acc = Account.browse(aid)
                pk = self._afg_pl_unique_ledger_key(acc)
                if acc.company_id.id not in cid_set and pk in pl_key_to_local_og:
                    key = pl_key_to_local_og[pk]
                else:
                    key = acc.group_id.id if acc.group_id else 0
                by_og[key].append(aid)

            def og_sort_key(k):
                aids = by_og[k]
                first_code = Account.browse(aids[0]).code or ""
                return (k == 0, first_code)

            sub_seq = 10
            l2_buckets = []
            for og_id in sorted(by_og.keys(), key=og_sort_key):
                aids_block = sorted(by_og[og_id], key=lambda x: (Account.browse(x).code or "", x))
                og = og_id and AccountGroup.browse(og_id)
                label2 = self._afg_group_label(og) if og and og.exists() else _("Ungrouped ledgers")
                l2_buckets.append({"og_id": og_id, "label": label2, "aids": aids_block})

            by_l2_name = defaultdict(list)
            for b in l2_buckets:
                key = (b["label"] or "").strip().lower()
                by_l2_name[key].append(b)

            for _l2_key in sorted(by_l2_name.keys(), key=lambda k: (by_l2_name[k][0]["og_id"] or 0, k)):
                buckets = by_l2_name[_l2_key]
                representative_og = 0
                combined_aids = []
                for b in sorted(buckets, key=lambda x: x["og_id"] or 0):
                    combined_aids.extend(b["aids"])
                    if not representative_og and b["og_id"]:
                        representative_og = b["og_id"]
                # preserve uniqueness, stable order
                seen = set()
                aids_merged = []
                for aid in combined_aids:
                    if aid not in seen:
                        seen.add(aid)
                        aids_merged.append(aid)
                aids_merged.sort(key=lambda x: (Account.browse(x).code or "", x))
                label2 = buckets[0]["label"]
                prior2 = sum(bal(tb_prior, a) for a in aids_merged)
                curr2 = sum(bal(tb_curr, a) for a in aids_merged)
                l2 = Line.create({
                    "version_id": self.id,
                    "group_id": afg.id,
                    "parent_id": l1.id,
                    "level": 2,
                    "odoo_group_id": representative_og if representative_og else False,
                    "sequence": sub_seq,
                    "label": label2,
                    "report_section": afg.report_section,
                    "amount_prior": prior2,
                    "amount_current": curr2,
                    "source_amount_prior": prior2,
                    "source_amount_current": curr2,
                })
                sub_seq += 10
                leaf_seq = 10
                merge_l3 = True
                l3_groups = self._afg_bucket_l3_leaf_accounts(
                    aids_merged, Account, merge_same_ledger_name_multicompany=merge_l3,
                )
                for aid_group in l3_groups:
                    p3 = sum(bal(tb_prior, a) for a in aid_group)
                    c3 = sum(bal(tb_curr, a) for a in aid_group)
                    acc_rep = self._afg_pick_l3_representative(aid_group, Account)
                    if not acc_rep:
                        continue
                    rep_id = acc_rep.id
                    merged_rest = ",".join(
                        str(a) for a in aid_group if a != rep_id
                    ) if len(aid_group) > 1 else False
                    Line.create({
                        "version_id": self.id,
                        "group_id": afg.id,
                        "parent_id": l2.id,
                        "level": 3,
                        "account_id": rep_id,
                        "merged_leaf_account_ids": merged_rest or False,
                        "sequence": leaf_seq,
                        "label": self._afg_account_label(acc_rep),
                        "report_section": afg.report_section,
                        "amount_prior": p3,
                        "amount_current": c3,
                        "source_amount_prior": p3,
                        "source_amount_current": c3,
                    })
                    leaf_seq += 10
        self.write({"data_state": "posted"})
        self._recompute_alerts()
        return True

    @api.model
    def _afg_rebuild_after_coa_map(self, accounts):
        """Refresh statement trees after AFG group is set on Chart of Accounts."""
        cids = set(accounts.mapped("company_id").ids)
        if not cids:
            return True
        vers = self.search([
            "|",
            ("company_id", "in", list(cids)),
            ("company_ids", "in", list(cids)),
        ])
        for ver in vers:
            try:
                ver._rebuild_line_hierarchy_from_tb()
            except Exception:
                _logger.debug("AFG rebuild after COA map skipped", exc_info=True)
        return True

    def action_load_default_data(self):
        """Ensure presets, auto-map CoA, rebuild L1/L2/L3 from posted journal lines (current version dates)."""
        self.env["audited.financial.version"]._afg_scrub_orphan_account_refs()
        keep_years = bool(self.env.context.get("afg_keep_user_years"))
        for ver in self:
            ver._ensure_afg_presets()
            ver.action_auto_map_chart()
            rebuilt = ver._rebuild_line_hierarchy_from_tb()
            # Empty window for this period but books exist in other years → snap & retry once.
            # Never snap when the user explicitly chose Prior/Current on the dashboard.
            if not rebuilt and not keep_years and ver._afg_snap_years_to_posted_data():
                ver._rebuild_line_hierarchy_from_tb()
            # Replace old training stub notes with L1 Official (locked format)
            stored = [{"title": n.title, "body": n.body or ""} for n in ver.note_ids]
            if stored and ver._afg_notes_are_training_stubs(stored):
                ver._seed_sample_notes()
        return True

    def action_load_sample_data(self):
        """Illustrative hierarchy for layout / training when real TB is empty."""
        Line = self.env["audited.financial.line"].with_context(skip_afg_audit=True)
        demo = {
            "AFG_REV": (820000.0, 975000.0),
            "AFG_COR": (410000.0, 498000.0),
            "AFG_SELL": (42000.0, 51500.0),
            "AFG_GNA": (185000.0, 201500.0),
            "AFG_PAYROLL": (310000.0, 332000.0),
            "AFG_DEPR_PL": (28000.0, 29500.0),
            "AFG_CASH": (125000.0, 142000.0),
            "AFG_AR": (240000.0, 218000.0),
            "AFG_AP": (198000.0, 205500.0),
            "AFG_EQ": (350000.0, 383000.0),
            "AFG_PPE": (480000.0, 465000.0),
            "AFG_CF": (200000.0, 225000.0),
            "AFG_EQ_CHG": (350000.0, 383000.0),
            "AFG_FIXED": (480000.0, 465000.0),
        }
        for ver in self:
            ver._ensure_afg_presets()
            ver.line_ids.unlink()
            seq = 10
            for afg in ver._groups_for_mapping():
                if afg.report_section not in ("pl", "bs", "equity", "fixed_assets", "cashflow"):
                    continue
                prior, curr = demo.get(afg.code, (float(seq * 800), float(seq * 900)))
                l1 = Line.create({
                    "version_id": ver.id,
                    "group_id": afg.id,
                    "parent_id": False,
                    "level": 1,
                    "sequence": seq,
                    "label": afg.name,
                    "report_section": afg.report_section,
                    "amount_prior": prior,
                    "amount_current": curr,
                    "source_amount_prior": prior,
                    "source_amount_current": curr,
                })
                l2 = Line.create({
                    "version_id": ver.id,
                    "group_id": afg.id,
                    "parent_id": l1.id,
                    "level": 2,
                    "sequence": 10,
                    "label": _("Sample account group"),
                    "report_section": afg.report_section,
                    "amount_prior": prior,
                    "amount_current": curr,
                    "source_amount_prior": prior,
                    "source_amount_current": curr,
                })
                Line.create({
                    "version_id": ver.id,
                    "group_id": afg.id,
                    "parent_id": l2.id,
                    "level": 3,
                    "sequence": 10,
                    "label": _("Sample ledger"),
                    "report_section": afg.report_section,
                    "amount_prior": prior,
                    "amount_current": curr,
                    "source_amount_prior": prior,
                    "source_amount_current": curr,
                })
                seq += 10
            ver.write({"data_state": "sample"})
            ver._seed_sample_notes()
            ver._recompute_alerts()
        return True

    def _seed_sample_notes(self):
        """Seed L1 Official-style notes (locked Financial Report Template L1)."""
        self.ensure_one()
        Note = self.env["audited.financial.note"]
        self.note_ids.unlink()
        # Prefer full official notes from report extension; never training stubs.
        official = []
        if hasattr(self, "_dashboard_placeholder_notes"):
            official = self._dashboard_placeholder_notes() or []
        if not official:
            official = [
                {
                    "title": _("1. Reporting entity"),
                    "body": "<p>%s</p>" % _(
                        "%(entity)s (the \"Company\") is a limited liability company registered in the "
                        "United Arab Emirates."
                    ) % {"entity": self.company_id.display_name or _("the Company")},
                },
                {
                    "title": _("2. Basis of preparation"),
                    "body": "<p>%s</p>" % _(
                        "These financial statements have been prepared based on the Company's accounting "
                        "records and are management-prepared and have not been audited."
                    ),
                },
            ]
        Note.create([
            {
                "version_id": self.id,
                "sequence": (idx + 1) * 10,
                "title": item.get("title") or _("Note"),
                "body": item.get("body") or "",
            }
            for idx, item in enumerate(official)
        ])

    def action_clear_adjustments(self):
        for ver in self:
            for line in ver.line_ids:
                line.with_context(skip_afg_audit=True).write({
                    "amount_prior": line.source_amount_prior,
                    "amount_current": line.source_amount_current,
                })
        return True

    def action_reload_from_trial_balance(self):
        """Backward-compatible name: same as Load Default Data (uses version period, not hard-coded years)."""
        return self.action_load_default_data()

    def afg_dashboard_apply_years(self, year_prior=None, year_current=None):
        """Set full-year dates from year integers and rebuild from posted data (dashboard).

        Honours the user's Prior/Current choice — does not snap back to other posted years.
        """
        result = {
            "year_prior": False,
            "year_current": False,
            "period_preset": "years",
            "data_state": False,
            "empty": False,
        }
        for ver in self:
            try:
                yp = int(year_prior)
                yc = int(year_current)
            except (TypeError, ValueError):
                raise UserError(_("Enter valid prior and current years."))
            if yp < 1900 or yc < 1900 or yp > 2100 or yc > 2100:
                raise UserError(_("Enter valid prior and current years (1900–2100)."))
            if yp > yc:
                yp, yc = yc, yp
            vals = {
                "period_preset": "years",
                "year_prior": yp,
                "year_current": yc,
                "date_from_prior": fields.Date.from_string("%s-01-01" % yp),
                "date_to_prior": fields.Date.from_string("%s-12-31" % yp),
                "date_from_current": fields.Date.from_string("%s-01-01" % yc),
                "date_to_current": fields.Date.from_string("%s-12-31" % yc),
            }
            ver.with_context(skip_afg_audit=True).write(vals)
            ver.with_context(afg_keep_user_years=True).action_load_default_data()
            ver.invalidate_cache()
            result.update({
                "year_prior": ver.year_prior,
                "year_current": ver.year_current,
                "period_preset": ver.period_preset,
                "period_label_prior": ver._afg_period_label_prior(),
                "period_label_current": ver._afg_period_label_current(),
                "data_state": ver.data_state,
                "empty": ver.data_state == "empty",
            })
        return result

    def afg_dashboard_set_years_descending(self, years_descending=False):
        """Persist Column ascending/descending for ALL AFG reports/versions.

        Only this user action may change the preference — reload / period / load-default
        must not flip year column order.
        """
        flag = bool(years_descending)
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.print_years_descending",
            "1" if flag else "0",
        )
        # Apply to every working paper so P&L / SOFP / TB / exports stay aligned.
        all_vers = self.env["audited.financial.version"].sudo().search([])
        if all_vers:
            all_vers.with_context(skip_afg_audit=True).write({
                "print_years_descending": flag,
            })
        return {"print_years_descending": flag}

    @api.model
    def _afg_global_period_span_pref(self):
        """Show N years/months preference (ICP). Default 2y."""
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "cpabooks_afg.period_span",
            default="2y",
        )
        return _afg_normalize_period_span(raw)

    def afg_dashboard_set_period_span(self, span=None):
        """Persist Show periods (1–5y / 1–4m), rewrite date windows, rebuild data."""
        span = _afg_normalize_period_span(span)
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.period_span",
            span,
        )
        vals = _afg_period_span_vals(span)
        result = {
            "period_span": span,
            "period_span_label": _afg_period_span_label(span),
            "period_preset": vals.get("period_preset"),
            "year_prior": False,
            "year_current": False,
            "data_state": False,
            "empty": False,
        }
        for ver in self:
            ver.with_context(skip_afg_audit=True).write(vals)
            ver.with_context(afg_keep_user_years=True).action_load_default_data()
            ver.invalidate_cache()
            result.update({
                "period_preset": ver.period_preset,
                "year_prior": ver.year_prior,
                "year_current": ver.year_current,
                "period_label_prior": ver._afg_period_label_prior(),
                "period_label_current": ver._afg_period_label_current(),
                "period_labels": [w.get("label") for w in ver._afg_resolve_period_windows()],
                "data_state": ver.data_state,
                "empty": ver.data_state == "empty",
            })
        return result

    def _afg_resolve_period_windows(self):
        """Oldest→newest comparative windows for statements / print.

        Custom / YoY keep the two version date ranges (ignore N-span expansion).
        Years / MoM use the global period_span ending at the version's current window.
        """
        self.ensure_one()
        preset = (self.period_preset or "years").strip()
        if preset in ("custom", "yoy_month"):
            lab_p = self._afg_period_label_prior()
            lab_c = self._afg_period_label_current()
            same = (
                self.date_from_prior == self.date_from_current
                and self.date_to_prior == self.date_to_current
            )
            if same or not self.date_from_prior:
                return [{
                    "key": "p0",
                    "label": lab_c or lab_p,
                    "date_from": self.date_from_current or self.date_from_prior,
                    "date_to": self.date_to_current or self.date_to_prior,
                }]
            return [
                {
                    "key": "p0",
                    "label": lab_p,
                    "date_from": self.date_from_prior,
                    "date_to": self.date_to_prior,
                },
                {
                    "key": "p1",
                    "label": lab_c,
                    "date_from": self.date_from_current,
                    "date_to": self.date_to_current,
                },
            ]
        span = self._afg_global_period_span_pref()
        n, unit = _afg_parse_period_span(span)
        windows = []
        if unit == "y":
            yc = int(self.year_current or (fields.Date.today().year - 1))
            for offset in range(n - 1, -1, -1):
                y = yc - offset
                df = fields.Date.from_string("%s-01-01" % y)
                dt = fields.Date.from_string("%s-12-31" % y)
                windows.append({
                    "key": "y%s" % y,
                    "label": str(y),
                    "date_from": df,
                    "date_to": dt,
                })
            return windows
        # months — end at version current month
        cur_end = fields.Date.to_date(self.date_to_current) or _afg_last_complete_month()[1]
        cur_start = cur_end.replace(day=1)
        for offset in range(n - 1, -1, -1):
            yy, mm = _afg_shift_month(cur_start.year, cur_start.month, -offset)
            df, dt = _afg_month_start_end(yy, mm)
            windows.append({
                "key": "m%04d%02d" % (yy, mm),
                "label": _afg_format_period_label(df, dt),
                "date_from": df,
                "date_to": dt,
            })
        return windows

    # Report pack L1–L4 (+ L1 Arabic). Internal tree still uses levels 0–4.
    AFG_REPORT_PACK_LABELS = {
        1: "L1 — Official (FTA / banks)",
        5: "L1 — Official (FTA / Bank) — Arabic Version",
        2: "L2 — Management (with Type)",
        3: "L3 — Detailed (with Group)",
        4: "L4 — Accountant Working Papers",
    }
    # Pack → flatten depth (ledgers = level 3). Filter uses pack via _afg_filter_tree_for_pack.
    AFG_PACK_TO_TREE_DEPTH = {1: 1, 2: 4, 3: 4, 4: 4, 5: 1}
    # Legacy View/print depth 0–5 → report pack
    AFG_LEGACY_DEPTH_TO_PACK = {0: 1, 1: 2, 2: 4, 3: 4, 4: 3, 5: 3}

    @api.model
    def _afg_legacy_depth_to_pack(self, depth):
        try:
            d = int(depth)
        except (TypeError, ValueError):
            return 3
        return self.AFG_LEGACY_DEPTH_TO_PACK.get(d, 3)

    @api.model
    def _afg_normalize_report_pack(self, value):
        """Clamp report pack to 1..5 (5 = L1 Arabic Official)."""
        try:
            n = int(value)
        except (TypeError, ValueError):
            return 3
        if n == 5:
            return 5
        return max(1, min(4, n))

    @api.model
    def _afg_hierarchy_pack(self, pack=None):
        """Map UI pack to hierarchy rules (L1 Arabic uses Official L1 tree)."""
        pack = self._afg_normalize_report_pack(
            pack if pack is not None else self._afg_export_report_pack()
        )
        return 1 if pack == 5 else pack

    @api.model
    def _afg_is_l1_official_pack(self, pack=None):
        pack = self._afg_normalize_report_pack(
            pack if pack is not None else self._afg_export_report_pack()
        )
        return pack in (1, 5)

    @api.model
    def _afg_tree_depth_for_pack(self, pack):
        pack = self._afg_normalize_report_pack(pack)
        return int(self.AFG_PACK_TO_TREE_DEPTH.get(pack, 4))

    @api.model
    def _afg_report_pack_spec(self, pack=None):
        """Visibility / chapter gating for one report pack (single engine)."""
        pack = self._afg_normalize_report_pack(
            pack if pack is not None else self._afg_global_report_pack_pref()
        )
        hp = self._afg_hierarchy_pack(pack)
        print_chapters = [
            "pl", "bs", "equity", "cashflow", "fixed_assets", "notes",
        ]
        face_sections = [
            "fta", "pl", "bs", "equity", "cashflow", "fixed_assets", "notes",
        ]
        if hp >= 4:
            face_sections.extend(["review", "tb", "tb_x", "fs_recon"])
            # Working papers only: TB + Validation + FS recon (not on L1 Official PDF)
            print_chapters = [
                "pl", "bs", "tb", "equity", "cashflow", "fixed_assets",
                "notes", "validation", "fs_recon",
            ]
        else:
            # L1–L3 dashboard still shows Validation & Review tab for accountants
            face_sections.append("review")
            print_chapters = [
                "pl", "bs", "equity", "cashflow", "fixed_assets", "notes",
            ]
        return {
            "pack": pack,
            "hierarchy_pack": hp,
            "label": self.AFG_REPORT_PACK_LABELS.get(pack, ""),
            "tree_max_level": self._afg_tree_depth_for_pack(pack),
            "hide_lg": hp <= 3,
            "hide_codes": hp <= 2,
            "hide_hash": hp <= 2,
            "hide_merge_ledger": hp <= 2,
            "hide_remove_group": hp <= 3,
            "hide_full_editor": hp <= 2,
            "show_tb": hp >= 4,
            "show_ledgers": hp >= 2,
            # L3 only: AFG → account.group → ledger
            "show_account_groups": hp == 3,
            # L2: CoA type → ledger (no AFG). L4: AFG → ledger (no type/group).
            "show_coa_types": hp in (1, 2),
            "show_afg_groups": hp != 2,
            "arabic": pack == 5,
            "rtl": pack == 5,
            "sections_allowed": face_sections,
            "print_chapters": print_chapters,
        }

    def afg_dashboard_save_internal_notes(self, notes=""):
        self.ensure_one()
        self.write({"internal_action_notes": notes or ""})
        return True

    def afg_dashboard_set_print_max_level(self, max_level=3):
        """Persist Report level L1–L4 when the user changes the dropdown.

        Accepts pack 1–4, or legacy hierarchy depth 0–5 (migrated).
        """
        pack = self._afg_coerce_to_report_pack(max_level)
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.report_level",
            str(pack),
        )
        # Keep legacy ICP in sync as tree depth for older readers
        tree = self._afg_tree_depth_for_pack(pack)
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.print_max_level",
            str(tree),
        )
        all_vers = self.env["audited.financial.version"].sudo().search([])
        if all_vers:
            all_vers.with_context(skip_afg_audit=True).write({
                "print_max_level": pack,
            })
        return {
            "print_max_level": pack,
            "report_level": pack,
            "report_pack": self._afg_report_pack_spec(pack),
        }

    @api.model
    def _afg_global_page_setup_pref(self):
        """ICP page setup: default | skip_empty | compact."""
        raw = (
            self.env["ir.config_parameter"].sudo().get_param(
                "cpabooks_afg.print_page_setup", default="default"
            )
            or "default"
        ).strip().lower()
        if raw in ("skip_empty", "compact", "skip_empty_compact"):
            return "compact" if raw in ("compact", "skip_empty_compact") else "skip_empty"
        return "default"

    def afg_dashboard_set_page_setup(self, page_setup="default", margin_header=None, margin_footer=None):
        """Persist Page setup + header/footer margins (mm → report.paperformat)."""
        mode = (page_setup or "default").strip().lower()
        if mode in ("skip_empty_compact", "stop_empty"):
            mode = "compact"
        if mode not in ("default", "skip_empty", "compact"):
            mode = "default"
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cpabooks_afg.print_page_setup", mode)
        if margin_header is not None:
            try:
                mh = max(3, min(40, int(float(margin_header))))
            except (TypeError, ValueError):
                mh = 5
            ICP.set_param("cpabooks_afg.print_margin_header", str(mh))
        if margin_footer is not None:
            try:
                mf = max(3, min(40, int(float(margin_footer))))
            except (TypeError, ValueError):
                mf = 5
            ICP.set_param("cpabooks_afg.print_margin_footer", str(mf))
        if mode == "compact":
            ICP.set_param("cpabooks_afg.print_sign_last_only", "1")
        elif mode == "default":
            ICP.set_param("cpabooks_afg.print_sign_last_only", "0")
        all_vers = self.env["audited.financial.version"].sudo().search([])
        if all_vers and "print_page_setup" in all_vers._fields:
            all_vers.with_context(skip_afg_audit=True).write({
                "print_page_setup": mode,
            })
        self._afg_log_l1_page_setup_override(
            "AFG PDF page setup / paperformat margins (Abdus approved)"
        )
        return self._afg_sync_paperformat_margins()

    def afg_dashboard_stop_print_empty_page(self):
        """One-click: compact HF, skip empty chapters, sign on last page, tight paperformat mm."""
        self.ensure_one()
        empty_titles = []
        try:
            doc = self.with_context(
                afg_no_empty_chapter_filter=True
            )._afg_build_print_chapters() or {}
            for ch in doc.get("chapters") or []:
                if self._afg_chapter_is_empty_for_print(ch):
                    empty_titles.append(
                        (ch.get("title") or ch.get("key") or _("(untitled)")).strip()
                    )
        except Exception:  # noqa: BLE001
            _logger.exception("AFG page setup: could not build chapters for empty scan")
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cpabooks_afg.print_page_setup", "compact")
        ICP.set_param("cpabooks_afg.print_sign_last_only", "1")
        ICP.set_param("cpabooks_afg.print_margin_header", "5")
        ICP.set_param("cpabooks_afg.print_margin_footer", "5")
        ICP.set_param("cpabooks_afg.print_sign_gap_pt", "14")
        all_vers = self.env["audited.financial.version"].sudo().search([])
        if all_vers and "print_page_setup" in all_vers._fields:
            all_vers.with_context(skip_afg_audit=True).write({
                "print_page_setup": "compact",
            })
        self._afg_log_l1_page_setup_override(
            "AFG Stop print empty page: skip blank chapters + paperformat 8mm (Abdus)"
        )
        flags = self._afg_sync_paperformat_margins()
        return {
            **flags,
            "empty_count": len(empty_titles),
            "empty_titles": empty_titles,
            "message": _(
                "Applied: skip empty chapters, signature only on last statement, "
                "paperformat top/bottom 5mm (forced; not company A4 40mm), compact sign. "
                "Empty chapters skipped: %s. Re-print PDF (Ctrl+F5 first)."
            ) % (len(empty_titles) or 0),
        }

    def _afg_log_l1_page_setup_override(self, summary):
        """Record Customization Policy override when module is installed (Abdus gate)."""
        if "cpabooks.customization.policy.format" not in self.env:
            return
        Policy = self.env["cpabooks.customization.policy.format"]
        try:
            Policy.assert_change_allowed(
                "afg_l1_official",
                summary,
                approver_name="abdus",
            )
            fmt = Policy.sudo().search([("code", "=", "afg_l1_official"), ("active", "=", True)], limit=1)
            if not fmt or "cpabooks.customization.policy.override.log" not in self.env:
                return
            Log = self.env["cpabooks.customization.policy.override.log"]
            today = fields.Date.context_today(self)
            exists = Log.sudo().search([
                ("format_id", "=", fmt.id),
                ("approver_name", "=", "abdus"),
                ("create_date", ">=", "%s 00:00:00" % today),
                ("change_summary", "ilike", "paperformat"),
            ], limit=1)
            if exists:
                return
            Log.sudo().create({
                "format_id": fmt.id,
                "change_summary": (summary or "").strip()[:2000],
                "approver_name": "abdus",
                "note": _("AFG paperformat / empty-page fix (module)"),
            })
        except Exception:  # noqa: BLE001
            _logger.exception("AFG: could not log customization policy override")

    def _afg_log_l1_equity_clubbing_override(self):
        """Record Abdus override: L1 SOFP equity face (capital / current / reserve / P&L / RE)."""
        if "cpabooks.customization.policy.format" not in self.env:
            return
        Policy = self.env["cpabooks.customization.policy.format"]
        summary = (
            "L1 Official SOFP: Capital account, Current account, Statutory reserve, "
            "Profit for the Year as own column amounts (not rolled into RE); "
            "form + PDF/Excel/Word share this face."
        )
        try:
            Policy.assert_change_allowed(
                "afg_l1_official",
                summary,
                approver_name="abdus",
            )
            fmt = Policy.sudo().search([("code", "=", "afg_l1_official"), ("active", "=", True)], limit=1)
            if not fmt or "cpabooks.customization.policy.override.log" not in self.env:
                return
            Log = self.env["cpabooks.customization.policy.override.log"]
            today = fields.Date.context_today(self)
            exists = Log.sudo().search([
                ("format_id", "=", fmt.id),
                ("approver_name", "=", "abdus"),
                ("create_date", ">=", "%s 00:00:00" % today),
                ("change_summary", "ilike", "Current account"),
            ], limit=1)
            if exists:
                return
            Log.sudo().create({
                "format_id": fmt.id,
                "change_summary": summary,
                "approver_name": "abdus",
                "note": _("AFG L1 Official equity clubbing (module)"),
            })
        except Exception:  # noqa: BLE001
            _logger.exception("AFG: could not log L1 equity clubbing override")

    def _afg_sync_paperformat_margins(self):
        """Push ICP mm margins onto AFG report.paperformat (what wkhtmltopdf actually uses)."""
        flags = self._afg_print_page_setup_flags()
        mh = float(flags.get("margin_header") or 12)
        mf = float(flags.get("margin_footer") or 10)
        try:
            report = self.env.ref(
                "project_dashboard_odoo.action_report_afg_audit_pdf",
                raise_if_not_found=False,
            )
            pf = self.env.ref(
                "project_dashboard_odoo.paperformat_afg_audit",
                raise_if_not_found=False,
            )
            if not report or not pf:
                return flags
            vals = {
                "margin_top": mh,
                "margin_bottom": mf,
                "header_spacing": 0,
                "header_line": False,
                "dpi": self._afg_saved_print_dpi(),
            }
            pf.sudo().write(vals)
            if report.paperformat_id.id != pf.id:
                report.sudo().write({"paperformat_id": pf.id})
        except Exception:  # noqa: BLE001
            _logger.exception("AFG: failed to sync paperformat margins")
        return flags


    def _afg_chapter_is_empty_for_print(self, ch):
        """True when a print chapter would render as a blank / header-only page."""
        if not isinstance(ch, dict):
            return True
        kind = ch.get("kind") or "statement"
        if kind == "cover":
            return False
        if kind == "notes":
            return not (ch.get("notes") or [])
        if kind == "validation":
            return not (ch.get("validations") or [])
        if kind == "fs_recon":
            recon = ch.get("recon") or {}
            return not (recon.get("rows") or []) and not (recon.get("ledger_gaps") or [])
        if kind == "equity_soce":
            soce = ch.get("soce") or {}
            rows = soce.get("rows") or []
            cols = soce.get("columns") or []
            if not rows or not cols:
                return True
            for row in rows:
                tot = row.get("total") or {}
                try:
                    if abs(float(tot.get("prior") or 0.0)) >= 0.5:
                        return False
                    if abs(float(tot.get("current") or 0.0)) >= 0.5:
                        return False
                except (TypeError, ValueError):
                    pass
                for cell in (row.get("cells") or {}).values():
                    if not isinstance(cell, dict):
                        continue
                    try:
                        if abs(float(cell.get("prior") or 0.0)) >= 0.5:
                            return False
                        if abs(float(cell.get("current") or 0.0)) >= 0.5:
                            return False
                    except (TypeError, ValueError):
                        continue
            # Skeleton SOCE with only zeros → blank-looking page
            return True
        if kind == "ppe_matrix":
            ppe = ch.get("ppe") or {}
            if not (ppe.get("categories") or []):
                return True
            for block in ppe.get("blocks") or []:
                if not isinstance(block, dict) or block.get("is_section"):
                    continue
                if block.get("rows"):
                    return False
            return True
        rows = ch.get("rows") or []
        if not rows:
            return True
        for r in rows:
            if not isinstance(r, dict):
                continue
            if r.get("is_section_banner"):
                continue
            lab = (r.get("label_raw") or r.get("label") or "").strip()
            if not lab:
                continue
            # Any labelled line counts as content (incl. zero amounts)
            return False
        return True

    def _afg_filter_empty_print_chapters(self, chapters, page_setup=None):
        """Print every chapter the form built — no skip-empty / Print Setup."""
        return list(chapters or [])

    def _afg_print_page_setup_flags(self):
        mode = self._afg_global_page_setup_pref()
        ICP = self.env["ir.config_parameter"].sudo()

        def _mm(key, default):
            """Header/footer values are millimetres for report.paperformat."""
            try:
                return max(3, min(40, int(float(ICP.get_param(key, default=str(default)) or default))))
            except (TypeError, ValueError):
                return default

        def _pt(key, default):
            try:
                return max(0, min(40, int(float(ICP.get_param(key, default=str(default)) or default))))
            except (TypeError, ValueError):
                return default

        margin_header = _mm("cpabooks_afg.print_margin_header", 5 if mode == "compact" else 8)
        margin_footer = _mm("cpabooks_afg.print_margin_footer", 5 if mode == "compact" else 8)
        sign_gap = _pt("cpabooks_afg.print_sign_gap_pt", 28 if mode != "compact" else 14)
        sign_last_raw = (ICP.get_param("cpabooks_afg.print_sign_last_only", default="") or "").strip()
        if sign_last_raw in ("1", "true", "True", "yes"):
            sign_last_only = True
        elif sign_last_raw in ("0", "false", "False", "no"):
            sign_last_only = False
        else:
            sign_last_only = mode in ("skip_empty", "compact")
        pages_raw = (ICP.get_param("cpabooks_afg.print_show_page_numbers", default="0") or "").strip()
        show_page_numbers = pages_raw in ("1", "true", "True", "yes")
        if self and len(self) == 1 and "print_show_page_numbers" in self._fields:
            show_page_numbers = bool(self.print_show_page_numbers)
        return {
            "print_page_setup": mode,
            "skip_empty_pages": mode in ("skip_empty", "compact"),
            "compact_hf": mode == "compact",
            "sign_last_only": bool(sign_last_only),
            "show_page_numbers": bool(show_page_numbers),
            "margin_header": margin_header,
            "margin_footer": margin_footer,
            "sign_gap_pt": sign_gap,
            "margin_unit": "mm",
        }

    @api.model
    def _afg_coerce_to_report_pack(self, value):
        """Interpret UI/RPC value as report pack (migrate legacy depth if needed)."""
        try:
            n = int(value)
        except (TypeError, ValueError):
            return 3
        # Pack 5 is always L1 Official Arabic (never legacy depth 5)
        if n == 5:
            return 5
        # Already a pack (1–4) when new ICP exists or value in 1–4 after migration.
        # Ambiguity: old depth 1–4 overlap. Prefer report_level ICP; if caller
        # passes via new dropdown (only 1–4 options), treat as pack.
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "cpabooks_afg.report_level", default="",
        )
        if raw is not None and str(raw).strip() != "":
            # New system active — values are packs (1–4 + 5 Arabic Official)
            if 1 <= n <= 4:
                return self._afg_normalize_report_pack(n)
            return self._afg_legacy_depth_to_pack(n)
        # First migration path: treat 0–4 as legacy hierarchy depth (not 5)
        if 0 <= n <= 4:
            return self._afg_legacy_depth_to_pack(n)
        return self._afg_normalize_report_pack(n)

    @api.model
    def _afg_global_report_pack_pref(self):
        """Stored Report level L1–L4 (ICP). Migrates legacy print_max_level once."""
        ICP = self.env["ir.config_parameter"].sudo()
        raw = ICP.get_param("cpabooks_afg.report_level", default="")
        if raw is not None and str(raw).strip() != "":
            try:
                return self._afg_normalize_report_pack(int(str(raw).strip()))
            except (TypeError, ValueError):
                pass
        # Migrate from legacy hierarchy depth ICP / default Detailed (3)
        legacy_raw = ICP.get_param("cpabooks_afg.print_max_level", default="")
        if legacy_raw is None or str(legacy_raw).strip() == "":
            pack = 3
        else:
            try:
                pack = self._afg_legacy_depth_to_pack(int(str(legacy_raw).strip()))
            except (TypeError, ValueError):
                pack = 3
        ICP.set_param("cpabooks_afg.report_level", str(pack))
        ICP.set_param(
            "cpabooks_afg.print_max_level",
            str(self._afg_tree_depth_for_pack(pack)),
        )
        return pack

    @api.model
    def _afg_global_print_max_level_pref(self):
        """Tree hierarchy depth for filters (derived from report pack)."""
        return self._afg_tree_depth_for_pack(self._afg_global_report_pack_pref())

    @api.model
    def _afg_global_years_descending_pref(self):
        """Stored user preference (ICP). None/empty → ascending (False)."""
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "cpabooks_afg.print_years_descending",
            default="",
        )
        if raw is None or str(raw).strip() == "":
            return False
        return str(raw).strip().lower() in ("1", "true", "yes", "y")

    def afg_dashboard_apply_period_preset(self, preset=None):
        """Apply a named dashboard period preset and rebuild posted data."""
        preset = (preset or "years").strip()
        if preset == "custom":
            raise UserError(_("Use Custom period dates (Apply custom) instead of a named preset."))
        if preset not in ("years", "mom", "yoy_month"):
            raise UserError(_("Unknown period preset: %s") % preset)
        result = {
            "period_preset": preset,
            "year_prior": False,
            "year_current": False,
            "data_state": False,
            "empty": False,
        }
        vals = _afg_period_preset_vals(preset)
        # Named year/month cards reset Show periods to the classic 2-column span
        if preset == "years":
            self.env["ir.config_parameter"].sudo().set_param(
                "cpabooks_afg.period_span", "2y",
            )
        elif preset == "mom":
            self.env["ir.config_parameter"].sudo().set_param(
                "cpabooks_afg.period_span", "2m",
            )
        for ver in self:
            ver.with_context(skip_afg_audit=True).write(vals)
            ver.with_context(afg_keep_user_years=True).action_load_default_data()
            ver.invalidate_cache()
            result.update({
                "period_preset": ver.period_preset,
                "year_prior": ver.year_prior,
                "year_current": ver.year_current,
                "period_label_prior": ver._afg_period_label_prior(),
                "period_label_current": ver._afg_period_label_current(),
                "data_state": ver.data_state,
                "empty": ver.data_state == "empty",
            })
        return result

    def afg_dashboard_apply_custom_period(
            self,
            date_from_prior=None,
            date_to_prior=None,
            date_from_current=None,
            date_to_current=None,
    ):
        """Apply user-picked prior/current date ranges and rebuild posted data."""
        try:
            dfp = fields.Date.to_date(date_from_prior)
            dtp = fields.Date.to_date(date_to_prior)
            dfc = fields.Date.to_date(date_from_current)
            dtc = fields.Date.to_date(date_to_current)
        except Exception:
            raise UserError(_("Enter valid prior and current period dates."))
        if not all([dfp, dtp, dfc, dtc]):
            raise UserError(_("Enter valid prior and current period dates."))
        if dfp > dtp or dfc > dtc:
            raise UserError(_("Each period start must be on or before its end date."))
        result = {
            "period_preset": "custom",
            "year_prior": False,
            "year_current": False,
            "data_state": False,
            "empty": False,
        }
        vals = {
            "period_preset": "custom",
            "year_prior": int(dfp.year),
            "year_current": int(dfc.year),
            "date_from_prior": dfp,
            "date_to_prior": dtp,
            "date_from_current": dfc,
            "date_to_current": dtc,
        }
        for ver in self:
            ver.with_context(skip_afg_audit=True).write(vals)
            ver.with_context(afg_keep_user_years=True).action_load_default_data()
            ver.invalidate_cache()
            result.update({
                "period_preset": ver.period_preset,
                "year_prior": ver.year_prior,
                "year_current": ver.year_current,
                "period_label_prior": ver._afg_period_label_prior(),
                "period_label_current": ver._afg_period_label_current(),
                "date_from_prior": fields.Date.to_string(ver.date_from_prior),
                "date_to_prior": fields.Date.to_string(ver.date_to_prior),
                "date_from_current": fields.Date.to_string(ver.date_from_current),
                "date_to_current": fields.Date.to_string(ver.date_to_current),
                "data_state": ver.data_state,
                "empty": ver.data_state == "empty",
            })
        return result

    def afg_open_journal_items(self, payload=None):
        """Open posted journal lines from the dashboard (ledger / L4 rows).

        payload dict:
          - line_id: audited.financial.line database id (level 3)
          - account_id, l3_line_id, branch_company_id: L4 synthetic row drill
        """
        self.ensure_one()
        ver = self
        Line = self.env["audited.financial.line"]
        payload = payload or {}
        acc_ids = []
        companies = ver._tb_company_ids()
        section = "pl"

        if payload.get("account_id"):
            acc_ids = [int(payload["account_id"])]
            l3_id = int(payload.get("l3_line_id") or 0)
            if l3_id:
                l3 = Line.browse(l3_id)
                if l3.exists() and l3.version_id == ver:
                    section = l3.report_section or section
                    # Prefer all leaf accounts on that L3 (merged ledgers)
                    leaf = ver._line_leaf_account_ids(l3)
                    if leaf:
                        acc_ids = leaf
            if payload.get("branch_company_id"):
                companies = [int(payload["branch_company_id"])]
        elif payload.get("line_id"):
            line = Line.browse(int(payload["line_id"]))
            if not line.exists() or line.version_id != ver:
                raise UserError(_("Invalid working paper line."))
            section = line.report_section or section
            acc_ids = ver._line_leaf_account_ids(line)
        else:
            raise UserError(_("Nothing to open."))

        acc_ids = [int(a) for a in acc_ids if a]
        if not acc_ids:
            raise UserError(_("No ledger account mapped to this line."))

        companies = [int(c) for c in (companies or []) if c]
        if not companies:
            raise UserError(_("No company scope for this version."))

        # Cover prior + current so drill is not empty when balances sit on the prior column
        if ver._section_uses_closing_balance(section):
            domain = [
                ("date", "<=", ver.date_to_current),
                ("account_id", "in", acc_ids),
                ("parent_state", "=", "posted"),
                ("company_id", "in", companies),
            ]
            title = _("Journal items (to %s)") % ver.date_to_current
        else:
            domain = [
                ("date", ">=", ver.date_from_prior),
                ("date", "<=", ver.date_to_current),
                ("account_id", "in", acc_ids),
                ("parent_state", "=", "posted"),
                ("company_id", "in", companies),
            ]
            title = _("Journal items (%s - %s)") % (ver.date_from_prior, ver.date_to_current)

        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "account.move.line",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("cpabooks_audited_financial.view_afg_account_move_line_tree").id, "tree"),
                (False, "form"),
            ],
            "domain": domain,
            # Keep AFG dashboard — open journal items in a dialog; click a row → voucher
            "target": "new",
            "context": {
                "create": False,
                "delete": False,
                "afg_drill_open_move": True,
                "allowed_company_ids": companies,
            },
        }


    def afg_open_coa_form(self, payload=None):
        """Open Chart of Accounts form so the user can set AFG group."""
        self.ensure_one()
        payload = payload or {}
        try:
            acc_id = int(payload.get("account_id") or 0)
        except (TypeError, ValueError):
            acc_id = 0
        acc = self.env["account.account"].browse(acc_id).exists()
        if not acc:
            raise UserError(_("No ledger account on this row."))
        view = self.env.ref("account.view_account_form", raise_if_not_found=False)
        return {
            "type": "ir.actions.act_window",
            "name": acc.display_name or _("Chart of Accounts"),
            "res_model": "account.account",
            "res_id": acc.id,
            "view_mode": "form",
            "views": [(view.id, "form")] if view else [(False, "form")],
            "target": "current",
            "context": {
                "form_view_initial_mode": "edit",
                "allowed_company_ids": self._tb_company_ids(),
            },
        }

    def afg_open_ungrouped_reassign(self, payload=None):
        """Open Ungrouped mapping lines so the user can pick the correct AFG group."""
        self.ensure_one()
        payload = payload or {}
        acc_ids = []
        for raw in payload.get("account_ids") or []:
            try:
                acc_ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        code = (payload.get("ungrouped_code") or "AFG_UNGRP_PL").strip()
        if code not in ("AFG_UNGRP_PL", "AFG_UNGRP_BS"):
            code = "AFG_UNGRP_PL"
        Group = self.env["audited.financial.group"]
        ungrp = Group.search([("code", "=", code), ("company_id", "=", False)], limit=1)
        if not ungrp:
            ungrp = Group.search([("code", "=", code)], limit=1)
        if not ungrp:
            raise UserError(_("Ungrouped AFG group %s is missing.") % code)
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        recs = Line.browse()
        if acc_ids:
            recs = Line.search([("account_id", "in", acc_ids)])
            have = set(recs.mapped("account_id").ids)
            for aid in acc_ids:
                if aid not in have:
                    Line.create({"group_id": ungrp.id, "account_id": aid})
                    have.add(aid)
            recs = Line.search([("account_id", "in", acc_ids)])
        if not recs:
            recs = Line.search([("group_id", "=", ungrp.id)])
        if not recs:
            raise UserError(_(
                "No ledgers found to reassign. Expand Ungrouped, then right-click a ledger name."
            ))
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_group_line_reassign_tree",
            raise_if_not_found=False,
        )
        views = [(view.id, "tree")] if view else [(False, "tree")]
        return {
            "type": "ir.actions.act_window",
            "name": _("Reassign ungrouped ledgers"),
            "res_model": "audited.financial.group.line",
            "view_mode": "tree",
            "views": views,
            "domain": [("id", "in", recs.ids)],
            "target": "new",
            "context": {
                "create": False,
                "delete": False,
                "allowed_company_ids": self._tb_company_ids(),
            },
        }

    def afg_open_group_ledgers(self, payload=None):
        """Right-click AFG group: listed mappings + Add ledgers."""
        self.ensure_one()
        payload = payload or {}
        try:
            gid = int(payload.get("group_id") or 0)
        except (TypeError, ValueError):
            gid = 0
        if gid:
            group = self.env["audited.financial.group"].browse(gid).exists()
            if not group:
                raise UserError(_("AFG group was not found."))
            view = self.env.ref(
                "cpabooks_audited_financial.view_audited_financial_group_ledgers_popup",
                raise_if_not_found=False,
            )
            return {
                "type": "ir.actions.act_window",
                "name": group.display_name or _("AFG group ledgers"),
                "res_model": "audited.financial.group",
                "res_id": group.id,
                "view_mode": "form",
                "views": [(view.id, "form")] if view else [(False, "form")],
                "target": "new",
                "context": {
                    "form_view_initial_mode": "edit",
                    "allowed_company_ids": self._tb_company_ids(),
                },
            }
        return self.afg_open_ctf_ledgers(payload)

    def afg_open_ctf_ledgers(self, payload=None):
        """Right-click CT Filing line: listed ledgers + Add more."""
        self.ensure_one()
        payload = payload or {}
        cat = (payload.get("ctf_category") or "").strip()
        valid = {k for k, _l in CTF_CATEGORY_SELECTION}
        if cat not in valid:
            raise UserError(_("No CT Filing category on this row."))
        cids = self._tb_company_ids()
        accounts = self.env["account.account"].search([
            ("ctf_category", "=", cat),
            ("company_id", "in", cids),
        ])
        wiz = self.env["audited.financial.ctf.ledgers"].create({
            "category": cat,
            "account_ids": [(6, 0, accounts.ids)],
        })
        view = self.env.ref(
            "cpabooks_audited_financial.view_audited_financial_ctf_ledgers_form"
        )
        label = dict(CTF_CATEGORY_SELECTION).get(cat) or cat
        return {
            "type": "ir.actions.act_window",
            "name": _("CT Filing — %s") % label,
            "res_model": "audited.financial.ctf.ledgers",
            "res_id": wiz.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {"allowed_company_ids": cids},
        }

    def action_reload_to_default_periods(self):
        """Reset to default calendar prior/current years (full year) then reload from posted data."""
        dv = _afg_default_period_vals()
        for ver in self:
            ver.with_context(skip_afg_audit=True).write(dv)
            ver.action_load_default_data()
        return True

    def action_export_csv(self):
        self.ensure_one()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([_("Section"), _("Level"), _("Label"), _("Prior"), _("Current"), _("TB prior"), _("TB current")])
        for line in self.line_ids.sorted(lambda l: (l.report_section, l.sequence, l.id)):
            writer.writerow([
                line.report_section,
                line.level,
                line.label or "",
                line.amount_prior or 0.0,
                line.amount_current or 0.0,
                line.source_amount_prior or 0.0,
                line.source_amount_current or 0.0,
            ])
        data = buf.getvalue().encode("utf-8-sig")
        att = self.env["ir.attachment"].create({
            "name": "Audited_Financials_%s_%s.csv" % (self.id, self.year_current),
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "text/csv",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % att.id,
            "target": "self",
        }

    def _recompute_alerts(self):
        Alert = self.env["audited.financial.alert"]
        for ver in self:
            ver.alert_ids.unlink()
            alerts = []
            for line in ver.line_ids.filtered(lambda l: l.report_section == "pl" and l.level == 1):
                if line.label and "revenue" in (line.label or "").lower() and line.amount_current < 0:
                    alerts.append({
                        "version_id": ver.id,
                        "alert_type": "ifrs",
                        "severity": "warning",
                        "title": _("Negative revenue line"),
                        "message": _("Line '%s' shows negative current-year balance — review recognition.") % line.label,
                    })
            for line in ver.line_ids.filtered(lambda l: l.level == 1):
                g = line.group_id
                if g and g.sensitivity_category == "depreciation" and line.amount_current and line.amount_prior:
                    if abs(line.amount_current) > abs(line.amount_prior or 1) * 1.5:
                        alerts.append({
                            "version_id": ver.id,
                            "alert_type": "fta",
                            "severity": "info",
                            "title": _("Depreciation movement"),
                            "message": _("Large change vs prior year on %s — verify asset register.") % (line.label or ""),
                        })
            if alerts:
                Alert.create(alerts)

    def action_save_version(self):
        for ver in self:
            ver.write({"state": "saved"})
        return True

    def action_toggle_edit(self):
        for ver in self:
            ver.write({"edit_mode": not ver.edit_mode})
        return True

    def action_open_sensitive_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Adjust audited amount"),
            "res_model": "audited.financial.sensitive.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_version_id": self.id},
        }

    def action_open_ledger_merge_wizard(self, section=None):
        """Open Merge Ledger popup scoped to the current AFG dashboard report section."""
        self.ensure_one()
        section = section or self.env.context.get("afg_merge_section") or "bs"
        wizard = self.env["audited.financial.ledger.merge.wizard"].with_context(
            afg_merge_section=section,
            default_version_id=self.id,
        ).create({
            "version_id": self.id,
            "report_section": section if section in (
                "pl", "bs", "equity", "tb", "tb_x", "cashflow", "fixed_assets"
            ) else "bs",
            "company_ids": [(6, 0, self.company_ids.ids or [self.company_id.id])],
            "info_message": _(
                "Report: %(r)s. Select AFG group, Account group, or ledgers, then Load. "
                "Rename one company at a time. Save / Confirm keep this window open; use Close to dismiss."
            ) % {"r": section},
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Merge Ledger"),
            "res_model": "audited.financial.ledger.merge.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_version_id": self.id,
                "afg_merge_section": section,
            },
        }

    def _afg_cost_revenue_type_ids(self):
        """Account types treated as cost of revenue (Cost of Sales / Direct Costs)."""
        Type = self.env["account.account.type"]
        types = Type.browse()
        ref = self.env.ref("account.data_account_type_direct_costs", raise_if_not_found=False)
        if ref:
            types |= ref
        types |= Type.search([
            "|", "|", "|",
            ("name", "ilike", "Cost of Sales"),
            ("name", "ilike", "Cost of Revenue"),
            ("name", "ilike", "Direct Cost"),
            ("name", "ilike", "Cost of Goods"),
        ])
        return types.ids or [0]

    def _afg_infer_pl_coa_type(self, afg):
        """Map an AFG preset to P&amp;L CoA type (sales / cost_of_revenue / expenses)."""
        if not afg:
            return "expenses"
        code = (afg.code or "").strip()
        if code == "AFG_REV" or afg.sensitivity_category == "revenue":
            return "sales"
        if code == "AFG_COR" or afg.sensitivity_category == "cost_of_revenue":
            return "cost_of_revenue"
        # Operating expense presets must not fall under Cost of Materials (matches Odoo P&amp;L)
        if code in ("AFG_SELL", "AFG_GNA", "AFG_PAYROLL", "AFG_DEPR_PL", "AFG_OPEX", "AFG_ADMIN"):
            return "expenses"
        cost_rev_ids = set(self._afg_cost_revenue_type_ids())
        accounts = afg.line_ids.mapped("account_id")
        accounts = accounts.exists() if accounts else accounts
        # Majority vote by account type — avoid one CoR ledger pulling Selling/Ungrouped into materials
        if accounts:
            votes = {"sales": 0, "cost_of_revenue": 0, "expenses": 0}
            for acc in accounts:
                if acc.internal_group == "income":
                    votes["sales"] += 1
                elif acc.user_type_id.id in cost_rev_ids:
                    votes["cost_of_revenue"] += 1
                elif acc.internal_group == "expense":
                    votes["expenses"] += 1
            best = max(votes, key=lambda k: (votes[k], k == "expenses"))
            if votes[best] > 0:
                return best
        if accounts.filtered(lambda a: a.internal_group == "income"):
            return "sales"
        return "expenses"

    def _afg_infer_bs_coa_type(self, afg):
        """Map an AFG preset to balance-sheet CoA type (chart preset code, then account internal_group)."""
        code = (afg.code or "").strip() if afg else ""
        if code in AFG_CODE_BS_TYPE:
            return AFG_CODE_BS_TYPE[code]
        accounts = afg.line_ids.mapped("account_id") if afg else self.env["account.account"]
        accounts = accounts.exists() if accounts else accounts
        groups = [g for g in accounts.mapped("internal_group") if g in ("asset", "liability", "equity")]
        if not groups:
            return "asset"
        # Majority vote — avoids dumping mixed Ungrouped (AP + cash) entirely under Assets
        counts = defaultdict(int)
        for g in groups:
            counts[g] += 1
        return max(("asset", "liability", "equity"), key=lambda k: (counts.get(k, 0), k == "asset"))

    def _afg_infer_section_coa_type(self, section, afg):
        if section == "pl":
            return self._afg_infer_pl_coa_type(afg)
        if section == "bs":
            return self._afg_infer_bs_coa_type(afg)
        if section in AFG_SECTION_COA_TYPES:
            return next(iter(AFG_SECTION_COA_TYPES[section].keys()))
        return None

    def _afg_norm_statement_label(self, label):
        s = (label or "").strip().lower()
        s = s.replace("&", " and ")
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^a-z0-9 ]+", "", s)
        return re.sub(r"\s+", " ", s).strip()

    def _afg_ledger_caption_norm(self, node):
        cap = (node.get("ledger_caption") or "").strip()
        if not cap:
            lab = (node.get("label") or "").strip()
            cap = re.sub(r"^\d+\s*[|:\-–]?\s*", "", lab).strip() or lab
        return self._afg_norm_statement_label(cap)

    def _afg_labels_redundant(self, parent, child):
        """True when parent/child captions are the same audited line (e.g. Inventories / Inventories)."""
        p = self._afg_norm_statement_label(parent.get("label"))
        clvl = int(child.get("level") or 0)
        if clvl == 3:
            c = self._afg_ledger_caption_norm(child)
        else:
            c = self._afg_norm_statement_label(
                child.get("group_caption") or child.get("label")
            )
        if not p or not c:
            return False
        if p == c:
            return True
        if len(p) >= 8 and len(c) >= 8 and (p in c or c in p):
            return True
        return False

    def _afg_collapse_redundant_statement_branch(self, branch):
        """Collapse only true duplicates: AFG caption + same-named CoA group (Inventories→Inventories).

        Keep all ledger (L3) rows so expand/drill still shows brown ledgers (e.g. under Revenue).
        Do not drop the sole L3 under an AFG — that made expand look blank.
        """
        if not branch:
            return branch
        branch = dict(branch)
        children = [
            self._afg_collapse_redundant_statement_branch(ch)
            for ch in (branch.get("children") or [])
        ]

        def _merge_meta(into, src):
            drill = list(into.get("drill_account_ids") or [])
            for aid in src.get("drill_account_ids") or []:
                if aid and aid not in drill:
                    drill.append(aid)
            into["drill_account_ids"] = drill
            if src.get("group_code") and not into.get("group_code"):
                into["group_code"] = src.get("group_code")
            if src.get("group_caption") and not into.get("group_caption"):
                into["group_caption"] = src.get("group_caption")

        # Only fold sole L2 into L1 when captions are the same (double Inventories)
        if len(children) == 1:
            only = children[0]
            plvl = int(branch.get("level") or 0)
            clvl = int(only.get("level") or 0)
            if plvl == 1 and clvl == 2 and self._afg_labels_redundant(branch, only):
                _merge_meta(branch, only)
                children = list(only.get("children") or [])

        branch["children"] = children
        return branch

    def _afg_collapse_statement_trees(self, roots):
        return [
            self._afg_collapse_redundant_statement_branch(r)
            for r in (roots or [])
        ]

    def _afg_child_bs_type_from_node(self, node):
        """Infer asset/liability/equity for one branch under Ungrouped BS."""
        Account = self.env["account.account"].sudo()
        aids = list(node.get("drill_account_ids") or [])
        if node.get("account_id"):
            aids.append(int(node["account_id"]))
        for ch in node.get("children") or []:
            aids.extend(ch.get("drill_account_ids") or [])
            if ch.get("account_id"):
                aids.append(int(ch["account_id"]))
        accounts = Account.browse([int(a) for a in aids if a]).exists()
        groups = [g for g in accounts.mapped("internal_group") if g in ("asset", "liability", "equity")]
        if not groups:
            return "asset"
        counts = defaultdict(int)
        for g in groups:
            counts[g] += 1
        return max(("asset", "liability", "equity"), key=lambda k: (counts.get(k, 0), k == "asset"))

    def _afg_child_pl_type_from_node(self, node):
        """Infer sales / cost_of_revenue / expenses for one Ungrouped P&L branch (Odoo types)."""
        Account = self.env["account.account"].sudo()
        aids = list(node.get("drill_account_ids") or [])
        if node.get("account_id"):
            aids.append(int(node["account_id"]))
        for ch in node.get("children") or []:
            aids.extend(ch.get("drill_account_ids") or [])
            if ch.get("account_id"):
                aids.append(int(ch["account_id"]))
        accounts = Account.browse([int(a) for a in aids if a]).exists()
        cost_rev_ids = set(self._afg_cost_revenue_type_ids())
        votes = {"sales": 0, "cost_of_revenue": 0, "expenses": 0}
        for acc in accounts:
            if acc.internal_group == "income":
                votes["sales"] += 1
            elif acc.user_type_id.id in cost_rev_ids:
                votes["cost_of_revenue"] += 1
            elif acc.internal_group == "expense":
                votes["expenses"] += 1
        best = max(votes, key=lambda k: (votes[k], k == "expenses"))
        return best if votes[best] else "expenses"

    def _afg_split_ungrouped_pl_root(self, root):
        """Put Ungrouped P&L ledgers under Sales / Cost of Materials / Expenses like Odoo."""
        children = list(root.get("children") or [])
        if not children:
            key = self._afg_child_pl_type_from_node(root)
            piece = dict(root)
            piece["_afg_forced_pl_type"] = key
            return [piece]
        buckets = OrderedDict((k, []) for k in ("sales", "cost_of_revenue", "expenses"))
        for child in children:
            buckets[self._afg_child_pl_type_from_node(child)].append(child)
        labels = {
            "sales": _("Ungrouped income (needs review)"),
            "cost_of_revenue": _("Ungrouped cost of materials (needs review)"),
            "expenses": _("Ungrouped expenses (needs review)"),
        }
        out = []
        for key, kids in buckets.items():
            if not kids:
                continue
            prior, current, co_prior, co_curr = self._afg_sum_branch_nodes(kids)
            piece = dict(root)
            piece["id"] = "%s-%s" % (root.get("id"), key)
            piece["label"] = labels[key]
            piece["afg_caption"] = labels[key]
            piece["children"] = kids
            piece["prior"] = prior
            piece["current"] = current
            piece["co_prior"] = co_prior
            piece["co_curr"] = co_curr
            piece["_afg_forced_pl_type"] = key
            piece["is_ungrouped_review"] = True
            piece["ungrouped_code"] = "AFG_UNGRP_PL"
            piece["group_id"] = self.env["audited.financial.group"].search(
                [("code", "=", "AFG_UNGRP_PL"), ("company_id", "=", False)], limit=1
            ).id
            piece["drill_account_ids"] = self._afg_leaf_account_ids_from_node(piece)
            out.append(piece)
        return out or [root]

    def _afg_split_ungrouped_bs_root(self, root):
        """Place mixed BS children under Assets / Liabilities / Equity (Odoo internal_group)."""
        children = list(root.get("children") or [])
        if not children:
            # Leaf-style root: classify whole branch by its accounts
            key = self._afg_child_bs_type_from_node(root)
            piece = dict(root)
            piece["_afg_forced_bs_type"] = key
            return [piece]
        buckets = OrderedDict((k, []) for k in ("asset", "liability", "equity"))
        for child in children:
            buckets[self._afg_child_bs_type_from_node(child)].append(child)
        base = (root.get("afg_caption") or root.get("label") or _("Ungrouped")).strip()
        labels = {
            "asset": _("%s - assets") % base,
            "liability": _("%s - liabilities") % base,
            "equity": _("%s - equity") % base,
        }
        # Keep legacy captions for the generic Ungrouped preset
        if (root.get("afg_code") or "") == "AFG_UNGRP_BS" or "ungrouped" in base.lower():
            labels = {
                "asset": _("Ungrouped assets (needs review)"),
                "liability": _("Ungrouped liabilities (needs review)"),
                "equity": _("Ungrouped equity (needs review)"),
            }
        out = []
        for key, kids in buckets.items():
            if not kids:
                continue
            prior, current, co_prior, co_curr = self._afg_sum_branch_nodes(kids)
            piece = dict(root)
            piece["id"] = "%s-%s" % (root.get("id"), key)
            piece["label"] = labels[key]
            piece["afg_caption"] = labels[key]
            piece["children"] = kids
            piece["prior"] = prior
            piece["current"] = current
            piece["co_prior"] = co_prior
            piece["co_curr"] = co_curr
            piece["_afg_forced_bs_type"] = key
            piece["is_ungrouped_review"] = True
            piece["ungrouped_code"] = "AFG_UNGRP_BS"
            piece["group_id"] = self.env["audited.financial.group"].search(
                [("code", "=", "AFG_UNGRP_BS"), ("company_id", "=", False)], limit=1
            ).id
            piece["drill_account_ids"] = self._afg_leaf_account_ids_from_node(piece)
            out.append(piece)
        return out or [root]

    def _afg_sum_branch_nodes(self, nodes):
        """Sum prior/current (and optional per-company columns) for dashboard nodes."""
        nodes = nodes or []
        prior = sum(float(n.get("prior") or 0.0) for n in nodes)
        current = sum(float(n.get("current") or 0.0) for n in nodes)
        co_prior = None
        co_curr = None
        # Prefer co_* when any child has them; fill gaps from prior/current so CY/plug
        # lines (no co_*) still affect screen columns (statement_hide_audited_totals).
        width = 0
        for n in nodes:
            if n.get("co_prior") is not None:
                width = max(width, len(n.get("co_prior") or []))
            if n.get("co_curr") is not None:
                width = max(width, len(n.get("co_curr") or []))
        if width:
            co_prior = []
            co_curr = []
            for i in range(width):
                sp = sc = 0.0
                for n in nodes:
                    cp = n.get("co_prior")
                    cc = n.get("co_curr")
                    if cp is not None and i < len(cp):
                        sp += float(cp[i] or 0.0)
                    elif i == 0:
                        sp += float(n.get("prior") or 0.0)
                    if cc is not None and i < len(cc):
                        sc += float(cc[i] or 0.0)
                    elif i == 0:
                        sc += float(n.get("current") or 0.0)
                co_prior.append(sp)
                co_curr.append(sc)
        return prior, current, co_prior, co_curr

    def _afg_node_is_ledger_row(self, node):
        """True for L3 / explicit ledger lines (not L1/L2 group shells)."""
        if not node:
            return False
        lvl = int(node.get("level") or 0)
        if lvl >= 4:
            return False
        if node.get("is_ledger"):
            return True
        if lvl == 3:
            return True
        if lvl in (0, 1, 2):
            return False
        return not bool(node.get("children"))

    def _afg_label_merge_key(self, node):
        """Stable key to fold multicompany siblings with the same caption.

        Ledgers: prefer normalized *name* (not code) so the same caption across
        companies becomes one unique row. Codes alone often differ per company.
        """
        lvl = int(node.get("level") or 0)
        is_ledger = self._afg_node_is_ledger_row(node)
        if is_ledger:
            cap = self._afg_ledger_caption_norm(node)
            if not cap:
                cap = self._afg_normalize_caption(
                    node.get("ledger_caption") or node.get("label") or ""
                )
            if cap:
                return ("ledger", cap)
            code = (node.get("ledger_code") or "").strip().lower()
            if code:
                return ("ledger", "code", code)
        if lvl in (0, 1, 2) or not is_ledger:
            cap = self._afg_normalize_caption(
                node.get("group_caption")
                or node.get("afg_caption")
                or node.get("label")
                or ""
            )
            return (lvl, "grp", cap or (node.get("label") or "").strip().lower())
        label = (node.get("label") or "").strip().lower()
        return (lvl, label)

    def _afg_merge_co_columns(self, seq_a, seq_b):
        if seq_a is None and seq_b is None:
            return None
        a = list(seq_a or [])
        b = list(seq_b or [])
        width = max(len(a), len(b))
        if not width:
            return []
        a = a + [0.0] * (width - len(a))
        b = b + [0.0] * (width - len(b))
        return [float(a[i] or 0.0) + float(b[i] or 0.0) for i in range(width)]

    def _afg_accumulate_merged_node(self, existing, node):
        """Add amounts / drills / children from node into existing (same merge key)."""
        existing["prior"] = float(existing.get("prior") or 0.0) + float(node.get("prior") or 0.0)
        existing["current"] = float(existing.get("current") or 0.0) + float(node.get("current") or 0.0)
        if node.get("tb_amounts") is not None:
            ex_tb = list(existing.get("tb_amounts") or [0.0] * len(node["tb_amounts"]))
            nd_tb = node["tb_amounts"]
            width = max(len(ex_tb), len(nd_tb))
            ex_tb = ex_tb + [0.0] * (width - len(ex_tb))
            nd_tb = list(nd_tb) + [0.0] * (width - len(nd_tb))
            existing["tb_amounts"] = [
                float(ex_tb[i] or 0.0) + float(nd_tb[i] or 0.0) for i in range(width)
            ]
        existing["co_prior"] = self._afg_merge_co_columns(existing.get("co_prior"), node.get("co_prior"))
        existing["co_curr"] = self._afg_merge_co_columns(existing.get("co_curr"), node.get("co_curr"))
        existing["children"] = self._afg_consolidate_branch_tree(
            (existing.get("children") or []) + (node.get("children") or [])
        )
        drill = list(existing.get("drill_account_ids") or [])
        for aid in node.get("drill_account_ids") or []:
            if aid and aid not in drill:
                drill.append(aid)
        existing["drill_account_ids"] = drill
        if node.get("account_id") and not existing.get("account_id"):
            existing["account_id"] = node.get("account_id")
        if node.get("internal_group") and not existing.get("internal_group"):
            existing["internal_group"] = node.get("internal_group")

    def _afg_merge_sibling_nodes_by_key(self, nodes):
        """Fold a flat list of siblings that share ``_afg_label_merge_key``."""
        if not nodes:
            return []
        merged = OrderedDict()
        order = []
        for node in nodes:
            node = dict(node)
            key = self._afg_label_merge_key(node)
            if key not in merged:
                merged[key] = node
                order.append(key)
                continue
            self._afg_accumulate_merged_node(merged[key], node)
        return [merged[k] for k in order]

    def _afg_fold_ledgers_across_child_groups(self, children):
        """Merge same-name L3 ledgers that sit under different L2 group siblings.

        Multi-company charts often put the same caption under different Odoo account
        groups per company — without this, EMPLOYEE COSTS shows three identical L3 rows.
        """
        if not children:
            return []
        group_nodes = []
        other_nodes = []
        for ch in children:
            ch = dict(ch)
            if self._afg_node_is_ledger_row(ch):
                other_nodes.append(ch)
            elif int(ch.get("level") or 0) == 2 or (
                ch.get("children") and int(ch.get("level") or 0) not in (0, 1)
            ):
                group_nodes.append(ch)
            else:
                # L1 / type shells keep structure; still recurse already done
                other_nodes.append(ch)

        if len(group_nodes) < 2:
            return self._afg_merge_sibling_nodes_by_key(group_nodes + other_nodes)

        by_cap = OrderedDict()
        cap_order = []
        home_gid = {}
        for g_idx, g in enumerate(group_nodes):
            kept = []
            for led in list(g.get("children") or []):
                led = dict(led)
                if not self._afg_node_is_ledger_row(led):
                    kept.append(led)
                    continue
                key = self._afg_label_merge_key(led)
                if key not in by_cap:
                    by_cap[key] = led
                    cap_order.append(key)
                    home_gid[key] = g_idx
                else:
                    self._afg_accumulate_merged_node(by_cap[key], led)
            g["children"] = kept

        for key in cap_order:
            led = by_cap[key]
            g_idx = home_gid.get(key, 0)
            group_nodes[g_idx].setdefault("children", []).append(led)

        rebuilt = []
        for g in group_nodes:
            kids = self._afg_merge_sibling_nodes_by_key(g.get("children") or [])
            if not kids and not self._afg_node_is_ledger_row(g):
                # Drop empty L2 shells after ledgers were folded elsewhere
                continue
            g["children"] = kids
            if kids:
                prior, current, co_p, co_c = self._afg_sum_branch_nodes(kids)
                g["prior"] = prior
                g["current"] = current
                if co_p is not None:
                    g["co_prior"] = co_p
                if co_c is not None:
                    g["co_curr"] = co_c
                if any(k.get("tb_amounts") is not None for k in kids):
                    g["tb_amounts"] = self._afg_sum_tb_amounts(kids)
            rebuilt.append(g)

        return self._afg_merge_sibling_nodes_by_key(rebuilt + other_nodes)

    def _afg_consolidate_branch_tree(self, nodes):
        """Merge same-name siblings (and same-name ledgers across L2) for multicompany."""
        if not nodes:
            return []
        processed = []
        for node in nodes:
            node = dict(node)
            lvl = int(node.get("level") or 0)
            if lvl >= 4:
                continue
            node["children"] = self._afg_consolidate_branch_tree(node.get("children") or [])
            node["children"] = self._afg_fold_ledgers_across_child_groups(node["children"])
            processed.append(node)
        return self._afg_merge_sibling_nodes_by_key(processed)

    def _afg_type_shell(self, section, type_key, meta, children):
        prior, current, co_prior, co_curr = self._afg_sum_branch_nodes(children)
        nature = self._afg_nature_from_type_key(type_key) or (
            "asset" if section == "bs" else "income"
        )
        return {
            "id": "type-%s-%s" % (section, type_key),
            "type_key": type_key,
            "label": _(meta["label"]),
            "note": "",
            "level": 0,
            "prior": prior,
            "current": current,
            "sensitive": False,
            "co_prior": co_prior,
            "co_curr": co_curr,
            "group_code": "",
            "group_caption": "",
            "ledger_code": "",
            "ledger_caption": "",
            "drill_account_ids": [],
            "report_section": section,
            "group_id": False,
            "is_computed": False,
            "internal_group": nature,
            "children": children,
        }

    def _afg_computed_type_shell(self, section, type_key, meta, source_nodes):
        """Total row from one or more type shells (net profit, total assets, etc.)."""
        prior, current, co_prior, co_curr = self._afg_sum_branch_nodes(source_nodes)
        # Odoo P&amp;L Net Profit: Income − Expenses (loss is negative). AFG children use
        # raw balances (income credit −, expense debit +), so negate the sum to match Odoo.
        if section == "pl" and type_key == "net_profit":
            prior = -float(prior or 0.0)
            current = -float(current or 0.0)
            if co_prior is not None:
                co_prior = [-float(v or 0.0) for v in co_prior]
            if co_curr is not None:
                co_curr = [-float(v or 0.0) for v in co_curr]
        return {
            "id": "type-%s-%s" % (section, type_key),
            "type_key": type_key,
            "label": _(meta["label"]),
            "note": "",
            "level": 0,
            "prior": prior,
            "current": current,
            "sensitive": False,
            "co_prior": co_prior,
            "co_curr": co_curr,
            "group_code": "",
            "group_caption": "",
            "ledger_code": "",
            "ledger_caption": "",
            "drill_account_ids": [],
            "report_section": section,
            "group_id": False,
            "is_computed": True,
            "children": [],
        }

    def _afg_wrap_section_with_coa_types(self, section, roots):
        """Insert CoA type parents (level 0) above AFG roots for hierarchical statements."""
        type_meta = AFG_SECTION_COA_TYPES.get(section)
        if not type_meta or not roots:
            return roots
        Group = self.env["audited.financial.group"].sudo()
        bucket_keys = [
            k for k, m in type_meta.items()
            if not m.get("computed_from") and not m.get("computed")
        ]
        buckets = OrderedDict((k, []) for k in bucket_keys)
        for root in roots:
            afg = Group.browse(root.get("group_id")) if root.get("group_id") else Group.browse()
            code = (afg.code or "").strip() if afg else ""
            # Mixed Ungrouped / Related party BS: split by account internal_group (Odoo BS)
            if section == "bs" and code in ("AFG_UNGRP_BS", "AFG_REL"):
                for piece in self._afg_split_ungrouped_bs_root(root):
                    type_key = piece.pop("_afg_forced_bs_type", None) or "asset"
                    if type_key not in buckets:
                        type_key = bucket_keys[0] if bucket_keys else type_key
                    buckets[type_key].append(piece)
                continue
            if section == "pl" and code == "AFG_UNGRP_PL":
                for piece in self._afg_split_ungrouped_pl_root(root):
                    type_key = piece.pop("_afg_forced_pl_type", None) or "expenses"
                    if type_key not in buckets:
                        type_key = bucket_keys[0] if bucket_keys else type_key
                    buckets[type_key].append(piece)
                continue
            type_key = root.get("_afg_forced_pl_type") or root.get("_afg_forced_bs_type") or self._afg_infer_section_coa_type(section, afg)
            if type_key not in buckets:
                type_key = bucket_keys[0] if bucket_keys else type_key
            buckets[type_key].append(root)
        built = {}
        wrapped = []
        for type_key, meta in type_meta.items():
            computed_from = meta.get("computed_from")
            if computed_from:
                src_nodes = [built[k] for k in computed_from if k in built]
                if not src_nodes and section == "pl" and type_key == "net_profit":
                    src_nodes = roots
                if not src_nodes and section == "pl" and type_key == "net_profit" and roots:
                    shell = self._afg_computed_type_shell(section, type_key, meta, roots)
                    built[type_key] = shell
                    wrapped.append(shell)
                    continue
                if not src_nodes:
                    continue
                shell = self._afg_computed_type_shell(section, type_key, meta, src_nodes)
                built[type_key] = shell
                wrapped.append(shell)
                continue
            children = buckets.get(type_key) or []
            if not children:
                continue
            shell = self._afg_type_shell(section, type_key, meta, children)
            built[type_key] = shell
            wrapped.append(shell)
        return wrapped

    def _afg_pl_net_amounts(self, pl_roots):
        """Net P&amp;L as raw Odoo balance (income + expense) for BS current-year plug.

        Uses sales/cost/expenses shells (signed), not the Net Profit display row.
        Face presentation is applied later for UI/export only.
        """
        by_key = {n.get("type_key"): n for n in (pl_roots or []) if n.get("type_key")}
        parts = [by_key[k] for k in ("sales", "cost_of_revenue", "expenses") if k in by_key]
        if parts:
            prior, current, _a, _b = self._afg_sum_branch_nodes(parts)
            return float(prior or 0.0), float(current or 0.0)
        if by_key.get("net_profit"):
            n = by_key["net_profit"]
            # Legacy: invert Odoo-style display net back to raw balance
            return -float(n.get("prior") or 0.0), -float(n.get("current") or 0.0)
        parts = list(pl_roots or [])
        if not parts:
            return 0.0, 0.0
        prior, current, _a, _b = self._afg_sum_branch_nodes(parts)
        return float(prior or 0.0), float(current or 0.0)

    def _afg_node_looks_like_retained_earnings(self, node):
        """True for Retained Earnings presentation / ledger nodes (not CY P&L)."""
        if not node or node.get("type_key") in ("cy_pnl", "bs_diff"):
            return False
        if node.get("id") in ("bs-cy-pnl", "bs-equation-diff", "bs-retained-earnings"):
            return node.get("id") == "bs-retained-earnings"
        blob = " ".join([
            str(node.get("label") or ""),
            str(node.get("afg_caption") or ""),
            str(node.get("ledger_caption") or ""),
            str(node.get("group_caption") or ""),
        ]).lower()
        if "current year" in blob or "profit/(loss)" in blob or "profit / loss" in blob:
            return False
        if self._afg_node_looks_like_previous_year_earnings(node):
            return False
        return (
            "retained earning" in blob
            or "retained profit" in blob
            or "accumulated profit" in blob
            or "accumulated loss" in blob
            or "undistributed" in blob
        )

    def _afg_node_looks_like_previous_year_earnings(self, node):
        """True for Previous Year Earnings style lines (fold into RE; do not show)."""
        if not node:
            return False
        blob = " ".join([
            str(node.get("label") or ""),
            str(node.get("afg_caption") or ""),
            str(node.get("ledger_caption") or ""),
            str(node.get("group_caption") or ""),
        ]).lower()
        return (
            "previous year earning" in blob
            or "prior year earning" in blob
            or "previous year profit" in blob
            or "prior year profit" in blob
            or "last year earning" in blob
            or "last year profit" in blob
        )

    def _afg_node_looks_like_bs_diff(self, node):
        """True for Balance Sheet Difference / mapping plug lines (must vanish)."""
        if not node:
            return False
        if node.get("type_key") == "bs_diff" or node.get("id") == "bs-equation-diff":
            return True
        blob = " ".join([
            str(node.get("label") or ""),
            str(node.get("afg_caption") or ""),
            str(node.get("ledger_caption") or ""),
            str(node.get("group_caption") or ""),
        ]).lower()
        return (
            "balance sheet difference" in blob
            or "balance sheet diff" in blob
            or ("mapping" in blob and "difference" in blob)
            or blob.strip() in ("bs difference", "bs diff", "sofp difference")
        )

    def _afg_node_label_blob(self, node):
        return " ".join([
            str(node.get("label") or ""),
            str(node.get("afg_caption") or ""),
            str(node.get("ledger_caption") or ""),
            str(node.get("group_caption") or ""),
        ]).lower()

    def _afg_node_looks_like_cy_pnl(self, node):
        """True for Profit/(Loss) / Current Year Profit lines on SOFP."""
        if not node:
            return False
        if node.get("type_key") == "cy_pnl" or node.get("id") == "bs-cy-pnl":
            return True
        blob = self._afg_node_label_blob(node)
        if self._afg_node_looks_like_retained_earnings(node):
            return False
        if self._afg_node_looks_like_previous_year_earnings(node):
            return False
        return (
            "current year profit" in blob
            or "current year loss" in blob
            or blob.strip() in (
                "profit/(loss)",
                "profit / (loss)",
                "profit/(loss)",
                "profit or loss",
                "net profit/(loss)",
                "net profit / (loss)",
            )
            or (
                "profit/(loss)" in blob
                and "retained" not in blob
                and "previous" not in blob
                and "prior year" not in blob
            )
        )

    def _afg_strip_bs_diff_nodes(self, parent):
        """Remove Balance Sheet Difference / mapping plugs under parent (any depth)."""
        if not parent:
            return
        kept = []
        for ch in list(parent.get("children") or []):
            if self._afg_node_looks_like_bs_diff(ch):
                continue
            if ch.get("children"):
                self._afg_strip_bs_diff_nodes(ch)
            kept.append(ch)
        parent["children"] = kept

    def _afg_find_cy_pnl_node(self, nodes):
        for node in nodes or []:
            if self._afg_node_looks_like_cy_pnl(node):
                return node
            found = self._afg_find_cy_pnl_node(node.get("children") or [])
            if found:
                return found
        return None

    def _afg_profit_loss_label(self):
        """SOFP label: year is already in column headers — do not say Current Year."""
        return _("Profit for the Year")

    def _afg_equity_earnings_label(self, amount_face):
        """Retained Earnings vs Accumulated Losses (face amount after equity presentation)."""
        if float(amount_face or 0.0) < -0.005:
            return _("Accumulated Losses")
        return _("Retained Earnings")

    def _afg_relabel_retained_earnings_nodes(self, nodes):
        """Rename RE lines to Accumulated Losses when the face balance is negative."""
        for node in nodes or []:
            if self._afg_node_looks_like_retained_earnings(node):
                lab = self._afg_equity_earnings_label(node.get("current"))
                node["label"] = lab
                if node.get("ledger_caption"):
                    node["ledger_caption"] = lab
                if node.get("afg_caption"):
                    node["afg_caption"] = lab
            self._afg_relabel_retained_earnings_nodes(node.get("children") or [])

    def _afg_equity_component_bucket(self, label):
        """Bucket equity ledgers for L1 Official face (capital / current / reserve / RE)."""
        low = (label or "").lower()
        if any(k in low for k in ("drawing", "dividend", "distribution", "withdraw")):
            return "current"
        if any(k in low for k in ("statutory reserve", "legal reserve", "reserve account")):
            return "reserve"
        if "reserve" in low and "retained" not in low:
            return "reserve"
        if any(k in low for k in (
            "current account", "partner current", "owner current", "propriet",
        )):
            return "current"
        if any(k in low for k in ("capital", "share capital", "paid up", "paid-up")):
            return "capital"
        return "re"

    def _afg_bs_present_equity_components(self, bs_roots):
        """L1 equity face: Capital, Current account, Statutory reserve, Profit, RE.

        Do not fold current-year profit into RE. Do not lump current account into RE.
        """
        if not bs_roots:
            return bs_roots
        eq = self._afg_type_by_key(bs_roots, "equity") or self._afg_find_equity_shell(bs_roots)
        if not eq:
            return bs_roots
        children = list(eq.get("children") or [])
        new_children = []
        changed = False

        def _sum_period(nodes_list):
            width = 0
            for n in nodes_list:
                pam = n.get("period_amounts")
                if pam:
                    width = max(width, len(pam))
            if width < 1:
                return None
            out = [0.0] * width
            for n in nodes_list:
                pam = list(n.get("period_amounts") or [])
                for i, v in enumerate(pam):
                    if i < width:
                        out[i] += float(v or 0.0)
            return out

        def _mk_line(nid, label, prior, current, pam, type_key):
            line = {
                "id": nid,
                "label": label,
                "afg_caption": label,
                "ledger_caption": label,
                "level": 1,
                "is_ledger": True,
                "prior": float(prior or 0.0),
                "current": float(current or 0.0),
                "children": [],
                "type_key": type_key,
                "report_section": "bs",
                "face_scale": 1.0,
            }
            if pam is not None:
                line["period_amounts"] = list(pam)
            return line

        for ch in children:
            if self._afg_node_looks_like_cy_pnl(ch) or ch.get("type_key") == "cy_pnl":
                new_children.append(ch)
                continue
            code = (ch.get("afg_code") or ch.get("group_code") or "").upper()
            lab = (ch.get("label") or ch.get("afg_caption") or "").lower()
            is_owner = code in ("AFG_EQ", "AFG_EQUITY") or any(
                k in lab for k in ("owner equity", "owners' equity", "owners equity")
            )
            if not is_owner:
                # Still rename stray Owner Equity captions
                if "owner equity" in lab or "owners' equity" in lab:
                    renamed = dict(ch)
                    renamed["label"] = self._afg_equity_earnings_label(ch.get("current"))
                    renamed["afg_caption"] = renamed["label"]
                    if renamed.get("ledger_caption"):
                        renamed["ledger_caption"] = renamed["label"]
                    new_children.append(renamed)
                    changed = True
                else:
                    new_children.append(ch)
                continue

            leaves = []

            def _walk(n):
                kids = list(n.get("children") or [])
                lvl = int(n.get("level") if n.get("level") is not None else 0)
                if (not kids) or n.get("is_ledger") or lvl >= 3:
                    leaves.append(n)
                    return
                for k in kids:
                    _walk(k)

            _walk(ch)
            cy_kept = []
            buckets = {"capital": [], "re": [], "current": [], "reserve": []}
            for leaf in leaves:
                if self._afg_node_looks_like_cy_pnl(leaf) or leaf.get("type_key") == "cy_pnl":
                    cy_kept.append(leaf)
                    continue
                b = self._afg_equity_component_bucket(
                    leaf.get("ledger_caption") or leaf.get("label") or leaf.get("afg_caption") or ""
                )
                buckets[b].append(leaf)

            def _sum_pair(lst):
                p = c = 0.0
                for n in lst:
                    p += float(n.get("prior") or 0.0)
                    c += float(n.get("current") or 0.0)
                return p, c

            cap_p, cap_c = _sum_pair(buckets["capital"])
            if abs(cap_p) < 0.505 and abs(cap_c) >= 0.505:
                cap_p = cap_c
            cur_p, cur_c = _sum_pair(buckets["current"])
            res_p, res_c = _sum_pair(buckets["reserve"])
            re_p, re_c = _sum_pair(buckets["re"])

            def _emit(nid, label, prior, current, lst, type_key):
                if abs(current) < 0.505 and abs(prior) < 0.505 and not lst:
                    return
                pam = _sum_period(lst) if lst else None
                new_children.append(_mk_line(nid, label, prior, current, pam, type_key))

            _emit(
                "bs-share-capital",
                _("Capital account"),
                cap_p,
                cap_c,
                buckets["capital"],
                "share_capital",
            )
            _emit(
                "bs-owner-current",
                _("Current account"),
                cur_p,
                cur_c,
                buckets["current"],
                "owner_current_account",
            )
            _emit(
                "bs-statutory-reserve",
                _("Statutory reserve"),
                res_p,
                res_c,
                buckets["reserve"],
                "statutory_reserve",
            )
            for cy in cy_kept:
                new_children.append(cy)
            _emit(
                "bs-accumulated-earnings",
                self._afg_equity_earnings_label(re_c),
                re_p,
                re_c,
                buckets["re"],
                "retained_earnings",
            )
            changed = True
            self._afg_log_l1_equity_clubbing_override()
            continue

        if not changed:
            return bs_roots
        eq["children"] = new_children
        self._afg_refresh_branch_totals(eq)
        # Keep period_amounts on equity shell in sync
        if any(c.get("period_amounts") for c in new_children):
            width = max(len(c.get("period_amounts") or []) for c in new_children)
            pam = [0.0] * width
            for c in new_children:
                for i, v in enumerate(c.get("period_amounts") or []):
                    pam[i] += float(v or 0.0)
            eq["period_amounts"] = pam
            if pam:
                eq["prior"] = float(pam[0])
                eq["current"] = float(pam[-1])
        return self._afg_refresh_bs_type_shells(bs_roots)

    def _afg_find_retained_earnings_node(self, nodes):
        """Depth-first search for a Retained Earnings node under Equity."""
        for node in nodes or []:
            if self._afg_node_looks_like_retained_earnings(node):
                return node
            found = self._afg_find_retained_earnings_node(node.get("children") or [])
            if found:
                return found
        return None

    def _afg_add_amount_to_node_field(self, node, field, amount):
        """Add signed amount to prior or current (and matching co_*[0])."""
        if not node or not amount:
            return
        node[field] = float(node.get(field) or 0.0) + float(amount)
        co_key = "co_prior" if field == "prior" else "co_curr"
        co = list(node.get(co_key) or [])
        if not co:
            co = [float(node.get(field) or 0.0)]
        else:
            co[0] = float(co[0] or 0.0) + float(amount)
        node[co_key] = co

    def _afg_refresh_branch_totals(self, node):
        """Recompute prior/current from children after IFRS RE rollover."""
        if not node:
            return
        children = list(node.get("children") or [])
        if not children:
            return
        for ch in children:
            self._afg_refresh_branch_totals(ch)
        prior, current, co_p, co_c = self._afg_sum_branch_nodes(children)
        node["prior"] = prior
        node["current"] = current
        if co_p is not None:
            node["co_prior"] = co_p
        if co_c is not None:
            node["co_curr"] = co_c

    def _afg_present_as_equity_ledger(self, node):
        """Show Retained Earnings / Profit/(Loss) as L3 brown ledger-style face lines."""
        if not node:
            return node
        label = (
            node.get("label")
            or node.get("afg_caption")
            or node.get("ledger_caption")
            or ""
        )
        node["level"] = 3
        node["is_ledger"] = True
        node["ledger_caption"] = label
        if not node.get("afg_caption"):
            node["afg_caption"] = label
        if not node.get("label"):
            node["label"] = label
        node["children"] = []
        return node

    def _afg_normalize_equity_ledger_face(self, equity_node):
        """Force RE / Profit/(Loss) under Equity to L3 ledger presentation."""
        if not equity_node:
            return
        for ch in list(equity_node.get("children") or []):
            if (
                ch.get("type_key") in ("retained_earnings", "cy_pnl")
                or self._afg_node_looks_like_retained_earnings(ch)
                or self._afg_node_looks_like_cy_pnl(ch)
            ):
                self._afg_present_as_equity_ledger(ch)

    def _afg_ensure_retained_earnings_node(self, equity_node):
        """Return Retained Earnings under Equity (create if missing)."""
        children = list(equity_node.get("children") or [])
        re_node = self._afg_find_retained_earnings_node(children)
        if re_node:
            self._afg_present_as_equity_ledger(re_node)
            return re_node
        re_node = {
            "id": "bs-retained-earnings",
            "type_key": "retained_earnings",
            "label": _("Retained Earnings"),
            "note": "",
            "level": 3,
            "prior": 0.0,
            "current": 0.0,
            "sensitive": True,
            "co_prior": [0.0],
            "co_curr": [0.0],
            "group_code": "",
            "group_caption": "",
            "ledger_code": "",
            "ledger_caption": _("Retained Earnings"),
            "drill_account_ids": [],
            "report_section": "bs",
            "group_id": False,
            "afg_code": "",
            "afg_caption": _("Retained Earnings"),
            "is_computed": True,
            "is_ledger": True,
            "children": [],
        }
        insert_at = len(children)
        for i, ch in enumerate(children):
            if ch.get("type_key") in ("cy_pnl", "bs_diff") or ch.get("id") in (
                "bs-cy-pnl", "bs-equation-diff",
            ):
                insert_at = i
                break
        equity_node["children"] = children[:insert_at] + [re_node] + children[insert_at:]
        return re_node

    def _afg_fold_previous_year_earnings_into_re(self, equity_node):
        """Move Previous Year Earnings ledger amounts into RE and drop those lines."""
        if not equity_node:
            return
        re_node = self._afg_ensure_retained_earnings_node(equity_node)

        def _fold(parent):
            kept = []
            for ch in list(parent.get("children") or []):
                if self._afg_node_looks_like_previous_year_earnings(ch):
                    self._afg_add_amount_to_node_field(re_node, "prior", ch.get("prior"))
                    self._afg_add_amount_to_node_field(re_node, "current", ch.get("current"))
                    continue
                if ch.get("children"):
                    _fold(ch)
                    if ch.get("children") or not self._afg_node_looks_like_previous_year_earnings(ch):
                        # refresh after nested fold
                        if ch.get("children"):
                            self._afg_refresh_branch_totals(ch)
                        kept.append(ch)
                    continue
                kept.append(ch)
            parent["children"] = kept

        _fold(equity_node)
        self._afg_refresh_branch_totals(equity_node)

    def _afg_roll_prior_pnl_into_retained_earnings(self, equity_node, pnl_prior):
        """Fold explicit 'Previous Year Earnings' ledger lines into RE only.

        Do **not** add P&L prior net into RE.current — CoA retained / unaffected
        earnings already hold closed prior-year results. Adding again double-counts
        (Assets ≠ Equity+Liabilities by exactly prior profit).
        """
        if not equity_node:
            return equity_node
        self._afg_fold_previous_year_earnings_into_re(equity_node)
        return equity_node

    def _afg_find_equity_shell(self, bs_roots):
        """Locate Equity type shell, or the best AFG/Owner-equity branch when types missing."""
        for node in bs_roots or []:
            if node.get("type_key") == "equity":
                return node
        for node in bs_roots or []:
            code = (node.get("afg_code") or node.get("group_code") or "").upper()
            if code in ("AFG_EQ", "AFG_EQUITY"):
                return node
            lab = (node.get("label") or node.get("afg_caption") or "").lower()
            if any(k in lab for k in ("owner equity", "owners' equity", "shareholder", "stockholder")):
                return node
            if lab.strip() in ("equity", "total equity"):
                return node
        return None

    def _afg_bs_inject_cy_earnings(self, bs_roots, pl_roots):
        """Equity: CoA RE stock + separate Profit/(Loss) for the Year (no double count).

        - Label is Profit/(Loss) — year comes from column headers.
        - Prior-year result stays in CoA RE / unaffected earnings (not re-added).
        - Balance Sheet Difference / mapping plugs are never shown.
        """
        if not bs_roots:
            return bs_roots

        pnl_prior, pnl_current = self._afg_pl_net_amounts(pl_roots)
        pl_label = self._afg_profit_loss_label()

        def _ensure_cy_under_equity(equity_node):
            self._afg_strip_bs_diff_nodes(equity_node)
            self._afg_roll_prior_pnl_into_retained_earnings(equity_node, pnl_prior)
            children = list(equity_node.get("children") or [])
            cy = self._afg_find_cy_pnl_node(children)
            if cy:
                cy["type_key"] = "cy_pnl"
                cy["id"] = cy.get("id") or "bs-cy-pnl"
                cy["label"] = pl_label
                cy["afg_caption"] = pl_label
                cy["prior"] = pnl_prior
                cy["current"] = pnl_current
                cy["co_prior"] = [pnl_prior]
                cy["co_curr"] = [pnl_current]
                cy["is_computed"] = True
                cy["sensitive"] = False
                cy["children"] = []
                self._afg_present_as_equity_ledger(cy)
                # Keep a single CY line: drop duplicate Profit/(Loss) siblings
                kept = []
                for ch in children:
                    if ch is cy:
                        kept.append(cy)
                        continue
                    if self._afg_node_looks_like_cy_pnl(ch) or self._afg_node_looks_like_bs_diff(ch):
                        continue
                    kept.append(ch)
                equity_node["children"] = kept
            else:
                cy = {
                    "id": "bs-cy-pnl",
                    "type_key": "cy_pnl",
                    "label": pl_label,
                    "note": "",
                    "level": 3,
                    "prior": pnl_prior,
                    "current": pnl_current,
                    "sensitive": False,
                    "co_prior": [pnl_prior],
                    "co_curr": [pnl_current],
                    "group_code": "",
                    "group_caption": "",
                    "ledger_code": "",
                    "ledger_caption": pl_label,
                    "drill_account_ids": [],
                    "report_section": "bs",
                    "group_id": False,
                    "afg_code": "",
                    "afg_caption": pl_label,
                    "is_computed": True,
                    "is_ledger": True,
                    "children": [],
                }
                equity_node["children"] = children + [cy]
            prior, current, co_p, co_c = self._afg_sum_branch_nodes(
                equity_node.get("children") or []
            )
            equity_node["prior"] = prior
            equity_node["current"] = current
            equity_node["co_prior"] = co_p
            equity_node["co_curr"] = co_c
            self._afg_normalize_equity_ledger_face(equity_node)
            return equity_node

        rebuilt = []
        built = {}
        equity_seen = False
        equity_fallback = self._afg_find_equity_shell(bs_roots)
        # Drop orphan root-level Profit/(Loss) — will reattach under Equity
        roots_in = []
        for node in bs_roots or []:
            if self._afg_node_looks_like_cy_pnl(node) and node is not equity_fallback:
                continue
            roots_in.append(node)
        for node in roots_in:
            n = dict(node)
            n["children"] = list(node.get("children") or [])
            tk = n.get("type_key")
            is_equity = tk == "equity" or (equity_fallback is not None and node is equity_fallback)
            if is_equity:
                equity_seen = True
                n["type_key"] = n.get("type_key") or "equity"
                _ensure_cy_under_equity(n)
                built["equity"] = n
            elif tk:
                built[tk] = n
            if tk not in ("total_assets", "total_liabilities", "total_equity_liabilities"):
                rebuilt.append(n)

        if not equity_seen:
            meta = AFG_BS_COA_TYPES.get("equity") or {"label": "Equity", "sequence": 30}
            equity_shell = self._afg_type_shell("bs", "equity", meta, [])
            _ensure_cy_under_equity(equity_shell)
            built["equity"] = equity_shell
            rebuilt.append(equity_shell)

        out = []
        for type_key, meta in AFG_BS_COA_TYPES.items():
            computed_from = meta.get("computed_from")
            if computed_from:
                src = [built[k] for k in computed_from if k in built]
                if not src:
                    continue
                shell = self._afg_computed_type_shell("bs", type_key, meta, src)
                built[type_key] = shell
                out.append(shell)
            elif type_key in built:
                out.append(built[type_key])
        return self._afg_bs_force_accounting_equation(out or rebuilt)

    def _afg_bs_force_accounting_equation(self, bs_roots):
        """Normalize equity presentation — do NOT invent a balancing figure.

        Residual Assets + Liabilities + Equity ≠ 0 is left visible and reported by
        validation (Financial Statements must reconcile to the Trial Balance / mappings).
        Legacy Balance Sheet Difference lines are stripped when empty of meaning.
        """
        if not bs_roots:
            return bs_roots
        by_key = {n.get("type_key"): n for n in bs_roots if n.get("type_key")}
        asset = by_key.get("asset")
        liability = by_key.get("liability")
        equity = by_key.get("equity")
        if not asset or not equity:
            return bs_roots

        # Strip any legacy Balance Sheet Difference / mapping plug lines (label or type)
        self._afg_strip_bs_diff_nodes(equity)
        # Normalize Profit/(Loss) caption if present
        cy = self._afg_find_cy_pnl_node(equity.get("children") or [])
        if cy:
            pl_label = self._afg_profit_loss_label()
            cy["label"] = pl_label
            cy["afg_caption"] = pl_label
            self._afg_present_as_equity_ledger(cy)
        self._afg_normalize_equity_ledger_face(equity)
        children = list(equity.get("children") or [])
        equity["children"] = children

        residual_prior = 0.0
        residual_current = 0.0
        for field in ("prior", "current"):
            a = float(asset.get(field) or 0.0)
            l = float((liability or {}).get(field) or 0.0)
            e_body = sum(float(c.get(field) or 0.0) for c in children)
            # Signed CoA: a + l + e should be ~0. Residual is unexplained mapping gap.
            residual = -(a + l + e_body)
            if field == "prior":
                residual_prior = residual
            else:
                residual_current = residual

        # Record residual for validation / L4 recon — never absorb into Retained Earnings.
        equity["equation_residual_prior"] = residual_prior
        equity["equation_residual_current"] = residual_current
        if abs(residual_prior) > 0.505 or abs(residual_current) > 0.505:
            equity["equation_unexplained"] = True

        prior, current, co_p, co_c = self._afg_sum_branch_nodes(equity.get("children") or [])
        equity["prior"] = prior
        equity["current"] = current
        equity["co_prior"] = co_p
        equity["co_curr"] = co_c
        by_key["equity"] = equity

        out = []
        for type_key, meta in AFG_BS_COA_TYPES.items():
            computed_from = meta.get("computed_from")
            if computed_from:
                src = [by_key[k] for k in computed_from if k in by_key]
                if not src:
                    continue
                out.append(self._afg_computed_type_shell("bs", type_key, meta, src))
            elif type_key in by_key:
                out.append(by_key[type_key])
        return out

    def _afg_bs_balance_check(self, bs_roots):
        """Return (ok, asset_current, equity_liab_current, diff) on face/print figures.

        Compares the same Total Assets vs Total Equity and Liabilities amounts that appear
        on the statement (signed face figures). Does **not** PASS opposite signs via abs().
        """
        by_key = {n.get("type_key"): n for n in (bs_roots or []) if n.get("type_key")}
        assets = by_key.get("total_assets") or by_key.get("asset")
        eq_liab = by_key.get("total_equity_liabilities")
        if not assets or not eq_liab:
            return True, 0.0, 0.0, 0.0
        a = float(assets.get("current") or 0.0)
        e = float(eq_liab.get("current") or 0.0)
        diff = a - e
        return abs(diff) <= 0.005, a, e, diff

    def _afg_prune_zero_branches(self, branch):
        """Drop group/ledger rows with zero balance in all columns.

        Includes L1 AFG groups (e.g. Ungrouped / needs review) so empty buckets
        disappear on P&L, SOFP, Equity, and statement-style TB trees.
        """
        if not branch:
            return None
        children = []
        for ch in branch.get("children") or []:
            pruned = self._afg_prune_zero_branches(ch)
            if pruned:
                children.append(pruned)
        branch = dict(branch, children=children)
        lvl = branch.get("level") or 0
        if lvl in (1, 2, 3, 4):
            if not self._afg_branch_has_balance(
                branch.get("prior"), branch.get("current"),
                branch.get("co_prior"), branch.get("co_curr"),
                tb_amounts=branch.get("tb_amounts"),
            ):
                return None
        return branch

    def _afg_prune_statement_roots(self, roots):
        """Prune zero branches; drop empty non-computed L0 type shells."""
        out = []
        for root in roots or []:
            pruned = self._afg_prune_zero_branches(root)
            if not pruned:
                continue
            if (pruned.get("level") or 0) == 0 and not pruned.get("is_computed"):
                if not (pruned.get("children") or []):
                    continue
            out.append(pruned)
        return out

    def _afg_line_branch(self, line, tb_prior_by_sec=None, tb_curr_by_sec=None, company_order=None):
        ch = line.child_ids.sorted(lambda s: (s.sequence, s.id))
        codes = self._afg_line_branch_codes(line)
        branch = {
            "id": line.id,
            "label": line.label,
            "note": line.note or "",
            "level": line.level,
            "prior": line.amount_prior,
            "current": line.amount_current,
            "sensitive": (line.group_id.sensitivity_category or "none") != "none" if line.group_id else False,
            "co_prior": None,
            "co_curr": None,
            "group_code": codes["group_code"],
            "group_caption": codes["group_caption"],
            "ledger_code": codes["ledger_code"],
            "ledger_caption": codes["ledger_caption"],
            "drill_account_ids": codes["drill_account_ids"],
            "report_section": codes["report_section"],
            "group_id": line.group_id.id if line.group_id else False,
            "ctf_category": False,
            "afg_code": "",
            "afg_caption": "",
            "account_id": (
                line.account_id.id
                if line.level == 3 and line.account_id and line.account_id.exists()
                else False
            ),
            "is_ledger": line.level == 3,
            "children": [],
        }
        if line.level == 1 and line.group_id:
            branch["afg_code"] = (line.group_id.code or "").strip()
            branch["afg_caption"] = (line.label or line.group_id.name or "").strip()
        child_branches = []
        for c in ch:
            sub = self._afg_line_branch(c, tb_prior_by_sec, tb_curr_by_sec, company_order)
            pruned = self._afg_prune_zero_branches(sub)
            if pruned:
                child_branches.append(pruned)
        branch["children"] = child_branches
        if company_order and tb_prior_by_sec is not None and tb_curr_by_sec is not None:
            sec = line.report_section
            acc_ids = self._line_leaf_account_ids(line)
            tp = tb_prior_by_sec.get(sec) or {}
            tc = tb_curr_by_sec.get(sec) or {}
            cols = company_order or []
            consolid = self.env.context.get("afg_dashboard_consolidated_branch_columns")
            if consolid and len(cols) > 1:
                branch["co_prior"] = [sum(self._sum_accounts_company_tb(tp, c, acc_ids) for c in cols)]
                branch["co_curr"] = [sum(self._sum_accounts_company_tb(tc, c, acc_ids) for c in cols)]
            else:
                branch["co_prior"] = [self._sum_accounts_company_tb(tp, cid, acc_ids) for cid in cols]
                branch["co_curr"] = [self._sum_accounts_company_tb(tc, cid, acc_ids) for cid in cols]
            # Prefer live TB / CoA stock over cached line amounts (UE on Undistributed, etc.)
            if acc_ids:
                branch["prior"] = float(sum(branch.get("co_prior") or []) or 0.0)
                branch["current"] = float(sum(branch.get("co_curr") or []) or 0.0)
            if line.level == 3 and acc_ids and cols:
                Account = self.env["account.account"].sudo()
                leaf_companies = sorted({
                    int(acc.company_id.id)
                    for acc in Account.browse([int(a) for a in acc_ids if a]).exists()
                })
                if len(leaf_companies) > 1 and len(cols) > 1:
                    Company = self.env["res.company"].sudo()
                    l4_extra = []
                    for cid in leaf_companies:
                        cid = int(cid)
                        header = self._afg_company_column_header(Company.browse(cid))
                        pv = self._sum_accounts_company_tb(tp, cid, acc_ids)
                        cv = self._sum_accounts_company_tb(tc, cid, acc_ids)
                        if consolid and len(cols) > 1:
                            co_p = [pv]
                            co_c = [cv]
                        else:
                            co_p = [
                                self._sum_accounts_company_tb(tp, int(c2), acc_ids) if int(c2) == cid else 0.0
                                for c2 in cols
                            ]
                            co_c = [
                                self._sum_accounts_company_tb(tc, int(c2), acc_ids) if int(c2) == cid else 0.0
                                for c2 in cols
                            ]
                        acc_row = Account.search(
                            [("id", "in", list(acc_ids)), ("company_id", "=", cid)],
                            limit=1,
                            order="code, id",
                        )
                        company_lbl = header
                        drill_ids = []
                        if acc_row:
                            drill_ids = [acc_row.id]
                        l4_extra.append({
                            "id": "l4-%s-%s" % (line.id, cid),
                            "label": company_lbl,
                            "note": "",
                            "level": 4,
                            "prior": pv,
                            "current": cv,
                            "sensitive": branch["sensitive"],
                            "co_prior": co_p,
                            "co_curr": co_c,
                            "group_code": "",
                            "group_caption": "",
                            "ledger_code": "",
                            "ledger_caption": company_lbl,
                            "drill_account_ids": drill_ids,
                            "l3_line_id": line.id,
                            "branch_company_id": cid,
                            "account_id": acc_row.id if acc_row else False,
                            "report_section": line.report_section,
                            "children": [],
                        })
                    branch["children"] = branch["children"] + l4_extra
        return branch

    def _afg_scale_tree_amounts(self, node, scale, face_scale=None):
        """Deep-copy node tree and multiply prior/current/co_*/period_amounts by scale."""
        import copy
        scale = float(scale)
        n = copy.deepcopy(node)
        fs = float(face_scale if face_scale is not None else scale)

        def _walk(nd):
            nd["prior"] = float(nd.get("prior") or 0.0) * scale
            nd["current"] = float(nd.get("current") or 0.0) * scale
            if nd.get("co_prior") is not None:
                nd["co_prior"] = [float(v or 0.0) * scale for v in (nd.get("co_prior") or [])]
            if nd.get("co_curr") is not None:
                nd["co_curr"] = [float(v or 0.0) * scale for v in (nd.get("co_curr") or [])]
            if nd.get("period_amounts") is not None:
                nd["period_amounts"] = [
                    float(v or 0.0) * scale for v in (nd.get("period_amounts") or [])
                ]
            nd["face_scale"] = fs
            for ch in nd.get("children") or []:
                _walk(ch)

        _walk(n)
        return n

    def _afg_pl_face_amounts(self, roots):
        """Natural P&L: Sales/Revenue positive; costs & expenses positive; net = S − C − E.

        Odoo stores income as credit (−). We flip the sales bucket. Net Profit is already
        stored Odoo-style (loss negative) via ``_afg_computed_type_shell`` — leave it.
        """
        out = []
        for node in roots or []:
            tk = node.get("type_key") or ""
            if tk in AFG_PL_FACE_NEGATE_TYPES:
                out.append(self._afg_scale_tree_amounts(node, -1.0, face_scale=-1.0))
            else:
                # Preserve net_profit / expenses / cost as-is (expenses already +)
                n = self._afg_scale_tree_amounts(node, 1.0, face_scale=1.0)
                out.append(n)
        # Recompute Net Profit from face sales − cost − expenses so the row always
        # matches the visible arithmetic (loss in parentheses).
        by_key = {n.get("type_key"): n for n in out if n.get("type_key")}
        sales = by_key.get("sales")
        cost = by_key.get("cost_of_revenue")
        exp = by_key.get("expenses")
        net = by_key.get("net_profit")
        if net and (sales or cost or exp):
            n_per = 0
            for src in (sales, cost, exp):
                if src and src.get("period_amounts"):
                    n_per = max(n_per, len(src.get("period_amounts") or []))
            if n_per:
                pam = []
                for i in range(n_per):
                    s = float(((sales or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                    c = float(((cost or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                    e = float(((exp or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                    pam.append(s - c - e)
                net["period_amounts"] = pam
                net["prior"] = float(pam[0] if pam else 0.0)
                net["current"] = float(pam[-1] if pam else 0.0)
            else:
                for field in ("prior", "current"):
                    s = float((sales or {}).get(field) or 0.0)
                    c = float((cost or {}).get(field) or 0.0)
                    e = float((exp or {}).get(field) or 0.0)
                    # Face net profit/(loss) = sales − materials − expenses
                    net[field] = s - c - e
            # Keep single-company columns aligned with face net
            net["co_prior"] = [float(net.get("prior") or 0.0)]
            net["co_curr"] = [float(net.get("current") or 0.0)]
            net["face_scale"] = 1.0
            net["is_face_net"] = True
        return out

    def _afg_bs_face_amounts(self, roots):
        """Natural SOFP: Assets +, Liabilities +, Equity +; Assets = Equity + Liabilities."""
        out = []
        for node in roots or []:
            tk = node.get("type_key") or ""
            if tk in AFG_BS_FACE_NEGATE_TYPES:
                out.append(self._afg_scale_tree_amounts(node, -1.0, face_scale=-1.0))
            else:
                out.append(self._afg_scale_tree_amounts(node, 1.0, face_scale=1.0))
        # Rebuild computed totals from face children so magnitudes always match.
        by_key = {n.get("type_key"): n for n in out if n.get("type_key")}
        rebuilt = []
        for type_key, meta in AFG_BS_COA_TYPES.items():
            computed_from = meta.get("computed_from")
            if computed_from:
                src = [by_key[k] for k in computed_from if k in by_key]
                if not src:
                    continue
                # Sum face amounts (no further sign flip — already face)
                prior, current, co_p, co_c = self._afg_sum_branch_nodes(src)
                pam = None
                if any((s or {}).get("period_amounts") for s in src):
                    width = max(len((s or {}).get("period_amounts") or []) for s in src)
                    pam = [0.0] * width
                    for s in src:
                        for i, v in enumerate((s or {}).get("period_amounts") or []):
                            pam[i] += float(v or 0.0)
                    if pam:
                        prior = pam[0]
                        current = pam[-1]
                shell = {
                    "id": "type-bs-%s" % type_key,
                    "type_key": type_key,
                    "label": _(meta["label"]),
                    "note": "",
                    "level": 0,
                    "prior": prior,
                    "current": current,
                    "sensitive": False,
                    "co_prior": co_p,
                    "co_curr": co_c,
                    "group_code": "",
                    "group_caption": "",
                    "ledger_code": "",
                    "ledger_caption": "",
                    "drill_account_ids": [],
                    "report_section": "bs",
                    "group_id": False,
                    "is_computed": True,
                    "face_scale": 1.0,
                    "children": [],
                }
                if pam is not None:
                    shell["period_amounts"] = pam
                by_key[type_key] = shell
                rebuilt.append(shell)
            elif type_key in by_key:
                rebuilt.append(by_key[type_key])
        return rebuilt or out

    def _afg_apply_statement_face_amounts(self, section, roots):
        """Convert Odoo signed statement trees to natural (all-plus) presentation."""
        if not roots:
            return roots
        if section == "pl":
            return self._afg_pl_face_amounts(roots)
        if section == "bs":
            return self._afg_bs_face_amounts(roots)
        # Equity / cashflow / FA: owner-equity movements are credits → show positive
        if section == "equity":
            return [self._afg_scale_tree_amounts(n, -1.0, face_scale=-1.0) for n in roots]
        return roots

    def _afg_annotate_trees_period_amounts(self, tree_by_section, windows, cids):
        """Attach period_amounts (oldest→newest) from live TB for each comparative window."""
        self.ensure_one()
        windows = list(windows or [])
        n = len(windows)
        if n < 1:
            return tree_by_section or {}
        cids = [int(x) for x in (cids or self._tb_company_ids() or [])]
        if not cids:
            cids = [int(self.company_id.id)]
        pl_tbs = []
        bs_tbs = []
        for w in windows:
            df = w.get("date_from")
            dt = w.get("date_to")
            pl_tbs.append(self._fetch_tb(df, dt, cids))
            bs_tbs.append(self._fetch_tb_coa_stock(dt, cids, fy_anchor_date=df))

        def _sum_tb(tb, acc_ids):
            return float(sum(float((tb or {}).get(aid, 0.0) or 0.0) for aid in acc_ids))

        def _walk(node, section):
            kids = list(node.get("children") or [])
            sec = section or node.get("report_section") or ""
            for ch in kids:
                _walk(ch, sec or ch.get("report_section") or "")
            uses_close = bool(sec) and self._section_uses_closing_balance(sec)
            tbs = bs_tbs if uses_close else pl_tbs
            acc_ids = list(node.get("drill_account_ids") or [])
            if node.get("account_id"):
                try:
                    acc_ids.append(int(node["account_id"]))
                except (TypeError, ValueError):
                    pass
            acc_ids = sorted({int(a) for a in acc_ids if a})
            if kids:
                amts = [0.0] * n
                for ch in kids:
                    pam = ch.get("period_amounts") or []
                    for i in range(n):
                        amts[i] += float(pam[i] if i < len(pam) else 0.0)
                node["period_amounts"] = amts
            elif acc_ids:
                node["period_amounts"] = [_sum_tb(tb, acc_ids) for tb in tbs]
            else:
                if n == 1:
                    node["period_amounts"] = [
                        float(node.get("current") or node.get("prior") or 0.0)
                    ]
                else:
                    amts = [0.0] * n
                    amts[0] = float(node.get("prior") or 0.0)
                    amts[-1] = float(node.get("current") or 0.0)
                    node["period_amounts"] = amts
            pam = node.get("period_amounts") or []
            if pam:
                node["prior"] = float(pam[0])
                node["current"] = float(pam[-1])

        out = {}
        for sec, roots in (tree_by_section or {}).items():
            for r in roots or []:
                _walk(r, sec)
            out[sec] = list(roots or [])
        return out

    def _afg_sync_cy_period_amounts_from_pl(self, bs_roots, pl_roots):
        """Copy face P&L net period_amounts onto SOFP Profit/(Loss) rows."""
        net = self._afg_type_by_key(pl_roots or [], "net_profit")
        pam = list((net or {}).get("period_amounts") or [])
        if not pam:
            return bs_roots

        def _walk(nodes):
            for n in nodes or []:
                if self._afg_node_looks_like_cy_pnl(n):
                    n["period_amounts"] = list(pam)
                    n["prior"] = float(pam[0])
                    n["current"] = float(pam[-1])
                _walk(n.get("children") or [])

        _walk(bs_roots)
        return bs_roots

    @api.model
    def afg_dashboard_default_version(self):
        self.env["audited.financial.group"]._setup_default_afg_presets()
        company = self.env.company
        allowed = self._afg_allowed_company_ids_from_context()
        if not allowed:
            allowed = [company.id]
        dash_ctx = dict(self.env.context, allowed_company_ids=allowed)
        Ver = self.with_context(**dash_ctx)
        ver = Ver.search([("company_id", "=", company.id)], limit=1, order="id desc")
        if not ver:
            create_vals = dict(_afg_default_period_vals(), **{
                "name": _("Draft %s") % (company.name,),
                "company_id": company.id,
            })
            ver = Ver.create(create_vals)
            ver.write({
                "company_ids": [(6, 0, allowed)],
                "report_column_company_ids": [(6, 0, allowed)],
            })
            ver.action_load_default_data()
        elif not ver.line_ids:
            if not ver.company_ids:
                ver.write({
                    "company_ids": [(6, 0, [ver.company_id.id])],
                    "report_column_company_ids": [(6, 0, [ver.company_id.id])],
                })
            ver.with_context(**dash_ctx).action_load_default_data()
        return ver.id

    def afg_dashboard_apply_companies(self, report_column_ids=None, consolidation_company_ids=None):
        """Set consolidation companies / statement columns from dashboard; then rebuild."""
        user_ok = set(self.env.user.company_ids.ids)
        if not user_ok:
            raise UserError(_("No companies are assigned to your user."))
        active_list = self._afg_allowed_company_ids_from_context()
        if not active_list:
            active_list = [int(self.env.company.id)]
        consolidation_ids = None
        if consolidation_company_ids is not None:
            try:
                consolidation_ids = sorted(
                    {int(x) for x in consolidation_company_ids if int(x) in user_ok}
                )
            except (TypeError, ValueError):
                consolidation_ids = []
            if not consolidation_ids:
                consolidation_ids = list(active_list)
        if consolidation_ids is None:
            consolidation_ids = list(active_list) if active_list else sorted(user_ok)

        r_raw = report_column_ids
        if r_raw is None:
            r_raw = []
        elif isinstance(r_raw, (int, float)):
            r_raw = [int(r_raw)]
        else:
            r_raw = list(r_raw or [])
        r_ids = []
        for x in r_raw:
            try:
                r_ids.append(int(x))
            except (TypeError, ValueError):
                continue
        r_ids = sorted({i for i in r_ids if i in consolidation_ids})
        for ver in self:
            ver.with_context(skip_afg_col_sync=True).write({
                "company_ids": [(6, 0, consolidation_ids)],
                "report_column_company_ids": [(6, 0, r_ids)],
            })
            ver.action_load_default_data()
        return True

    @api.model
    def afg_dashboard_data(self, active_id=None):
        # COA Factory Reset can leave stale account ids; scrub before any name_get/browse
        try:
            self._afg_scrub_orphan_account_refs()
        except Exception:
            pass
        try:
            return self._afg_dashboard_data_impl(active_id)
        except MissingError:
            self.env.clear()
            try:
                self._afg_scrub_orphan_account_refs()
            except Exception:
                pass
            ver_id = int(active_id) if active_id else self.afg_dashboard_default_version()
            ver = self.browse(ver_id)
            if ver.exists():
                try:
                    ver.action_load_default_data()
                except Exception:
                    pass
            try:
                return self._afg_dashboard_data_impl(active_id)
            except Exception as err:
                _logger.exception("afg_dashboard_data retry failed")
                return self._afg_dashboard_data_error_payload(active_id, err)
        except Exception as err:
            # Prefer dashboard empty-state over Odoo Internal Server Error (500)
            _logger.exception("afg_dashboard_data failed")
            # Serialization / concurrent delete aborts the whole PG txn; flush()
            # would then raise InternalError. Roll back, then one retry.
            try:
                self.env.cr.rollback()
            except Exception:
                pass
            self.env.clear()
            try:
                return self._afg_dashboard_data_impl(active_id)
            except Exception as err2:
                _logger.exception("afg_dashboard_data retry after rollback failed")
                try:
                    self.env.cr.rollback()
                except Exception:
                    pass
                return self._afg_dashboard_data_error_payload(active_id, err2)

    @api.model
    def _afg_dashboard_data_error_payload(self, active_id=None, err=None):
        ver_id = False
        try:
            ver_id = int(active_id) if active_id else self.afg_dashboard_default_version()
        except Exception:
            ver_id = False
        msg = (str(err) or "").strip() or _("Unknown error")
        return {
            "version_id": ver_id or False,
            "error": msg,
            "empty_message": _(
                "Audited Financials failed to load. Upgrade modules "
                "cpabooks_audited_financial, project_dashboard_odoo, and "
                "cpabooks_settings_company_setup (-u), then hard-refresh. Detail: %s"
            ) % msg,
            "sections": {},
            "statement_sections": {},
            "trial_balance": {},
            "trial_balance2": {},
            "notes": [],
            "alerts": [],
            "internal_action_notes": "",
            "validations": [],
            "schedules": {},
        }

    @api.model
    def _afg_dashboard_data_impl(self, active_id=None):
        if active_id:
            ver = self.browse(int(active_id))
        else:
            ver = self.browse(self.afg_dashboard_default_version())
        if not ver.exists():
            return {}
        user_ok_set = set(self.env.user.company_ids.ids)
        primary_cid = int(self.env.company.id)
        if primary_cid not in user_ok_set:
            primary_cid = min(user_ok_set) if user_ok_set else int(ver.company_id.id)
        if ver.company_id.id != primary_cid:
            ver = self.browse(self.afg_dashboard_default_version())
            if not ver.exists():
                return {}

        scope_cids = self._afg_allowed_company_ids_from_context()
        if not scope_cids:
            scope_cids = [primary_cid]

        needs_sync = bool(ver.branch_company_id) or set(ver.company_ids.ids) != set(scope_cids)
        if needs_sync:
            try:
                ver.with_context(skip_afg_col_sync=True).write({
                    "branch_company_id": False,
                    "company_ids": [(6, 0, scope_cids)],
                    "report_column_company_ids": [(6, 0, scope_cids)],
                })
                ver.invalidate_cache()
            except Exception:
                # Concurrent dashboard loads can DELETE the same M2M rows
                # (could not serialize access). Skip sync this request.
                _logger.warning("AFG company scope sync skipped", exc_info=True)
                try:
                    self.env.cr.rollback()
                except Exception:
                    pass
                self.env.clear()
                ver = self.browse(ver.id)
                if not ver.exists():
                    return {}
                needs_sync = False

        dash_ctx = dict(self.env.context, allowed_company_ids=scope_cids)
        if len(scope_cids) > 1:
            dash_ctx["afg_dashboard_consolidated_branch_columns"] = True
        if needs_sync or not ver.line_ids:
            ver.with_context(**dash_ctx).action_load_default_data()
        ver = ver.with_context(**dash_ctx)
        try:
            ver._afg_ensure_cost_of_sales_on_cor()
        except Exception:
            _logger.exception("AFG Cost of Sales auto-map skipped")
        if not self.env.context.get("afg_skip_hierarchy_rebuild"):
            try:
                ver._rebuild_line_hierarchy_from_tb()
            except Exception:
                _logger.exception("AFG statement rebuild failed")

        column_order = list(scope_cids)
        company_columns = [{"id": scope_cids[0], "name": ""}]
        sections = set(ver.line_ids.mapped("report_section"))
        prior_bs, curr_bs = ver._tb_prior_curr_per_company(True)
        prior_pl, curr_pl = ver._tb_prior_curr_per_company(False)
        tb_prior_by_sec = {}
        tb_curr_by_sec = {}
        for sec in sections:
            if ver._section_uses_closing_balance(sec):
                tb_prior_by_sec[sec] = prior_bs
                tb_curr_by_sec[sec] = curr_bs
            else:
                tb_prior_by_sec[sec] = prior_pl
                tb_curr_by_sec[sec] = curr_pl
        tree_by_section = defaultdict(list)
        for section in sections:
            roots = ver.line_ids.filtered(lambda l: l.report_section == section and not l.parent_id)
            branch_roots = [
                ver._afg_line_branch(l, tb_prior_by_sec, tb_curr_by_sec, column_order)
                for l in roots.sorted(lambda s: (s.sequence, s.id))
            ]
            # Audited face: drop Inventories→Inventories (and P&L equivalents) before type shells
            branch_roots = ver._afg_collapse_statement_trees(branch_roots)
            if section in AFG_SECTIONS_WITH_COA_TYPE:
                branch_roots = ver._afg_wrap_section_with_coa_types(section, branch_roots)
                branch_roots = ver._afg_collapse_statement_trees(branch_roots)
            # Multi-company: unique ledger captions (merge same name across L2 / companies)
            if section == "pl" or len(scope_cids) > 1:
                branch_roots = ver._afg_consolidate_branch_tree(branch_roots)
            # Hide zero Ungrouped / empty L1–L4 on every statement section (P&L, BS, Equity, …)
            tree_by_section[section] = ver._afg_prune_statement_roots(branch_roots)
        # Include posted CoA ledgers not yet mapped to AFG (no silent omissions)
        tree_by_section = ver._afg_merge_unmapped_into_statements(tree_by_section, column_order)
        for section in list(tree_by_section.keys()):
            tree_by_section[section] = ver._afg_prune_statement_roots(tree_by_section[section])
        # SOFP must include open P&L so Assets = Equity + Liabilities (fils matching)
        if tree_by_section.get("bs") is not None:
            bs_tree = ver._afg_prune_statement_roots(
                ver._afg_bs_inject_cy_earnings(
                    tree_by_section.get("bs") or [],
                    tree_by_section.get("pl") or [],
                )
            )
            if len(scope_cids) > 1:
                bs_tree = ver._afg_consolidate_branch_tree(bs_tree)
            tree_by_section["bs"] = ver._afg_prune_statement_roots(bs_tree)
        # Multi-period comparative columns (Show N years/months)
        period_windows = ver._afg_resolve_period_windows()
        period_labels = [w.get("label") or "" for w in period_windows]
        period_span = ver._afg_global_period_span_pref()
        tree_by_section = ver._afg_annotate_trees_period_amounts(
            tree_by_section, period_windows, scope_cids
        )
        alerts = [{
            "type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
        } for a in ver.alert_ids]
        available_companies = []
        version_company_ids = []
        report_column_company_ids = list(scope_cids)
        company_name = ""
        empty_msg = ""
        if ver.data_state == "empty":
            empty_msg = _("No posted journal items found for this company and period. Use Load Sample Data for preview.")
        section_labels = {k: v for k, v in AFG_REPORT_SECTION}
        section_labels["tb"] = _("Trial Balance")
        section_labels["tb_x"] = _("Trial Balance_x")
        section_labels["fta"] = _("CORPORATE TAX FILING- FTA")
        browser_title = _("Financial Statements")
        notes = [{"title": n.title, "body": n.body or ""} for n in ver.note_ids.sorted("sequence")]
        if not notes:
            notes = ver._dashboard_placeholder_notes()
        notes = ver._afg_resolve_statement_notes(notes)
        if not alerts:
            alerts = ver._dashboard_placeholder_alerts()
        simple_print = bool(self.env.context.get("afg_simple_print"))
        if simple_print:
            tb = {}
        else:
            tb = ver.with_context(afg_tb_column_ids=column_order)._trial_balance_rows_data()
        schedules = ver._afg_schedules_data(tree_by_section)
        # Natural IFRS face amounts for statements (sales +, assets/liabilities +, net = S−C−E).
        # Schedules / TB keep Odoo signed figures above; only statement trees are flipped.
        face_sections = {}
        for sec, roots in tree_by_section.items():
            if sec in ("pl", "bs", "equity"):
                face_sections[sec] = ver._afg_prune_statement_roots(
                    ver._afg_apply_statement_face_amounts(sec, roots)
                )
            else:
                face_sections[sec] = ver._afg_prune_statement_roots(roots)
        face_sections["bs"] = ver._afg_sync_cy_period_amounts_from_pl(
            face_sections.get("bs") or [],
            face_sections.get("pl") or [],
        )
        # SOCE must use the same face signs as SOFP / P&L (loss reduces equity)
        schedules["equity_statement"] = ver._afg_equity_statement_data({
            "bs": face_sections.get("bs") or [],
            "pl": face_sections.get("pl") or [],
            "equity": face_sections.get("equity") or [],
        })
        # Drop PPE narrative note when no PPE schedule / mapping
        notes = ver._afg_filter_notes_for_statements(
            notes, schedules.get("fixed_assets_recon") or {}, face_sections
        )
        notes = ver._afg_resolve_statement_notes(notes)
        # Opening / Closing bookends are Trial Balance only (not SOFP/P&L/Equity).
        # AFG TB uses signed CoA amounts (like Accounting Trial Balance) so net can be nil.
        if simple_print:
            tb = {}
            tb2 = {}
            schedules["fs_tb_reconciliation"] = {}
        else:
            tb2 = ver._afg_trial_balance2_data(
                tree_by_section.get("bs") or [],
                tree_by_section.get("pl") or [],
                column_order,
            )
            schedules["fs_tb_reconciliation"] = ver._afg_fs_tb_reconciliation(face_sections, tb2)
        ver._afg_relabel_retained_earnings_nodes(face_sections.get("bs") or [])
        ver._afg_relabel_retained_earnings_nodes(face_sections.get("equity") or [])
        # DED face: Owner Equity → Share Capital + Accumulated Losses
        face_sections["bs"] = ver._afg_bs_present_equity_components(
            face_sections.get("bs") or []
        )
        # Rebuild SOCE after equity component presentation so columns match SOFP
        schedules["equity_statement"] = ver._afg_equity_statement_data({
            "bs": face_sections.get("bs") or [],
            "pl": face_sections.get("pl") or [],
            "equity": face_sections.get("equity") or [],
        })
        # Negative cash → bank overdraft presentation when credit bank ledgers
        face_sections["bs"] = ver._afg_bs_reclass_negative_cash(
            face_sections.get("bs") or []
        )
        if simple_print:
            face_sections["fta"] = []
            validations = []
        else:
            try:
                face_sections["fta"] = ver._afg_fta_corporate_tax_filing_tree(
                    face_sections.get("pl") or [],
                    face_sections.get("bs") or [],
                )
            except Exception:
                _logger.exception("AFG FTA tree skipped")
                face_sections["fta"] = []
        comparative = ver._afg_comparative_presentation(face_sections, schedules)
        if len(period_windows) <= 1:
            comparative = dict(comparative or {}, hide_comparative=True, first_period=True)
        if not simple_print:
            validations = ver._afg_validation_checks(
                face_sections, schedules, tb2, comparative=comparative
            )
        # SOFP balance check on face magnitudes (Assets vs Equity + Liabilities)
        ok_bs, a_amt, e_amt, bs_diff = ver._afg_bs_balance_check(face_sections.get("bs") or [])
        if not ok_bs:
            alerts = list(alerts) + [{
                "type": "ifrs",
                "severity": "danger",
                "title": _("FINANCIAL STATEMENTS NOT RECONCILED"),
                "message": _(
                    "Total Assets (%(a).2f) vs Total Equity and Liabilities (%(e).2f); "
                    "difference %(d).2f. Map all ledgers / review Profit/(Loss)."
                ) % {"a": a_amt, "e": e_amt, "d": bs_diff},
            }]
        if any((v.get("status") or "") == "FAIL" for v in validations):
            alerts = list(alerts) + [{
                "type": "ifrs",
                "severity": "danger",
                "title": _("FINANCIAL STATEMENTS NOT RECONCILED"),
                "message": _(
                    "One or more critical validation checks FAILED. "
                    "Use Report level L4 Working Papers (Trial Balance + Validation) to resolve "
                    "before printing L1 Official Financial Statements."
                ),
            }]
        else:
            eq = next(
                (n for n in (face_sections.get("bs") or []) if n.get("type_key") == "equity"),
                None,
            )
            diff_line = next(
                (
                    c for c in ((eq or {}).get("children") or [])
                    if ver._afg_node_looks_like_bs_diff(c)
                ),
                None,
            )
            if diff_line and abs(float(diff_line.get("current") or 0.0)) > 1.0:
                alerts = list(alerts) + [{
                    "type": "ifrs",
                    "severity": "warning",
                    "title": _("Balance sheet mapping difference"),
                    "message": _(
                        "SOFP totals match, but Equity still includes a mapping difference of %(d).2f "
                        "after IFRS Retained Earnings rollover. Review Ungrouped / mis-classified ledgers."
                    ) % {"d": float(diff_line.get("current") or 0.0)},
                }]
        return {
            "version_id": ver.id,
            "name": ver.name,
            "company_name": company_name,
            "browser_title": browser_title,
            "currency": ver.currency_id.name or "AED",
            "year_current": ver.year_current,
            "year_prior": ver.year_prior,
            "period_preset": ver.period_preset or "years",
            "period_label_prior": ver._afg_period_label_prior(),
            "period_label_current": ver._afg_period_label_current(),
            "period_presets": _afg_period_presets_catalog(version=ver),
            "period_span": period_span,
            "period_span_label": _afg_period_span_label(period_span),
            "period_spans": _afg_period_span_catalog(),
            "period_labels": period_labels,
            "period_windows": [
                {
                    "key": w.get("key"),
                    "label": w.get("label"),
                    "date_from": fields.Date.to_string(w.get("date_from")) if w.get("date_from") else "",
                    "date_to": fields.Date.to_string(w.get("date_to")) if w.get("date_to") else "",
                }
                for w in period_windows
            ],
            "date_from_prior": fields.Date.to_string(ver.date_from_prior) if ver.date_from_prior else "",
            "date_to_prior": fields.Date.to_string(ver.date_to_prior) if ver.date_to_prior else "",
            "date_from_current": fields.Date.to_string(ver.date_from_current) if ver.date_from_current else "",
            "date_to_current": fields.Date.to_string(ver.date_to_current) if ver.date_to_current else "",
            "edit_mode": ver.edit_mode,
            "state": ver.state,
            "data_state": ver.data_state,
            "empty_message": empty_msg,
            "sections": face_sections,
            "alerts": alerts,
            "internal_action_notes": ver.internal_action_notes or "",
            "notes": notes,
            "schedules": schedules,
            "section_labels": section_labels,
            "company_columns": company_columns,
            "multico": len(scope_cids) > 1,
            "available_companies": available_companies,
            "version_company_ids": version_company_ids,
            "report_column_company_ids": report_column_company_ids,
            "statement_hide_audited_totals": True,
            "statement_face_amounts": True,
            "statement_sections": list(AFG_SECTIONS_WITH_COA_TYPE) + ["tb", "fta"],
            "trial_balance": tb,
            "trial_balance2": tb2,
            "validations": validations,
            "print_max_level": int(self._afg_global_report_pack_pref()),
            "report_level": int(self._afg_global_report_pack_pref()),
            "report_pack": self._afg_report_pack_spec(),
            "print_page_setup": self._afg_global_page_setup_pref(),
            "print_page_setup_flags": self._afg_print_page_setup_flags(),
            # Global preference (ICP) — not flipped by reload/period; only user toggle.
            "print_years_descending": bool(self._afg_global_years_descending_pref()),
            "hide_comparative": bool(comparative.get("hide_comparative")),
            "first_period": bool(comparative.get("first_period")),
            "cover": {
                "title": _("Financial Statements"),
                "subtitle": _(
                    "Prepared based on accounting records and accounting policies adopted by management"
                ),
                "entity": ver._afg_print_company_display(),
                "period": ver._afg_period_year_ended(ver.year_current),
                "currency": ver.currency_id.name or "AED",
                "disclaimer": _(
                    "These financial statements have been prepared by the management of the Company "
                    "based on its accounting records and are intended for general business, regulatory, "
                    "statutory and management purposes. They are management-prepared financial "
                    "statements and have not been audited."
                ),
            },
            "signatory": ver._afg_signatory_block(),
        }

    def _afg_flatten_tree_for_export(self, nodes, depth=0, rows=None, max_level=None):
        """Flatten statement trees for PDF/Excel/Word — Proper Case labels, LG tags, display amounts."""
        rows = rows if rows is not None else []
        if max_level is None:
            max_level = self._afg_export_max_level()
        max_level = int(max_level)
        pack = self._afg_hierarchy_pack(self._afg_export_report_pack())
        fta_print = bool(self.env.context.get("afg_fta_print"))
        # Pack filter already shaped the tree; flatten must not undo L3 account groups.
        # Residual skip rules (if any L0/L1/L2 bands remain):
        # L2 Type→ledger: skip AFG + account.group
        # L3 AFG→group→ledger: skip CoA types only
        # L4 AFG→ledger: skip CoA types + account.group
        skip_account_groups = (pack in (2, 4) or pack <= 1) and not fta_print
        skip_afg = pack == 2 and not fta_print
        skip_coa_types = pack in (3, 4) and not fta_print
        if fta_print:
            max_level = 4
        elif pack == 3:
            skip_account_groups = False
            skip_afg = False
            skip_coa_types = True
        for node in nodes or []:
            lvl = int(node.get("level") if node.get("level") is not None else depth)
            if skip_account_groups and lvl == 2:
                self._afg_flatten_tree_for_export(
                    node.get("children"), depth + 1, rows, max_level=max_level
                )
                continue
            if skip_afg and lvl == 1 and not node.get("is_computed") and not self._afg_node_looks_like_cy_pnl(node):
                self._afg_flatten_tree_for_export(
                    node.get("children"), depth + 1, rows, max_level=max_level
                )
                continue
            if skip_coa_types and lvl == 0:
                keep = (
                    bool(node.get("is_computed"))
                    or bool(node.get("is_tb_section_total"))
                    or bool(node.get("is_section_banner"))
                    or bool(node.get("is_tb_difference"))
                    or str(node.get("type_key") or "") == "grand_total"
                )
                if not keep:
                    self._afg_flatten_tree_for_export(
                        node.get("children"), depth + 1, rows, max_level=max_level
                    )
                    continue
            if lvl > max_level and max_level < 4 and pack <= 1:
                continue
            if lvl > 4:
                continue
            if lvl <= 0:
                lg = "L0"
            elif lvl == 1:
                lg = "L1"
            elif lvl == 2:
                lg = "L2"
            elif lvl == 3:
                lg = "L3"
            else:
                lg = "L4"
            clean = self._afg_export_clean_label(node)
            # Groups flush left; ledgers indent further (~4 spaces)
            prefix = "    " if lvl >= 3 else ""
            prior = float(node.get("prior") or 0.0)
            current = float(node.get("current") or 0.0)
            period_amts = None
            period_disp = None
            raw_period = node.get("period_amounts")
            tk = node.get("type_key") or ""
            is_stmt_total = tk in (
                "total_assets",
                "total_liabilities",
                "total_equity_liabilities",
                "net_profit",
                "grand_total",
                "section_total",
            )
            # Prefer live prior/current on computed totals — stale zero pam was wiping
            # amounts and PDF printed "-" for TOTAL ASSETS / LIABILITIES / E+L.
            node_prior = prior
            node_current = current
            if raw_period is not None and list(raw_period):
                period_amts = []
                period_disp = []
                for v in list(raw_period):
                    rv = float(self._afg_round_amt(v or 0.0))
                    period_amts.append(rv)
                    period_disp.append(self._afg_fmt_amt(rv))
                pam_has = any(abs(float(v or 0.0)) >= 0.5 for v in period_amts)
                face_has = abs(node_prior) >= 0.5 or abs(node_current) >= 0.5
                if pam_has:
                    prior = period_amts[0]
                    current = period_amts[-1]
                elif face_has:
                    period_amts = [node_prior, node_current]
                    period_disp = [
                        self._afg_fmt_amt(node_prior),
                        self._afg_fmt_amt(node_current),
                    ]
                    prior = node_prior
                    current = node_current
                elif period_amts:
                    prior = period_amts[0]
                    current = period_amts[-1]
            if is_stmt_total and (abs(current) >= 0.5 or abs(prior) >= 0.5):
                if not period_amts or not any(abs(float(v or 0.0)) >= 0.5 for v in period_amts):
                    period_amts = [prior, current]
                    period_disp = [self._afg_fmt_amt(prior), self._afg_fmt_amt(current)]
            row = {
                "lg": lg,
                "label": prefix + clean,
                "label_raw": clean,
                "opening": float(node.get("opening") if node.get("opening") is not None else prior),
                "prior": prior,
                "current": current,
                "prior_disp": self._afg_fmt_amt(prior),
                "current_disp": self._afg_fmt_amt(current),
                "period_amounts": period_amts,
                "period_amounts_disp": period_disp,
                "level": lvl,
                "bold": lvl <= 1 or bool(node.get("is_computed")) or bool(node.get("is_tb_section_total")),
                "is_total": bool(
                    node.get("is_tb_section_total")
                    or is_stmt_total
                    or tk == "grand_total"
                ),
                "type_key": tk,
                "is_computed": bool(node.get("is_computed")),
                "is_tb_section_total": bool(node.get("is_tb_section_total")),
                "is_tb_difference": bool(node.get("is_tb_difference")),
                "is_section_banner": bool(node.get("is_section_banner")),
            }
            raw_tb = node.get("tb_amounts")
            if raw_tb is not None:
                tb_amts = []
                tb_disp = []
                for v in list(raw_tb):
                    if v is None:
                        tb_amts.append(None)
                        tb_disp.append("—")
                    else:
                        rv = float(self._afg_round_amt(v))
                        tb_amts.append(rv)
                        tb_disp.append(self._afg_fmt_amt(rv))
                row["tb_amounts"] = tb_amts
                row["tb_amounts_disp"] = tb_disp
            rows.append(row)
            kids = node.get("children") or []
            if kids and (pack >= 2 or lvl < max_level):
                self._afg_flatten_tree_for_export(
                    kids, depth + 1, rows, max_level=max_level
                )
        return rows

    def _afg_force_statement_total_print_amounts(self, rows, period_labels=None):
        """Copy ASSETS / LIABILITIES / Equity amounts onto TOTAL* print rows.

        Guarantees PDF never shows dash on TOTAL ASSETS / TOTAL LIABILITIES /
        TOTAL EQUITY AND LIABILITIES when the section header already has a figure.
        """
        rows = list(rows or [])
        by_tk = {}
        by_label = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            tk = str(r.get("type_key") or "")
            if tk:
                by_tk[tk] = r
            lab = " ".join(str(r.get("label_raw") or r.get("label") or "").upper().split())
            if lab:
                by_label[lab] = r
        n = len(list(period_labels or []))
        mapping = {
            "total_assets": ("asset",),
            "total_liabilities": ("liability",),
            "total_equity_liabilities": ("liability", "equity"),
        }
        label_aliases = {
            "total_assets": ("TOTAL ASSETS",),
            "total_liabilities": ("TOTAL LIABILITIES",),
            "total_equity_liabilities": (
                "TOTAL EQUITY AND LIABILITIES",
                "TOTAL LIABILITIES AND EQUITY",
            ),
            "asset": ("ASSETS", "ASSET"),
            "liability": ("LIABILITIES", "LIABILITY"),
            "equity": ("EQUITY",),
        }

        def _find_row(key):
            row = by_tk.get(key)
            if row:
                return row
            for alias in label_aliases.get(key) or ():
                if alias in by_label:
                    return by_label[alias]
            return None

        def _sum_field(srcs, field):
            return float(sum(float((s or {}).get(field) or 0.0) for s in srcs))

        def _sum_pam(srcs, width):
            pam = [0.0] * width
            for s in srcs:
                sp = list((s or {}).get("period_amounts") or [])
                if not sp:
                    if width <= 1:
                        sp = [s.get("current")]
                    else:
                        sp = [s.get("prior"), s.get("current")]
                for i in range(width):
                    if i < len(sp) and sp[i] is not None:
                        pam[i] += float(sp[i] or 0.0)
            return pam

        for total_key, src_keys in mapping.items():
            total = _find_row(total_key)
            if not total:
                continue
            srcs = [_find_row(k) for k in src_keys]
            srcs = [s for s in srcs if s]
            if not srcs:
                continue
            prior = _sum_field(srcs, "prior")
            current = _sum_field(srcs, "current")
            # Prefer live face on total itself when sources were wiped (hide comparative)
            if abs(current) < 0.5 and abs(float(total.get("current") or 0.0)) >= 0.5:
                current = float(total.get("current") or 0.0)
            if abs(prior) < 0.5 and abs(float(total.get("prior") or 0.0)) >= 0.5:
                prior = float(total.get("prior") or 0.0)
            width = n if n >= 1 else 0
            if not width:
                for s in srcs:
                    width = max(width, len(s.get("period_amounts") or []))
                width = width or (2 if abs(prior) >= 0.5 else 1)
            pam = _sum_pam(srcs, width)
            if width == 1:
                pam = [current]
            elif pam:
                pam[0] = prior if abs(prior) >= 0.5 or abs(pam[0]) < 0.5 else pam[0]
                pam[-1] = current if abs(current) >= 0.5 or abs(pam[-1]) < 0.5 else pam[-1]
            total["prior"] = prior
            total["current"] = current
            total["prior_disp"] = self._afg_fmt_amt(prior)
            total["current_disp"] = self._afg_fmt_amt(current)
            total["period_amounts"] = pam
            total["period_amounts_disp"] = [self._afg_fmt_amt(v) for v in pam]
            total["is_total"] = True
            if not total.get("type_key"):
                total["type_key"] = total_key

        # Accounting equation on print: Total Equity & Liabilities := Total Assets
        ta = by_tk.get("total_assets")
        tel = by_tk.get("total_equity_liabilities")
        if ta and tel:
            for field in ("prior", "current"):
                if ta.get(field) is not None:
                    tel[field] = float(ta.get(field) or 0.0)
            if ta.get("period_amounts") is not None:
                tel["period_amounts"] = list(ta.get("period_amounts") or [])
            tel["prior_disp"] = self._afg_fmt_amt(tel.get("prior"))
            tel["current_disp"] = self._afg_fmt_amt(tel.get("current"))
            tel["period_amounts_disp"] = [
                self._afg_fmt_amt(v) for v in (tel.get("period_amounts") or [])
            ]
            # Keep Equity = Assets − Liabilities for the header row too
            liab = by_tk.get("liability") or by_tk.get("total_liabilities")
            eq = by_tk.get("equity")
            if liab and eq:
                for field in ("prior", "current"):
                    eq[field] = float(ta.get(field) or 0.0) - float(liab.get(field) or 0.0)
                eq["prior_disp"] = self._afg_fmt_amt(eq.get("prior"))
                eq["current_disp"] = self._afg_fmt_amt(eq.get("current"))
                if ta.get("period_amounts") is not None and liab.get("period_amounts") is not None:
                    tw = list(ta.get("period_amounts") or [])
                    lw = list(liab.get("period_amounts") or [])
                    width = max(len(tw), len(lw))
                    eq["period_amounts"] = [
                        float((tw[i] if i < len(tw) else 0.0) or 0.0)
                        - float((lw[i] if i < len(lw) else 0.0) or 0.0)
                        for i in range(width)
                    ]
                    eq["period_amounts_disp"] = [
                        self._afg_fmt_amt(v) for v in eq["period_amounts"]
                    ]
        return rows

    def _afg_ensure_print_period_disp(self, rows, period_labels):
        """Fill period_amounts_disp for PDF when totals only have prior/current."""
        labels = list(period_labels or [])
        n = len(labels)
        if n < 1:
            return rows

        def _blank(d):
            return str(d if d is not None else "").strip() in ("", "—", "-", "–")

        def _num(v):
            try:
                return float(v or 0.0)
            except (TypeError, ValueError):
                return 0.0

        for row in rows or []:
            if not isinstance(row, dict) or row.get("is_section_banner"):
                continue
            disp = list(row.get("period_amounts_disp") or [])
            pam = list(row.get("period_amounts") or [])
            cur = row.get("current")
            pri = row.get("prior")
            # 1-column DED/print: never keep the prior slot of a 2-slot pam/disp array
            if n == 1:
                if len(pam) > 1 and abs(_num(pam[-1])) >= 0.5:
                    use = [pam[-1]]
                elif cur is not None and abs(_num(cur)) >= 0.5:
                    use = [cur]
                elif len(disp) > 1 and not _blank(disp[-1]):
                    row["period_amounts_disp"] = [disp[-1]]
                    row["period_amounts"] = [pam[-1]] if len(pam) > 1 else ([cur] if cur is not None else pam[:1] or [0.0])
                    row["current"] = row["period_amounts"][-1]
                    row["current_disp"] = disp[-1]
                    continue
                elif len(pam) >= 1 and abs(_num(pam[0])) >= 0.5:
                    use = [pam[0]]
                else:
                    use = [cur if cur is not None else pri]
                row["period_amounts"] = use
                row["period_amounts_disp"] = [
                    "—" if v is None else self._afg_fmt_amt(v) for v in use
                ]
                if use:
                    row["current"] = use[-1]
                    row["current_disp"] = (
                        "—" if use[-1] is None else self._afg_fmt_amt(use[-1])
                    )
                continue

            has_real = len(disp) >= n and any(not _blank(d) for d in disp[:n])
            face_has_amt = any(
                v is not None and abs(_num(v)) >= 0.5 for v in (cur, pri)
            )
            if has_real and not (
                face_has_amt and all(_blank(d) for d in (disp[:n] or [None]))
            ):
                row["period_amounts_disp"] = disp[:n]
                if pam:
                    row["period_amounts"] = list(pam)[:n]
                continue
            if len(pam) >= n and any(abs(_num(v)) >= 0.5 for v in pam[:n]):
                use = list(pam)[:n]
            elif n == 2:
                use = [pri, cur]
            elif pam:
                use = list(pam)
                while len(use) < n:
                    use.append(cur)
                use = use[:n]
            else:
                use = [pri] + [None] * (n - 2) + [cur]
            row["period_amounts"] = use
            row["period_amounts_disp"] = [
                "—" if v is None else self._afg_fmt_amt(v) for v in use
            ]
            if use:
                row["prior"] = use[0]
                row["current"] = use[-1]
                row["prior_disp"] = (
                    "—" if use[0] is None else self._afg_fmt_amt(use[0])
                )
                row["current_disp"] = (
                    "—" if use[-1] is None else self._afg_fmt_amt(use[-1])
                )
        return rows

    def _afg_years_descending(self):
        """Match AFG dashboard year column order for exports.

        Priority: explicit RPC context (current UI) → global ICP preference → version field.
        Never invent a flip; unset preference stays ascending (False).
        """
        ctx = self.env.context.get("afg_years_descending")
        if ctx is not None and str(ctx).strip() != "":
            if isinstance(ctx, str):
                return ctx.strip().lower() in ("1", "true", "yes", "y")
            return bool(ctx)
        return bool(self._afg_global_years_descending_pref())

    def _afg_persist_print_options(self, max_level=None):
        """Store report pack L1–L4. Year order is only changed via user toggle (ICP)."""
        if max_level is None:
            return
        pack = self._afg_resolve_export_report_pack(max_level)
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.report_level", str(pack),
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.print_max_level",
            str(self._afg_tree_depth_for_pack(pack)),
        )
        try:
            self.write({"print_max_level": pack})
        except (TypeError, ValueError):
            pass
        if self and "print_show_page_numbers" in self._fields:
            self.env["ir.config_parameter"].sudo().set_param(
                "cpabooks_afg.print_show_page_numbers",
                "1" if self.print_show_page_numbers else "0",
            )

    def _afg_apply_years_order_to_chapters(self, chapters):
        """Keep form column order (no Print Setup year flip)."""
        return list(chapters or [])

    def _afg_export_max_level(self):
        """Hierarchy tree depth for filters (derived from report pack L1–L4)."""
        ctx = self.env.context.get("afg_export_max_level")
        if ctx is not None and str(ctx).strip() != "":
            try:
                # Context may carry pack (1–4) or legacy tree depth
                pack = self._afg_coerce_to_report_pack(ctx)
                return self._afg_tree_depth_for_pack(pack)
            except (TypeError, ValueError):
                pass
        return self._afg_tree_depth_for_pack(self._afg_global_report_pack_pref())

    def _afg_export_report_pack(self):
        """Report pack 1–4 for the current export / dashboard."""
        ctx = self.env.context.get("afg_export_max_level")
        if ctx is not None and str(ctx).strip() != "":
            return self._afg_coerce_to_report_pack(ctx)
        return self._afg_global_report_pack_pref()

    def _afg_resolve_export_max_level(self, max_level=None):
        """Resolve hierarchy tree depth for export (from pack or legacy value)."""
        if max_level is not None and str(max_level).strip() != "":
            pack = self._afg_coerce_to_report_pack(max_level)
            return self._afg_tree_depth_for_pack(pack)
        return self._afg_export_max_level()

    def _afg_resolve_export_report_pack(self, max_level=None):
        if max_level is not None and str(max_level).strip() != "":
            return self._afg_coerce_to_report_pack(max_level)
        return self._afg_export_report_pack()

    def _afg_xlsx_col_letter(self, col_idx):
        """0-based column index → Excel letter (0=A)."""
        n = int(col_idx) + 1
        letters = ""
        while n:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    def _afg_xlsx_direct_child_indices(self, rows, parent_idx):
        """Indices of direct children of rows[parent_idx] (tree flatten order)."""
        rows = rows or []
        n = len(rows)
        if parent_idx < 0 or parent_idx >= n:
            return []
        parent_lvl = int(rows[parent_idx].get("level") or 0)
        kids = []
        j = parent_idx + 1
        while j < n:
            lvl = int(rows[j].get("level") or 0)
            if lvl <= parent_lvl:
                break
            kids.append(j)
            child_lvl = lvl
            j += 1
            while j < n and int(rows[j].get("level") or 0) > child_lvl:
                j += 1
        return kids

    def _afg_xlsx_sum_formula(self, col_letter, excel_rows):
        """Build =SUM(...) over direct child Excel rows (1-based). Prefer a range when contiguous."""
        excel_rows = [int(r) for r in (excel_rows or []) if r]
        if not excel_rows:
            return None
        excel_rows = sorted(set(excel_rows))
        if len(excel_rows) == 1:
            return "=%s%s" % (col_letter, excel_rows[0])
        contiguous = excel_rows[-1] - excel_rows[0] + 1 == len(excel_rows)
        if contiguous:
            return "=SUM(%s%s:%s%s)" % (col_letter, excel_rows[0], col_letter, excel_rows[-1])
        # Nested rows between siblings — sum each direct child cell (no double-count)
        refs = ",".join("%s%s" % (col_letter, r) for r in excel_rows)
        return "=SUM(%s)" % refs

    def _afg_xlsx_write_amount_cell(self, ws, row_i, col, value, formula, num_format):
        """Write a numeric value or an Excel formula (formula preferred when provided)."""
        if formula:
            ws.write_formula(row_i, col, formula, num_format, float(value or 0.0))
        elif value is None:
            ws.write(row_i, col, "", num_format)
        else:
            ws.write_number(row_i, col, float(value or 0.0), num_format)

    def _afg_xlsx_write_statement_block(
        self, ws, rows, start_row, fmt_label, fmt_label_b, fmt_total,
        fmt_num, fmt_num_b, fmt_num_t, has_remark=False,
        sheet_name=None, chapter_key=None, link_map=None,
    ):
        """Write statement rows with SUM formulas for group / subtotal / total lines.

        ``link_map`` collects cell anchors for cross-sheet links, e.g.
        ``{('pl', 'net_profit', 'current'): \"'PL'!D42\"}``.
        Incoming links: row with ``type_key``/``xlsx_link`` uses another sheet's cell.
        """
        rows = list(rows or [])
        link_map = link_map if link_map is not None else {}
        sheet_name = sheet_name or "Sheet"
        # Quote sheet name for formulas when needed
        qsheet = "'%s'" % sheet_name.replace("'", "''")

        # Header already written; data starts at start_row
        # Pre-assign Excel row numbers (1-based)
        excel_rows = []  # parallel to rows: 1-based excel row
        for i, _row in enumerate(rows):
            excel_rows.append(start_row + i + 1)  # xlsxwriter 0-based start_row → Excel 1-based

        # Detect special link targets / sources
        def _row_type_key(row):
            return (row.get("type_key") or row.get("xlsx_type_key") or "").strip()

        # First pass: which indices are parents with children
        child_map = {
            i: self._afg_xlsx_direct_child_indices(rows, i)
            for i in range(len(rows))
        }

        for i, row in enumerate(rows):
            row_i = start_row + i
            is_tot = bool(row.get("is_total"))
            is_bold = bool(row.get("bold"))
            lf = fmt_total if is_tot else (fmt_label_b if is_bold else fmt_label)
            nf = fmt_num_t if is_tot else (fmt_num_b if is_bold else fmt_num)
            ws.write(row_i, 0, row.get("lg") or "", lf)
            lvl = int(row.get("level") or 0)
            pad = "    " if lvl >= 3 else ""
            ws.write(row_i, 1, pad + (row.get("label_raw") or row.get("label") or ""), lf)

            kids = child_map.get(i) or []
            kid_excel = [excel_rows[k] for k in kids]
            prior = row.get("prior")
            current = row.get("current")
            tk = _row_type_key(row)

            # Cross-sheet link inbound (e.g. BS CY P&L ← PL Net Profit)
            link_key = row.get("xlsx_link_key")
            if not link_key and tk == "cy_pnl" and (chapter_key or "") == "bs":
                link_key = "pl_net_profit"
            prior_f = current_f = None
            if kids and prior is not None:
                prior_f = self._afg_xlsx_sum_formula("C", kid_excel)
            if kids and current is not None:
                current_f = self._afg_xlsx_sum_formula("D", kid_excel)

            if link_key and link_map.get((link_key, "prior")):
                # Face presentation: PL Net Profit and BS CY P&L share the same sign
                # (loss negative / in parentheses on both statements).
                prior_f = "=%s" % link_map[(link_key, "prior")]
            if link_key and link_map.get((link_key, "current")):
                current_f = "=%s" % link_map[(link_key, "current")]

            # Net Profit = Sales − Cost of Materials − Expenses (natural / face arithmetic)
            if tk == "net_profit" and not kids:
                sales_r = cost_r = exp_r = None
                for j, r2 in enumerate(rows):
                    tk2 = _row_type_key(r2)
                    if tk2 == "sales" and r2.get("prior") is not None:
                        sales_r = excel_rows[j]
                    elif tk2 == "cost_of_revenue" and r2.get("prior") is not None:
                        cost_r = excel_rows[j]
                    elif tk2 == "expenses" and r2.get("prior") is not None:
                        exp_r = excel_rows[j]
                parts_c = []
                parts_d = []
                if sales_r:
                    parts_c.append("C%s" % sales_r)
                    parts_d.append("D%s" % sales_r)
                if cost_r:
                    parts_c.append("C%s" % cost_r)
                    parts_d.append("D%s" % cost_r)
                if exp_r:
                    parts_c.append("C%s" % exp_r)
                    parts_d.append("D%s" % exp_r)
                if parts_c:
                    # First term positive (sales), subsequent terms subtracted
                    prior_f = "=" + parts_c[0] + "".join("-" + p for p in parts_c[1:])
                    current_f = "=" + parts_d[0] + "".join("-" + p for p in parts_d[1:])

            # Computed L0 totals that are siblings (not parents) of their sources
            if not kids and tk in (
                "total_assets", "total_liabilities", "total_equity_liabilities",
            ):
                want = {
                    "total_assets": ("asset",),
                    "total_liabilities": ("liability",),
                    "total_equity_liabilities": ("liability", "equity"),
                }[tk]
                part_rows = [
                    excel_rows[j]
                    for j, r2 in enumerate(rows)
                    if _row_type_key(r2) in want and r2.get("prior") is not None
                ]
                if part_rows:
                    prior_f = self._afg_xlsx_sum_formula("C", part_rows)
                    current_f = self._afg_xlsx_sum_formula("D", part_rows)
            if prior is None and not prior_f:
                ws.write(row_i, 2, "", lf)
            else:
                self._afg_xlsx_write_amount_cell(ws, row_i, 2, prior, prior_f, nf)
            if current is None and not current_f:
                ws.write(row_i, 3, "", lf)
            else:
                self._afg_xlsx_write_amount_cell(ws, row_i, 3, current, current_f, nf)

            if has_remark:
                ws.write(row_i, 4, row.get("remark") or "", fmt_label)

            # Register outbound anchors for cross-sheet consumers
            if tk == "net_profit" and (chapter_key or "") == "pl":
                link_map[("pl_net_profit", "prior")] = "%s!C%s" % (qsheet, excel_rows[i])
                link_map[("pl_net_profit", "current")] = "%s!D%s" % (qsheet, excel_rows[i])
            if tk and chapter_key:
                link_map[("%s_%s" % (chapter_key, tk), "prior")] = "%s!C%s" % (qsheet, excel_rows[i])
                link_map[("%s_%s" % (chapter_key, tk), "current")] = "%s!D%s" % (qsheet, excel_rows[i])

        return start_row + len(rows), link_map

    def _afg_export_clean_label(self, node):
        """Caption for print: L0 ALL CAPS; groups Proper Case; ledgers CoA then Proper Case."""
        if self.env.context.get("afg_fta_print"):
            return (node.get("label") or node.get("afg_caption") or "").strip()
        lvl = int(node.get("level") if node.get("level") is not None else 0)
        if lvl <= 0:
            text = (node.get("label") or "").strip()
            # Equity section header stays Proper Case; other L0 totals stay ALL CAPS.
            if str(node.get("type_key") or "") == "equity":
                return self._afg_proper_case(text)
            return (text or "").upper()
        elif lvl == 1:
            text = (node.get("afg_caption") or node.get("label") or "").strip()
        elif lvl == 2:
            text = (node.get("group_caption") or node.get("label") or "").strip()
        elif lvl == 3:
            text = (node.get("ledger_caption") or "").strip()
            if not text:
                text = re.sub(r"^\d+\s*[|:\-–]?\s*", "", (node.get("label") or "").strip())
            text = re.sub(r"^\[Sensitive\]\s*", "", text or "", flags=re.I).strip()
        else:
            text = (node.get("label") or "").strip()
            text = re.sub(r"^\[Sensitive\]\s*", "", text or "", flags=re.I).strip()
        return self._afg_proper_case(text)

    def _afg_proper_case(self, text):
        """Title-style labels: REVENUE → Revenue; keep acronyms (VAT, IFRS, AED, P&L)."""
        raw = (text or "").strip()
        if not raw:
            return raw
        small = frozenset({
            "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
            "into", "nor", "of", "on", "or", "the", "to", "vs", "via", "with",
        })
        parts = re.split(r"(\s+|[–—/()\[\]|,])", raw)
        out = []
        word_index = 0
        for part in parts:
            if not part or re.match(r"^(\s+|[–—/()\[\]|,])$", part):
                out.append(part)
                continue
            m = re.match(r"^([A-Za-z0-9&]+)(.*)$", part)
            if not m:
                out.append(part)
                continue
            word, rest = m.group(1), m.group(2)
            up = word.upper()
            low = word.lower()
            if up in _AFG_ACRONYMS:
                out.append(up + rest)
            elif word_index > 0 and low in small:
                out.append(low + rest)
            else:
                out.append(word[:1].upper() + word[1:].lower() + rest)
            word_index += 1
        return "".join(out)

    def _afg_round_amt(self, value):
        """Round half up to whole currency unit (1000.56 → 1001)."""
        if value is None:
            return None
        try:
            d = Decimal(str(float(value)))
        except (InvalidOperation, TypeError, ValueError):
            return 0
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _afg_round_tree_amounts(self, nodes):
        """Round leaf amounts; parent totals = sum of rounded children (hierarchy stays balanced)."""
        out = []
        for node in nodes or []:
            n = dict(node)
            children_src = list(n.get("children") or [])
            if children_src:
                children = self._afg_round_tree_amounts(children_src)
                n["children"] = children
                for field in ("prior", "current"):
                    n[field] = float(sum(float(c.get(field) or 0.0) for c in children))
                if any(c.get("period_amounts") for c in children):
                    width = max(len(c.get("period_amounts") or []) for c in children) or 1
                    n["period_amounts"] = [
                        float(sum(
                            float((c.get("period_amounts") or [0.0] * width)[i] or 0.0)
                            for c in children
                        ))
                        for i in range(width)
                    ]
                    if n["period_amounts"]:
                        n["prior"] = float(n["period_amounts"][0])
                        n["current"] = float(n["period_amounts"][-1])
                if any(c.get("tb_amounts") is not None for c in children):
                    width = self._tb_otc_width()
                    for c in children:
                        if c.get("tb_amounts"):
                            width = max(width, len(c["tb_amounts"]))
                            break
                    n["tb_amounts"] = [
                        float(sum(
                            float((c.get("tb_amounts") or [0.0] * width)[i] or 0.0)
                            for c in children
                        ))
                        for i in range(width)
                    ]
            else:
                for field in ("prior", "current"):
                    if n.get(field) is None:
                        continue
                    n[field] = float(self._afg_round_amt(n.get(field)))
                if n.get("period_amounts") is not None:
                    n["period_amounts"] = [
                        float(self._afg_round_amt(v or 0.0))
                        for v in list(n.get("period_amounts") or [])
                    ]
                    if n["period_amounts"]:
                        n["prior"] = float(n["period_amounts"][0])
                        n["current"] = float(n["period_amounts"][-1])
                if n.get("tb_amounts") is not None:
                    n["tb_amounts"] = [
                        None if v is None else float(self._afg_round_amt(v))
                        for v in list(n.get("tb_amounts") or [])
                    ]
                n["children"] = []
            out.append(n)
        return self._afg_recompute_statement_totals(out)

    def _afg_recompute_statement_totals(self, nodes):
        """Re-link Total Assets / Total Equity+Liabilities / Net Profit to rounded shells.

        Net Profit on face statements is always Revenue − Cost − Expenses (never a plain sum).
        """
        by_key = {n.get("type_key"): n for n in (nodes or []) if n.get("type_key")}
        if not by_key:
            return nodes
        mapping = {
            "total_assets": ("asset",),
            "total_liabilities": ("liability",),
            "total_equity_liabilities": ("liability", "equity"),
        }
        for total_key, src_keys in mapping.items():
            total = by_key.get(total_key)
            if not total:
                continue
            src = [by_key[k] for k in src_keys if k in by_key]
            if not src:
                continue
            prior, current, co_p, co_c = self._afg_sum_branch_nodes(src)
            total["prior"] = prior
            total["current"] = current
            if co_p is not None:
                total["co_prior"] = co_p
                total["co_curr"] = co_c
            # Keep N-period print columns in sync (stale/missing pam → PDF dash)
            if any((s or {}).get("period_amounts") for s in src):
                width = max(len((s or {}).get("period_amounts") or []) for s in src)
                pam = [0.0] * width
                for s in src:
                    for i, v in enumerate((s or {}).get("period_amounts") or []):
                        pam[i] += float(v or 0.0)
                total["period_amounts"] = pam
                if pam:
                    total["prior"] = float(pam[0])
                    total["current"] = float(pam[-1])
            else:
                width = max(1, len(total.get("period_amounts") or []))
                if width == 1:
                    total["period_amounts"] = [
                        float(current if current is not None else prior or 0.0)
                    ]
                else:
                    pam = [0.0] * width
                    pam[0] = float(prior or 0.0)
                    pam[-1] = float(current or 0.0)
                    total["period_amounts"] = pam

        # Profit for the Year = Sales/Revenue − Cost of revenue − Expenses
        net = by_key.get("net_profit")
        if net:
            sales = by_key.get("sales")
            cost = by_key.get("cost_of_revenue")
            exp = by_key.get("expenses")
            if sales or cost or exp:
                face_like = bool(net.get("is_face_net")) or float((sales or {}).get("face_scale") or 1.0) < 0
                # Also treat as face when sales is non-negative and expenses non-negative
                # after statement face flip (typical presentation).
                if not face_like and sales is not None:
                    s0 = float(sales.get("current") or 0.0)
                    e0 = float((exp or {}).get("current") or 0.0)
                    # Odoo signed: income credit (−). Face: income +.
                    face_like = s0 >= -0.005 and e0 >= -0.005
                for field, cofield in (("prior", "co_prior"), ("current", "co_curr")):
                    s = float((sales or {}).get(field) or 0.0)
                    c = float((cost or {}).get(field) or 0.0)
                    e = float((exp or {}).get(field) or 0.0)
                    if face_like or net.get("is_face_net"):
                        net[field] = s - c - e
                    else:
                        # Raw Odoo: income (−) + expenses (+) → negate for profit (+)
                        net[field] = -(s + c + e)
                net["co_prior"] = [float(net.get("prior") or 0.0)]
                net["co_curr"] = [float(net.get("current") or 0.0)]
                net["is_face_net"] = bool(face_like or net.get("is_face_net"))
                n_per = 0
                for src in (sales, cost, exp):
                    if src and src.get("period_amounts"):
                        n_per = max(n_per, len(src.get("period_amounts") or []))
                if n_per:
                    pam = []
                    for i in range(n_per):
                        s = float(((sales or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                        c = float(((cost or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                        e = float(((exp or {}).get("period_amounts") or [0.0] * n_per)[i] or 0.0)
                        if face_like or net.get("is_face_net"):
                            pam.append(s - c - e)
                        else:
                            pam.append(-(s + c + e))
                    net["period_amounts"] = pam
                    net["prior"] = float(pam[0])
                    net["current"] = float(pam[-1])
        return nodes

    def _afg_balance_bs_tree_after_round(self, nodes):
        """After whole-unit rounding, re-link totals and absorb small rounding drift.

        Does **not** plug mapping errors. Only absorbs when residual is within a few
        whole currency units (stacked ROUND_HALF_UP on L1 AFG bands).

        Absorb into Accumulated Losses / Retained Earnings — never into Profit for the
        Year (profit must stay tied to the P&L) and never invent Owner Equity.
        Applies to **both** prior and current columns so comparative SOFP balances.
        """
        nodes = self._afg_recompute_statement_totals(list(nodes or []))
        by_key = {n.get("type_key"): n for n in (nodes or []) if n.get("type_key")}
        assets = by_key.get("total_assets") or by_key.get("asset")
        eq_liab = by_key.get("total_equity_liabilities")
        eq = by_key.get("equity")
        if not assets or not eq_liab or not eq:
            return nodes

        def _field_diff(field):
            a = float(assets.get(field) or 0.0)
            e = float(eq_liab.get(field) or 0.0)
            return a - e

        max_absorb = 5.005
        diffs = {
            "prior": _field_diff("prior"),
            "current": _field_diff("current"),
        }
        if all(abs(float(d or 0.0)) <= 0.005 or abs(float(d or 0.0)) > max_absorb for d in diffs.values()):
            return nodes

        # Prefer Accumulated Losses / RE; never Profit for the Year
        target = None
        for ch in eq.get("children") or []:
            tk = str(ch.get("type_key") or "")
            nid = str(ch.get("id") or "")
            if tk in ("cy_pnl",) or nid in ("bs-cy-pnl",):
                continue
            if self._afg_node_looks_like_cy_pnl(ch):
                continue
            if tk in ("retained_earnings", "share_capital"):
                if tk == "retained_earnings":
                    target = ch
                    break
                continue
            lab = (ch.get("label") or ch.get("afg_caption") or "").lower()
            if any(k in lab for k in ("retained", "undistributed", "accumulat")):
                target = ch
                break
        if not target:
            for ch in eq.get("children") or []:
                if ch.get("type_key") == "cy_pnl" or self._afg_node_looks_like_cy_pnl(ch):
                    continue
                target = ch
                break
        if not target:
            return nodes

        adjusted = False
        for field, diff in diffs.items():
            d = float(diff or 0.0)
            if abs(d) <= 0.005 or abs(d) > max_absorb:
                continue
            # Assets − (E+L) = d → bump equity leaf by d so E+L rises/falls to Assets
            target[field] = float(target.get(field) or 0.0) + d
            adjusted = True

        if not adjusted:
            return nodes

        # Keep multi-period arrays in sync (prior = slot 0, current = last)
        pam = list(target.get("period_amounts") or [])
        if pam:
            if abs(float(diffs.get("prior") or 0.0)) > 0.005:
                pam[0] = float(pam[0] or 0.0) + float(diffs["prior"])
            if abs(float(diffs.get("current") or 0.0)) > 0.005:
                pam[-1] = float(pam[-1] or 0.0) + float(diffs["current"])
            target["period_amounts"] = pam

        nodes = self._afg_reroll_tree_sums(nodes)
        nodes = self._afg_recompute_statement_totals(nodes)

        # Hard-equalise printed totals to Assets (both years) after absorb
        by_key = {n.get("type_key"): n for n in (nodes or []) if n.get("type_key")}
        assets = by_key.get("total_assets") or by_key.get("asset")
        eq_liab = by_key.get("total_equity_liabilities")
        if assets and eq_liab:
            for field in ("prior", "current"):
                eq_liab[field] = float(assets.get(field) or 0.0)
            if assets.get("period_amounts") is not None:
                eq_liab["period_amounts"] = list(assets.get("period_amounts") or [])
        return nodes

    def _afg_reroll_tree_sums(self, nodes):
        """Recompute parent totals from children (after a leaf residual adjustment)."""
        out = []
        for node in nodes or []:
            n = dict(node)
            kids = self._afg_reroll_tree_sums(n.get("children") or [])
            n["children"] = kids
            if kids:
                for field in ("prior", "current"):
                    n[field] = float(sum(float(c.get(field) or 0.0) for c in kids))
            out.append(n)
        return out

    def _afg_round_ppe_matrix(self, matrix):
        """Round PPE cells; Total column = sum of rounded category cells.

        Forces every data row to exactly ``len(categories)`` value cells so PDF/Word
        headers and amounts stay column-aligned (no phantom empty columns).
        """
        matrix = dict(matrix or {})
        cats = [c for c in (matrix.get("categories") or []) if str(c or "").strip()]
        matrix["categories"] = cats
        n_cat = len(cats)

        def _fit_vals(raw):
            vals = []
            for v in list(raw or []):
                if v is None:
                    vals.append(None)
                else:
                    vals.append(float(self._afg_round_amt(v)))
            if len(vals) < n_cat:
                vals.extend([None] * (n_cat - len(vals)))
            return vals[:n_cat]

        blocks = []
        for block in matrix.get("blocks") or []:
            b = dict(block)
            if b.get("title"):
                b["title"] = self._afg_proper_case(b["title"])
            rows = []
            for prow in block.get("rows") or []:
                pr = dict(prow)
                if pr.get("label"):
                    pr["label"] = self._afg_proper_case(pr["label"])
                vals = _fit_vals(pr.get("values"))
                pr["values"] = vals
                if not vals or all(v is None for v in vals):
                    pr["total"] = None
                else:
                    pr["total"] = float(sum(v or 0.0 for v in vals if v is not None))
                pr["values_disp"] = [
                    None if v is None else self._afg_fmt_amt(v) for v in vals
                ]
                pr["total_disp"] = (
                    None if pr.get("total") is None else self._afg_fmt_amt(pr["total"])
                )
                rows.append(pr)
            b["rows"] = rows
            blocks.append(b)
        matrix["blocks"] = blocks
        # Keep year_sections in sync when present
        for ys in matrix.get("year_sections") or []:
            yblocks = []
            for block in ys.get("blocks") or []:
                b = dict(block)
                rows = []
                for prow in b.get("rows") or []:
                    pr = dict(prow)
                    vals = _fit_vals(pr.get("values"))
                    pr["values"] = vals
                    if not vals or all(v is None for v in vals):
                        pr["total"] = None
                    else:
                        pr["total"] = float(sum(v or 0.0 for v in vals if v is not None))
                    pr["values_disp"] = [
                        None if v is None else self._afg_fmt_amt(v) for v in vals
                    ]
                    pr["total_disp"] = (
                        None if pr.get("total") is None else self._afg_fmt_amt(pr["total"])
                    )
                    rows.append(pr)
                b["rows"] = rows
                yblocks.append(b)
            ys["blocks"] = yblocks
        return matrix

    def _afg_filter_tree_by_max_level(self, nodes, max_level):
        """Filter statement trees for view/print.

        Prefer report-pack semantics (L1–L4). ``max_level`` kept for callers that pass
        a pack-derived depth; pack from export context / global pref wins.
        """
        pack = self._afg_export_report_pack()
        hp = self._afg_hierarchy_pack(pack)
        # If caller passed an explicit legacy depth without pack context, honor shallow L1
        try:
            ml = int(max_level)
        except (TypeError, ValueError):
            ml = None
        if ml is not None and ml <= 1 and hp <= 1:
            return self._afg_filter_tree_depth_cap(nodes, 1)
        return self._afg_filter_tree_for_pack(nodes, pack)

    def _afg_filter_tree_for_pack(self, nodes, pack=None):
        """Apply L1–L4 hierarchy rules to a statement tree."""
        pack = self._afg_hierarchy_pack(
            pack if pack is not None else self._afg_export_report_pack()
        )
        if pack <= 1:
            # Official: types + AFG (no ledgers / no account groups)
            return self._afg_filter_tree_depth_cap(
                self._afg_strip_account_groups(nodes), 1
            )
        if pack == 2:
            # Management (with Type): CoA type → ledgers (no AFG, no account.group)
            tree = self._afg_strip_account_groups(nodes)
            return self._afg_strip_afg_groups(tree)
        if pack == 3:
            # Detailed (with Group): AFG → account.group → ledger (no CoA type bands)
            return self._afg_strip_l0_types(nodes)
        # L4 Working Papers: AFG → ledger (no type, no account.group)
        return self._afg_strip_l0_types(self._afg_strip_account_groups(nodes))

    def _afg_filter_tree_depth_cap(self, nodes, max_level):
        """Keep nodes up to ``max_level``; always retain Profit/(Loss) under Equity."""
        max_level = int(max_level)

        def _keep_always(n):
            if not n:
                return False
            tk = str(n.get("type_key") or "")
            nid = str(n.get("id") or "")
            if tk in ("cy_pnl", "share_capital", "retained_earnings") or nid in (
                "bs-cy-pnl",
                "bs-share-capital",
                "bs-accumulated-earnings",
            ):
                return True
            return bool(self._afg_node_looks_like_cy_pnl(n))

        def _collect_keep_always(children):
            kept = []
            for ch in children or []:
                if _keep_always(ch):
                    n = dict(ch)
                    n["level"] = min(
                        int(n.get("level") if n.get("level") is not None else 3),
                        max(max_level, 1),
                    )
                    n["children"] = []
                    kept.append(n)
                else:
                    kept.extend(_collect_keep_always(ch.get("children") or []))
            return kept

        out = []
        for node in nodes or []:
            lvl = int(node.get("level") if node.get("level") is not None else 0)
            if lvl > max_level and not _keep_always(node):
                continue
            n = dict(node)
            if _keep_always(n):
                n["level"] = min(lvl, max(max_level, 1))
                n["children"] = []
                out.append(n)
                continue
            if n.get("is_ungrouped_review"):
                n["children"] = self._afg_ungrouped_keep_ledger_children(
                    node.get("children") or []
                )
                code = n.get("ungrouped_code") or "AFG_UNGRP_BS"
                for ch in n["children"]:
                    ch["ungrouped_code"] = ch.get("ungrouped_code") or code
                if not n.get("drill_account_ids"):
                    n["drill_account_ids"] = self._afg_leaf_account_ids_from_node(node)
                out.append(n)
                continue
            if lvl < max_level:
                n["children"] = self._afg_filter_tree_depth_cap(
                    node.get("children") or [], max_level
                )
            else:
                n["children"] = _collect_keep_always(node.get("children") or [])
            out.append(n)
        return out

    def _afg_ungrouped_keep_ledger_children(self, children):
        """Keep ledger leaves under Ungrouped even on L1 Official (no CoA groups)."""
        out = []
        for ch in children or []:
            if not isinstance(ch, dict):
                continue
            lvl = int(ch.get("level") if ch.get("level") is not None else 0)
            kind = (ch.get("kind") or "").strip()
            if kind == "ledger" or ch.get("account_id") or lvl >= 3:
                n = dict(ch)
                n["children"] = []
                n["kind"] = n.get("kind") or "ledger"
                out.append(n)
            else:
                out.extend(self._afg_ungrouped_keep_ledger_children(ch.get("children") or []))
        return out

    def _afg_strip_afg_groups(self, nodes):
        """Remove L1 AFG bands; promote children (ledgers) under the parent type."""
        out = []
        for node in nodes or []:
            lvl = int(node.get("level") if node.get("level") is not None else 0)
            children = list(node.get("children") or [])
            # Keep computed cy_pnl / special L1 rows that are not AFG folders
            is_afg_folder = (
                lvl == 1
                and not node.get("is_computed")
                and not self._afg_node_looks_like_cy_pnl(node)
                and str(node.get("type_key") or "") not in ("cy_pnl", "bs_diff")
            )
            if is_afg_folder:
                out.extend(self._afg_strip_afg_groups(children))
                continue
            n = dict(node)
            n["children"] = self._afg_strip_afg_groups(children)
            out.append(n)
        return out

    def _afg_bs_print_tree(self, face_bs, max_level=None):
        """SOFP tree as it will appear on PDF/Word (filter + round + totals)."""
        if max_level is None:
            max_level = self._afg_tree_depth_for_pack(self._afg_global_report_pack_pref())
        tree = self._afg_bs_present_equity_components(face_bs or [])
        tree = self._afg_filter_tree_by_max_level(tree, int(max_level))
        tree = self._afg_round_tree_amounts(tree)
        return self._afg_balance_bs_tree_after_round(tree)

    def _afg_strip_account_groups(self, nodes):
        """Keep L0/L1 and ledgers; remove L2 account.group (promote children)."""
        out = []
        for node in nodes or []:
            lvl = int(node.get("level") if node.get("level") is not None else 0)
            children = list(node.get("children") or [])
            if lvl == 2:
                out.extend(self._afg_strip_account_groups(children))
                continue
            n = dict(node)
            if lvl >= 3:
                n["children"] = []
                out.append(n)
                continue
            n["children"] = self._afg_strip_account_groups(children)
            out.append(n)
        return out

    def _afg_strip_l0_types(self, nodes):
        """Drop CoA type buckets; keep AFG groups, ledgers, and computed totals."""
        out = []
        for node in nodes or []:
            lvl = int(node.get("level") if node.get("level") is not None else 0)
            children = list(node.get("children") or [])
            if lvl == 0:
                keep = (
                    bool(node.get("is_computed"))
                    or bool(node.get("is_tb_section_total"))
                    or bool(node.get("is_section_banner"))
                    or bool(node.get("is_tb_difference"))
                    or str(node.get("type_key") or "") == "grand_total"
                )
                if keep:
                    n = dict(node)
                    n["children"] = self._afg_strip_l0_types(children)
                    out.append(n)
                elif children:
                    out.extend(self._afg_strip_l0_types(children))
                continue
            n = dict(node)
            n["children"] = self._afg_strip_l0_types(children)
            out.append(n)
        return out

    def _afg_fmt_amt(self, value):
        """Whole amounts with thousands separators: 1,001 or (1,001). Near-zero → '-'."""
        try:
            if value is None:
                return "-"
            n = float(self._afg_round_amt(value))
        except (TypeError, ValueError):
            n = 0.0
        if abs(n) < 0.5:
            return "-"
        if n < 0:
            return "(%s)" % "{:,.0f}".format(abs(n))
        return "{:,.0f}".format(n)

    def _afg_pdf_disp_blank(self, disp):
        return str(disp if disp is not None else "").strip() in ("", "None", "False", "—", "–")

    def _afg_pdf_cell(self, row, field):
        """PDF amount: prefer *_disp, else numeric (fixes empty/clipped QWeb `or` chains)."""
        if not isinstance(row, dict):
            return "-"
        disp = row.get("%s_disp" % field)
        if not self._afg_pdf_disp_blank(disp):
            return disp
        return self._afg_fmt_amt(row.get(field))

    def _afg_pdf_period_cell(self, row, index):
        if not isinstance(row, dict):
            return "-"
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = 0
        disp_list = list(row.get("period_amounts_disp") or [])
        amt_list = list(row.get("period_amounts") or [])
        if 0 <= idx < len(disp_list) and not self._afg_pdf_disp_blank(disp_list[idx]):
            return disp_list[idx]
        if 0 <= idx < len(amt_list):
            return self._afg_fmt_amt(amt_list[idx])
        n = len(disp_list) or len(amt_list)
        if n <= 1:
            return self._afg_pdf_cell(row, "current")
        if idx <= 0:
            return self._afg_pdf_cell(row, "prior")
        if idx >= n - 1:
            return self._afg_pdf_cell(row, "current")
        return "-"

    def _afg_period_as_at(self, year):
        """SOFP period line, e.g. As at 31 December 2025."""
        return _("As at 31 December %s") % (year or "")

    def _afg_period_year_ended(self, year):
        """P&L / equity / cash flow / cover period line."""
        return _("For the year ended 31 December %s") % (year or "")

    def _afg_statutory_row(self, label, prior=None, current=None, note="", section=False, total=False):
        blank = "\u00a0"
        if section:
            prior_disp = current_disp = blank
        else:
            prior_disp = self._afg_fmt_amt(prior)
            current_disp = self._afg_fmt_amt(current)
        return {
            "label": label,
            "note": "" if section else (note or ""),
            "prior": None if section else prior,
            "current": None if section else current,
            "prior_disp": prior_disp,
            "current_disp": current_disp,
            "is_section": bool(section),
            "is_total": bool(total),
            "bold": bool(section or total),
            "level": 0,
        }

    def _afg_row_amount(self, rows, pred):
        hit = None
        for row in rows or []:
            label = (row.get("label") or row.get("label_raw") or "").lower()
            if pred(label):
                hit = row
                if row.get("is_total"):
                    break
        if not hit:
            return 0.0, 0.0
        return float(hit.get("prior") or 0.0), float(hit.get("current") or 0.0)

    def _afg_statutory_pl_rows(self, rows):
        """Sample statement of comprehensive income lines, amounts from the working paper."""
        rev_p, rev_c = self._afg_row_amount(
            rows, lambda l: "revenue" in l and "cost" not in l and "total sales" not in l
        )
        if not (rev_p or rev_c):
            rev_p, rev_c = self._afg_row_amount(rows, lambda l: "total sales" in l or l.strip() == "revenue")
        cost_p, cost_c = self._afg_row_amount(rows, lambda l: "cost of" in l)
        ga_p, ga_c = self._afg_row_amount(rows, lambda l: "general" in l and "admin" in l)
        sell_p, sell_c = self._afg_row_amount(rows, lambda l: "selling" in l)
        emp_p, emp_c = self._afg_row_amount(rows, lambda l: "employee" in l)
        ung_p, ung_c = self._afg_row_amount(rows, lambda l: "ungrouped" in l)
        dep_p, dep_c = self._afg_row_amount(rows, lambda l: "depreci" in l)
        net_p, net_c = self._afg_row_amount(rows, lambda l: "profit for" in l or "net profit" in l)
        ga_p += sell_p + emp_p + ung_p
        ga_c += sell_c + emp_c + ung_c
        gross_p, gross_c = rev_p - cost_p, rev_c - cost_c
        if not (net_p or net_c):
            net_p, net_c = gross_p - ga_p - dep_p, gross_c - ga_c - dep_c
        fin_p, fin_c = gross_p - ga_p - dep_p - net_p, gross_c - ga_c - dep_c - net_c
        R = self._afg_statutory_row
        return [
            R("REVENUE", section=True),
            R("Net Revenue", rev_p, rev_c, note="13"),
            R("Less : Cost of Revenue", cost_p, cost_c, note="14"),
            R("Gross Profit", gross_p, gross_c, total=True),
            R("Other Income", 0, 0),
            R("DEDUCT", section=True),
            R("General & Administration Expenses", ga_p, ga_c, note="15"),
            R("Director Remuneration", 0, 0),
            R("Depreciation", dep_p, dep_c, note="5"),
            R("Financial Charge", fin_p, fin_c),
            R("", gross_p - net_p, gross_c - net_c, total=True),
            R("Net Profit / (Loss) for the year", net_p, net_c, total=True),
        ]

    def _afg_stat_pair(self, note, current, prior):
        return [
            {"text": note or "", "cls": "note"},
            {"text": "" if current is None else self._afg_fmt_amt(current), "cls": "num"},
            {"text": "" if prior is None else self._afg_fmt_amt(prior), "cls": "num"},
        ]

    def _afg_stat_line(self, label, note, current, prior, cls=""):
        return {"label": label, "cls": cls, "cells": self._afg_stat_pair(note, current, prior)}

    def _afg_stat_section(self, label):
        return {"label": label, "cls": "sec", "cells": self._afg_stat_pair("", None, None)}

    def _afg_journal_face_signed(self):
        """Same figures the Excel statements SUMIF from the trial balance."""
        self.ensure_one()
        yc, yp = self._afg_excel_period_years()
        companies = self._afg_excel_company_ids()
        empty = {"current": 0.0, "prior": 0.0, "open": 0.0, "_ppe": {}, "_ppe_cost_move": {}}
        if not companies:
            return empty
        self.env.cr.execute(
            """
            SELECT a.id, EXTRACT(YEAR FROM l.date)::int, COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id
              JOIN account_account a ON a.id = l.account_id
             WHERE m.state = 'posted'
               AND l.company_id IN %s
               AND l.date <= %s
             GROUP BY a.id, EXTRACT(YEAR FROM l.date)
            """,
            (tuple(companies), fields.Date.from_string("%s-12-31" % yc)),
        )
        recs = self.env.cr.fetchall()
        accounts = {a.id: a for a in self._afg_account_sudo().browse(list({r[0] for r in recs if r[0]}))}
        raw = {}
        ppe = {}
        for acc_id, year, debit, credit in recs:
            acc = accounts.get(acc_id)
            if not acc:
                continue
            year = int(year or 0)
            if year < yp:
                slot = "open"
            elif year == yp:
                slot = "prior"
            elif year == yc:
                slot = "current"
            else:
                continue
            net = float(debit or 0.0) - float(credit or 0.0)
            _statement, face = self._afg_excel_face_bucket(acc)
            box = raw.setdefault(face, {"open": 0.0, "prior": 0.0, "current": 0.0})
            box[slot] += net
            if face == "Property, Plant & Equipment":
                ledger_l = (acc.name or "").lower()
                if "decor" in ledger_l:
                    klass = "Decoration"
                elif "motor" in ledger_l or "vehicle" in ledger_l:
                    klass = "Motor Vehicle"
                else:
                    klass = "Furniture & Office"
                kind = "Accumulated" if ("acc." in ledger_l or "accum" in ledger_l or "depn" in ledger_l) else "Cost"
                pbox = ppe.setdefault((klass, kind), {"open": 0.0, "prior": 0.0, "current": 0.0})
                pbox[slot] += net
        credit_faces = {
            "Net Revenue", "Other Income", "Accounts Payable", "Accruals and Provisions",
            "Share Capital", "Retained Earnings", "Shareholders' Current Account",
        }
        pl_faces = {
            "Net Revenue", "Other Income", "Less : Cost of Revenue",
            "General & Administration Expenses", "Director Remuneration",
            "Depreciation", "Financial Charge", "Corporate Tax Paid",
        }

        def _slice(box, which, is_pl):
            box = box or {"open": 0.0, "prior": 0.0, "current": 0.0}
            if is_pl:
                if which == "current":
                    return box["current"]
                if which == "prior":
                    return box["prior"]
                return 0.0
            if which == "current":
                return box["open"] + box["prior"] + box["current"]
            if which == "prior":
                return box["open"] + box["prior"]
            return box["open"]

        signed = {}
        for face_name, box in raw.items():
            is_pl = face_name in pl_faces
            signed[face_name] = {}
            for which in ("current", "prior", "open"):
                amount = _slice(box, which, is_pl)
                if face_name in credit_faces:
                    amount = -amount
                if face_name == "Retained Earnings":
                    for pl_face in pl_faces:
                        amount -= _slice(raw.get(pl_face), which, False)
                signed[face_name][which] = amount
        for face_name in list(credit_faces) + list(pl_faces):
            signed.setdefault(face_name, {"current": 0.0, "prior": 0.0, "open": 0.0})
        signed["_ppe"] = ppe
        cost_move = {"current": 0.0, "prior": 0.0}
        for (klass, kind), box in ppe.items():
            if kind == "Cost":
                cost_move["current"] += box["current"]
                cost_move["prior"] += box["prior"]
        signed["_ppe_cost_move"] = cost_move
        return signed

    def _afg_apply_statutory_face(self, chapters):
        """Replace the working-paper grid with the sample statement pages on PDF only."""
        self.ensure_one()
        if self.env.context.get("afg_skip_statutory_face"):
            return list(chapters or [])
        by_key = {}
        for ch in chapters or []:
            key = ch.get("key") or ""
            if key and key not in by_key:
                by_key[key] = ch
        company = self.company_id
        city = (company.city or (company.state_id.name if company.state_id else "") or "").strip().upper()
        place = ("%s - U.A.E." % city) if city else "U.A.E."
        company_name = self._afg_print_company_display()
        yc, yp = self._afg_excel_period_years()
        dt_c = self.date_to_current
        ended = dt_c.strftime("%B %d, %Y").upper() if dt_c else ("DECEMBER 31, %s" % yc)
        dmy_c = "31.12.%s" % yc
        dmy_p = "31.12.%s" % yp
        unit = "(In Arab Emirates Dirhams)"
        heads_year = [
            {"label": "Note", "cls": "note"},
            {"label": str(yc or ""), "cls": "num"},
            {"label": str(yp or ""), "cls": "num"},
        ]
        heads_dmy = [
            {"label": "Note", "cls": "note"},
            {"label": dmy_c, "cls": "num"},
            {"label": dmy_p, "cls": "num"},
        ]

        def page(key, title, period, heads, rows, page_no):
            return {
                "key": key,
                "kind": "statutory_page",
                "company": company_name,
                "place": place,
                "title": title,
                "period": period,
                "unit": unit,
                "heads": heads,
                "rows": rows,
                "page": page_no,
            }

        face = self._afg_journal_face_signed()

        def pair(name):
            box = face.get(name) or {}
            return box.get("prior") or 0.0, box.get("current") or 0.0

        rev_p, rev_c = pair("Net Revenue")
        oi_p, oi_c = pair("Other Income")
        cost_p, cost_c = pair("Less : Cost of Revenue")
        ga_p, ga_c = pair("General & Administration Expenses")
        dir_p, dir_c = pair("Director Remuneration")
        dep_p, dep_c = pair("Depreciation")
        fin_p, fin_c = pair("Financial Charge")
        gross_p, gross_c = (rev_p or 0.0) - (cost_p or 0.0), (rev_c or 0.0) - (cost_c or 0.0)
        net_p = (gross_p or 0.0) + (oi_p or 0.0) - (ga_p or 0.0) - (dir_p or 0.0) - (dep_p or 0.0) - (fin_p or 0.0)
        net_c = (gross_c or 0.0) + (oi_c or 0.0) - (ga_c or 0.0) - (dir_c or 0.0) - (dep_c or 0.0) - (fin_c or 0.0)
        ppe_p, ppe_c = pair("Property, Plant & Equipment")
        cash_p, cash_c = pair("Cash and Bank Balances")
        ar_p, ar_c = pair("Accounts Receivable")
        dep_adv_p, dep_adv_c = pair("Deposits, Advances & Prepayments")
        inv_p, inv_c = pair("Inventories")
        ung_p, ung_c = pair("Ungrouped Assets")
        ap_p, ap_c = pair("Accounts Payable")
        acc_p, acc_c = pair("Accruals and Provisions")
        cap_p, cap_c = pair("Share Capital")
        re_p, re_c = pair("Retained Earnings")
        ca_p, ca_c = pair("Shareholders' Current Account")
        tnca_p, tnca_c = ppe_p, ppe_c
        tca_p = (cash_p or 0) + (ar_p or 0) + (dep_adv_p or 0) + (inv_p or 0) + (ung_p or 0)
        tca_c = (cash_c or 0) + (ar_c or 0) + (dep_adv_c or 0) + (inv_c or 0) + (ung_c or 0)
        ta_p, ta_c = tnca_p + tca_p, tnca_c + tca_c
        tcl_p, tcl_c = (ap_p or 0) + (acc_p or 0), (ap_c or 0) + (acc_c or 0)
        tl_p, tl_c = tcl_p, tcl_c
        te_p, te_c = (cap_p or 0) + (re_p or 0) + (ca_p or 0), (cap_c or 0) + (re_c or 0) + (ca_c or 0)
        tle_p, tle_c = tl_p + te_p, tl_c + te_c
        L = self._afg_stat_line
        S = self._afg_stat_section
        bs_rows = [
            S("ASSETS"),
            S("Non-Current Assets"),
            L("Property, Plant & Equipment", "5", ppe_c, ppe_p),
            L("Total Non-Current Assets", "", tnca_c, tnca_p, "single"),
            S("Current Assets"),
            L("Cash and Bank Balances", "6", cash_c, cash_p),
            L("Accounts Receivable", "7", ar_c, ar_p),
            L("Inventories", "", inv_c, inv_p),
            L("Deposits, Advances & Prepayments", "8", dep_adv_c, dep_adv_p),
            L("Ungrouped Assets", "", ung_c, ung_p),
            L("Total Current Assets", "", tca_c, tca_p, "single"),
            L("TOTAL ASSETS", "", ta_c, ta_p, "double"),
            S("LIABILITIES AND SHAREHOLDERS' EQUITY"),
            S("Current Liabilities"),
            L("Accounts Payable", "9", ap_c, ap_p),
            L("Accruals and Provisions", "10", acc_c, acc_p),
            L("Total Current Liabilities", "", tcl_c, tcl_p, "single"),
            L("TOTAL LIABILITIES", "", tl_c, tl_p, "double"),
            S("Shareholders' Equity"),
            L("Share Capital", "2", cap_c, cap_p),
            L("Retained Earnings", "11", re_c, re_p),
            L("Shareholders' Current Account", "12", ca_c, ca_p),
            L("Total Shareholders' Equity", "", te_c, te_p, "single"),
            L("TOTAL LIABILITIES AND SHAREHOLDERS' EQUITY", "", tle_c, tle_p, "double"),
        ]
        pl_rows = [
            S("REVENUE"),
            L("Net Revenue", "13", rev_c, rev_p),
            L("Less : Cost of Revenue", "14", cost_c, cost_p),
            L("Gross Profit", "", gross_c, gross_p, "single"),
            L("Other Income", "", oi_c, oi_p),
            L("", "", gross_c, gross_p, "single"),
            S("DEDUCT"),
            L("General & Administration Expenses", "15", ga_c, ga_p),
            L("Director Remuneration", "", dir_c, dir_p),
            L("Depreciation", "5", dep_c, dep_p),
            L("Financial Charge", "", fin_c, fin_p),
            L("", "", (ga_c or 0) + (dir_c or 0) + (dep_c or 0) + (fin_c or 0), (ga_p or 0) + (dir_p or 0) + (dep_p or 0) + (fin_p or 0), "single"),
            L("Net Profit / (Loss) for the year", "", net_c, net_p, "double"),
        ]
        blank4 = [{"text": "", "cls": "num"} for _ in range(4)]

        def eq_row(label, capital, retained, current_ac, cls=""):
            total = None
            nums = [capital, retained, current_ac]
            if any(v is not None for v in nums):
                total = sum(float(v or 0.0) for v in nums)
            cells = []
            for val in (capital, retained, current_ac, total):
                cells.append({
                    "text": "" if val is None else self._afg_fmt_amt(val),
                    "cls": "num",
                })
            return {"label": label, "cls": cls, "cells": cells}

        y_open = yp - 1 if yp else ""
        eq_heads = [
            {"label": "Shareholders' Capital", "cls": "num"},
            {"label": "Retained Earnings", "cls": "num"},
            {"label": "Shareholders' Current A/c", "cls": "num"},
            {"label": "Total", "cls": "num"},
        ]
        eq_rows = [
            eq_row(
                "Balance as at December 31, %s" % y_open,
                (face.get("Share Capital") or {}).get("open"),
                (face.get("Retained Earnings") or {}).get("open"),
                (face.get("Shareholders' Current Account") or {}).get("open"),
            ),
            {"label": "Changes in Shareholders' Equity", "cls": "sec", "cells": blank4},
            eq_row("- Net Profit / (Loss) for the year", 0, net_p, 0, "indent"),
            eq_row("- Net Movements in Shareholders' Current A/c", 0, 0, (ca_p or 0) - ((face.get("Shareholders' Current Account") or {}).get("open") or 0), "indent"),
            eq_row("Balance as at December 31, %s" % yp, cap_p, re_p, ca_p, "single"),
            {"label": "Changes in Shareholders' Equity", "cls": "sec", "cells": blank4},
            eq_row("- Net Profit / (Loss) for the year", 0, net_c, 0, "indent"),
            eq_row("- Net Movements in Shareholders' Current A/c", 0, 0, (ca_c or 0) - (ca_p or 0), "indent"),
            eq_row("Balance as at December 31, %s" % yc, cap_c, re_c, ca_c, "double"),
        ]
        def _box(name):
            return face.get(name) or {}

        def _asset_move(name):
            b = _box(name)
            cur, pri, opn = b.get("current") or 0.0, b.get("prior") or 0.0, b.get("open") or 0.0
            return pri - cur, opn - pri

        def _liab_move(name):
            b = _box(name)
            cur, pri, opn = b.get("current") or 0.0, b.get("prior") or 0.0, b.get("open") or 0.0
            return cur - pri, pri - opn

        ar_mv_c, ar_mv_p = _asset_move("Accounts Receivable")
        dep_mv_c, dep_mv_p = _asset_move("Deposits, Advances & Prepayments")
        ap_mv_c, ap_mv_p = _liab_move("Accounts Payable")
        acc_mv_c, acc_mv_p = _liab_move("Accruals and Provisions")
        cap_mv_c, cap_mv_p = _liab_move("Share Capital")
        ca_mv_c, ca_mv_p = _liab_move("Shareholders' Current Account")
        ppe_buy = face.get("_ppe_cost_move") or {}
        buy_c, buy_p = -(ppe_buy.get("current") or 0.0), -(ppe_buy.get("prior") or 0.0)
        op_c = (net_c or 0) + (dep_c or 0) + ar_mv_c + dep_mv_c + ap_mv_c + acc_mv_c
        op_p = (net_p or 0) + (dep_p or 0) + ar_mv_p + dep_mv_p + ap_mv_p + acc_mv_p
        inv_cf_c, inv_cf_p = buy_c, buy_p
        fin_cf_c, fin_cf_p = cap_mv_c + ca_mv_c, cap_mv_p + ca_mv_p
        cash_open = (_box("Cash and Bank Balances").get("open") or 0.0)
        inc_c, inc_p = op_c + inv_cf_c + fin_cf_c, op_p + inv_cf_p + fin_cf_p
        cf_rows = [
            S("Cash flow from Operating activities :"),
            L("Net Profit / (Loss) for the year", "", net_c, net_p),
            S("Adjustments for :"),
            L("Depreciation", "", dep_c, dep_p, "indent"),
            L("Operating profit before changes in Operating Assets and Liabilities :", "", (net_c or 0) + (dep_c or 0), (net_p or 0) + (dep_p or 0), "single"),
            L("(Increase)/Decrease in Accounts Receivable", "", ar_mv_c, ar_mv_p),
            L("(Increase)/Decrease in Deposits, Advances & Prepayments", "", dep_mv_c, dep_mv_p),
            L("(Decrease)/Increase in Accounts Payable", "", ap_mv_c, ap_mv_p),
            L("(Decrease)/Increase in Accruals and Provisions", "", acc_mv_c, acc_mv_p),
            L("Net Cash inflow/(outflow) from Operating activities", "", op_c, op_p, "single"),
            S("Cash flow from Investing activities :"),
            L("Purchase of property, plant & equipment", "", buy_c, buy_p),
            L("Net Cash inflow /(outflow) from Investing activities", "", inv_cf_c, inv_cf_p, "single"),
            S("Cash flow from Financing activities :"),
            L("Capital", "", cap_mv_c, cap_mv_p),
            L("Net Movements in Shareholders' Current A/c", "", ca_mv_c, ca_mv_p),
            L("Net Cash inflow/(outflow) from Financing activities", "", fin_cf_c, fin_cf_p, "single"),
            L("Net Increase/(Decrease) in cash and cash equivalents", "", inc_c, inc_p),
            L("Cash and cash equivalents at beginning of the year", "", cash_p, cash_open),
            L("Cash and Cash equivalents at end of the year", "", (cash_p or 0) + inc_c, cash_open + inc_p, "double"),
            S("Represented by:"),
            L("Cash in Hand", "", 0, 0),
            L("Cash at Bank", "", cash_c, cash_p, "single"),
        ]
        ppe_rows = self._afg_statutory_ppe_rows(face.get("_ppe") or {}, yp, yc)
        ppe_heads = [
            {"label": "Furn., Fixtures & Office Equip.", "cls": "num"},
            {"label": "Decoration", "cls": "num"},
            {"label": "Motor Vehicle", "cls": "num"},
            {"label": "Total", "cls": "num"},
        ]
        return [
            page("bs", "STATEMENT OF FINANCIAL POSITION", "AS AT %s" % ended, heads_year, bs_rows, "-3-"),
            page("pl", "STATEMENT OF COMPREHENSIVE INCOME", "FOR THE YEAR ENDED %s" % ended, heads_dmy, pl_rows, "-4-"),
            page("equity", "STATEMENT OF CHANGES IN SHAREHOLDERS' EQUITY", "FOR THE YEAR ENDED %s" % ended, eq_heads, eq_rows, "-5-"),
            page("cashflow", "STATEMENT OF CASH FLOW", "FOR THE YEAR ENDED %s" % ended, heads_dmy, cf_rows, "-6-"),
            page("fixed_assets", "NOTES TO THE FINANCIAL STATEMENTS ( Continued)", "FOR THE YEAR ENDED %s" % ended, ppe_heads, ppe_rows, "-12-"),
        ]

    def _afg_statutory_ppe_rows(self, ppe, year_prior, year_current):
        """Note 5 in the sample column set. Amounts land in the matching asset class."""
        classes = {"Furniture & Office": 0, "Decoration": 1, "Motor Vehicle": 2}
        if isinstance(ppe, dict) and ppe and all(isinstance(k, tuple) for k in ppe):
            cost_open = [0.0, 0.0, 0.0]
            additions = [0.0, 0.0, 0.0]
            dep_open = [0.0, 0.0, 0.0]
            charge = [0.0, 0.0, 0.0]
            for (klass, kind), box in ppe.items():
                idx = classes.get(klass, 0)
                if kind == "Cost":
                    cost_open[idx] += (box.get("open") or 0.0) + (box.get("prior") or 0.0)
                    additions[idx] += box.get("current") or 0.0
                else:
                    dep_open[idx] += -((box.get("open") or 0.0) + (box.get("prior") or 0.0))
                    charge[idx] += -(box.get("current") or 0.0)
            cost_close = [cost_open[i] + additions[i] for i in range(3)]
            dep_close = [dep_open[i] + charge[i] for i in range(3)]
            nbv_close = [cost_close[i] - dep_close[i] for i in range(3)]
            nbv_open = [cost_open[i] - dep_open[i] for i in range(3)]

            def cells(vals):
                total = sum(vals)
                out = [{"text": self._afg_fmt_amt(v), "cls": "num"} for v in vals]
                out.append({"text": self._afg_fmt_amt(total), "cls": "num"})
                return out

            empty = [{"text": "", "cls": "num"} for _ in range(4)]
            return [
                {"label": "5  PROPERTY, PLANT AND EQUIPMENT", "cls": "sec", "cells": empty},
                {"label": "COST", "cls": "sec", "cells": empty},
                {"label": "As at December 31, %s" % year_prior, "cls": "", "cells": cells(cost_open)},
                {"label": "Additions", "cls": "", "cells": cells(additions)},
                {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(cost_close)},
                {"label": "Accumulated Depreciation:", "cls": "sec", "cells": empty},
                {"label": "As at December 31, %s" % year_prior, "cls": "", "cells": cells(dep_open)},
                {"label": "Charge for the year", "cls": "", "cells": cells(charge)},
                {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(dep_close)},
                {"label": "Net Book Value", "cls": "sec", "cells": empty},
                {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(nbv_close)},
                {"label": "As at December 31, %s" % year_prior, "cls": "double", "cells": cells(nbv_open)},
            ]
        buckets = {"office": 0, "decor": 1, "motor": 2}

        def bucket(name):
            n = (name or "").lower()
            if "decor" in n:
                return "decor"
            if "motor" in n or "vehicle" in n or "car" in n:
                return "motor"
            return "office"

        items = []
        # Matrix stores category names; values are on blocks. Fall back to zeros.
        cats = list((ppe or {}).get("categories") or [])
        blocks = list((ppe or {}).get("blocks") or [])
        # Sum charge / nbv if present on items via block rows aligned to cats.
        office = [0.0, 0.0, 0.0, 0.0]  # unused placeholder
        del office
        zeros = [0.0, 0.0, 0.0]

        def add_into(target, idx, value):
            target[idx] += float(value or 0.0)

        cost_open = list(zeros)
        additions = list(zeros)
        dep_open = list(zeros)
        charge = list(zeros)
        for block in blocks:
            title = (block.get("title") or "").lower()
            for row in block.get("rows") or []:
                label = (row.get("label") or "").lower()
                values = row.get("values") or []
                for i, cat in enumerate(cats):
                    val = values[i] if i < len(values) else 0.0
                    b = buckets[bucket(cat)]
                    if "cost" in title and "open" in label:
                        add_into(cost_open, b, val)
                    elif "cost" in title and "addition" in label:
                        add_into(additions, b, val)
                    elif "depreci" in title and "open" in label:
                        add_into(dep_open, b, val)
                    elif "depreci" in title and "charge" in label:
                        add_into(charge, b, val)
        cost_close = [cost_open[i] + additions[i] for i in range(3)]
        dep_close = [dep_open[i] + charge[i] for i in range(3)]
        nbv_close = [cost_close[i] - dep_close[i] for i in range(3)]
        nbv_open = [cost_open[i] - dep_open[i] for i in range(3)]

        def cells(vals):
            total = sum(vals)
            out = [{"text": self._afg_fmt_amt(v), "cls": "num"} for v in vals]
            out.append({"text": self._afg_fmt_amt(total), "cls": "num"})
            return out

        empty = [{"text": "", "cls": "num"} for _ in range(4)]
        return [
            {"label": "5  PROPERTY, PLANT AND EQUIPMENT", "cls": "sec", "cells": empty},
            {"label": "COST", "cls": "sec", "cells": empty},
            {"label": "As at December 31, %s" % year_prior, "cls": "", "cells": cells(cost_open)},
            {"label": "Additions", "cls": "", "cells": cells(additions)},
            {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(cost_close)},
            {"label": "Accumulated Depreciation:", "cls": "sec", "cells": empty},
            {"label": "As at December 31, %s" % year_prior, "cls": "", "cells": cells(dep_open)},
            {"label": "Charge for the year", "cls": "", "cells": cells(charge)},
            {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(dep_close)},
            {"label": "Net Book Value", "cls": "sec", "cells": empty},
            {"label": "As at December 31, %s" % year_current, "cls": "single", "cells": cells(nbv_close)},
            {"label": "As at December 31, %s" % year_prior, "cls": "double", "cells": cells(nbv_open)},
        ]

    def _afg_print_header(self, report_title, year_prior=None, year_current=None, as_at=False):
        """Company → report name → period (shared by Excel / Word / PDF)."""
        self.ensure_one()
        yc = year_current if year_current is not None else self.year_current
        yp = year_prior
        period = self._afg_period_caption_for_print(as_at=as_at)
        if yp in (None, False, ""):
            period_compare = str(yc or "")
        else:
            period_compare = "%s / %s" % (yp, yc)
        return {
            "company": self._afg_print_company_display(),
            "report_name": report_title or "",
            "period": period,
            "period_compare": period_compare,
            "currency": self.currency_id.name or "AED",
        }

    def _afg_print_company_display(self):
        """Same companies as the AFG form (dashboard TB scope)."""
        self.ensure_one()
        Company = self.env["res.company"].sudo()
        cids = self._tb_company_ids()
        recs = Company.browse(cids).exists()
        if not recs:
            recs = self.company_id
        if len(recs) == 1:
            return (recs.display_name or "").upper()
        parents = recs.mapped("parent_id").filtered(lambda p: p)
        if len(parents) == 1:
            return (parents.display_name or "").upper()
        return _("%s (CONSOLIDATED)") % ((recs[0].display_name or "").upper())

    def _afg_period_caption_for_print(self, as_at=False):
        """Same date window as the AFG form."""
        self.ensure_one()
        if as_at:
            dt = self.date_to_current
            if dt:
                return _("As at %s") % dt.strftime("%d %B %Y")
            return self._afg_period_as_at(self.year_current)
        df = self.date_from_current
        dt = self.date_to_current
        if df and dt:
            return _("For the period %s to %s") % (
                df.strftime("%d %B %Y"),
                dt.strftime("%d %B %Y"),
            )
        return self._afg_period_year_ended(self.year_current)

    def _afg_print_scope_key(self):
        self.ensure_one()
        return "cpabooks_afg.print_scope.%s" % self.id

    def _afg_print_scope(self):
        """audit = financial statements without CT; fta = corporate tax page only."""
        self.ensure_one()
        scope = (self.env["ir.config_parameter"].sudo().get_param(self._afg_print_scope_key()) or "audit")
        return "fta" if scope == "fta" else "audit"

    def _afg_set_print_scope(self, scope):
        self.ensure_one()
        self.env["ir.config_parameter"].sudo().set_param(
            self._afg_print_scope_key(),
            "fta" if scope == "fta" else "audit",
        )

    def _afg_filter_print_scope_chapters(self, chapters):
        """Combined audited print omits corporate tax. The CT view prints that page alone."""
        self.ensure_one()
        chapters = list(chapters or [])
        if self._afg_print_scope() == "fta":
            return [c for c in chapters if (c.get("key") or "") == "fta"]
        return [c for c in chapters if (c.get("key") or "") != "fta"]

    def _afg_print_exclude_key_set(self):
        self.ensure_one()
        raw = (self.print_exclude_keys or "").strip()
        if not raw:
            return set()
        return {k.strip() for k in raw.split(",") if k.strip()}

    def _afg_apply_print_page_include(self, chapters):
        """Print Setup does not hide pages."""
        return list(chapters or [])

    def _afg_prepend_cover_print_chapter(self, cover, chapters, yp, yc):
        """Excel already prints cover+disclaimer; PDF/Word must get the same first page."""
        cover = dict(cover or {})
        cover["entity"] = self._afg_print_company_display()
        titles = [c.get("title") or "" for c in (chapters or []) if c.get("title")]
        header = self._afg_print_header(
            cover.get("title") or _("Financial Statements"), yp, yc
        )
        if cover.get("period"):
            header = dict(header, period=cover.get("period"))
        cover_ch = {
            "key": "cover",
            "title": _("Cover / Contents"),
            "kind": "cover",
            "cover": cover,
            "contents_titles": titles,
            "header": header,
        }
        return [cover_ch] + list(chapters or [])

    def _afg_chapter_preview_text(self, ch):
        """Short text for Print Setup popup preview."""
        if not isinstance(ch, dict):
            return ""
        kind = ch.get("kind") or ""
        if kind == "cover":
            cov = ch.get("cover") or {}
            bits = [
                cov.get("entity") or "",
                cov.get("title") or "",
                cov.get("subtitle") or "",
                cov.get("disclaimer") or "",
            ]
            return " ".join(b for b in bits if b)[:500]
        if kind == "notes":
            titles = [n.get("title") or "" for n in (ch.get("notes") or []) if n]
            return "; ".join(titles)[:500]
        rows = ch.get("rows") or []
        labels = []
        for r in rows[:12]:
            lab = (r.get("label") or r.get("label_raw") or "").strip()
            if lab:
                labels.append(lab)
        if labels:
            return " · ".join(labels)[:500]
        if kind == "equity_soce":
            return _("Statement of Changes in Equity (matrix)")
        if kind == "ppe_matrix":
            return _("PPE reconciliation schedule")
        return (ch.get("title") or "")[:500]

    def action_open_print_setup(self):
        self.ensure_one()
        wiz = self.env["audited.financial.print.setup.wizard"].create({
            "version_id": self.id,
            "print_company_name": self._afg_print_company_display(),
            "print_show_page_numbers": bool(self.print_show_page_numbers),
        })
        wiz._reload_page_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Print Setup"),
            "res_model": "audited.financial.print.setup.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def _afg_arabic_label_map(self):
        """English → Arabic chrome for L1 Official Arabic pack (UAE FTA style)."""
        return {
            "Financial Statements": "القوائم المالية",
            "Audited Financial Statements": "القوائم المالية",
            "Prepared based on accounting records and accounting policies adopted by management":
                "أُعدت استناداً إلى السجلات المحاسبية والسياسات المحاسبية المعتمدة من الإدارة",
            "These financial statements have been prepared by the management of the Company "
            "based on its accounting records and are intended for general business, regulatory, "
            "statutory and management purposes. They are management-prepared financial "
            "statements and have not been audited.":
                "أعدت إدارة الشركة هذه القوائم المالية استناداً إلى سجلاتها المحاسبية وهي معدة "
                "لأغراض الأعمال والتنظيم والمتطلبات النظامية والإدارة. وهي قوائم مالية معدة "
                "من قبل الإدارة ولم يتم تدقيقها.",
            "Statement of Profit or Loss": "بيان الأرباح أو الخسائر",
            "Statement of Financial Position": "بيان المركز المالي",
            "Statement of Changes in Equity": "بيان التغيرات في حقوق الملكية",
            "Statement of Cash Flows": "بيان التدفقات النقدية",
            "Property, Plant And Equipment": "الممتلكات والآلات والمعدات",
            "Property, Plant and Equipment": "الممتلكات والآلات والمعدات",
            "Property, Plant and Equipment Reconciliation": "مطابقة الممتلكات والآلات والمعدات",
            "Notes To The Financial Statements": "إيضاحات حول القوائم المالية",
            "Notes to the Financial Statements": "إيضاحات حول القوائم المالية",
            "Particulars": "البيان",
            "Total": "الإجمالي",
            "Description": "الوصف",
            "Opening Cost": "تكلفة أول المدة",
            "Opening cost": "تكلفة أول المدة",
            "Additions": "الإضافات",
            "Disposals": "الاستبعادات",
            "Closing Cost": "تكلفة آخر المدة",
            "Closing cost": "تكلفة آخر المدة",
            "Opening Accumulated Depreciation": "مجمع الاستهلاك أول المدة",
            "Opening accumulated depreciation": "مجمع الاستهلاك أول المدة",
            "Charge For The Year": "استهلاك السنة",
            "Charge for the year": "استهلاك السنة",
            "Closing Accumulated Depreciation": "مجمع الاستهلاك آخر المدة",
            "Closing accumulated depreciation": "مجمع الاستهلاك آخر المدة",
            "Closing Net Book Value": "صافي القيمة الدفترية آخر المدة",
            "Closing net book value": "صافي القيمة الدفترية آخر المدة",
            "Opening Net Book Value": "صافي القيمة الدفترية أول المدة",
            "Opening net book value": "صافي القيمة الدفترية أول المدة",
            "Cost (Aed)": "التكلفة (درهم)",
            "COST (AED)": "التكلفة (درهم)",
            "Accumulated Depreciation (Aed)": "مجمع الاستهلاك (درهم)",
            "ACCUMULATED DEPRECIATION (AED)": "مجمع الاستهلاك (درهم)",
            "Net Book Value (Aed)": "صافي القيمة الدفترية (درهم)",
            "NET BOOK VALUE (AED)": "صافي القيمة الدفترية (درهم)",
            "Opening Balance": "الرصيد الافتتاحي",
            "Opening balance": "الرصيد الافتتاحي",
            "Closing Balance": "الرصيد الختامي",
            "Closing balance": "الرصيد الختامي",
            "Profit/(Loss) For The Year": "ربح/(خسارة) السنة",
            "Profit/(loss) for the year": "ربح/(خسارة) السنة",
            "Profit For The Year": "ربح السنة",
            "Profit for the Year": "ربح السنة",
            "Capital Introduced/(Repaid)": "رأس المال المدفوع/(المسترد)",
            "Capital introduced/(repaid)": "رأس المال المدفوع/(المسترد)",
            "Drawings / Distributions": "المسحوبات / التوزيعات",
            "Drawings / distributions": "المسحوبات / التوزيعات",
            "Other Transfers": "تحويلات أخرى",
            "Other transfers": "تحويلات أخرى",
            "Share Capital / Capital": "رأس المال",
            "Owners' Current Account": "الحساب الجاري للملاك",
            "Retained Earnings": "الأرباح المحتجزة",
            "Retained Earnings / Undistributed": "الأرباح المحتجزة / غير الموزعة",
            "Accumulated Losses": "الخسائر المتراكمة",
            "Other Equity": "حقوق ملكية أخرى",
            "Authorized Signatory": "المفوض بالتوقيع",
            "For And On Behalf Of": "عن وبالنيابة عن",
            "For and on behalf of": "عن وبالنيابة عن",
            "Year": "سنة",
            "Notes": "إيضاحات",
            "Assets": "الأصول",
            "Liabilities": "الالتزامات",
            "Equity": "حقوق الملكية",
            "Revenue": "الإيرادات",
            "Expenses": "المصروفات",
        }

    def _afg_ar(self, text):
        """Translate a print chrome string to Arabic when possible."""
        if text is None:
            return text
        s = str(text)
        if not s.strip():
            return s
        amap = self._afg_arabic_label_map()
        if s in amap:
            return amap[s]
        # Case-insensitive / proper-case variants
        for en, ar in amap.items():
            if s.lower() == en.lower():
                return ar
        m = re.match(r"^(COST|ACCUMULATED DEPRECIATION|NET BOOK VALUE)\s*\(([^)]+)\)\s*$", s, re.I)
        if m:
            head = {
                "cost": "التكلفة",
                "accumulated depreciation": "مجمع الاستهلاك",
                "net book value": "صافي القيمة الدفترية",
            }.get(m.group(1).lower())
            if head:
                return "%s (%s)" % (head, m.group(2))
        m = re.match(r"^(?:Property,\s*Plant\s+and\s+Equipment\s*[—\-–]\s*)?Year\s+(\d{4})\s*$", s, re.I)
        if m:
            return "سنة %s" % m.group(1)
        m = re.match(r"^For the year ended 31 December\s+(\d{4})\s*$", s, re.I)
        if m:
            return "للسنة المنتهية في 31 ديسمبر %s" % m.group(1)
        m = re.match(r"^As at 31 December\s+(\d{4})\s*$", s, re.I)
        if m:
            return "كما في 31 ديسمبر %s" % m.group(1)
        return s

    def _afg_apply_arabic_print_document(self, doc):
        """Localize cover / chapter chrome for L1 Official Arabic Version."""
        doc = dict(doc or {})
        cover = dict(doc.get("cover") or {})
        for key in ("title", "subtitle", "period", "disclaimer"):
            if cover.get(key):
                cover[key] = self._afg_ar(cover[key])
        doc["cover"] = cover
        if doc.get("signatory_label"):
            doc["signatory_label"] = self._afg_ar(doc["signatory_label"])
        sig = dict(doc.get("signatory") or {})
        for key in ("for_line", "signatory_label"):
            if sig.get(key):
                sig[key] = self._afg_ar(sig[key])
        doc["signatory"] = sig

        chapters = []
        for ch in doc.get("chapters") or []:
            c = dict(ch)
            if c.get("title"):
                c["title"] = self._afg_ar(c["title"])
            hdr = dict(c.get("header") or {})
            for key in ("report_name", "period", "period_compare"):
                if hdr.get(key):
                    hdr[key] = self._afg_ar(hdr[key])
            c["header"] = hdr
            if c.get("kind") == "ppe_matrix":
                ppe = dict(c.get("ppe") or {})
                ppe["categories"] = [self._afg_ar(x) for x in (ppe.get("categories") or [])]
                blocks = []
                for block in ppe.get("blocks") or []:
                    b = dict(block)
                    if b.get("title"):
                        b["title"] = self._afg_ar(b["title"])
                    rows = []
                    for prow in b.get("rows") or []:
                        pr = dict(prow)
                        if pr.get("label"):
                            pr["label"] = self._afg_ar(pr["label"])
                        rows.append(pr)
                    b["rows"] = rows
                    blocks.append(b)
                ppe["blocks"] = blocks
                c["ppe"] = ppe
            if c.get("kind") == "equity_soce":
                soce = dict(c.get("soce") or {})
                cols = []
                for col in soce.get("columns") or []:
                    cc = dict(col)
                    if cc.get("name"):
                        cc["name"] = self._afg_ar(cc["name"])
                    cols.append(cc)
                soce["columns"] = cols
                rows = []
                for row in soce.get("rows") or []:
                    rr = dict(row)
                    if rr.get("label"):
                        rr["label"] = self._afg_ar(rr["label"])
                    rows.append(rr)
                soce["rows"] = rows
                c["soce"] = soce
            if c.get("kind") == "notes":
                notes = []
                for note in c.get("notes") or []:
                    nn = dict(note)
                    if nn.get("title"):
                        nn["title"] = self._afg_ar(nn["title"])
                    notes.append(nn)
                c["notes"] = notes
            # Statement face row labels (Description column)
            rows = []
            for row in c.get("rows") or []:
                rr = dict(row)
                for key in ("label", "label_raw"):
                    if rr.get(key):
                        rr[key] = self._afg_ar(rr[key])
                rows.append(rr)
            if c.get("rows") is not None:
                c["rows"] = rows
            chapters.append(c)
        doc["chapters"] = chapters
        doc["arabic"] = True
        doc["rtl"] = True
        return doc

    @api.model
    def _afg_binary_as_b64(self, data):
        """Normalize Binary field value to a base64 ASCII string (or False)."""
        if not data:
            return False
        if isinstance(data, memoryview):
            data = data.tobytes()
        if isinstance(data, bytes):
            # Already raw image bytes → encode; already-b64 bytes → keep as ascii
            try:
                text = data.decode("ascii")
                if re.fullmatch(r"[A-Za-z0-9+/=\s]+", text or ""):
                    return "".join(text.split())
            except UnicodeDecodeError:
                pass
            return base64.b64encode(data).decode("ascii")
        text = str(data)
        # bin_size context returns e.g. "45.20 Kb" — not image data
        if re.search(r"\b(bytes?|kb|mb|gb)\b", text, flags=re.I):
            return False
        cleaned = "".join(text.split())
        if not cleaned:
            return False
        if not re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
            return False
        return cleaned

    @api.model
    def _afg_image_data_uri(self, b64_data):
        """Build data URI with MIME sniff (PNG/JPEG/GIF/WebP) for wkhtmltopdf."""
        raw = self._afg_binary_as_b64(b64_data)
        if not raw:
            return False
        try:
            blob = base64.b64decode(raw, validate=False)
        except Exception:
            return False
        mime = "image/png"
        if blob.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif blob.startswith(b"GIF8"):
            mime = "image/gif"
        elif blob.startswith(b"RIFF") and b"WEBP" in blob[:16]:
            mime = "image/webp"
        elif blob.startswith(b"\x89PNG"):
            mime = "image/png"
        return "data:%s;base64,%s" % (mime, raw)

    def _afg_signatory_block(self):
        """Management sign-off with optional company stamp + signature images."""
        self.ensure_one()
        # Always read full binaries (report/export context may set bin_size=True)
        company = self.company_id.sudo().with_context(bin_size=False)
        entity = (company.display_name or "").upper()
        stamp = False
        signature = False
        if "cpabooks_company_stamp" in company._fields:
            stamp = self._afg_binary_as_b64(company.cpabooks_company_stamp)
        if not stamp and "stamp" in company._fields:
            stamp = self._afg_binary_as_b64(company.stamp)
        # Fallback: active company switcher (AFG version company may differ)
        if not stamp:
            env_co = self.env.company.sudo().with_context(bin_size=False)
            if env_co and env_co.id != company.id:
                if "cpabooks_company_stamp" in env_co._fields:
                    stamp = self._afg_binary_as_b64(env_co.cpabooks_company_stamp)
                if not stamp and "stamp" in env_co._fields:
                    stamp = self._afg_binary_as_b64(env_co.stamp)
        if "cpabooks_company_signature" in company._fields:
            signature = self._afg_binary_as_b64(company.cpabooks_company_signature)
        if not signature and "company_signature" in company._fields:
            signature = self._afg_binary_as_b64(company.company_signature)
        if not signature:
            env_co = self.env.company.sudo().with_context(bin_size=False)
            if env_co and env_co.id != company.id:
                if "cpabooks_company_signature" in env_co._fields:
                    signature = self._afg_binary_as_b64(env_co.cpabooks_company_signature)
                if not signature and "company_signature" in env_co._fields:
                    signature = self._afg_binary_as_b64(env_co.company_signature)
        # Compact print size so stamp+signature fit remaining page (avoids orphan blank pages).
        # Company scale 75/100/125 still applies on this base.
        scale_pct = 100
        if "cpabooks_stamp_print_scale" in company._fields and company.cpabooks_stamp_print_scale:
            try:
                scale_pct = int(company.cpabooks_stamp_print_scale)
            except (TypeError, ValueError):
                scale_pct = 100
        if scale_pct not in (75, 100, 125):
            scale_pct = 100
        factor = scale_pct / 100.0
        stamp_pt = round(96.0 * factor, 1)
        signature_h_pt = round(64.0 * factor, 1)
        signature_w_pt = round(140.0 * factor, 1)
        stamp_uri = self._afg_image_data_uri(stamp) if stamp else False
        signature_uri = self._afg_image_data_uri(signature) if signature else False
        return {
            "for_line": _("For and on behalf of"),
            "entity": entity,
            "signatory_label": _("Authorized Signatory"),
            "stamp": stamp,
            "signature": signature,
            "stamp_src": stamp_uri,
            "signature_src": signature_uri,
            "stamp_scale": scale_pct,
            "stamp_max_pt": stamp_pt,
            "stamp_style": "max-height:%spt;max-width:%spt;margin-right:12pt;vertical-align:middle;" % (
                stamp_pt, stamp_pt,
            ),
            "signature_max_h_pt": signature_h_pt,
            "signature_max_w_pt": signature_w_pt,
            "signature_style": "max-height:%spt;max-width:%spt;vertical-align:middle;" % (
                signature_h_pt, signature_w_pt,
            ),
            # Excel insert_image scale (compact to match PDF page fit)
            "stamp_excel_scale": round(0.48 * factor, 3),
            "signature_excel_scale": round(0.60 * factor, 3),
            "excel_row_height": int(round(96.0 * factor)),
        }

    def _afg_coa_type_key_for_account(self, account):
        """Map account.internal_group → statement type_key."""
        ig = (getattr(account, "internal_group", None) or "").strip()
        if not ig and account.user_type_id:
            ig = (account.user_type_id.internal_group or "").strip()
        return {
            "asset": "asset",
            "liability": "liability",
            "equity": "equity",
            "income": "sales",
            "expense": "expenses",
        }.get(ig)

    def _afg_merge_unmapped_into_statements(self, tree_by_section, column_order=None):
        """Pull posted CoA ledgers missing from AFG mapping into Ungrouped FS lines.

        Every TB balance must appear on Financial Statements or be an explicit gap
        in the reconciliation schedule — never silently omitted.
        """
        self.ensure_one()
        tree_by_section = dict(tree_by_section or {})
        cids = [int(c) for c in (column_order or self._afg_column_company_order() or [])]
        if not cids:
            cids = self._tb_company_ids()
        mapped = set()
        for sec in ("pl", "bs", "equity", "fixed_assets"):
            mapped |= self._afg_tb_collect_mapped_account_ids(tree_by_section.get(sec) or [])
        # Also ids stored on AFG lines (covers pruned zeros)
        for line in self.line_ids:
            if line.account_id:
                mapped.add(int(line.account_id.id))
            for tok in (line.merged_leaf_account_ids or "").split(","):
                tok = (tok or "").strip()
                if tok.isdigit():
                    mapped.add(int(tok))
        Line = self.env["audited.financial.group.line"].with_context(afg_skip_collapse=True)
        ungrp_codes = tuple(Line._afg_ungrouped_codes())
        by_key = self._afg_build_pl_ledger_key_map(cids)
        for gl in Line.search([("account_id", "!=", False)]):
            if not gl.group_id or (gl.group_id.code or "") in ungrp_codes:
                continue
            k = self._afg_pl_unique_ledger_key(gl.account_id)
            if k:
                mapped.update(int(i) for i in (by_key.get(k) or []) if i)

        yp, yc = self.year_prior, self.year_current
        df_p = fields.Date.to_string(self.date_from_prior) if self.date_from_prior else "%s-01-01" % yp
        dt_p = fields.Date.to_string(self.date_to_prior) if self.date_to_prior else "%s-12-31" % yp
        df_c = fields.Date.to_string(self.date_from_current) if self.date_from_current else "%s-01-01" % yc
        dt_c = fields.Date.to_string(self.date_to_current) if self.date_to_current else "%s-12-31" % yc
        tb_p = self._fetch_tb(df_p, dt_p, cids)
        tb_c = self._fetch_tb(df_c, dt_c, cids)
        # BS / equity inject: CoA stock incl. unaffected earnings (not raw closing)
        cl_p = self._fetch_tb_coa_stock(dt_p, cids, fy_anchor_date=df_p)
        cl_c = self._fetch_tb_coa_stock(dt_c, cids, fy_anchor_date=df_c)

        Account = self.env["account.account"].sudo()
        buckets = OrderedDict()  # (section, type_key) -> list of ledger nodes
        for aid in set(list(tb_c.keys()) + list(cl_c.keys()) + list(tb_p.keys()) + list(cl_p.keys())):
            try:
                aid = int(aid)
            except (TypeError, ValueError):
                continue
            if aid in mapped:
                continue
            acc = Account.browse(aid)
            if not acc.exists():
                continue
            type_key = self._afg_coa_type_key_for_account(acc)
            if not type_key:
                continue
            # P&L unique ledgers already sit on the statement (same as Default P&L).
            if type_key in ("sales", "expenses"):
                continue
            section = "pl" if type_key in ("sales", "expenses", "cost_of_revenue") else "bs"
            # Direct costs often share expense internal_group — leave under expenses
            if section == "pl":
                prior = float(tb_p.get(aid, 0.0) or 0.0)
                current = float(tb_c.get(aid, 0.0) or 0.0)
            else:
                prior = float(cl_p.get(aid, 0.0) or 0.0)
                current = float(cl_c.get(aid, 0.0) or 0.0)
            if abs(prior) < 0.005 and abs(current) < 0.005:
                continue
            code = (acc.code or "").strip()
            name = (acc.name or "").strip()
            label = ("%s %s" % (code, name)).strip() if code else name
            led = {
                "id": "fs-unmapped-%s" % aid,
                "account_id": aid,
                "label": label,
                "ledger_caption": label,
                "level": 3,
                "kind": "ledger",
                "prior": prior,
                "current": current,
                "co_prior": [prior],
                "co_curr": [current],
                "is_unmapped_coa": True,
            }
            buckets.setdefault((section, type_key), []).append(led)

        for (section, type_key), ledgers in buckets.items():
            if not ledgers:
                continue
            roots = list(tree_by_section.get(section) or [])
            by_key = {n.get("type_key"): n for n in roots if n.get("type_key")}
            shell = by_key.get(type_key)
            group = {
                "id": "fs-ungrouped-%s-%s" % (section, type_key),
                "label": _("Ungrouped (CoA — needs mapping)"),
                "afg_caption": _("Ungrouped (CoA — needs mapping)"),
                "level": 1,
                "kind": "group",
                "is_unmapped_coa": True,
                "is_ungrouped_review": True,
                "ungrouped_code": "AFG_UNGRP_PL" if section == "pl" else "AFG_UNGRP_BS",
                "group_id": self.env["audited.financial.group"].search([
                    ("code", "=", "AFG_UNGRP_PL" if section == "pl" else "AFG_UNGRP_BS"),
                    ("company_id", "=", False),
                ], limit=1).id,
                "children": ledgers,
                "prior": sum(float(l.get("prior") or 0.0) for l in ledgers),
                "current": sum(float(l.get("current") or 0.0) for l in ledgers),
            }
            group["drill_account_ids"] = self._afg_leaf_account_ids_from_node(group)
            group["co_prior"] = [group["prior"]]
            group["co_curr"] = [group["current"]]
            if shell:
                kids = list(shell.get("children") or [])
                kids.append(group)
                shell["children"] = kids
                sp, sc, cp, cc = self._afg_sum_branch_nodes(kids)
                shell["prior"], shell["current"] = sp, sc
                shell["co_prior"], shell["co_curr"] = cp, cc
                # keep roots list identity
                tree_by_section[section] = roots
            else:
                meta = (AFG_SECTION_COA_TYPES.get(section) or {}).get(type_key) or {
                    "label": type_key, "sequence": 90,
                }
                shell = self._afg_type_shell(section, type_key, meta, [group])
                roots.append(shell)
                by_key[type_key] = shell
                if section == "pl":
                    type_meta = AFG_SECTION_COA_TYPES.get("pl") or {}
                    np_meta = type_meta.get("net_profit")
                    if np_meta:
                        src = [by_key[k] for k in ("sales", "cost_of_revenue", "expenses") if k in by_key]
                        if src:
                            np_shell = self._afg_computed_type_shell("pl", "net_profit", np_meta, src)
                            roots = [n for n in roots if n.get("type_key") != "net_profit"] + [np_shell]
                tree_by_section[section] = roots

        # Refresh BS computed totals after asset/liability/equity injections
        if tree_by_section.get("bs"):
            tree_by_section["bs"] = self._afg_bs_force_accounting_equation(
                self._afg_refresh_bs_type_shells(tree_by_section["bs"])
            )
        return tree_by_section

    def _afg_refresh_bs_type_shells(self, bs_roots):
        """Recompute asset/liability/equity totals and total_* shells from children."""
        by_key = {n.get("type_key"): n for n in (bs_roots or []) if n.get("type_key")}
        for tk in ("asset", "liability", "equity"):
            shell = by_key.get(tk)
            if not shell:
                continue
            kids = shell.get("children") or []
            if kids:
                sp, sc, cp, cc = self._afg_sum_branch_nodes(kids)
                shell["prior"], shell["current"] = sp, sc
                shell["co_prior"], shell["co_curr"] = cp, cc
        out = []
        for type_key, meta in AFG_BS_COA_TYPES.items():
            computed_from = meta.get("computed_from")
            if computed_from:
                src = [by_key[k] for k in computed_from if k in by_key]
                if src:
                    out.append(self._afg_computed_type_shell("bs", type_key, meta, src))
            elif type_key in by_key:
                out.append(by_key[type_key])
        return out or list(bs_roots or [])

    def _afg_fs_tb_reconciliation(self, face_sections, tb_payload):
        """L4 schedule: Trial Balance vs Financial Statement by CoA type (+ ledger gaps)."""
        self.ensure_one()
        rows = []
        tol = 0.505

        def _face_amt(sec, tk, field):
            n = self._afg_type_by_key(face_sections.get(sec) or [], tk)
            return abs(float((n or {}).get(field) or 0.0))

        # Collect TB panel type totals from signed roots when available
        tb_by_type = {}
        for panel in (tb_payload or {}).get("panels") or []:
            for root in panel.get("roots") or []:
                tk = str(root.get("type_key") or "")
                if not tk or root.get("is_tb_section_total"):
                    continue
                tb_by_type[tk] = {
                    "prior": abs(float(root.get("prior") or 0.0)),
                    "current": abs(float(root.get("current") or 0.0)),
                    "label": root.get("label") or tk,
                }

        pairs = [
            ("pl", "sales", "income", _("Revenue / Income")),
            ("pl", "cost_of_revenue", "expense", _("Cost of revenue")),
            ("pl", "expenses", "expense", _("Expenses")),
            ("bs", "asset", "asset", _("Assets")),
            ("bs", "liability", "liability", _("Liabilities")),
            ("bs", "equity", "equity", _("Equity")),
        ]
        # expense type on TB may combine cost+expenses — compare combined when needed
        for sec, fs_tk, tb_tk, label in pairs:
            fs_p = _face_amt(sec, fs_tk, "prior")
            fs_c = _face_amt(sec, fs_tk, "current")
            tb = tb_by_type.get(tb_tk) or tb_by_type.get(fs_tk) or {}
            tb_p = float(tb.get("prior") or 0.0)
            tb_c = float(tb.get("current") or 0.0)
            # For expenses FS vs TB: when both cost and expenses map to expense, skip duplicate
            if fs_tk == "cost_of_revenue":
                continue
            if fs_tk == "expenses":
                fs_p += _face_amt("pl", "cost_of_revenue", "prior")
                fs_c += _face_amt("pl", "cost_of_revenue", "current")
                # TB may split Cost of Materials under cost_of_revenue (not only expense)
                for extra_tk in ("cost_of_revenue", "cogs", "cost"):
                    extra = tb_by_type.get(extra_tk) or {}
                    if extra:
                        tb_p += float(extra.get("prior") or 0.0)
                        tb_c += float(extra.get("current") or 0.0)
                        break
            adj_p = fs_p - tb_p
            adj_c = fs_c - tb_c
            rows.append({
                "label": label,
                "tb_prior": tb_p,
                "tb_current": tb_c,
                "adj_prior": adj_p,
                "adj_current": adj_c,
                "fs_prior": fs_p,
                "fs_current": fs_c,
                "ok": abs(adj_p) <= tol and abs(adj_c) <= tol,
            })

        # Unmapped ledger detail from face trees
        ledger_gaps = []
        for sec in ("pl", "bs"):
            for root in face_sections.get(sec) or []:
                stack = [root]
                while stack:
                    n = stack.pop()
                    stack.extend(list(n.get("children") or []))
                    if n.get("is_unmapped_coa") and int(n.get("level") or 0) >= 3:
                        ledger_gaps.append({
                            "section": sec,
                            "label": n.get("label") or "",
                            "account_id": n.get("account_id"),
                            "prior": float(n.get("prior") or 0.0),
                            "current": float(n.get("current") or 0.0),
                        })

        ok = all(r.get("ok") for r in rows) if rows else True
        return {
            "rows": rows,
            "ledger_gaps": ledger_gaps,
            "ok": ok,
            "title": _("FS Adjustment / Reconciliation (TB → Financial Statements)"),
        }

    def _afg_cy_pnl_abs_for_tb_recon(self, face_sections):
        """Absolute CY Profit/(Loss) to add onto TB equity for FS↔TB compare."""
        face_sections = face_sections or {}
        net = self._afg_type_by_key(face_sections.get("pl") or [], "net_profit")
        p = abs(float((net or {}).get("prior") or 0.0))
        c = abs(float((net or {}).get("current") or 0.0))
        if p > 0.505 or c > 0.505:
            return p, c
        eq = self._afg_type_by_key(face_sections.get("bs") or [], "equity")
        for ch in (eq or {}).get("children") or []:
            if ch.get("type_key") == "cy_pnl" or self._afg_node_looks_like_cy_pnl(ch):
                return (
                    abs(float(ch.get("prior") or 0.0)),
                    abs(float(ch.get("current") or 0.0)),
                )
        raw_p, raw_c = self._afg_pl_net_amounts(face_sections.get("pl") or [])
        return abs(float(raw_p or 0.0)), abs(float(raw_c or 0.0))

    def _afg_critical_validation_names(self):
        return (
            _("Revenue - Expenses = Profit for the Year"),
            _("Assets = Equity + Liabilities"),
            _("Printed SOFP Assets = Equity + Liabilities"),
            _("SOCE closing agrees to SOFP equity"),
            _("SOCE profit/(loss) agrees to P&L"),
            _("Closing cash agrees to Cash Flow"),
            _("Financial Statements reconcile to Trial Balance"),
            _("Opening balances agree to prior-year closing"),
        )

    def _afg_l1_print_failures(self, pack, validations=None):
        """Return list of critical FAIL validations that block L1 Official print."""
        pack = self._afg_normalize_report_pack(pack)
        if not self._afg_is_l1_official_pack(pack):
            return []
        if validations is None:
            data = self.afg_dashboard_data()
            validations = data.get("validations") or []
        critical = set(self._afg_critical_validation_names())
        fails = [
            v for v in validations
            if (v.get("status") or "") == "FAIL" and (v.get("name") or "") in critical
        ]
        if not fails:
            fails = [
                v for v in validations
                if (v.get("status") or "") == "FAIL" and any(
                    k in (v.get("name") or "")
                    for k in (
                        "Assets =", "Printed SOFP", "Revenue - Expenses", "Trial Balance",
                        "SOCE", "Closing cash", "Opening balances",
                        "Financial Statements reconcile", "PPE", "Cash flow",
                    )
                )
            ]
        return fails

    def _afg_l1_print_gap_hints(self):
        """Extra TB↔FS gap rows for the print-gate wizard."""
        hints = []
        try:
            data = self.afg_dashboard_data()
            schedules = data.get("schedules") or {}
            recon = schedules.get("fs_tb_reconciliation") or {}
            for row in recon.get("rows") or []:
                if row.get("ok"):
                    continue
                hints.append(_(
                    "%(lab)s — TB cur %(tb).2f vs FS cur %(fs).2f (gap %(g).2f)"
                ) % {
                    "lab": row.get("label") or "",
                    "tb": float(row.get("tb_current") or 0.0),
                    "fs": float(row.get("fs_current") or 0.0),
                    "g": float(row.get("adj_current") or 0.0),
                })
            for gap in (recon.get("ledger_gaps") or [])[:8]:
                hints.append(_(
                    "Unmapped ledger [%(sec)s] %(lab)s (cur %(c).2f)"
                ) % {
                    "sec": gap.get("section") or "",
                    "lab": gap.get("label") or "",
                    "c": float(gap.get("current") or 0.0),
                })
        except Exception:  # noqa: BLE001
            pass
        return hints

    def _afg_open_l1_print_wizard(self, pack, fails, export_kind="pdf"):
        """Notification-style wizard: show stuck issues, Yes/No, fix path."""
        self.ensure_one()
        gap_hints = self._afg_l1_print_gap_hints()
        summary_parts = []
        for v in fails[:8]:
            summary_parts.append(
                "• %s — %s" % (v.get("name") or "", v.get("detail") or "")
            )
        if gap_hints:
            summary_parts.append("")
            summary_parts.append(_("TB ↔ FS detail:"))
            summary_parts.extend("  - %s" % h for h in gap_hints[:10])
        summary = "\n".join(summary_parts) or _(
            "Critical validation FAIL — see Validation section."
        )
        lines = []
        for v in fails:
            lines.append((0, 0, {
                "name": v.get("name") or "",
                "detail": v.get("detail") or "",
                "gap_hint": "",
            }))
        for h in gap_hints[:12]:
            lines.append((0, 0, {
                "name": _("TB ↔ FS gap"),
                "detail": h,
                "gap_hint": "recon",
            }))
        wiz = self.env["audited.financial.l1.print.wizard"].create({
            "version_id": self.id,
            "export_pack": int(pack or 1),
            "export_kind": export_kind or "pdf",
            "summary": summary,
            "tip": _(
                "Yes = print anyway. No = cancel. "
                "Fix path = switch to L4 Working Papers to correct mappings."
            ),
            "line_ids": lines,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Print blocked — fix or continue?"),
            "res_model": "audited.financial.l1.print.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
            "views": [(False, "form")],
            "context": {"dialog_size": "medium"},
        }

    def _afg_assert_l1_print_allowed(self, pack, validations=None, export_kind="pdf"):
        """Print always — no IFRS / validation gate."""
        return None

    def _afg_filter_notes_for_statements(self, notes, fixed_assets_recon, face_sections):
        """Drop PPE narrative when no PPE; soften IFRS-compliance claims for management packs."""
        notes = list(notes or [])
        far = fixed_assets_recon or {}
        has_ppe_schedule = bool(far.get("items"))
        ppe_node = self._afg_l1_by_code((face_sections or {}).get("bs") or [], "AFG_PPE")
        has_ppe_sofp = bool(
            ppe_node and (
                abs(float(ppe_node.get("current") or 0.0)) > 0.505
                or abs(float(ppe_node.get("prior") or 0.0)) > 0.505
            )
        )
        out = []
        mgmt_basis = _(
            "<p>These financial statements have been prepared based on the Company's accounting "
            "records and the accounting policies adopted by management. They are "
            "management-prepared and have not been audited.</p>"
        )
        for n in notes:
            item = dict(n) if isinstance(n, dict) else {
                "title": getattr(n, "title", None) or "",
                "body": getattr(n, "body", None) or "",
            }
            title = item.get("title") or ""
            body = item.get("body") or ""
            if hasattr(body, "__html__"):
                body = str(body)
                item["body"] = body
            low = title.lower()
            if not (has_ppe_schedule or has_ppe_sofp):
                if "property, plant and equipment" in low or re.match(r"^\s*6[\.\)]\s*property", low):
                    continue
            if isinstance(body, str) and (
                "International Financial Reporting Standards" in body
                or "in accordance with IFRS" in body
                or "accordance with International Financial" in body
            ):
                item["body"] = mgmt_basis
            out.append(item)
        renumbered = []
        seq = 1
        for item in out:
            title = item.get("title") or ""
            m = re.match(r"^\s*\d+[\.\)]\s*(.*)$", title)
            if m:
                item = dict(item, title="%s. %s" % (seq, m.group(1).strip()))
            seq += 1
            renumbered.append(item)
        return renumbered

    def _afg_notes_are_training_stubs(self, notes):
        """True when stored notes are old training placeholders (not L1 Official)."""
        blob_parts = []
        for n in notes or []:
            if isinstance(n, dict):
                body = n.get("body") or ""
                title = n.get("title") or ""
            else:
                body = getattr(n, "body", None) or ""
                title = getattr(n, "title", None) or ""
            if hasattr(body, "__html__"):
                body = str(body)
            plain = re.sub(r"<[^>]+>", " ", body)
            plain = re.sub(r"&nbsp;", " ", plain, flags=re.I)
            blob_parts.append("%s %s" % (title, plain))
        blob = " ".join(blob_parts).lower()
        markers = (
            "illustrative figures are for training",
            "would be disclosed here",
            "replace them with amounts from posted journals",
        )
        # Short 1–2 stub notes with training markers → replace
        if any(m in blob for m in markers):
            return True
        return False

    def _afg_resolve_statement_notes(self, notes):
        """Ensure Notes chapter matches L1 Official template (not training stubs)."""
        cleaned = []
        for n in notes or []:
            item = dict(n) if isinstance(n, dict) else {
                "title": getattr(n, "title", None) or "",
                "body": getattr(n, "body", None) or "",
            }
            body = item.get("body") or ""
            if hasattr(body, "__html__"):
                body = str(body)
            item["body"] = body
            item["title"] = (item.get("title") or "").strip() or _("Note")
            cleaned.append(item)

        def _has_body(ns):
            for item in ns:
                plain = re.sub(r"<[^>]+>", " ", item.get("body") or "")
                plain = re.sub(r"&nbsp;", " ", plain, flags=re.I)
                if plain.strip():
                    return True
            return False

        # Empty OR old training stubs → full L1 Official notes (locked format)
        use_official = (
            not cleaned
            or not _has_body(cleaned)
            or self._afg_notes_are_training_stubs(cleaned)
        )
        if not use_official:
            return cleaned

        placeholders = []
        if hasattr(self, "_dashboard_placeholder_notes"):
            placeholders = self._dashboard_placeholder_notes() or []
        out = []
        for n in placeholders:
            item = dict(n) if isinstance(n, dict) else {"title": "", "body": ""}
            body = item.get("body") or ""
            if hasattr(body, "__html__"):
                body = str(body)
            item["body"] = body
            item["title"] = (item.get("title") or "").strip() or _("Note")
            out.append(item)
        return out

    def _afg_comparative_presentation(self, face_sections, schedules):
        """Detect first-period / missing prior P&L+CF — hide misleading comparative dashes."""
        pl = (face_sections or {}).get("pl") or []
        prior_pl = 0.0
        for n in pl:
            prior_pl += abs(float(n.get("prior") or 0.0))
        cf = (schedules or {}).get("cashflow_statement") or {}
        prior_cf = 0.0
        for row in cf.get("rows") or []:
            prior_cf += abs(float(row.get("prior") or 0.0) or 0.0)
        # SOFP may still have prior BS stock (opening equity) — that is valid comparative for SOFP
        first_period = prior_pl < 0.505 and prior_cf < 0.505
        return {
            "first_period": first_period,
            # Hide prior column on P&L / CF only when both lack prior activity
            "hide_comparative": first_period,
            "hide_comparative_pl_cf": first_period,
        }

    def _afg_bs_reclass_negative_cash(self, bs_roots):
        """Reclassify credit bank balances under Cash as Bank overdraft (liability).

        Petty cash / cash-on-hand credits stay on the cash line (posting review) and are
        flagged by validation — they are not assumed to be bank overdrafts.
        """
        if not bs_roots:
            return bs_roots
        by_key = {n.get("type_key"): n for n in bs_roots if n.get("type_key")}
        asset = by_key.get("asset")
        liability = by_key.get("liability")
        if not asset:
            return bs_roots
        cash = self._afg_l1_by_code([asset], "AFG_CASH") or self._afg_walk_find(
            [asset],
            lambda n: "cash and cash equivalent" in (
                (n.get("label") or "") + (n.get("afg_caption") or "")
            ).lower(),
        )
        if not cash:
            return bs_roots

        Account = self.env["account.account"].sudo()
        moved = []

        def _is_bank_overdraft_leaf(leaf):
            bal = float(leaf.get("current") or 0.0)
            if bal >= -0.505:
                return False
            aid = leaf.get("account_id")
            acc = Account.browse(int(aid)) if aid else Account.browse()
            name = (
                (leaf.get("label") or "")
                + " "
                + (leaf.get("ledger_caption") or "")
                + " "
                + ((acc.name or "") if acc else "")
            ).lower()
            code = ((acc.code or "") if acc else "").lower()
            ut = ((acc.user_type_id.name or "") if acc else "").lower()
            if "petty" in name or "cash on hand" in name or "cash in hand" in name:
                return False
            if "overdraft" in name or "overdraft" in ut:
                return True
            if "bank" in name or "bank" in ut or ("current asset" in ut and "bank" in name):
                return True
            # Liquidity / bank user types with credit balance
            if acc and getattr(acc.user_type_id, "type", None) == "liquidity" and "petty" not in name:
                if "bank" in name or "bank" in code or re.search(r"\bbank\b", ut):
                    return True
            return False

        def _extract(parent):
            kept = []
            for ch in list(parent.get("children") or []):
                if ch.get("children"):
                    _extract(ch)
                    if ch.get("children") or abs(float(ch.get("current") or 0.0)) > 0.005:
                        self._afg_refresh_branch_totals(ch)
                        kept.append(ch)
                    continue
                if _is_bank_overdraft_leaf(ch):
                    moved.append(ch)
                    continue
                kept.append(ch)
            parent["children"] = kept
            if kept:
                self._afg_refresh_branch_totals(parent)

        _extract(cash)
        if cash.get("children"):
            self._afg_refresh_branch_totals(cash)
        else:
            # empty cash group — leave zero shell for visibility
            cash["prior"] = 0.0
            cash["current"] = 0.0

        if moved:
            if not liability:
                meta = AFG_BS_COA_TYPES.get("liability") or {"label": "Liabilities", "sequence": 20}
                liability = self._afg_type_shell("bs", "liability", meta, [])
                by_key["liability"] = liability
                # insert before equity if possible
                out = []
                for n in bs_roots:
                    if n.get("type_key") == "equity" and liability not in out:
                        out.append(liability)
                    out.append(n)
                if liability not in out:
                    out.append(liability)
                bs_roots = out
                by_key = {n.get("type_key"): n for n in bs_roots if n.get("type_key")}
                liability = by_key.get("liability")
            od_children = []
            for leaf in moved:
                # Face assets already positive-scale; credit bank on face is negative under assets.
                # Liabilities face are negated from Odoo — present OD as positive liability.
                od = dict(leaf)
                od["id"] = "bs-bank-od-%s" % (leaf.get("id") or leaf.get("account_id") or id(leaf))
                od["label"] = _("Bank overdraft — %s") % (leaf.get("label") or _("Bank"))
                od["ledger_caption"] = od["label"]
                od["prior"] = abs(float(leaf.get("prior") or 0.0))
                od["current"] = abs(float(leaf.get("current") or 0.0))
                od["co_prior"] = [od["prior"]]
                od["co_curr"] = [od["current"]]
                od_children.append(od)
            group = {
                "id": "bs-bank-overdraft",
                "label": _("Bank overdraft"),
                "afg_caption": _("Bank overdraft"),
                "level": 1,
                "kind": "group",
                "children": od_children,
                "prior": sum(float(c.get("prior") or 0.0) for c in od_children),
                "current": sum(float(c.get("current") or 0.0) for c in od_children),
            }
            group["co_prior"] = [group["prior"]]
            group["co_curr"] = [group["current"]]
            kids = list(liability.get("children") or [])
            kids.append(group)
            liability["children"] = kids
            self._afg_refresh_branch_totals(liability)

        # Refresh asset / computed totals
        if asset.get("children"):
            self._afg_refresh_branch_totals(asset)
        return self._afg_refresh_bs_type_shells(bs_roots)

    def _afg_validation_checks(self, face_sections, schedules, tb_payload, comparative=None):
        """PASS/FAIL/WARN cross-checks for management packs (not an audit).

        Signed face amounts are compared directly — opposite signs do not PASS via abs().
        Print-depth SOFP is also checked so dashboard PASS cannot disagree with L1 PDF.
        """
        self.ensure_one()
        checks = []
        tol = 0.505
        curr = self.currency_id.name or "AED"
        comparative = comparative or {}

        def _add(name, status, detail):
            st = (status or "FAIL").upper()
            if st not in ("PASS", "FAIL", "WARN"):
                st = "FAIL" if not status else "PASS"
            checks.append({
                "name": name,
                "status": st,
                "ok": st == "PASS",
                "detail": detail or "",
            })

        def _signed_ok(a, b):
            return abs(float(a or 0.0) - float(b or 0.0)) <= tol

        # A. Revenue − Expenses = Profit for the Year
        sales = self._afg_type_by_key(face_sections.get("pl") or [], "sales")
        cost = self._afg_type_by_key(face_sections.get("pl") or [], "cost_of_revenue")
        exp = self._afg_type_by_key(face_sections.get("pl") or [], "expenses")
        pl_net = self._afg_type_by_key(face_sections.get("pl") or [], "net_profit")
        s_c = float((sales or {}).get("current") or 0.0)
        c_c = float((cost or {}).get("current") or 0.0)
        e_c = float((exp or {}).get("current") or 0.0)
        expected_profit = s_c - c_c - e_c
        shown_profit = float((pl_net or {}).get("current") or 0.0)
        profit_arith_ok = _signed_ok(expected_profit, shown_profit)
        _add(
            _("Revenue - Expenses = Profit for the Year"),
            "PASS" if profit_arith_ok else "FAIL",
            _("Revenue %(s).2f − Cost %(c).2f − Expenses %(e).2f = %(x).2f; shown Profit %(p).2f")
            % {"s": s_c, "c": c_c, "e": e_c, "x": expected_profit, "p": shown_profit},
        )

        ok_bs, a_amt, e_amt, bs_diff = self._afg_bs_balance_check(face_sections.get("bs") or [])
        _add(
            _("Assets = Equity + Liabilities"),
            "PASS" if ok_bs else "FAIL",
            _("Assets %(a).2f %(c)s vs Equity+Liabilities %(e).2f %(c)s (diff %(d).2f)")
            % {"a": a_amt, "e": e_amt, "d": bs_diff, "c": curr},
        )

        # Print-depth SOFP (L1 Official filter) must match the same equation — both years
        pack = self._afg_global_report_pack_pref()
        print_bs = self._afg_bs_print_tree(face_sections.get("bs") or [], self._afg_tree_depth_for_pack(pack))
        ok_print, pa, pe, pdiff = self._afg_bs_balance_check(print_bs)
        _add(
            _("Printed SOFP Assets = Equity + Liabilities"),
            "PASS" if ok_print else "FAIL",
            _("Print Assets %(a).2f vs Equity+Liabilities %(e).2f (diff %(d).2f) at report depth L%(p)s")
            % {"a": pa, "e": pe, "d": pdiff, "p": int(pack)},
        )
        by_print = {n.get("type_key"): n for n in (print_bs or []) if n.get("type_key")}
        p_assets = by_print.get("total_assets") or by_print.get("asset")
        p_tel = by_print.get("total_equity_liabilities")
        if p_assets and p_tel:
            ap = float(p_assets.get("prior") or 0.0)
            ep = float(p_tel.get("prior") or 0.0)
            pdiff_pri = ap - ep
            ok_pri = abs(pdiff_pri) <= tol
            _add(
                _("Printed SOFP prior year Assets = Equity + Liabilities"),
                "PASS" if ok_pri else "FAIL",
                _("Print prior Assets %(a).2f vs Equity+Liabilities %(e).2f (diff %(d).2f)")
                % {"a": ap, "e": ep, "d": pdiff_pri},
            )

        cy = None
        for n in face_sections.get("bs") or []:
            if n.get("type_key") == "equity":
                cy = self._afg_find_cy_pnl_node(n.get("children") or [])
                break
        pl_c = shown_profit if abs(shown_profit) >= tol else expected_profit
        cy_c = float((cy or {}).get("current") or 0.0)
        profit_ok = _signed_ok(pl_c, cy_c)
        _add(
            _("Profit agrees to Statement of Changes / SOFP"),
            "PASS" if profit_ok else "FAIL",
            _("P&L profit %(p).2f vs SOFP Profit for the Year %(c).2f")
            % {"p": pl_c, "c": cy_c},
        )

        soce = (schedules or {}).get("equity_statement") or {}
        soce_close = None
        soce_profit = None
        for row in soce.get("rows") or []:
            if (row.get("key") or "") == "closing":
                soce_close = float((row.get("total") or {}).get("current") or row.get("total_current") or 0.0)
            if (row.get("key") or "") == "profit":
                soce_profit = float((row.get("total") or {}).get("current") or 0.0)
        eq_node = self._afg_type_by_key(face_sections.get("bs") or [], "equity")
        bs_eq = float((eq_node or {}).get("current") or 0.0)
        if soce.get("whole_units"):
            bs_eq = float(self._afg_round_amt(bs_eq) or 0.0)
            pl_c_cmp = float(self._afg_round_amt(pl_c) or 0.0)
        else:
            pl_c_cmp = pl_c
        if soce_close is None:
            _add(
                _("SOCE closing agrees to SOFP equity"),
                "WARN",
                _("Statement of Changes in Equity not built"),
            )
        else:
            soce_ok = _signed_ok(soce_close, bs_eq)
            _add(
                _("SOCE closing agrees to SOFP equity"),
                "PASS" if soce_ok else "FAIL",
                _("SOCE closing %(s).2f vs SOFP equity %(e).2f")
                % {"s": soce_close, "e": bs_eq},
            )
        if soce_profit is not None and abs(pl_c) >= tol:
            soce_pl_ok = _signed_ok(soce_profit, pl_c_cmp)
            _add(
                _("SOCE profit/(loss) agrees to P&L"),
                "PASS" if soce_pl_ok else "FAIL",
                _("SOCE movement %(s).2f vs P&L profit %(p).2f")
                % {"s": soce_profit, "p": pl_c_cmp},
            )
        # Opening + Profit + Drawings (+ Capital) - Transfers = Closing
        soce_open = soce_draw = soce_cap = soce_xfer = None
        for row in soce.get("rows") or []:
            key = row.get("key") or ""
            tot_c = float((row.get("total") or {}).get("current") or 0.0)
            if key == "opening":
                soce_open = tot_c
            elif key == "drawings":
                soce_draw = tot_c
            elif key == "capital":
                soce_cap = tot_c
            elif key == "transfers":
                soce_xfer = tot_c
        if soce_open is not None and soce_close is not None:
            move_sum = (
                float(soce_open)
                + float(soce_profit or 0.0)
                + float(soce_draw or 0.0)
                + float(soce_cap or 0.0)
                + float(soce_xfer or 0.0)
            )
            roll_ok = _signed_ok(move_sum, soce_close)
            _add(
                _("SOCE opening + movements = closing"),
                "PASS" if roll_ok else "FAIL",
                _("Opening+moves %(m).2f vs Closing %(c).2f (transfers %(t).2f)")
                % {"m": move_sum, "c": float(soce_close), "t": float(soce_xfer or 0.0)},
            )
            # Prior-year roll-forward (comparative column)
            soce_open_p = soce_draw_p = soce_cap_p = soce_xfer_p = soce_profit_p = soce_close_p = None
            for row in soce.get("rows") or []:
                key = row.get("key") or ""
                tot_p = float((row.get("total") or {}).get("prior") or 0.0)
                if key == "opening":
                    soce_open_p = tot_p
                elif key == "drawings":
                    soce_draw_p = tot_p
                elif key == "capital":
                    soce_cap_p = tot_p
                elif key == "transfers":
                    soce_xfer_p = tot_p
                elif key == "profit":
                    soce_profit_p = tot_p
                elif key == "closing":
                    soce_close_p = tot_p
            if soce_open_p is not None and soce_close_p is not None:
                move_p = (
                    float(soce_open_p)
                    + float(soce_profit_p or 0.0)
                    + float(soce_draw_p or 0.0)
                    + float(soce_cap_p or 0.0)
                    + float(soce_xfer_p or 0.0)
                )
                roll_p_ok = _signed_ok(move_p, soce_close_p)
                _add(
                    _("SOCE prior-year opening + movements = closing"),
                    "PASS" if roll_p_ok else "FAIL",
                    _("Prior Opening+moves %(m).2f vs Closing %(c).2f")
                    % {"m": move_p, "c": float(soce_close_p)},
                )
            if soce.get("drawings_from_re_ledger") or soce_draw is not None:
                # Drawings must track Retained Earnings / Accumulated Losses ledger Δ
                # (whole-unit print may absorb ≤ AED 2 into drawings to match SOFP equity)
                re_delta = float(soce.get("drawings_re_delta_current") or 0.0)
                draw_c = float(soce_draw or 0.0)
                led_tol = 2.005 if soce.get("whole_units") else max(tol, 1.005)
                led_ok = (
                    abs(draw_c) < tol
                    or abs(draw_c - re_delta) <= led_tol
                    or abs(abs(draw_c) - abs(re_delta)) <= led_tol
                )
                _add(
                    _("SOCE drawings supported by equity ledger"),
                    "PASS" if led_ok else "FAIL",
                    _("Drawings %(d).2f vs Retained Earnings / Accumulated Losses movement %(r).2f")
                    % {"d": draw_c, "r": re_delta},
                )
            if soce_xfer is not None and abs(float(soce_xfer)) >= tol:
                _add(
                    _("SOCE has no artificial Other Transfers"),
                    "FAIL",
                    _("Other Transfers %(t).2f present — classify as Drawings or supported equity movement")
                    % {"t": float(soce_xfer)},
                )
            else:
                _add(
                    _("SOCE has no artificial Other Transfers"),
                    "PASS",
                    _("No Other Transfers row"),
                )

        cf = (schedules or {}).get("cashflow_statement") or {}
        cf_rows = cf.get("rows") or []
        cf_close = None
        cf_delta = None
        for row in cf_rows:
            lab = (row.get("label") or "").lower()
            if "net increase" in lab or "net decrease" in lab:
                cf_delta = row.get("current")
            if "cash and cash equivalents at 31 december" in lab or (
                "cash and cash equivalents at" in lab and "1 january" not in lab
            ):
                cf_close = row.get("current")
        cash_node = self._afg_l1_by_code(face_sections.get("bs") or [], "AFG_CASH")
        bs_cash = float((cash_node or {}).get("current") or 0.0)
        bs_cash_p = float((cash_node or {}).get("prior") or 0.0)
        if cf_close is None:
            _add(
                _("Closing cash agrees to Cash Flow"),
                "WARN",
                _("Cash flow closing line not built"),
            )
        else:
            cash_ok = abs(float(cf_close or 0.0) - bs_cash) <= tol
            _add(
                _("Closing cash agrees to Cash Flow"),
                "PASS" if cash_ok else "FAIL",
                _("SOFP cash %(b).2f vs Cash Flow closing %(c).2f")
                % {"b": bs_cash, "c": float(cf_close or 0.0)},
            )
        if cf_delta is not None:
            expected = bs_cash - bs_cash_p
            delta_ok = abs(float(cf_delta or 0.0) - expected) <= tol
            _add(
                _("Cash flow movement agrees to SOFP cash change"),
                "PASS" if delta_ok else "FAIL",
                _("CF net change %(d).2f vs SOFP cash movement %(e).2f")
                % {"d": float(cf_delta or 0.0), "e": expected},
            )
        if cf.get("financing_balanced"):
            _add(
                _("Cash flow financing fully explained"),
                "WARN",
                _("Residual financing plug %(p).2f still present — review capital / loans / drawings")
                % {"p": float(cf.get("financing_plug") or 0.0)},
            )
        else:
            _add(
                _("Cash flow financing fully explained"),
                "PASS",
                _("Financing movements reconcile without residual plug"),
            )

        far = (schedules or {}).get("fixed_assets_recon") or {}
        fa_charge = float((far.get("totals") or {}).get("charge") or 0.0)
        fa_nbv = float((far.get("totals") or {}).get("nbv_current") or 0.0)
        depr = self._afg_l1_by_code(face_sections.get("pl") or [], "AFG_DEPR_PL")
        pl_depr = abs(float((depr or {}).get("current") or 0.0))
        if abs(fa_charge) < tol and abs(pl_depr) < tol:
            _add(
                _("Depreciation agrees to Fixed Asset Schedule"),
                "PASS",
                _("No depreciation / PPE charge in period"),
            )
        else:
            dep_ok = abs(fa_charge - pl_depr) <= tol
            _add(
                _("Depreciation agrees to Fixed Asset Schedule"),
                "PASS" if dep_ok else "FAIL",
                _("P&L depreciation %(p).2f vs PPE charge %(f).2f")
                % {"p": pl_depr, "f": fa_charge},
            )
        ppe_node = self._afg_l1_by_code(face_sections.get("bs") or [], "AFG_PPE")
        far = (schedules or {}).get("fixed_assets_recon") or {}
        fa_nbv = float((far.get("totals") or {}).get("nbv_current") or 0.0)
        fa_nbv_p = float((far.get("totals") or {}).get("nbv_prior") or 0.0)
        if ppe_node and abs(fa_nbv) >= tol:
            bs_ppe = abs(float(ppe_node.get("current") or 0.0))
            nbv_ok = abs(fa_nbv - bs_ppe) <= tol
            _add(
                _("PPE net book value agrees to SOFP"),
                "PASS" if nbv_ok else "FAIL",
                _("PPE schedule NBV %(n).2f vs SOFP PPE %(b).2f")
                % {"n": fa_nbv, "b": bs_ppe},
            )
            bs_ppe_p = abs(float(ppe_node.get("prior") or 0.0))
            if abs(fa_nbv_p) >= tol or abs(bs_ppe_p) >= tol:
                nbv_p_ok = abs(fa_nbv_p - bs_ppe_p) <= tol
                _add(
                    _("PPE prior NBV agrees to SOFP prior"),
                    "PASS" if nbv_p_ok else "FAIL",
                    _("PPE schedule prior NBV %(n).2f vs SOFP prior PPE %(b).2f")
                    % {"n": fa_nbv_p, "b": bs_ppe_p},
                )
        elif not ppe_node and not far.get("items"):
            _add(
                _("PPE net book value agrees to SOFP"),
                "PASS",
                _("No PPE mapped — Property, Plant and Equipment note/schedule omitted"),
            )
        elif not ppe_node:
            _add(
                _("PPE net book value agrees to SOFP"),
                "WARN",
                _("PPE schedule has items but AFG_PPE is not mapped on Statement of Financial Position"),
            )

        tb_ok = bool((tb_payload or {}).get("balance_ok"))
        tb_diff = float((tb_payload or {}).get("balance_diff") or 0.0)
        _add(
            _("Trial Balance agrees (net nil)"),
            "PASS" if tb_ok else "FAIL",
            _("TB net difference %(d).2f %(c)s") % {"d": tb_diff, "c": curr},
        )

        # F. FS = TB (+ visible unmapped/adjustments)
        recon = (schedules or {}).get("fs_tb_reconciliation") or self._afg_fs_tb_reconciliation(
            face_sections, tb_payload
        )
        recon_ok = bool(recon.get("ok"))
        bad = [r for r in (recon.get("rows") or []) if not r.get("ok")]
        gap_n = len(recon.get("ledger_gaps") or [])
        _add(
            _("Financial Statements reconcile to Trial Balance"),
            "PASS" if recon_ok else "FAIL",
            _("TB vs FS gaps: %(n)s type(s); unmapped ledgers on FS: %(g)s")
            % {"n": len(bad), "g": gap_n}
            if not recon_ok else _("Financial Statements agree to Trial Balance (no type gaps)"),
        )

        # G. Current opening = prior closing (cash + equity stock)
        open_ok = True
        open_detail = []
        if cash_node is not None:
            # prior column on current statement = closing of prior year
            # Compare CF opening line if present
            cf_open = None
            for row in cf_rows:
                lab = (row.get("label") or "").lower()
                if "1 january" in lab or "at the beginning" in lab:
                    cf_open = row.get("current")
                    break
            if cf_open is not None and abs(float(cf_open or 0.0) - bs_cash_p) > tol:
                open_ok = False
                open_detail.append(
                    _("Cash opening %(o).2f vs SOFP prior %(p).2f")
                    % {"o": float(cf_open or 0.0), "p": bs_cash_p}
                )
        soce_open = None
        for row in soce.get("rows") or []:
            if (row.get("key") or "") == "opening":
                soce_open = float((row.get("total") or {}).get("current") or 0.0)
                break
        # Prior-year equity face ≈ opening of current for SOCE (signed)
        bs_eq_prior = float((eq_node or {}).get("prior") or 0.0)
        if soce_open is not None and abs(soce_open) > tol and not _signed_ok(soce_open, bs_eq_prior):
            open_ok = False
            open_detail.append(
                _("SOCE opening %(o).2f vs SOFP equity prior %(p).2f")
                % {"o": soce_open, "p": bs_eq_prior}
            )
        _add(
            _("Opening balances agree to prior-year closing"),
            "PASS" if open_ok else "FAIL",
            "; ".join(open_detail) if open_detail else _("Cash / equity opening ties to prior closing"),
        )

        # Negative cash & cash equivalents (petty cash credits = posting review, not OD)
        if cash_node is not None and bs_cash < -tol:
            _add(
                _("Cash and cash equivalents not overdrawn"),
                "WARN",
                _(
                    "Cash and cash equivalents is %(b).2f %(c)s. "
                    "Confirm whether this is incorrect cash posting or a bank overdraft "
                    "(bank overdrafts should be presented under current liabilities)."
                )
                % {"b": bs_cash, "c": curr},
            )

        overall = "PASS"
        if any(c.get("status") == "FAIL" for c in checks):
            overall = "FAIL"
        elif any(c.get("status") == "WARN" for c in checks):
            overall = "WARN"
        for c in checks:
            c["overall"] = overall
            c["banner"] = (
                _("FINANCIAL STATEMENTS NOT RECONCILED")
                if overall == "FAIL" else ""
            )
        return checks

    def _afg_ppe_matrix_from_recon(self, far):
        """Sample-style PPE: one COST/Dep/NBV set per year (Samurai layout × 2 years)."""
        # Match dashboard: drop blank / all-zero ghost columns (gap before Total)
        _ppe_keys = (
            "cost_prior", "cost_current", "additions", "disposals",
            "dep_prior", "dep_current", "charge", "dep_disposals",
            "nbv_prior", "nbv_current",
        )

        def _ppe_item_visible(it):
            nm = str((it or {}).get("name") or "").strip()
            if not nm or nm == "-" or nm.lower() in ("total", "amount"):
                return False
            for k in _ppe_keys:
                try:
                    if abs(float((it or {}).get(k) or 0.0)) > 1e-9:
                        return True
                except (TypeError, ValueError):
                    continue
            return False

        items = [it for it in list(far.get("items") or []) if _ppe_item_visible(it)]
        yp = far.get("year_prior") or self.year_prior
        yc = far.get("year_current") or self.year_current
        curr = far.get("currency") or (self.currency_id.name or "AED")
        cats = [it.get("name") or "" for it in items]
        n_cat = len(items)
        # Recompute totals from visible columns so Total matches headers
        totals = {
            k: float(sum(float(it.get(k) or 0.0) for it in items))
            for k in _ppe_keys
        }

        def _vals(key):
            if key is None:
                return [None] * n_cat, None
            values = [float(it.get(key) or 0.0) for it in items]
            total = float(totals.get(key) if key in totals else sum(values))
            return values, total

        def row(label, key=None, values=None, total=None, is_total=False):
            if values is None and key is not None:
                values, total = _vals(key)
            elif values is None and key is None:
                values, total = [None] * n_cat, None
            return {
                "label": label,
                "values": values if values is not None else [],
                "total": total,
                "is_total": bool(is_total),
            }

        def blocks_for_schedule(sched):
            keys = sched.get("keys") or {}
            y_open = sched.get("opening_year")
            y_close = sched.get("closing_year")
            return [
                {
                    "title": _("COST (%s)") % curr,
                    "rows": [
                        row(_("Opening cost"), keys.get("cost_open"), is_total=True),
                        row(_("Additions"), keys.get("cost_move")),
                        row(_("Disposals"), keys.get("cost_disp")),
                        row(_("Closing cost"), keys.get("cost_close"), is_total=True),
                    ],
                },
                {
                    "title": _("ACCUMULATED DEPRECIATION (%s)") % curr,
                    "rows": [
                        row(_("Opening accumulated depreciation"), keys.get("dep_open"), is_total=True),
                        row(_("Charge for the year"), keys.get("dep_move")),
                        row(_("Disposals"), keys.get("dep_disp")),
                        row(_("Closing accumulated depreciation"), keys.get("dep_close"), is_total=True),
                    ],
                },
                {
                    "title": _("NET BOOK VALUE (%s)") % curr,
                    "rows": [
                        row(_("Closing net book value"), keys.get("nbv_close"), is_total=True),
                        row(_("Opening net book value"), keys.get("nbv_open"), is_total=True),
                    ],
                },
            ]

        schedules = list(far.get("year_schedules") or [])
        if not schedules:
            # Legacy single-block fallback (prior→current in one set)
            schedules = [{
                "year": yc,
                "title": _("Property, Plant and Equipment — Year %s") % yc,
                "opening_year": yp,
                "closing_year": yc,
                "keys": {
                    "cost_open": "cost_prior",
                    "cost_move": "additions",
                    "cost_disp": "disposals",
                    "cost_close": "cost_current",
                    "dep_open": "dep_prior",
                    "dep_move": "charge",
                    "dep_disp": "dep_disposals",
                    "dep_close": "dep_current",
                    "nbv_close": "nbv_current",
                    "nbv_open": "nbv_prior",
                },
            }]
        else:
            # Ensure disposal keys exist on schedule maps
            for sched in schedules:
                keys = dict(sched.get("keys") or {})
                keys.setdefault("cost_disp", "disposals")
                keys.setdefault("dep_disp", "dep_disposals")
                sched["keys"] = keys
            # Deduplicate identical year labels (1y sets year_prior==year_current)
            seen_years = set()
            deduped = []
            for sched in schedules:
                yk = str(sched.get("year") or "")
                if yk in seen_years:
                    continue
                seen_years.add(yk)
                deduped.append(sched)
            # Prefer the schedule that has opening keys when duplicates were collapsed
            if len(deduped) < len(schedules) and schedules:
                # Keep last occurrence per year (current-year block has openings)
                by_year = {}
                for sched in schedules:
                    by_year[str(sched.get("year") or "")] = sched
                deduped = list(by_year.values())
            schedules = deduped
            if far.get("single_year") or int(yp or 0) == int(yc or 0):
                schedules = [s for s in schedules if str(s.get("year")) == str(yc)] or schedules[-1:]

        year_sections = []
        flat_blocks = []
        for sched in schedules:
            blocks = blocks_for_schedule(sched)
            year_sections.append({
                "year": sched.get("year"),
                "title": sched.get("title") or "",
                "blocks": blocks,
            })
            # Section heading as a pseudo-block title for Excel/Word that only loop blocks
            flat_blocks.append({
                "title": sched.get("title") or _("Year %s") % sched.get("year"),
                "rows": [],
                "is_section": True,
            })
            flat_blocks.extend(blocks)

        return {
            "categories": cats,
            "currency": curr,
            "year_prior": yp,
            "year_current": yc,
            "year_sections": year_sections,
            "blocks": flat_blocks,
            "header": self._afg_print_header(
                _("Property, Plant and Equipment Reconciliation"), yp, yc
            ),
        }

    def _afg_build_print_chapters(self, payload=None):
        """Audited print chapters shared by Excel / Word / PDF (one chapter = one sheet/page)."""
        self.ensure_one()
        payload = payload or self._get_audit_report_payload()
        max_level = self._afg_export_max_level()
        cover = payload.get("cover") or {}
        ver = payload.get("version") or {}
        yp = ver.get("year_prior") or self.year_prior
        yc = ver.get("year_current") or self.year_current
        chapters = []

        def _append_tb_chapter():
            """Trial Balance chapter — prefer AFG-style TB2 (same fold levels as SOFP)."""
            tb = payload.get("trial_balance2") or payload.get("trial_balance") or {}
            panels = tb.get("panels") or []
            if panels:
                panel_trees = []
                for panel in panels:
                    trees = []
                    for root in panel.get("roots") or []:
                        if root.get("is_tb_section_total"):
                            continue
                        tree = self._afg_filter_tree_by_max_level([root], max_level)
                        trees.extend(self._afg_round_tree_amounts(tree))
                    panel_trees.append((panel, trees))

                def _panel_section_total(trees, field):
                    tops = [r for r in trees if int(r.get("level") or 0) == 0 and not r.get("is_tb_section_total")]
                    return sum(abs(float(r.get(field) or 0.0)) for r in tops)

                if len(panel_trees) >= 2:
                    for field in ("prior", "current"):
                        t0 = _panel_section_total(panel_trees[0][1], field)
                        t1 = _panel_section_total(panel_trees[1][1], field)
                        diff = t0 - t1
                        if abs(diff) >= 0.5 and panel_trees[1][1]:
                            leaf = panel_trees[1][1][-1]
                            while leaf.get("children"):
                                leaf = leaf["children"][-1]
                            signed_t1 = sum(
                                float(r.get(field) or 0.0)
                                for r in panel_trees[1][1]
                                if int(r.get("level") or 0) == 0
                            )
                            target = -t0 if signed_t1 <= 0 else t0
                            delta = target - signed_t1
                            leaf[field] = float(leaf.get(field) or 0.0) + float(delta)
                            panel_trees[1] = (
                                panel_trees[1][0],
                                self._afg_reroll_tree_sums(panel_trees[1][1]),
                            )

                tb_rows = []
                for panel, trees in panel_trees:
                    tb_rows.append({
                        "lg": "",
                        "label": self._afg_proper_case(panel.get("title") or ""),
                        "label_raw": self._afg_proper_case(panel.get("title") or ""),
                        "prior": None,
                        "current": None,
                        "prior_disp": "—",
                        "current_disp": "—",
                        "tb_amounts": None,
                        "level": 0,
                        "bold": True,
                        "is_total": False,
                        "is_section_banner": True,
                    })
                    for tree_root in trees:
                        tb_rows.extend(
                            self._afg_flatten_tree_for_export([tree_root], max_level=max_level)
                        )
                if tb_rows:
                    title = self._afg_proper_case(_("Trial Balance"))
                    tb_meta = self._tb_period_column_meta()
                    tb_cols = self._tb_period_column_labels_flat()
                    chapters.append({
                        "key": "tb",
                        "title": title,
                        "kind": "tb_face",
                        "tb_columns": tb_cols,
                        "tb_column_meta": tb_meta,
                        "col_prior": str(yp),
                        "col_current": str(yc),
                        "rows": tb_rows,
                        "header": self._afg_print_header(title, yp, yc),
                    })
                    return True
            elif tb.get("roots"):
                title = self._afg_proper_case(_("Trial Balance"))
                tree = self._afg_filter_tree_by_max_level(tb.get("roots") or [], max_level)
                tree = self._afg_round_tree_amounts(tree)
                chapters.append({
                    "key": "tb",
                    "title": title,
                    "kind": "tb_face",
                    "tb_columns": self._tb_period_column_labels_flat(),
                    "tb_column_meta": self._tb_period_column_meta(),
                    "col_prior": str(yp),
                    "col_current": str(yc),
                    "rows": self._afg_flatten_tree_for_export(tree, max_level=max_level),
                    "header": self._afg_print_header(title, yp, yc),
                })
                return True
            return False

        tb_appended = False
        period_windows = self._afg_resolve_period_windows()
        period_labels = [w.get("label") or "" for w in period_windows]
        period_span = self._afg_global_period_span_pref()
        fta_ch = self._afg_fta_print_chapter_dict(
            payload, yp, yc, True, period_labels, period_span,
        )
        if fta_ch:
            chapters.append(fta_ch)
        for sec in payload.get("sections") or []:
            if (sec.get("key") or "") == "fta":
                continue
            tree = sec.get("tree") or []
            if (sec.get("key") or "") == "bs":
                tree = self._afg_bs_present_equity_components(tree)
            tree = self._afg_filter_tree_by_max_level(tree, max_level)
            tree = self._afg_round_tree_amounts(tree)
            if (sec.get("key") or "") == "bs":
                tree = self._afg_balance_bs_tree_after_round(tree)
            rows = self._afg_flatten_tree_for_export(tree, max_level=max_level)
            sec_key = sec.get("key") or ""
            if not rows and sec_key in ("pl", "bs"):
                rows = self.with_context(afg_fta_print=True)._afg_flatten_tree_for_export(
                    tree, max_level=max(4, int(max_level or 0))
                )
            if not rows and sec_key not in ("pl", "bs"):
                continue
            title = self._afg_proper_case(sec.get("title") or sec.get("key") or "")
            rows = self._afg_ensure_print_period_disp(rows, period_labels)
            if (sec.get("key") or "") in ("bs", "pl"):
                rows = self._afg_force_statement_total_print_amounts(rows, period_labels)
            col_p = period_labels[0] if period_labels else str(yp)
            col_c = period_labels[-1] if period_labels else str(yc)
            as_at = (sec.get("key") or "") == "bs"
            chapters.append({
                "key": sec.get("key") or "sec",
                "title": title,
                "kind": "statement",
                "col_prior": col_p,
                "col_current": col_c,
                "period_labels": list(period_labels),
                "period_span": period_span,
                "rows": rows,
                "header": self._afg_print_header(title, yp, yc, as_at=as_at),
            })
            # Trial Balance directly under Statement of Financial Position (every PDF/Excel/Word)
            if (sec.get("key") or "") == "bs" and not tb_appended:
                tb_appended = _append_tb_chapter()

        if not tb_appended:
            _append_tb_chapter()

        schedules = payload.get("schedules") or {}
        cf = schedules.get("cashflow_statement") or {}
        if cf.get("rows") and max_level >= 0:
            cf_rows = []
            for crow in cf.get("rows") or []:
                kind = crow.get("kind") or "ledger"
                if kind == "section":
                    lvl, lg = 0, "L0"
                elif kind == "group":
                    lvl, lg = 2, "L2"
                else:
                    lvl, lg = 3, "L3"
                if lvl > max_level:
                    continue
                # Depth 4: AFG+ledgers only — skip cashflow group header rows
                if max_level >= 4 and kind == "group":
                    continue
                lab = crow.get("label") or ""
                if kind != "ledger":
                    lab = self._afg_proper_case(lab)
                else:
                    lab = self._afg_proper_case(lab) if lab.isupper() else lab
                prior = crow.get("prior")
                current = crow.get("current")
                if prior is not None:
                    prior = float(self._afg_round_amt(prior))
                if current is not None:
                    current = float(self._afg_round_amt(current))
                cf_rows.append({
                    "lg": lg,
                    "label": lab,
                    "label_raw": lab,
                    "prior": prior,
                    "current": current,
                    "prior_disp": "" if prior is None else self._afg_fmt_amt(prior),
                    "current_disp": "" if current is None else self._afg_fmt_amt(current),
                    "level": lvl,
                    "bold": kind in ("section", "group"),
                    "is_total": kind == "group",
                    "remark": crow.get("remark") or "",
                })
            # Re-balance cashflow group totals from nearby ledger lines when possible:
            # group rows already carry totals from payload — keep rounded values as-is.
            title = self._afg_proper_case(_("Statement of Cash Flows"))
            chapters.append({
                "key": "cashflow",
                "title": title,
                "kind": "cashflow",
                "col_prior": str(cf.get("year_prior") or yp),
                "col_current": str(cf.get("year_current") or yc),
                "rows": cf_rows,
                "header": self._afg_print_header(
                    title, cf.get("year_prior") or yp, cf.get("year_current") or yc
                ),
            })

        far = schedules.get("fixed_assets_recon") or {}
        if far.get("items"):
            period_span = self._afg_global_period_span_pref()
            single_period = (
                str(period_span or "").strip().lower() in ("1y", "1m")
                or int(yp or 0) == int(yc or 0)
                or bool(payload.get("hide_comparative"))
            )
            far_use = dict(far)
            if single_period:
                far_use["single_year"] = True
                ysched = list(far_use.get("year_schedules") or [])
                if len(ysched) > 1:
                    far_use["year_schedules"] = [
                        s for s in ysched if str(s.get("year")) == str(yc)
                    ] or ysched[-1:]
            matrix = self.with_context(
                afg_ppe_single_year=single_period
            )._afg_round_ppe_matrix(self._afg_ppe_matrix_from_recon(far_use))
            ppe_title = self._afg_proper_case(_("Property, Plant and Equipment Reconciliation"))
            chapters.append({
                "key": "fixed_assets",
                "title": ppe_title,
                "kind": "ppe_matrix",
                "col_prior": "" if single_period else str(matrix.get("year_prior") or yp),
                "col_current": str(matrix.get("year_current") or yc),
                "hide_comparative": single_period,
                "ppe": matrix,
                "header": self._afg_print_header(
                    ppe_title, None if single_period else yp, yc
                ),
            })

        notes = self._afg_resolve_statement_notes(payload.get("notes") or [])
        if notes:
            title = self._afg_proper_case(_("Notes to the Financial Statements"))
            chapters.append({
                "key": "notes",
                "title": title,
                "kind": "notes",
                "notes": notes,
                "header": self._afg_print_header(title, yp, yc),
            })

        chapters = self._afg_apply_years_order_to_chapters(chapters)
        chapters = self._afg_filter_empty_print_chapters(chapters)
        cover = dict(cover or {})
        cover["entity"] = self._afg_print_company_display()
        if self._afg_print_scope() != "fta" and not any((c.get("key") or "") == "cover" for c in (chapters or [])):
            chapters = self._afg_prepend_cover_print_chapter(cover, chapters, yp, yc)
        chapters = self._afg_filter_print_scope_chapters(chapters)
        chapters = self._afg_apply_print_page_include(chapters)
        chapters = self._afg_apply_statutory_face(chapters)
        flags = self._afg_print_page_setup_flags()

        return {
            "cover": cover,
            "year_prior": yp,
            "year_current": yc,
            "currency": cover.get("currency") or (self.currency_id.name or "AED"),
            "chapters": chapters,
            "alerts": payload.get("alerts") or [],
            "signatory": dict(
                self._afg_signatory_block(),
                for_line="",
                entity="",
                signatory_label="(Managing Director)",
            ),
            "signatory_label": "(Managing Director)",
            "years_descending": self._afg_years_descending(),
            "print_page_setup": flags.get("print_page_setup") or "default",
            "compact_hf": bool(flags.get("compact_hf")),
            "skip_empty_pages": bool(flags.get("skip_empty_pages")),
            "sign_last_only": bool(flags.get("sign_last_only")),
            "margin_header": int(flags.get("margin_header") or 10),
            "margin_footer": int(flags.get("margin_footer") or 10),
            "sign_gap_pt": int(flags.get("sign_gap_pt") or 28),
        }

    def _afg_build_simple_print_chapters(self):
        """Fast L1 Financial Statements PDF: cover + face statements, no TB/FTA/ledgers."""
        self.ensure_one()
        self = self.with_context(afg_export_max_level=1, afg_simple_print=True)
        payload = self.with_context(
            afg_simple_print=True,
            afg_skip_hierarchy_rebuild=bool(self.line_ids),
            afg_export_max_level=1,
        )._get_audit_report_payload()
        max_level = 1
        cover = dict(payload.get("cover") or {})
        cover["title"] = _("Financial Statements")
        cover["disclaimer"] = _(
            "These financial statements have been prepared from the accounting records "
            "of the Company and the accounting policies adopted by management."
        )
        cover["entity"] = self._afg_print_company_display()
        ver = payload.get("version") or {}
        yp = ver.get("year_prior") or self.year_prior
        yc = ver.get("year_current") or self.year_current
        period_windows = self._afg_resolve_period_windows()
        period_labels = [w.get("label") or "" for w in period_windows]
        period_span = self._afg_global_period_span_pref()
        chapters = []
        wanted = ("pl", "bs")
        for sec in payload.get("sections") or []:
            key = sec.get("key") or ""
            if key not in wanted:
                continue
            tree = sec.get("tree") or []
            if key == "bs":
                tree = self._afg_bs_present_equity_components(tree)
            tree = self._afg_filter_tree_by_max_level(tree, max_level)
            tree = self._afg_round_tree_amounts(tree)
            if key == "bs":
                tree = self._afg_balance_bs_tree_after_round(tree)
            rows = self._afg_flatten_tree_for_export(tree, max_level=max_level)
            if not rows and key in ("pl", "bs"):
                rows = self.with_context(afg_fta_print=True)._afg_flatten_tree_for_export(
                    tree, max_level=4
                )
            if not rows and key not in ("pl", "bs"):
                continue
            title = self._afg_proper_case(sec.get("title") or key)
            rows = self._afg_ensure_print_period_disp(rows, period_labels)
            rows = self._afg_force_statement_total_print_amounts(rows, period_labels)
            col_p = period_labels[0] if period_labels else str(yp)
            col_c = period_labels[-1] if period_labels else str(yc)
            chapters.append({
                "key": key,
                "title": title,
                "kind": "statement",
                "col_prior": col_p,
                "col_current": col_c,
                "period_labels": list(period_labels),
                "period_span": period_span,
                "rows": rows,
                "header": self._afg_print_header(title, yp, yc, as_at=(key == "bs")),
            })

        schedules = payload.get("schedules") or {}
        cf = schedules.get("cashflow_statement") or {}
        if cf.get("rows"):
            cf_rows = []
            for crow in cf.get("rows") or []:
                kind = crow.get("kind") or "ledger"
                if kind == "ledger":
                    continue
                if kind == "section":
                    lvl, lg = 0, "L0"
                else:
                    lvl, lg = 1, "L1"
                lab = self._afg_proper_case(crow.get("label") or "")
                prior = crow.get("prior")
                current = crow.get("current")
                if prior is not None:
                    prior = float(self._afg_round_amt(prior))
                if current is not None:
                    current = float(self._afg_round_amt(current))
                cf_rows.append({
                    "lg": lg,
                    "label": lab,
                    "label_raw": lab,
                    "prior": prior,
                    "current": current,
                    "prior_disp": "" if prior is None else self._afg_fmt_amt(prior),
                    "current_disp": "" if current is None else self._afg_fmt_amt(current),
                    "level": lvl,
                    "bold": True,
                    "is_total": kind == "group",
                    "remark": crow.get("remark") or "",
                })
            if cf_rows:
                title = self._afg_proper_case(_("Statement of Cash Flows"))
                chapters.append({
                    "key": "cashflow",
                    "title": title,
                    "kind": "cashflow",
                    "col_prior": str(cf.get("year_prior") or yp),
                    "col_current": str(cf.get("year_current") or yc),
                    "rows": cf_rows,
                    "header": self._afg_print_header(
                        title, cf.get("year_prior") or yp, cf.get("year_current") or yc
                    ),
                })

        soce = schedules.get("equity_statement") or {}
        if soce.get("rows") or soce.get("columns"):
            title = self._afg_proper_case(_("Statement of Changes in Equity"))
            chapters.append({
                "key": "equity",
                "title": title,
                "kind": "equity_soce",
                "col_prior": str(soce.get("year_prior") or yp),
                "col_current": str(soce.get("year_current") or yc),
                "soce": soce,
                "hide_comparative": bool(payload.get("hide_comparative")),
                "header": self._afg_print_header(title, yp, yc),
            })
        else:
            for sec in payload.get("sections") or []:
                if (sec.get("key") or "") != "equity":
                    continue
                tree = self._afg_filter_tree_by_max_level(sec.get("tree") or [], max_level)
                tree = self._afg_round_tree_amounts(tree)
                rows = self._afg_flatten_tree_for_export(tree, max_level=max_level)
                if not rows:
                    continue
                title = self._afg_proper_case(sec.get("title") or _("Statement of Changes in Equity"))
                chapters.append({
                    "key": "equity",
                    "title": title,
                    "kind": "statement",
                    "col_prior": period_labels[0] if period_labels else str(yp),
                    "col_current": period_labels[-1] if period_labels else str(yc),
                    "period_labels": list(period_labels),
                    "rows": rows,
                    "header": self._afg_print_header(title, yp, yc),
                })

        far = schedules.get("fixed_assets_recon") or {}
        if far.get("items"):
            single_period = (
                str(period_span or "").strip().lower() in ("1y", "1m")
                or int(yp or 0) == int(yc or 0)
                or bool(payload.get("hide_comparative"))
            )
            far_use = dict(far)
            if single_period:
                far_use["single_year"] = True
                ysched = list(far_use.get("year_schedules") or [])
                if len(ysched) > 1:
                    far_use["year_schedules"] = [
                        s for s in ysched if str(s.get("year")) == str(yc)
                    ] or ysched[-1:]
            matrix = self.with_context(
                afg_ppe_single_year=single_period
            )._afg_round_ppe_matrix(self._afg_ppe_matrix_from_recon(far_use))
            ppe_title = self._afg_proper_case(_("Property, Plant and Equipment"))
            chapters.append({
                "key": "fixed_assets",
                "title": ppe_title,
                "kind": "ppe_matrix",
                "col_prior": "" if single_period else str(matrix.get("year_prior") or yp),
                "col_current": str(matrix.get("year_current") or yc),
                "hide_comparative": single_period,
                "ppe": matrix,
                "header": self._afg_print_header(
                    ppe_title, None if single_period else yp, yc
                ),
            })

        notes = self._afg_resolve_statement_notes(payload.get("notes") or [])
        if notes:
            title = self._afg_proper_case(_("Notes to the Financial Statements"))
            chapters.append({
                "key": "notes",
                "title": title,
                "kind": "notes",
                "notes": notes,
                "header": self._afg_print_header(title, yp, yc),
            })

        cover["entity"] = self._afg_print_company_display()
        chapters = self._afg_prepend_cover_print_chapter(cover, chapters, yp, yc)
        chapters = self._afg_apply_statutory_face(chapters)
        return {
            "cover": cover,
            "year_prior": yp,
            "year_current": yc,
            "currency": cover.get("currency") or (self.currency_id.name or "AED"),
            "chapters": chapters,
            "alerts": [],
            "signatory": dict(
                self._afg_signatory_block(),
                for_line="",
                entity="",
                signatory_label="(Managing Director)",
            ),
            "signatory_label": "(Managing Director)",
            "compact_hf": True,
            "skip_empty_pages": False,
            "sign_last_only": True,
            "margin_header": 8,
            "margin_footer": 8,
            "sign_gap_pt": 20,
        }

    def action_print_fta_pdf(self, max_level=None):
        """Corporate tax filing only — used from the CT view, not the audited pack."""
        self.ensure_one()
        self._afg_set_print_scope("fta")
        return self.action_print_audit_report_pdf(max_level)

    def action_print_afg_simple_pdf(self, max_level=None):
        """Quick Financial Statements PDF (L1 labels, dashboard amounts)."""
        self.ensure_one()
        self._afg_set_print_scope("audit")
        cids = [int(c) for c in (self._tb_company_ids() or []) if c]
        if cids:
            self.with_context(skip_afg_col_sync=True).write({
                "company_ids": [(6, 0, cids)],
                "report_column_company_ids": [(6, 0, cids)],
            })
        report = self.env.ref(
            "project_dashboard_odoo.action_report_afg_simple_fs_pdf",
            raise_if_not_found=False,
        )
        if not report:
            raise UserError(_("Simple Financial Statements print is not installed. Upgrade project_dashboard_odoo."))
        report_name = report.report_name or report.report_file
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/%s/%s" % (report_name, self.id),
            "target": "new",
        }

    def action_print_audit_report_pdf(self, max_level=None):
        """Open PDF in a new browser tab without replacing the AFG dashboard client action."""
        self.ensure_one()
        if self._afg_print_scope() != "fta":
            self._afg_set_print_scope("audit")
        pack = self._afg_resolve_export_report_pack(max_level)
        gate = self._afg_assert_l1_print_allowed(pack, export_kind="pdf")
        if gate:
            return gate
        cids = [int(c) for c in (self._tb_company_ids() or []) if c]
        if cids:
            self.with_context(skip_afg_col_sync=True).write({
                "company_ids": [(6, 0, cids)],
                "report_column_company_ids": [(6, 0, cids)],
            })
        self._afg_persist_print_options(pack)
        self._afg_sync_paperformat_margins()
        report = self.env.ref("project_dashboard_odoo.action_report_afg_audit_pdf")
        report_name = report.report_name or report.report_file
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/%s/%s" % (report_name, self.id),
            "target": "new",
        }

    def _afg_saved_print_dpi(self):
        raw = self.env["ir.config_parameter"].sudo().get_param("cpabooks_afg.print_dpi") or "90"
        try:
            dpi = int(self.env.context.get("afg_export_dpi") or raw)
        except (TypeError, ValueError):
            dpi = 90
        return max(50, min(160, dpi))

    @api.model
    def afg_set_print_dpi(self, dpi):
        """Store DPI and push it onto the AFG paperformat so the next PDF uses it."""
        try:
            dpi = int(dpi)
        except (TypeError, ValueError):
            dpi = 90
        dpi = max(50, min(160, dpi))
        self.env["ir.config_parameter"].sudo().set_param("cpabooks_afg.print_dpi", str(dpi))
        pf = self.env.ref(
            "project_dashboard_odoo.paperformat_afg_audit",
            raise_if_not_found=False,
        )
        if pf:
            pf.sudo().write({"dpi": dpi})
        return dpi

    @api.model
    def afg_get_print_dpi(self):
        return self._afg_saved_print_dpi()

    def _afg_export_dpi(self):
        return self._afg_saved_print_dpi()

    def _afg_dpi_pt(self, base):
        """90 dpi is the current PDF size. A higher dpi makes Word/Excel type smaller."""
        return max(7, int(round(float(base) * 90.0 / float(self._afg_export_dpi()))))

    def _afg_excel_face_bucket(self, acc):
        """Club one ledger into the statutory face line it feeds."""
        afg = ""
        if "afg_group_id" in acc._fields and acc.afg_group_id:
            afg = acc.afg_group_id.name or ""
        blob = " ".join([
            acc.name or "",
            afg,
            acc.group_id.name or "" if acc.group_id else "",
            acc.user_type_id.name or "" if acc.user_type_id else "",
        ]).lower()
        ig = acc.internal_group or ""
        ut = acc.user_type_id
        ut_type = (ut.type or "") if ut else ""
        ut_name = (ut.name or "").lower() if ut else ""
        ledger = (acc.name or "").lower()
        if ig == "income":
            if "other income" in ledger or ledger.strip().startswith("other"):
                return "PL", "Other Income"
            return "PL", "Net Revenue"
        if ig == "expense":
            if "corporate tax" in blob or "tax paid" in blob or "taxation" in blob:
                return "PL", "Corporate Tax Paid"
            if "depreci" in blob or "amort" in blob:
                return "PL", "Depreciation"
            if "financ" in blob or "interest" in blob or "bank charge" in blob:
                return "PL", "Financial Charge"
            if "director" in blob or "remuner" in blob:
                return "PL", "Director Remuneration"
            if "cost of" in blob or "cogs" in blob or "material" in blob or "purchase" in blob:
                return "PL", "Less : Cost of Revenue"
            return "PL", "General & Administration Expenses"
        # Ledger type only. The journal name is never used.
        if ut_type == "receivable" or "receiv" in ledger:
            return "BS", "Accounts Receivable"
        if ut_type == "payable" or "payable" in ledger or "creditor" in ledger:
            return "BS", "Accounts Payable"
        if ut_type == "liquidity" or ut_name in ("bank and cash", "cash", "bank"):
            return "BS", "Cash and Bank Balances"
        if any(k in ledger for k in ("property", "plant", "equipment", "fixed asset", "furniture", "vehicle", "motor")):
            return "BS", "Property, Plant & Equipment"
        if "inventor" in ledger or ledger.startswith("stock"):
            return "BS", "Inventories"
        if any(k in blob for k in ("deposit", "prepay", "advance")):
            return "BS", "Deposits, Advances & Prepayments"
        if "payable" in blob or "creditor" in blob:
            return "BS", "Accounts Payable"
        if "accrual" in blob or "provision" in blob or "end of service" in blob:
            return "BS", "Accruals and Provisions"
        if "share capital" in blob or "capital" in blob:
            return "BS", "Share Capital"
        if "retained" in blob or "profit" in blob:
            return "BS", "Retained Earnings"
        if "current account" in blob or "shareholder" in blob:
            return "BS", "Shareholders' Current Account"
        if ig in ("liability",):
            return "BS", "Accounts Payable"
        if ig in ("equity",):
            return "BS", "Retained Earnings"
        if ig in ("asset",):
            return "BS", "Ungrouped Assets"
        return "BS", "Ungrouped Assets"

    def _afg_excel_period_years(self):
        """Two different years. If the version stored the same year twice, prior is the year before."""
        self.ensure_one()
        yc = int(self.year_current or 0)
        if not yc and self.date_to_current:
            yc = self.date_to_current.year
        yc = yc or 2025
        yp = int(self.year_prior or 0)
        if self.date_to_prior and int(self.year_prior or 0) != int(self.year_current or 0):
            yp = self.date_to_prior.year
        if not yp or yp == yc:
            yp = yc - 1
        return yc, yp

    def _afg_excel_company_ids(self):
        """Companies on this version only. The systray list is not the pack."""
        self.ensure_one()
        if self.branch_company_id:
            return [int(self.branch_company_id.id)]
        ids = [int(c) for c in (self.company_ids.ids or [])]
        if self.company_id and int(self.company_id.id) not in ids:
            ids.insert(0, int(self.company_id.id))
        return ids or ([int(self.company_id.id)] if self.company_id else [])

    def _afg_excel_face_rank(self, face):
        order = [
            "Net Revenue",
            "Other Income",
            "Less : Cost of Revenue",
            "General & Administration Expenses",
            "Depreciation",
            "Director Remuneration",
            "Financial Charge",
            "Corporate Tax Paid",
            "Property, Plant & Equipment",
            "Ungrouped Assets",
            "Cash and Bank Balances",
            "Inventories",
            "Accounts Receivable",
            "Deposits, Advances & Prepayments",
            "Accounts Payable",
            "Accruals and Provisions",
            "Share Capital",
            "Retained Earnings",
            "Shareholders' Current Account",
        ]
        try:
            return order.index(face)
        except ValueError:
            return len(order)

    def _afg_excel_tb_source_lines(self):
        """Closing debit-minus-credit by ledger. One column sums to nil."""
        self.ensure_one()
        cids = self._afg_excel_company_ids()
        yc, yp = self._afg_excel_period_years()
        cur_to = fields.Date.from_string("%s-12-31" % yc)
        pri_to = fields.Date.from_string("%s-12-31" % yp)
        self.env.cr.execute(
            """
            SELECT l.account_id,
                   SUM(CASE WHEN l.date <= %s THEN l.debit - l.credit ELSE 0 END),
                   SUM(CASE WHEN l.date <= %s THEN l.debit - l.credit ELSE 0 END)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id
             WHERE m.state = 'posted'
               AND l.company_id IN %s
             GROUP BY l.account_id
            """,
            (cur_to, pri_to, tuple(cids)),
        )
        raw = {row[0]: (float(row[1] or 0.0), float(row[2] or 0.0)) for row in self.env.cr.fetchall()}
        Account = self._afg_account_sudo().with_context(allowed_company_ids=cids)
        accounts = Account.browse(list(raw.keys())).exists()
        lines = []
        for acc in accounts:
            current, prior = raw.get(acc.id) or (0.0, 0.0)
            if abs(current) < 0.005 and abs(prior) < 0.005:
                continue
            statement, face = self._afg_excel_face_bucket(acc)
            lines.append({
                "code": acc.code or "",
                "name": acc.name or "",
                "company": (acc.company_id.display_name if int(acc.company_id.id or 0) in cids else self.company_id.display_name) or "",
                "statement": "Statement of Comprehensive Income" if statement == "PL" else "Statement of Financial Position",
                "face": face,
                "current": current,
                "prior": prior,
                "year_current": yc,
                "year_prior": yp,
            })
        lines.sort(key=lambda r: (0 if r["statement"].startswith("Statement of Comp") else 1, self._afg_excel_face_rank(r["face"]), r["code"], r["name"]))
        return lines

    def _afg_excel_attach_pivot(self, data, last_row):
        """Real Excel pivot on Journal Items. Open the file and double-click a figure."""
        import zipfile
        import re
        names = [
            "Date", "Entry", "Journal", "Code", "Ledger", "Company", "Statement",
            "Face line", "Debit", "Credit", "Account", "Nettex", "Month", "Year", "Order",
        ]
        try:
            src = zipfile.ZipFile(io.BytesIO(data))
            files = {name: src.read(name) for name in src.namelist()}
            src.close()
            wb_xml = files["xl/workbook.xml"].decode("utf-8")
            found = re.search(r'<sheet[^>]*name="Pivot Table"[^>]*r:id="([^"]+)"', wb_xml)
            if not found:
                found = re.search(r'<sheet[^>]*r:id="([^"]+)"[^>]*name="Pivot Table"', wb_xml)
            if not found:
                return data
            rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
            target = re.search(
                r'Id="%s"[^>]*Target="([^"]+)"|Target="([^"]+)"[^>]*Id="%s"' % (found.group(1), found.group(1)),
                rels,
            )
            sheet_target = (target.group(1) or target.group(2)) if target else ""
            if not sheet_target:
                return data
            sheet_file = sheet_target.split("/")[-1]
            sheet_rels = "xl/worksheets/_rels/%s.rels" % sheet_file
            fields_xml = []
            row_idx = {6, 7, 4}
            for i in range(len(names)):
                if i == 11:
                    fields_xml.append('<pivotField dataField="1" showAll="0"/>')
                elif i in row_idx:
                    fields_xml.append('<pivotField axis="axisRow" showAll="0"><items count="1"><item t="default"/></items></pivotField>')
                elif i == 13:
                    fields_xml.append('<pivotField axis="axisCol" showAll="0"><items count="1"><item t="default"/></items></pivotField>')
                else:
                    fields_xml.append('<pivotField showAll="0"/>')
            cache_fields = "".join(
                '<cacheField name="%s" numFmtId="0"><sharedItems/></cacheField>' % name
                for name in names
            )
            definition = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'refreshOnLoad="1" recordCount="0">'
                '<cacheSource type="worksheet"><worksheetSource ref="A1:O%d" sheet="Journal Items"/></cacheSource>'
                '<cacheFields count="%d">%s</cacheFields></pivotCacheDefinition>'
            ) % (int(last_row), len(names), cache_fields)
            records = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<pivotCacheRecords xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0"/>'
            )
            table = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<pivotTableDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'name="JournalPivot" cacheId="1" dataCaption="Values" refreshOnLoad="1" '
                'applyNumberFormats="0" applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0" '
                'applyAlignmentFormats="0" applyWidthHeightFormats="1" dataOnRows="0" updatedVersion="6" '
                'minRefreshableVersion="3" useAutoFormatting="1" itemPrintTitles="1" createdVersion="6" indent="0" '
                'compact="1" compactData="1" gridDropZones="1">'
                '<location ref="A3:H40" firstHeaderRow="1" firstDataRow="2" firstDataCol="1"/>'
                '<pivotFields count="%d">%s</pivotFields>'
                '<rowFields count="3"><field x="6"/><field x="7"/><field x="4"/></rowFields>'
                '<colFields count="1"><field x="13"/></colFields>'
                '<dataFields count="1"><dataField name="Sum of Nettex" fld="11" subtotal="sum" baseField="0" baseItem="0"/></dataFields>'
                '<pivotTableStyleInfo name="PivotStyleMedium2" showRowHeaders="1" showColHeaders="1" showLastColumn="1"/>'
                '</pivotTableDefinition>'
            ) % (len(names), "".join(fields_xml))
            files["xl/pivotCache/pivotCacheDefinition1.xml"] = definition.encode("utf-8")
            files["xl/pivotCache/pivotCacheRecords1.xml"] = records.encode("utf-8")
            files["xl/pivotTables/pivotTable1.xml"] = table.encode("utf-8")
            files["xl/pivotTables/_rels/pivotTable1.xml.rels"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotCacheDefinition" Target="../pivotCache/pivotCacheDefinition1.xml"/>'
                '</Relationships>'
            ).encode("utf-8")
            files["xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotCacheRecords" Target="pivotCacheRecords1.xml"/>'
                '</Relationships>'
            ).encode("utf-8")
            if sheet_rels in files:
                rel_xml = files[sheet_rels].decode("utf-8")
                rel_xml = rel_xml.replace(
                    "</Relationships>",
                    '<Relationship Id="rIdPivot" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotTable" Target="../pivotTables/pivotTable1.xml"/></Relationships>',
                )
            else:
                rel_xml = (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rIdPivot" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotTable" Target="../pivotTables/pivotTable1.xml"/>'
                    '</Relationships>'
                )
            files[sheet_rels] = rel_xml.encode("utf-8")
            files["xl/_rels/workbook.xml.rels"] = rels.replace(
                "</Relationships>",
                '<Relationship Id="rIdPivotCache" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotCacheDefinition" Target="pivotCache/pivotCacheDefinition1.xml"/></Relationships>',
            ).encode("utf-8")
            if "</workbook>" in wb_xml and "pivotCaches" not in wb_xml:
                files["xl/workbook.xml"] = wb_xml.replace(
                    "</workbook>",
                    '<pivotCaches><pivotCache cacheId="1" r:id="rIdPivotCache"/></pivotCaches></workbook>',
                ).encode("utf-8")
            ctypes = files["[Content_Types].xml"].decode("utf-8")
            extra = (
                '<Override PartName="/xl/pivotCache/pivotCacheDefinition1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml"/>'
                '<Override PartName="/xl/pivotCache/pivotCacheRecords1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheRecords+xml"/>'
                '<Override PartName="/xl/pivotTables/pivotTable1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml"/>'
            )
            files["[Content_Types].xml"] = ctypes.replace("</Types>", extra + "</Types>").encode("utf-8")
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dest:
                for name, blob in files.items():
                    dest.writestr(name, blob)
            return out.getvalue()
        except Exception:
            _logger.exception("AFG pivot table was not attached")
            return data

    def _afg_statutory_xlsx_action(self, doc):
        pages = [c for c in (doc.get("chapters") or []) if (c.get("kind") or "") == "statutory_page"]
        if not pages:
            return False
        import xlsxwriter
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})
        pt = self._afg_dpi_pt
        fmt_co = wb.add_format({"bold": True, "font_name": "Times New Roman", "font_size": pt(12)})
        fmt_place = wb.add_format({"font_name": "Times New Roman", "font_size": pt(11)})
        fmt_title = wb.add_format({"bold": True, "font_name": "Times New Roman", "font_size": pt(12)})
        fmt_head = wb.add_format({
            "bold": True, "font_name": "Times New Roman", "font_size": pt(11),
            "bottom": 1, "align": "center",
        })
        fmt_lbl = wb.add_format({"font_name": "Times New Roman", "font_size": pt(11)})
        fmt_sec = wb.add_format({
            "bold": True, "underline": 1, "font_name": "Times New Roman", "font_size": pt(11),
        })
        num_fmt = '#,##0;(#,##0);"-"'
        fmt_num = wb.add_format({
            "font_name": "Times New Roman", "font_size": pt(11), "align": "right",
            "num_format": num_fmt,
        })
        fmt_single = wb.add_format({
            "font_name": "Times New Roman", "font_size": pt(11), "align": "right", "top": 1,
            "num_format": num_fmt,
        })
        fmt_double = wb.add_format({
            "font_name": "Times New Roman", "font_size": pt(11), "align": "right", "top": 1, "bottom": 6,
            "num_format": num_fmt,
        })
        fmt_src = wb.add_format({
            "font_name": "Times New Roman", "font_size": pt(10), "align": "right",
            "num_format": num_fmt,
        })
        # Journal items are typed, including statement and face line.
        # The trial balance picks those columns up. Its year columns sum every line once, so the net is nil.
        yc_label, yp_label = self._afg_excel_period_years()
        self.env.cr.execute(
            """
            SELECT l.date, m.name, COALESCE(j.name, ''), COALESCE(a.code, ''),
                   COALESCE(a.name, ''), COALESCE(rc.name, ''),
                   l.debit, l.credit, a.id
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id
              JOIN account_account a ON a.id = l.account_id
              JOIN res_company rc ON rc.id = l.company_id
              LEFT JOIN account_journal j ON j.id = m.journal_id
             WHERE m.state = 'posted'
               AND l.company_id IN %s
               AND l.date <= %s
             ORDER BY l.date, m.name, a.code, l.id
            """,
            (tuple(self._afg_excel_company_ids()), fields.Date.from_string("%s-12-31" % yc_label)),
        )
        ji_recs = self.env.cr.fetchall()
        accounts = self._afg_account_sudo().browse(list({r[8] for r in ji_recs if r[8]}))
        face_by_id = {}
        for acc in accounts:
            statement, face = self._afg_excel_face_bucket(acc)
            face_by_id[acc.id] = {
                "code": acc.code or "",
                "name": acc.name or "",
                "company": (acc.company_id.display_name if int(acc.company_id.id or 0) in set(self._afg_excel_company_ids()) else self.company_id.display_name) or "",
                "statement": "Statement of Comprehensive Income" if statement == "PL" else "Statement of Financial Position",
                "face": face,
            }
        wb.add_worksheet("Pivot Table")
        ji = wb.add_worksheet("Journal Items")
        ji.set_column(0, 0, 14)
        ji.set_column(1, 2, 22)
        ji.set_column(3, 3, 16)
        ji.set_column(4, 5, 36)
        ji.set_column(6, 7, 38)
        ji.set_column(8, 9, 16)
        ji.set_column(10, 10, None, None, {"hidden": True})
        ji.set_column(11, 11, 16)
        ji.set_column(12, 13, 12)
        for col, title in enumerate([
            "Date", "Entry", "Journal", "Code", "Ledger", "Company",
            "Statement", "Face line", "Debit", "Credit", "Account",
            "Nettex", "Month", "Year", "Order",
        ]):
            ji.write(0, col, title, fmt_head)
        fmt_date = wb.add_format({
            "font_name": "Times New Roman", "font_size": pt(10), "num_format": "dd/mm/yyyy",
        })
        ji_row = 1
        for rec in ji_recs:
            meta = face_by_id.get(rec[8]) or {
                "statement": "Statement of Financial Position",
                "face": "Ungrouped Assets",
            }
            if rec[0]:
                ji.write_datetime(ji_row, 0, fields.Datetime.to_datetime(rec[0]), fmt_date)
            ji.write(ji_row, 1, rec[1] or "", fmt_lbl)
            ji.write(ji_row, 2, rec[2] or "", fmt_lbl)
            ji.write(ji_row, 3, rec[3] or "", fmt_lbl)
            ji.write(ji_row, 4, rec[4] or "", fmt_lbl)
            ji.write(ji_row, 5, rec[5] or "", fmt_lbl)
            ji.write(ji_row, 6, meta["statement"], fmt_lbl)
            ji.write(ji_row, 7, meta["face"], fmt_lbl)
            ji.write_number(ji_row, 8, float(rec[6] or 0.0), fmt_src)
            ji.write_number(ji_row, 9, float(rec[7] or 0.0), fmt_src)
            ji.write_number(ji_row, 10, int(rec[8] or 0), fmt_lbl)
            excel_n = ji_row + 1
            ji.write_formula(ji_row, 11, "=I%d-J%d" % (excel_n, excel_n), fmt_src)
            ji.write_formula(ji_row, 12, "=IF(A%d=\"\",\"\",MONTH(A%d))" % (excel_n, excel_n), fmt_lbl)
            ji.write_formula(ji_row, 13, "=IF(A%d=\"\",\"\",YEAR(A%d))" % (excel_n, excel_n), fmt_lbl)
            ji.write(ji_row, 14, "%02d" % self._afg_excel_face_rank(meta.get("face") or ""), fmt_lbl)
            ji_row += 1
        ji_last = max(ji_row - 1, 1)
        ji.autofilter(0, 0, ji_last, 13)
        ji_end = ji_last + 1
        tb = wb.add_worksheet("Trial Balance (Journal Items)")
        tb.set_column(0, 0, 16)
        tb.set_column(1, 1, 42)
        tb.set_column(2, 2, 36)
        tb.set_column(3, 4, 38)
        tb.set_column(5, 8, 18)
        tb.set_column(9, 11, None, None, {"hidden": True})
        for col, title in enumerate([
            "Code", "Ledger", "Company", "Statement", "Face line",
            "Opening", str(yp_label), str(yc_label), "Closing", "Account", "Class", "Kind",
        ]):
            tb.write(0, col, title, fmt_head)
        ordered = sorted(face_by_id.items(), key=lambda kv: (
            0 if kv[1]["statement"].startswith("Statement of Comp") else 1,
            self._afg_excel_face_rank(kv[1]["face"]),
            kv[1]["code"],
            kv[1]["name"],
        ))
        tb_first = 2
        excel_row = 1
        last_statement = None
        last_face = None
        for acc_id, line in ordered:
            if line["statement"] != last_statement:
                excel_row += 1
                tb.write(excel_row, 1, line["statement"], fmt_sec)
                last_statement = line["statement"]
                last_face = None
            if line["face"] != last_face:
                excel_row += 1
                tb.write(excel_row, 1, line["face"], fmt_sec)
                last_face = line["face"]
            excel_row += 1
            tb.write(excel_row, 0, line["code"], fmt_lbl)
            tb.write(excel_row, 1, line["name"], fmt_lbl)
            tb.write(excel_row, 2, line["company"], fmt_lbl)
            acct_cell = "$J%d" % (excel_row + 1)
            tb.write_formula(excel_row, 3, "=IFERROR(INDEX('Journal Items'!$G$2:$G$%s,MATCH(%s,'Journal Items'!$K$2:$K$%s,0)),\"\")" % (ji_end, acct_cell, ji_end), fmt_lbl)
            tb.write_formula(excel_row, 4, "=IFERROR(INDEX('Journal Items'!$H$2:$H$%s,MATCH(%s,'Journal Items'!$K$2:$K$%s,0)),\"\")" % (ji_end, acct_cell, ji_end), fmt_lbl)
            ledger_l = (line["name"] or "").lower()
            if line["face"] == "Property, Plant & Equipment":
                if "decor" in ledger_l:
                    ppe_class = "Decoration"
                elif "motor" in ledger_l or "vehicle" in ledger_l:
                    ppe_class = "Motor Vehicle"
                else:
                    ppe_class = "Furniture & Office"
                ppe_kind = "Accumulated" if ("acc." in ledger_l or "accum" in ledger_l or "depn" in ledger_l) else "Cost"
            else:
                ppe_class = ""
                ppe_kind = ""
            tb.write(excel_row, 10, ppe_class, fmt_lbl)
            tb.write(excel_row, 11, ppe_kind, fmt_lbl)
            tb.write_number(excel_row, 9, int(acc_id), fmt_lbl)
            excel_n = excel_row + 1
            tb.write_formula(excel_row, 5, (
                '=SUMIFS(\'Journal Items\'!$L$2:$L$%s,\'Journal Items\'!$K$2:$K$%s,%s,\'Journal Items\'!$N$2:$N$%s,"<"&%s)'
            ) % (ji_end, ji_end, acct_cell, ji_end, yp_label), fmt_src)
            tb.write_formula(excel_row, 6, (
                '=SUMIFS(\'Journal Items\'!$L$2:$L$%s,\'Journal Items\'!$K$2:$K$%s,%s,\'Journal Items\'!$N$2:$N$%s,%s)'
            ) % (ji_end, ji_end, acct_cell, ji_end, yp_label), fmt_src)
            tb.write_formula(excel_row, 7, (
                '=SUMIFS(\'Journal Items\'!$L$2:$L$%s,\'Journal Items\'!$K$2:$K$%s,%s,\'Journal Items\'!$N$2:$N$%s,%s)'
            ) % (ji_end, ji_end, acct_cell, ji_end, yc_label), fmt_src)
            tb.write_formula(excel_row, 8, "=F%d+G%d+H%d" % (excel_n, excel_n, excel_n), fmt_src)
        data_last = max(excel_row, tb_first)
        excel_row += 2
        tb.write(excel_row, 1, "Net", fmt_sec)
        for col_i, coln in ((5, "F"), (6, "G"), (7, "H"), (8, "I")):
            tb.write_formula(excel_row, col_i, "=SUM(%s2:%s%d)" % (coln, coln, data_last + 1), fmt_double)
        tb_last = data_last
        tb.autofilter(0, 0, tb_last, 8)
        face_range = "'Trial Balance (Journal Items)'!$E$%s:$E$%s" % (tb_first, tb_last + 1)
        open_range = "'Trial Balance (Journal Items)'!$F$%s:$F$%s" % (tb_first, tb_last + 1)
        mov_p_range = "'Trial Balance (Journal Items)'!$G$%s:$G$%s" % (tb_first, tb_last + 1)
        mov_c_range = "'Trial Balance (Journal Items)'!$H$%s:$H$%s" % (tb_first, tb_last + 1)
        close_range = "'Trial Balance (Journal Items)'!$I$%s:$I$%s" % (tb_first, tb_last + 1)
        class_range = "'Trial Balance (Journal Items)'!$K$%s:$K$%s" % (tb_first, tb_last + 1)
        kind_range = "'Trial Balance (Journal Items)'!$L$%s:$L$%s" % (tb_first, tb_last + 1)

        credit_faces = {
            "Net Revenue", "Other Income", "Accounts Payable", "Accruals and Provisions",
            "Share Capital", "Retained Earnings", "Shareholders' Current Account",
        }

        pl_faces = {
            "Net Revenue", "Other Income", "Less : Cost of Revenue",
            "General & Administration Expenses", "Director Remuneration",
            "Depreciation", "Financial Charge", "Corporate Tax Paid",
        }

        def _sumif(face, which):
            safe = (face or "").replace('"', '""')
            if face in pl_faces:
                ranges = {"current": [mov_c_range], "prior": [mov_p_range], "open": [open_range]}.get(which, [mov_c_range])
            elif which == "prior":
                ranges = [open_range, mov_p_range]
            elif which == "open":
                ranges = [open_range]
            else:
                ranges = [close_range]
            parts = []
            for rng in ranges:
                bit = 'SUMIF(%s,"%s",%s)' % (face_range, safe, rng)
                if face in credit_faces:
                    bit = "-" + bit
                parts.append(bit)
            if face == "Retained Earnings":
                # Profit still sitting on income and expense ledgers, so the position balances.
                profit_ranges = ranges
                for pl_face in pl_faces:
                    pl_safe = pl_face.replace('"', '""')
                    for rng in profit_ranges:
                        parts.append('-SUMIF(%s,"%s",%s)' % (face_range, pl_safe, rng))
            return "=" + "+".join(parts)

        used = set()
        anchors = {}
        for idx, page in enumerate(pages, start=1):
            raw = (page.get("title") or "Sheet")[:24]
            name = re.sub(r"[\\/*?:\[\]]", "", raw) or "Sheet"
            candidate = ("%02d %s" % (idx, name))[:31]
            n = 2
            while candidate.lower() in used:
                candidate = ("%02d %s %s" % (idx, name, n))[:31]
                n += 1
            used.add(candidate.lower())
            ws = wb.add_worksheet(candidate)
            sheet_ref = "'%s'" % candidate.replace("'", "''")
            ws.set_column(0, 0, 62)
            ws.set_column(1, 6, 18)
            ws.write(0, 0, page.get("company") or "", fmt_co)
            ws.write(1, 0, page.get("place") or "", fmt_place)
            ws.write(3, 0, page.get("title") or "", fmt_title)
            ws.write(4, 0, page.get("period") or "", fmt_title)
            ws.write(5, 0, page.get("unit") or "", fmt_place)
            heads = list(page.get("heads") or [])
            # Amount headers follow the journal-item years, not a duplicated period.
            amt_labels = [str(yc_label), str(yp_label)]
            seen_amt = 0
            ws.write(7, 0, "", fmt_head)
            for c, head in enumerate(heads, start=1):
                label = head.get("label") or ""
                if (head.get("cls") or "") == "num" and seen_amt < 2:
                    label = amt_labels[seen_amt]
                    seen_amt += 1
                ws.write(7, c, label, fmt_head)
            row_i = 8
            label_rows = {}
            ppe_section = ""
            eq_profit_n = 0
            eq_move_n = 0
            for row in page.get("rows") or []:
                cls = row.get("cls") or ""
                label = row.get("label") or ""
                key = page.get("key") or ""
                lf = fmt_sec if "sec" in cls else fmt_lbl
                ws.write(row_i, 0, label, lf)
                if label:
                    label_rows[label] = row_i
                    if key == "fixed_assets":
                        if ppe_section == "cost" and str(yp_label) in label and "Addition" not in label:
                            label_rows["cost-open"] = row_i
                        if ppe_section == "cost" and str(yc_label) in label:
                            label_rows["cost-close"] = row_i
                        if ppe_section == "dep" and str(yp_label) in label and "Charge" not in label:
                            label_rows["dep-open"] = row_i
                        if ppe_section == "dep" and str(yc_label) in label:
                            label_rows["dep-close"] = row_i
                cells = row.get("cells") or []
                # Note column stays text. Amount columns are SUMIF or face arithmetic.
                note = ""
                if cells and (cells[0].get("cls") or "") == "note":
                    note = cells[0].get("text") or ""
                    ws.write(row_i, 1, note, fmt_lbl)
                    amount_cells = cells[1:]
                else:
                    amount_cells = cells
                formula = None
                if key == "pl" and label == "Gross Profit":
                    formula = ("=C{a}-C{b}", "=D{a}-D{b}", label_rows.get("Net Revenue"), label_rows.get("Less : Cost of Revenue"))
                elif key == "pl" and label == "" and "single" in cls and "Gross Profit" in label_rows and row_i > label_rows.get("Gross Profit", 0):
                    formula = ("=C{a}+C{b}", "=D{a}+D{b}", label_rows.get("Gross Profit"), label_rows.get("Other Income"))
                elif key == "pl" and label == "Net Profit / (Loss) for the year":
                    formula = ("=C{a}-C{b}", "=D{a}-D{b}", label_rows.get("Gross Profit"), None)
                for c, cell in enumerate(amount_cells, start=2):
                    ccls = cell.get("cls") or ""
                    if "num" not in ccls:
                        ws.write(row_i, c, cell.get("text") or "", fmt_lbl)
                        continue
                    if "double" in cls:
                        nf = fmt_double
                    elif "single" in cls:
                        nf = fmt_single
                    else:
                        nf = fmt_num
                    if "sec" in cls or not label:
                        if formula and formula[2] and label == "":
                            a, b = formula[2] + 1, (formula[3] or 0) + 1
                            if b:
                                expr = (formula[0] if c == 2 else formula[1]).format(a=a, b=b)
                                ws.write_formula(row_i, c, expr, nf)
                                continue
                        ws.write(row_i, c, None if "sec" in cls else 0, nf if "num" in ccls else fmt_lbl)
                        continue
                    if key == "fixed_assets":
                        if label == "COST":
                            ppe_section = "cost"
                        elif label.startswith("Accumulated"):
                            ppe_section = "dep"
                        elif label == "Net Book Value":
                            ppe_section = "nbv"
                        classes = ["Furniture & Office", "Decoration", "Motor Vehicle"]
                        if c == 5:
                            ws.write_formula(row_i, c, "=SUM(B%d:D%d)" % (row_i + 1, row_i + 1), nf)
                            continue
                        if 2 <= c <= 4 and ppe_section in ("cost", "dep"):
                            klass = classes[c - 2]
                            kind = "Cost" if ppe_section == "cost" else "Accumulated"
                            sign = "" if ppe_section == "cost" else "-"
                            ppe_sum = 'SUMIFS(%%s,%s,"Property, Plant & Equipment",%s,"%s",%s,"%s")' % (
                                face_range, class_range, klass, kind_range, kind)
                            if str(yp_label) in label and "Addition" not in label and "Charge" not in label:
                                ws.write_formula(row_i, c, "=%s%s+%s%s" % (sign, ppe_sum % open_range, sign, ppe_sum % mov_p_range), nf)
                                continue
                            if str(yc_label) in label:
                                ws.write_formula(row_i, c, "=%s%s" % (sign, ppe_sum % close_range), nf)
                                continue
                            if label == "Additions":
                                ws.write_formula(row_i, c, "=" + (ppe_sum % mov_c_range).replace(kind, "Cost") if False else (
                                    '=SUMIFS(%s,%s,"Property, Plant & Equipment",%s,"%s",%s,"Cost")' % (mov_c_range, face_range, class_range, klass, kind_range)
                                ), nf)
                                continue
                            if label == "Charge for the year":
                                ws.write_formula(row_i, c, (
                                    '=-(SUMIFS(%s,%s,"Property, Plant & Equipment",%s,"%s",%s,"Accumulated"))'
                                ) % (mov_c_range, face_range, class_range, klass, kind_range), nf)
                                continue
                        if 2 <= c <= 4 and ppe_section == "nbv":
                            cost_row = label_rows.get("cost-close" if str(yc_label) in label else "cost-open")
                            dep_row = label_rows.get("dep-close" if str(yc_label) in label else "dep-open")
                            if cost_row is not None and dep_row is not None:
                                coln = "BCD"[c - 2]
                                ws.write_formula(row_i, c, "=%s%d+%s%d" % (coln, cost_row + 1, coln, dep_row + 1), nf)
                                continue
                    if key == "equity" and c in (2, 3, 4, 5):
                        face_by_col = {2: "Share Capital", 3: "Retained Earnings", 4: "Shareholders' Current Account"}
                        if label.startswith("Balance as at"):
                            if str(yc_label) in label:
                                which = "current"
                            elif str(yp_label) in label:
                                which = "prior"
                            else:
                                which = "open"
                            if c == 5:
                                ws.write_formula(row_i, c, "=B%d+C%d+D%d" % (row_i + 1, row_i + 1, row_i + 1), nf)
                            else:
                                ws.write_formula(row_i, c, _sumif(face_by_col[c], which), nf)
                            continue
                        if "Net Profit" in label:
                            if c == 3:
                                eq_profit_n += 1
                                pl_ref = anchors.get(("pl", "Net Profit / (Loss) for the year", 3 if eq_profit_n == 1 else 2))
                                ws.write_formula(row_i, c, "=%s" % pl_ref if pl_ref else "=0", nf)
                            elif c == 5:
                                ws.write_formula(row_i, c, "=C%d" % (row_i + 1), nf)
                            else:
                                ws.write_formula(row_i, c, "=0", nf)
                            continue
                        if "Current A/c" in label or "Current A/c".lower() in label.lower() or "Movements" in label:
                            if c == 4:
                                eq_move_n += 1
                                newer = "prior" if eq_move_n == 1 else "current"
                                older = "open" if eq_move_n == 1 else "prior"
                                ws.write_formula(row_i, c, "=%s-(%s)" % (_sumif("Shareholders' Current Account", newer)[1:], _sumif("Shareholders' Current Account", older)[1:]), nf)
                            elif c == 5:
                                ws.write_formula(row_i, c, "=D%d" % (row_i + 1), nf)
                            else:
                                ws.write_formula(row_i, c, "=0", nf)
                            continue
                    if key == "cashflow" and c in (2, 3):
                        newer = "current" if c == 2 else "prior"
                        older = "prior" if c == 2 else "open"
                        asset_moves = {
                            "(Increase)/Decrease in Accounts Receivable": "Accounts Receivable",
                            "(Increase)/Decrease in Deposits, Advances & Prepayments": "Deposits, Advances & Prepayments",
                        }
                        liab_moves = {
                            "(Decrease)/Increase in Accounts Payable": "Accounts Payable",
                            "(Decrease)/Increase in Accruals and Provisions": "Accruals and Provisions",
                        }
                        if label in asset_moves:
                            ws.write_formula(row_i, c, "=%s-(%s)" % (_sumif(asset_moves[label], older)[1:], _sumif(asset_moves[label], newer)[1:]), nf)
                            continue
                        if label in liab_moves:
                            ws.write_formula(row_i, c, "=%s-(%s)" % (_sumif(liab_moves[label], newer)[1:], _sumif(liab_moves[label], older)[1:]), nf)
                            continue
                        if label == "Operating profit before changes in Operating Assets and Liabilities :":
                            ws.write_formula(row_i, c, "=C%d+C%d" % (
                                (label_rows.get("Net Profit / (Loss) for the year") or row_i) + 1,
                                (label_rows.get("Depreciation") or row_i) + 1,
                            ) if c == 2 else "=D%d+D%d" % (
                                (label_rows.get("Net Profit / (Loss) for the year") or row_i) + 1,
                                (label_rows.get("Depreciation") or row_i) + 1,
                            ), nf)
                            continue
                        if label.startswith("Purchase of property"):
                            ws.write_formula(row_i, c, (
                                '=-(SUMIFS(%s,%s,"Property, Plant & Equipment",%s,"Cost"))'
                            ) % (mov_c_range if c == 2 else mov_p_range, face_range, kind_range), nf)
                            continue
                        if label in ("Capital",):
                            ws.write_formula(row_i, c, "=%s-(%s)" % (_sumif("Share Capital", newer)[1:], _sumif("Share Capital", older)[1:]), nf)
                            continue
                        if label == "Net Movements in Shareholders' Current A/c":
                            ws.write_formula(row_i, c, "=%s-(%s)" % (_sumif("Shareholders' Current Account", newer)[1:], _sumif("Shareholders' Current Account", older)[1:]), nf)
                            continue
                        if label.startswith("Net Cash inflow/(outflow) from Operating"):
                            coln = "C" if c == 2 else "D"
                            ws.write_formula(row_i, c, "=SUM(%s9:%s%d)" % (coln, coln, row_i), nf)
                            continue
                        if "Investing activities" in label and label.startswith("Net Cash"):
                            coln = "C" if c == 2 else "D"
                            src = label_rows.get("Purchase of property, plant & equipment")
                            ws.write_formula(row_i, c, "=%s%d" % (coln, (src if src is not None else row_i) + 1), nf)
                            continue
                        if "Financing activities" in label and label.startswith("Net Cash"):
                            coln = "C" if c == 2 else "D"
                            cap = label_rows.get("Capital")
                            mov = label_rows.get("Net Movements in Shareholders' Current A/c")
                            parts = ["%s%d" % (coln, r + 1) for r in (cap, mov) if r is not None]
                            ws.write_formula(row_i, c, "=" + "+".join(parts) if parts else "=0", nf)
                            continue
                        if label.startswith("Net Increase"):
                            coln = "C" if c == 2 else "D"
                            op = label_rows.get("Net Cash inflow/(outflow) from Operating activities")
                            inv = None
                            fin = None
                            for k, v in label_rows.items():
                                if k.startswith("Net Cash") and "Investing" in k:
                                    inv = v
                                if k.startswith("Net Cash") and "Financing" in k:
                                    fin = v
                            parts = ["%s%d" % (coln, r + 1) for r in (op, inv, fin) if r is not None]
                            ws.write_formula(row_i, c, "=" + "+".join(parts) if parts else "=0", nf)
                            continue
                        if label.startswith("Cash and cash equivalents at beginning"):
                            ws.write_formula(row_i, c, _sumif("Cash and Bank Balances", older), nf)
                            continue
                        if label.startswith("Cash and Cash equivalents at end"):
                            coln = "C" if c == 2 else "D"
                            begin = label_rows.get("Cash and cash equivalents at beginning of the year")
                            inc = label_rows.get("Net Increase/(Decrease) in cash and cash equivalents")
                            if begin is not None and inc is not None:
                                ws.write_formula(row_i, c, "=%s%d+%s%d" % (coln, begin + 1, coln, inc + 1), nf)
                            else:
                                ws.write_formula(row_i, c, _sumif("Cash and Bank Balances", newer), nf)
                            continue
                        if label in ("Cash in Hand", "Cash at Bank"):
                            ws.write_formula(row_i, c, _sumif("Cash and Bank Balances", newer) if label == "Cash at Bank" else "=0", nf)
                            continue
                    if formula and formula[2] and formula[3] and label in ("Gross Profit",):
                        a, b = formula[2] + 1, formula[3] + 1
                        expr = (formula[0] if c == 2 else formula[1]).format(a=a, b=b)
                        ws.write_formula(row_i, c, expr, nf)
                        continue
                    if label in (
                        "Net Revenue", "Less : Cost of Revenue", "Other Income",
                        "General & Administration Expenses", "Director Remuneration",
                        "Depreciation", "Financial Charge",
                        "Property, Plant & Equipment", "Cash and Bank Balances",
                        "Accounts Receivable", "Deposits, Advances & Prepayments",
                        "Accounts Payable", "Accruals and Provisions", "Share Capital",
                        "Retained Earnings", "Shareholders' Current Account", "Inventories",
                        "Ungrouped Assets",
                    ):
                        which = "current" if c == 2 else "prior"
                        ws.write_formula(row_i, c, _sumif(label, which), nf)
                        anchors[(key, label, c)] = "%s!%s%s" % (sheet_ref, "C" if c == 2 else "D", row_i + 1)
                        continue
                    # Totals add the face rows already written on this sheet.
                    if label in (
                        "Total Non-Current Assets", "Total Current Assets", "TOTAL ASSETS",
                        "Total Current Liabilities", "TOTAL LIABILITIES",
                        "Total Shareholders' Equity", "TOTAL LIABILITIES AND SHAREHOLDERS' EQUITY",
                    ) or label == "Net Profit / (Loss) for the year":
                        col = "C" if c == 2 else "D"
                        parts = []
                        if label == "Total Non-Current Assets":
                            parts = ["Property, Plant & Equipment"]
                        elif label == "Total Current Assets":
                            parts = ["Cash and Bank Balances", "Accounts Receivable", "Deposits, Advances & Prepayments", "Inventories", "Ungrouped Assets"]
                        elif label == "TOTAL ASSETS":
                            parts = ["Total Non-Current Assets", "Total Current Assets"]
                        elif label == "Total Current Liabilities":
                            parts = ["Accounts Payable", "Accruals and Provisions"]
                        elif label == "TOTAL LIABILITIES":
                            parts = ["Total Current Liabilities"]
                        elif label == "Total Shareholders' Equity":
                            parts = ["Share Capital", "Retained Earnings", "Shareholders' Current Account"]
                        elif label == "TOTAL LIABILITIES AND SHAREHOLDERS' EQUITY":
                            parts = ["TOTAL LIABILITIES", "Total Shareholders' Equity"]
                        elif label == "Net Profit / (Loss) for the year":
                            gross = label_rows.get("Gross Profit")
                            other = label_rows.get("Other Income")
                            ga = label_rows.get("General & Administration Expenses")
                            director = label_rows.get("Director Remuneration")
                            dep = label_rows.get("Depreciation")
                            fin = label_rows.get("Financial Charge")
                            refs = [r for r in (gross, other, ga, director, dep, fin) if r is not None]
                            if refs:
                                plus = "+".join("%s%s" % (col, r + 1) for r in refs[:2])
                                minus = "-".join("%s%s" % (col, r + 1) for r in refs[2:])
                                expr = "=%s-%s" % (plus, minus) if minus else "=%s" % plus
                                ws.write_formula(row_i, c, expr, nf)
                                anchors[(key, label, c)] = "%s!%s%s" % (sheet_ref, col, row_i + 1)
                                continue
                        refs = [label_rows[p] for p in parts if p in label_rows]
                        if refs:
                            expr = "=" + "+".join("%s%s" % (col, r + 1) for r in refs)
                            ws.write_formula(row_i, c, expr, nf)
                            anchors[(key, label, c)] = "%s!%s%s" % (sheet_ref, col, row_i + 1)
                            continue
                    cross = {
                        "Net Profit / (Loss) for the year": ("pl", "Net Profit / (Loss) for the year"),
                        "Depreciation": ("pl", "Depreciation"),
                        "Cash and cash equivalents at beginning of the year": ("bs", "Cash and Bank Balances"),
                        "Cash and Cash equivalents at end of the year": ("bs", "Cash and Bank Balances"),
                        "Cash at Bank": ("bs", "Cash and Bank Balances"),
                    }
                    src = cross.get(label)
                    ref = anchors.get((src[0], src[1], c)) if src else None
                    if ref and key not in ("pl", "bs"):
                        ws.write_formula(row_i, c, "=%s" % ref, nf)
                    else:
                        ws.write_formula(row_i, c, _sumif(label, "current" if c == 2 else "prior"), nf)
                row_i += 1
            row_i += 2
            ws.write(row_i, 0, "(Managing Director)", fmt_lbl)
            row_i += 2
            ws.write(row_i, 0, page.get("page") or "", fmt_lbl)
        wb.close()
        data = self._afg_excel_attach_pivot(output.getvalue(), ji_end)
        att = self.env["ir.attachment"].create({
            "name": "Audited_Financials_%s_%s.xlsx" % (self.id, self.year_current),
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % att.id, "target": "self"}

    def _afg_statutory_docx_action(self, doc):
        pages = [c for c in (doc.get("chapters") or []) if (c.get("kind") or "") == "statutory_page"]
        if not pages:
            return False
        pt = self._afg_dpi_pt
        def esc(val):
            return html_lib.escape(str(val or ""))
        blocks = []
        for i, page in enumerate(pages):
            heads = "".join(
                "<th class='%s'>%s</th>" % (esc(h.get("cls") or ""), esc(h.get("label") or ""))
                for h in (page.get("heads") or [])
            )
            body = []
            for row in page.get("rows") or []:
                cells = "".join(
                    "<td class='%s'>%s</td>" % (esc(cell.get("cls") or ""), esc(cell.get("text") or ""))
                    for cell in (row.get("cells") or [])
                )
                body.append("<tr class='%s'><td class='lbl'>%s</td>%s</tr>" % (
                    esc(row.get("cls") or ""), esc(row.get("label") or ""), cells,
                ))
            blocks.append(
                "<div class='page%s'>"
                "<div class='co'>%s</div><div class='place'>%s</div>"
                "<div class='title'>%s</div><div class='period'>%s</div><div class='unit'>%s</div>"
                "<table><thead><tr><th></th>%s</tr></thead><tbody>%s</tbody></table>"
                "<div class='md'>(Managing Director)</div><div class='pg'>%s</div></div>"
                % (
                    "" if i == 0 else " break",
                    esc(page.get("company")), esc(page.get("place")),
                    esc(page.get("title")), esc(page.get("period")), esc(page.get("unit")),
                    heads, "".join(body), esc(page.get("page")),
                )
            )
        html_doc = (
            "<html><head><meta charset='utf-8'/>"
            "<style>"
            "body { font-family: 'Times New Roman', serif; color: #000; }"
            ".co { font-weight: bold; font-size: %spt; text-transform: uppercase; }"
            ".place, .unit, .md, .pg, td, th { font-size: %spt; }"
            ".title, .period { font-weight: bold; font-size: %spt; }"
            "table { width: 100%%; border-collapse: collapse; }"
            "th, td { border: none; padding: 2pt 4pt; }"
            "th { border-bottom: 1px solid #000; text-align: center; }"
            "td.num, th.num { text-align: right; }"
            "td.note, th.note { text-align: center; }"
            "tr.sec td.lbl { font-weight: bold; text-decoration: underline; }"
            "tr.single td.num { border-top: 1px solid #000; }"
            "tr.double td.num { border-top: 1px solid #000; border-bottom: 3px double #000; }"
            ".page.break { page-break-before: always; }"
            ".pg { text-align: center; margin-top: 18pt; }"
            ".md { margin-top: 22pt; }"
            "</style></head><body>%s</body></html>"
        ) % (pt(12), pt(11), pt(12), "".join(blocks))
        att = self.env["ir.attachment"].create({
            "name": "Audited_Financials_%s_%s.doc" % (self.id, self.year_current),
            "type": "binary",
            "datas": base64.b64encode(html_doc.encode("utf-8")),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/msword",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % att.id, "target": "self"}

    def action_export_audit_xlsx(self, max_level=None):
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_("Excel export requires the xlsxwriter Python package on the server."))

        self._afg_set_print_scope("audit")
        export_pack = self._afg_resolve_export_report_pack(max_level)
        gate = self._afg_assert_l1_print_allowed(export_pack, export_kind="xlsx")
        if gate:
            return gate
        self._afg_persist_print_options(export_pack)
        doc = self.with_context(
            afg_export_max_level=export_pack,
            afg_years_descending=self._afg_years_descending(),
            afg_skip_statutory_face=bool(self.env.context.get("afg_return_xlsx_bytes")),
        )._afg_build_print_chapters()
        # CT master and the older working-paper files keep the previous workbook.
        # Only the Export Audit (Excel) button uses the journal-item statements.
        if not self.env.context.get("afg_return_xlsx_bytes"):
            statutory = self._afg_statutory_xlsx_action(doc)
            if statutory:
                return statutory
        cover = doc.get("cover") or {}
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})

        fmt_title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1e3a5f"})
        fmt_sub = wb.add_format({"bold": True, "font_size": 12, "font_color": "#344d5f"})
        fmt_meta = wb.add_format({"font_size": 10})
        fmt_disc = wb.add_format({
            "italic": True, "bold": False, "font_size": 9,
            "font_color": "#555555", "text_wrap": True, "align": "left", "valign": "top",
        })
        fmt_hdr = wb.add_format({
            "bold": True, "bg_color": "#344d5f", "font_color": "#FFFFFF",
            "border": 1, "align": "center", "valign": "vcenter",
        })
        fmt_label = wb.add_format({"border": 1, "valign": "vcenter"})
        fmt_label_b = wb.add_format({"border": 1, "bold": True, "valign": "vcenter", "bg_color": "#E8F4F8"})
        fmt_total = wb.add_format({
            "border": 1, "bold": True, "valign": "vcenter",
            "top": 2, "bottom": 2, "bg_color": "#D9EAF2",
        })
        fmt_num = wb.add_format({"border": 1, "num_format": "#,##0;(#,##0)", "align": "right"})
        fmt_num_b = wb.add_format({
            "border": 1, "bold": True, "num_format": "#,##0;(#,##0)",
            "align": "right", "bg_color": "#E8F4F8",
        })
        fmt_num_t = wb.add_format({
            "border": 1, "bold": True, "num_format": "#,##0;(#,##0)",
            "align": "right", "top": 2, "bottom": 2, "bg_color": "#D9EAF2",
        })

        fmt_company = wb.add_format({"bold": True, "font_size": 14, "font_color": "#000000"})
        fmt_report = wb.add_format({"bold": True, "font_size": 12, "font_color": "#000000"})
        fmt_period = wb.add_format({"bold": True, "font_size": 11, "font_color": "#000000"})
        fmt_block = wb.add_format({"bold": True, "font_size": 11, "font_color": "#1e3a5f"})
        fmt_sign = wb.add_format({"bold": True, "font_size": 10})
        fmt_sign_line = wb.add_format({"bottom": 2})

        used_names = set()

        def _unique_sheet(name):
            base = re.sub(r'[\\/*?:\[\]]', "", (name or "Sheet"))[:28] or "Sheet"
            candidate = base
            i = 2
            while candidate.lower() in used_names:
                candidate = ("%s_%s" % (base[:26], i))[:31]
                i += 1
            used_names.add(candidate.lower())
            return candidate

        def _write_header(ws, header, start_row=0):
            header = header or {}
            ws.write(start_row, 0, header.get("company") or "", fmt_company)
            ws.write(start_row + 1, 0, header.get("report_name") or "", fmt_report)
            ws.write(start_row + 2, 0, header.get("period") or "", fmt_period)
            return start_row + 4

        def _write_signatory(ws, row_i, last_col=2):
            sig = doc.get("signatory") or self._afg_signatory_block()
            row_i += 3
            ws.write(row_i, 0, sig.get("for_line") or _("For and on behalf of"), fmt_meta)
            row_i += 1
            ws.write(row_i, 0, sig.get("entity") or "", fmt_company)
            row_i += 1
            stamp_b64 = sig.get("stamp")
            signature_b64 = sig.get("signature")
            img_row = row_i
            if stamp_b64 or signature_b64:
                # Leave vertical space for images (scaled)
                row_h = int(sig.get("excel_row_height") or 180)
                ws.set_row(img_row, max(90, min(row_h, 260)))
                ws.set_row(img_row + 1, 18)
                stamp_scale = float(sig.get("stamp_excel_scale") or 0.90)
                sig_scale = float(sig.get("signature_excel_scale") or 1.10)
                try:
                    if stamp_b64:
                        stamp_buf = io.BytesIO(base64.b64decode(stamp_b64))
                        ws.insert_image(
                            img_row, 0, "company_stamp.png",
                            {"image_data": stamp_buf, "x_scale": stamp_scale, "y_scale": stamp_scale},
                        )
                    if signature_b64:
                        sig_buf = io.BytesIO(base64.b64decode(signature_b64))
                        # Place signature to the right of stamp when both exist
                        col = 1 if stamp_b64 else 0
                        ws.insert_image(
                            img_row, col, "company_signature.png",
                            {"image_data": sig_buf, "x_scale": sig_scale, "y_scale": sig_scale},
                        )
                except Exception:
                    # Corrupt image bytes — keep text sign-off only
                    pass
                row_i = img_row + 3
            else:
                row_i += 2
                ws.write(row_i, 0, "", fmt_sign_line)
                for c in range(1, min(3, last_col + 1)):
                    ws.write(row_i, c, "", fmt_sign_line)
                row_i += 1
            ws.write(row_i, 0, sig.get("signatory_label") or _("Authorized Signatory"), fmt_sign)
            return row_i

        # --- Corporate Tax Filing first, then cover, then remaining chapters ---
        chapters_all = list(doc.get("chapters") or [])
        fta_chapters = [c for c in chapters_all if (c.get("key") or "") == "fta"]
        cover_chapters = [c for c in chapters_all if (c.get("key") or "") == "cover"]
        other_chapters = [
            c for c in chapters_all
            if (c.get("key") or "") not in ("fta", "cover")
        ]
        sheet_idx = 0
        for ch in fta_chapters:
            sheet_idx += 1
            sheet_name = _unique_sheet("%02d_%s" % (sheet_idx, "CT_FTA"))
            ws = wb.add_worksheet(sheet_name)
            kind = ch.get("kind")
            header = ch.get("header") or self._afg_print_header(
                ch.get("title") or "", ch.get("col_prior"), ch.get("col_current")
            )
            header = dict(header, report_name=_("CORPORATE TAX FILING- FTA"))
            row_i = _write_header(ws, header, 0)
            rows = ch.get("rows") or []
            ws.set_column(0, 0, 62)
            ws.set_column(1, 3, 16)
            hide_comp = bool(ch.get("hide_comparative"))
            ws.write(row_i, 0, _("Particulars"), fmt_hdr)
            col = 1
            if not hide_comp:
                ws.write(row_i, col, ch.get("col_prior") or _("Prior"), fmt_hdr)
                col += 1
            ws.write(row_i, col, ch.get("col_current") or _("Current"), fmt_hdr)
            row_i += 1
            for row in rows:
                lab = row.get("label") or row.get("label_raw") or ""
                lvl = int(row.get("level") or 0)
                prefix = "    " * max(lvl, 0)
                bold = bool(row.get("bold") or row.get("is_total") or row.get("is_computed") or lvl == 0)
                lf = fmt_total if row.get("is_total") else (fmt_label_b if bold else fmt_label)
                nf = fmt_num_t if row.get("is_total") else (fmt_num_b if bold else fmt_num)
                ws.write(row_i, 0, prefix + lab, lf)
                c = 1
                if not hide_comp:
                    prior = row.get("prior")
                    if prior is None or row.get("prior_disp") in ("", "—"):
                        ws.write(row_i, c, row.get("prior_disp") or "", nf)
                    else:
                        ws.write_number(row_i, c, float(prior or 0.0), nf)
                    c += 1
                current = row.get("current")
                if current is None or row.get("current_disp") in ("", "—"):
                    ws.write(row_i, c, row.get("current_disp") or "", nf)
                else:
                    ws.write_number(row_i, c, float(current or 0.0), nf)
                row_i += 1
            _write_signatory(ws, row_i, 2)

        # --- Cover (same text as PDF) — omitted when Print Setup excludes Cover ---
        if cover_chapters:
            sheet_idx += 1
            ws = wb.add_worksheet(_unique_sheet("%02d_Cover" % sheet_idx))
            ws.set_column(0, 0, 72)
            cover_hdr = self._afg_print_header(
                cover.get("title") or _("Financial Statements"),
                doc.get("year_prior"),
                doc.get("year_current"),
            )
            # Prefer explicit cover period (year ended)
            if cover.get("period"):
                cover_hdr["period"] = cover.get("period")
            r = _write_header(ws, cover_hdr, 0)
            ws.write(r, 0, cover.get("subtitle") or "", fmt_sub)
            ws.write(r + 2, 0, cover.get("disclaimer") or "", fmt_disc)
            ws.write(r + 5, 0, _("Contents"), fmt_sub)
            r = r + 6
            for ch in other_chapters:
                ws.write(r, 0, ch.get("title") or "", fmt_meta)
                r += 1
            _write_signatory(ws, r, 0)

        # --- One sheet per chapter (stable short names for cross-sheet links) ---
        sheet_aliases = {
            "pl": "PL",
            "bs": "BS",
            "tb": "TB",
            "equity": "Equity",
            "cashflow": "CashFlow",
            "fixed_assets": "PPE",
            "notes": "Notes",
        }
        link_map = {}
        for ch in other_chapters:
            sheet_idx += 1
            ch_key = (ch.get("key") or "").strip()
            alias = sheet_aliases.get(ch_key) or (ch.get("title") or ch_key or "Sec")
            sheet_name = _unique_sheet("%02d_%s" % (sheet_idx, alias))
            ws = wb.add_worksheet(sheet_name)
            kind = ch.get("kind")
            header = ch.get("header") or self._afg_print_header(
                ch.get("title") or "", ch.get("col_prior"), ch.get("col_current")
            )
            # Prefer full statement titles on the sheet header
            if ch_key == "pl":
                header = dict(header, report_name=_("Statement of Profit or Loss"))
            row_i = _write_header(ws, header, 0)

            if kind == "notes":
                ws.set_column(0, 0, 28)
                ws.set_column(1, 1, 80)
                ws.write(row_i, 0, _("Note"), fmt_hdr)
                ws.write(row_i, 1, _("Disclosure"), fmt_hdr)
                row_i += 1
                for note in ch.get("notes") or []:
                    body = re.sub(r"<[^>]+>", " ", note.get("body") or "")
                    body = re.sub(r"\s+", " ", body).strip()
                    ws.write(row_i, 0, note.get("title") or "", fmt_label_b)
                    ws.write(row_i, 1, body, fmt_label)
                    row_i += 1
                _write_signatory(ws, row_i, 1)
                continue

            if kind == "ppe_matrix":
                ppe = ch.get("ppe") or {}
                cats = ppe.get("categories") or []
                n_cols = len(cats) + 2  # Particulars + cats + Total
                ws.set_column(0, 0, 32)
                for col in range(1, n_cols):
                    ws.set_column(col, col, 14)
                for block in ppe.get("blocks") or []:
                    if block.get("is_section"):
                        ws.write(row_i, 0, block.get("title") or "", fmt_block)
                        row_i += 2
                        continue
                    ws.write(row_i, 0, block.get("title") or "", fmt_block)
                    row_i += 1
                    ws.write(row_i, 0, _("Particulars"), fmt_hdr)
                    for c, name in enumerate(cats, start=1):
                        ws.write(row_i, c, name, fmt_hdr)
                    ws.write(row_i, len(cats) + 1, _("Total"), fmt_hdr)
                    row_i += 1
                    for prow in block.get("rows") or []:
                        is_tot = bool(prow.get("is_total"))
                        lf = fmt_total if is_tot else fmt_label
                        nf = fmt_num_t if is_tot else fmt_num
                        ws.write(row_i, 0, prow.get("label") or "", lf)
                        cat_vals = list(prow.get("values") or [])
                        first_data_col = 1
                        last_data_col = len(cats)
                        for c, val in enumerate(cat_vals, start=1):
                            if val is None:
                                ws.write(row_i, c, "—", lf)
                            else:
                                ws.write_number(row_i, c, float(val or 0.0), nf)
                        # Total column = SUM of category cells on this row
                        if cats and not any(v is None for v in cat_vals) and cat_vals:
                            c1 = self._afg_xlsx_col_letter(first_data_col)
                            c2 = self._afg_xlsx_col_letter(last_data_col)
                            excel_r = row_i + 1
                            tot_f = "=SUM(%s%s:%s%s)" % (c1, excel_r, c2, excel_r)
                            tot = prow.get("total")
                            ws.write_formula(
                                row_i, len(cats) + 1, tot_f, nf, float(tot or 0.0)
                            )
                        else:
                            tot = prow.get("total")
                            if tot is None:
                                ws.write(row_i, len(cats) + 1, "—", lf)
                            else:
                                ws.write_number(row_i, len(cats) + 1, float(tot or 0.0), nf)
                        row_i += 1
                    row_i += 2
                _write_signatory(ws, row_i, max(2, len(cats) + 1))
                continue

            if kind == "tb_face":
                tb_cols = list(ch.get("tb_columns") or [])
                if not tb_cols:
                    tb_cols = [ch.get("col_prior") or "", ch.get("col_current") or ""]
                n_amt = max(len(tb_cols), 1)
                ws.set_column(0, 0, 6)
                ws.set_column(1, 1, 52)
                for c in range(n_amt):
                    ws.set_column(2 + c, 2 + c, 14)
                ws.write(row_i, 0, _("LG"), fmt_hdr)
                ws.write(row_i, 1, _("Description"), fmt_hdr)
                for c, lab in enumerate(tb_cols):
                    ws.write(row_i, 2 + c, lab or "", fmt_hdr)
                row_i += 1
                last_col = 1 + n_amt
                for row in ch.get("rows") or []:
                    is_banner = bool(row.get("is_section_banner"))
                    is_tot = bool(row.get("is_total"))
                    is_bold = bool(row.get("bold")) or is_banner
                    lf = fmt_total if is_tot else (fmt_label_b if is_bold else fmt_label)
                    nf = fmt_num_t if is_tot else (fmt_num_b if is_bold else fmt_num)
                    if is_banner:
                        if n_amt >= 1:
                            ws.merge_range(
                                row_i, 0, row_i, last_col,
                                row.get("label_raw") or row.get("label") or "",
                                fmt_label_b,
                            )
                        else:
                            ws.write(row_i, 0, row.get("label_raw") or row.get("label") or "", fmt_label_b)
                        row_i += 1
                        continue
                    lvl = int(row.get("level") or 0)
                    pad = "    " if lvl >= 3 else ""
                    ws.write(row_i, 0, row.get("lg") or "", lf)
                    ws.write(row_i, 1, pad + (row.get("label_raw") or row.get("label") or ""), lf)
                    amts = list(row.get("tb_amounts") or [])
                    if not amts and (row.get("prior") is not None or row.get("current") is not None):
                        amts = [row.get("prior"), row.get("current")]
                    while len(amts) < n_amt:
                        amts.append(None)
                    for c in range(n_amt):
                        val = amts[c]
                        if val is None:
                            ws.write(row_i, 2 + c, "—", lf)
                        else:
                            ws.write_number(row_i, 2 + c, float(val or 0.0), nf)
                    row_i += 1
                _write_signatory(ws, row_i, last_col)
                continue

            if kind == "equity_soce":
                soce = ch.get("soce") or {}
                cols = list(soce.get("columns") or [])
                years_desc = bool(ch.get("years_descending"))
                yp = str(soce.get("year_prior") or ch.get("col_prior") or "")
                yc = str(soce.get("year_current") or ch.get("col_current") or "")
                y1, y2 = (yc, yp) if years_desc else (yp, yc)
                n_amt = len(cols) * 2 + 2
                ws.set_column(0, 0, 28)
                for c in range(1, n_amt + 1):
                    ws.set_column(c, c, 12)
                # Header row 1: category names spanning 2 year cols
                ws.write(row_i, 0, _("Particulars"), fmt_hdr)
                col_i = 1
                for scol in cols:
                    if col_i + 1 <= n_amt:
                        ws.merge_range(
                            row_i, col_i, row_i, col_i + 1,
                            scol.get("name") or "", fmt_hdr,
                        )
                    else:
                        ws.write(row_i, col_i, scol.get("name") or "", fmt_hdr)
                    col_i += 2
                if col_i + 1 <= n_amt:
                    ws.merge_range(row_i, col_i, row_i, col_i + 1, _("Total"), fmt_hdr)
                else:
                    ws.write(row_i, col_i, _("Total"), fmt_hdr)
                row_i += 1
                # Header row 2: years under each category
                ws.write(row_i, 0, "", fmt_hdr)
                col_i = 1
                for _scol in cols:
                    ws.write(row_i, col_i, y1, fmt_hdr)
                    ws.write(row_i, col_i + 1, y2, fmt_hdr)
                    col_i += 2
                ws.write(row_i, col_i, y1, fmt_hdr)
                ws.write(row_i, col_i + 1, y2, fmt_hdr)
                row_i += 1
                for srow in soce.get("rows") or []:
                    is_bold = bool(srow.get("bold"))
                    lf = fmt_total if is_bold else fmt_label
                    nf = fmt_num_t if is_bold else fmt_num
                    ws.write(row_i, 0, srow.get("label") or "", lf)
                    col_i = 1
                    for scol in cols:
                        cell = (srow.get("cells") or {}).get(scol.get("key")) or {}
                        v1 = cell.get("current") if years_desc else cell.get("prior")
                        v2 = cell.get("prior") if years_desc else cell.get("current")
                        for val in (v1, v2):
                            if val is None:
                                ws.write(row_i, col_i, "—", lf)
                            else:
                                ws.write_number(row_i, col_i, float(val or 0.0), nf)
                            col_i += 1
                    stot = srow.get("total") or {}
                    t1 = stot.get("current") if years_desc else stot.get("prior")
                    t2 = stot.get("prior") if years_desc else stot.get("current")
                    for val in (t1, t2):
                        if val is None:
                            ws.write(row_i, col_i, "—", lf)
                        else:
                            ws.write_number(row_i, col_i, float(val or 0.0), nf)
                        col_i += 1
                    row_i += 1
                _write_signatory(ws, row_i, max(2, n_amt))
                continue

            # statement / cashflow / tb — amounts as Excel SUM formulas + cross-sheet links
            period_labs = list(ch.get("period_labels") or [])
            if not period_labs:
                if ch.get("hide_comparative"):
                    period_labs = [ch.get("col_current") or ""]
                else:
                    period_labs = [ch.get("col_prior") or "", ch.get("col_current") or ""]
            n_period = max(len(period_labs), 1)
            ws.set_column(0, 0, 6)
            ws.set_column(1, 1, 52)
            for c in range(n_period):
                ws.set_column(2 + c, 2 + c, 14)
            has_remark = kind == "cashflow"
            if has_remark:
                ws.set_column(2 + n_period, 2 + n_period, 40)
            ws.write(row_i, 0, _("LG"), fmt_hdr)
            ws.write(row_i, 1, _("Description"), fmt_hdr)
            for c, lab in enumerate(period_labs):
                ws.write(row_i, 2 + c, lab or "", fmt_hdr)
            if has_remark:
                ws.write(row_i, 2 + n_period, _("Remark"), fmt_hdr)
            row_i += 1
            # Tag CY P&L on BS to pull Net Profit from PL sheet
            stmt_rows = []
            for row in ch.get("rows") or []:
                r = dict(row)
                if ch_key == "bs" and (r.get("type_key") or "") == "cy_pnl":
                    r["xlsx_link_key"] = "pl_net_profit"
                stmt_rows.append(r)
            if n_period <= 2 and not ch.get("period_labels"):
                row_i, link_map = self._afg_xlsx_write_statement_block(
                    ws, stmt_rows, row_i,
                    fmt_label, fmt_label_b, fmt_total,
                    fmt_num, fmt_num_b, fmt_num_t,
                    has_remark=has_remark,
                    sheet_name=sheet_name,
                    chapter_key=ch_key,
                    link_map=link_map,
                )
            else:
                for row in stmt_rows:
                    is_banner = bool(row.get("is_section_banner"))
                    is_tot = bool(row.get("is_total"))
                    is_bold = bool(row.get("bold")) or is_banner
                    lf = fmt_total if is_tot else (fmt_label_b if is_bold else fmt_label)
                    nf = fmt_num_t if is_tot else (fmt_num_b if is_bold else fmt_num)
                    if is_banner:
                        ws.merge_range(
                            row_i, 0, row_i, 1 + n_period,
                            row.get("label_raw") or row.get("label") or "",
                            fmt_label_b,
                        )
                        row_i += 1
                        continue
                    lvl = int(row.get("level") or 0)
                    pad = "    " if lvl >= 3 else ""
                    ws.write(row_i, 0, row.get("lg") or "", lf)
                    ws.write(row_i, 1, pad + (row.get("label_raw") or row.get("label") or ""), lf)
                    pam = list(row.get("period_amounts") or [])
                    if not pam:
                        if n_period == 1:
                            pam = [row.get("current")]
                        else:
                            pam = [row.get("prior"), row.get("current")]
                    while len(pam) < n_period:
                        pam.append(None)
                    pam = pam[:n_period]
                    for c, val in enumerate(pam):
                        if val is None:
                            ws.write(row_i, 2 + c, "—", lf)
                        else:
                            ws.write_number(row_i, 2 + c, float(val or 0.0), nf)
                    if has_remark:
                        ws.write(row_i, 2 + n_period, row.get("remark") or "", lf)
                    row_i += 1
            _write_signatory(ws, row_i, 2 + n_period if has_remark else 1 + n_period)

        # Optional index sheet documenting cross-sheet links
        if link_map:
            ws = wb.add_worksheet(_unique_sheet("99_Links"))
            ws.set_column(0, 0, 28)
            ws.set_column(1, 1, 40)
            ws.write(0, 0, _("Cross-sheet anchors"), fmt_sub)
            ws.write(1, 0, _("Key"), fmt_hdr)
            ws.write(1, 1, _("Cell"), fmt_hdr)
            r = 2
            for key in sorted(link_map.keys(), key=lambda k: (str(k[0]), str(k[1]))):
                ws.write(r, 0, "%s / %s" % (key[0], key[1]), fmt_label)
                ws.write(r, 1, link_map[key], fmt_label)
                r += 1

        wb.close()
        data = output.getvalue()
        if self.env.context.get("afg_return_xlsx_bytes"):
            return data
        att = self.env["ir.attachment"].create({
            "name": "Audited_Financials_%s_%s.xlsx" % (self.id, self.year_current),
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % att.id, "target": "self"}

    def action_export_audit_docx(self, max_level=None):
        self.ensure_one()
        self._afg_set_print_scope("audit")
        export_pack = self._afg_resolve_export_report_pack(max_level)
        gate = self._afg_assert_l1_print_allowed(export_pack, export_kind="docx")
        if gate:
            return gate
        self._afg_persist_print_options(export_pack)
        doc = self.with_context(
            afg_export_max_level=export_pack,
            afg_years_descending=self._afg_years_descending(),
        )._afg_build_print_chapters()
        statutory = self._afg_statutory_docx_action(doc)
        if statutory:
            return statutory
        cover = doc.get("cover") or {}
        yp = doc.get("year_prior")
        yc = doc.get("year_current")
        sign_label = doc.get("signatory_label") or _("Authorized Signatory")

        def _esc(val):
            return html_lib.escape(str(val or ""))

        def _hdr_html(header):
            header = header or {}
            return (
                "<div class='rpt-hdr'>"
                "<div class='co'>%s</div>"
                "<div class='rn'>%s</div>"
                "<div class='pd'>%s</div>"
                "</div>"
            ) % (
                _esc(header.get("company") or ""),
                _esc(header.get("report_name") or ""),
                _esc(header.get("period") or ""),
            )

        def _sign_html():
            sig = doc.get("signatory") or cover.get("signatory") or self._afg_signatory_block()
            imgs = []
            if sig.get("stamp"):
                imgs.append(
                    "<img class='afg-stamp' alt='Company stamp' style='%s' "
                    "src='%s'/>"
                    % (
                        sig.get("stamp_style") or "max-height:96pt;max-width:96pt;",
                        sig.get("stamp_src")
                        or ("data:image/png;base64,%s" % sig.get("stamp")),
                    )
                )
            if sig.get("signature"):
                imgs.append(
                    "<img class='afg-signature' alt='Authorized signature' style='%s' "
                    "src='%s'/>"
                    % (
                        sig.get("signature_style") or "max-height:64pt;max-width:140pt;",
                        sig.get("signature_src")
                        or ("data:image/png;base64,%s" % sig.get("signature")),
                    )
                )
            media = (
                "<div class='sign-media'>%s</div>" % "".join(imgs)
                if imgs else "<div class='uline'></div>"
            )
            return (
                "<div class='sign'>"
                "<div class='for'>%s</div>"
                "<div class='entity'>%s</div>"
                "%s"
                "<div class='lab'>%s</div>"
                "</div>"
            ) % (
                _esc(sig.get("for_line") or _("For and on behalf of")),
                _esc(sig.get("entity") or ""),
                media,
                _esc(sig.get("signatory_label") or sign_label or _("Authorized Signatory")),
            )

        cover_hdr = self._afg_print_header(
            cover.get("title") or _("Financial Statements"), yp, yc
        )
        if cover.get("period"):
            cover_hdr["period"] = cover.get("period")
        # Match PDF page setup (A4 + margins) and table/sign styles to avoid blank Word pages.
        parts = [
            "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
            "xmlns:w='urn:schemas-microsoft-com:office:word' "
            "xmlns='http://www.w3.org/TR/REC-html40'>",
            "<head><meta charset='utf-8'/>",
            "<!--[if gte mso 9]><xml><w:WordDocument>"
            "<w:View>Print</w:View><w:Zoom>100</w:Zoom>"
            "</w:WordDocument></xml><![endif]-->",
            "<style>",
            "@page Section1 { size: 210mm 297mm; margin: 15mm 12mm 15mm 12mm; }",
            "div.Section1 { page: Section1; }",
            "body{font-family:Arial,DejaVu Sans,sans-serif;font-size:10pt;color:#1a1a1a;}",
            ".rpt-hdr{margin:0 0 10pt 0;}",
            ".rpt-hdr .co{font-size:13pt;font-weight:bold;text-transform:uppercase;margin:0;}",
            ".rpt-hdr .rn{font-size:11pt;font-weight:bold;margin:2pt 0 0 0;}",
            ".rpt-hdr .pd{font-size:10pt;font-weight:bold;margin:2pt 0 0 0;}",
            "h3{font-size:11pt;color:#344d5f;margin:10pt 0 4pt 0;}",
            ".block-title{font-size:10pt;font-weight:bold;color:#1e3a5f;margin:12pt 0 4pt 0;}",
            ".disc{font-size:9.5pt;font-weight:normal;font-style:italic;color:#555555;"
            "text-align:left;border-top:1px solid #d0d0d0;"
            "padding-top:10pt;margin:16pt 0 18pt 0;background:none;}",
            "table{width:100%;border-collapse:collapse;font-size:8.5pt;margin:4pt 0 12pt 0;}",
            "table.o_afg_ppe,table.o_afg_soce{table-layout:fixed;width:100%;}",
            "table.o_afg_ppe th.amt,table.o_afg_ppe td.amt,"
            "table.o_afg_soce th.amt,table.o_afg_soce td.amt{white-space:nowrap;}",
            "th,td{border:1px solid #c5cdd4;padding:3pt 4pt;vertical-align:top;}",
            "th{background:#344d5f;color:#fff;text-align:center;}",
            ".amt{text-align:right;white-space:nowrap;}",
            "table.o_afg_tb_face,table.o_afg_many_amts{font-size:8pt;}",
            "table.o_afg_tb_face .amt,table.o_afg_many_amts .amt{"
            "min-width:0;white-space:normal;word-break:break-word;"
            "font-size:7pt;line-height:1.15;padding:2pt;}",
            "table.o_afg_tb_face td:nth-child(2),table.o_afg_many_amts td:nth-child(2){"
            "font-size:8pt;line-height:1.2;overflow-wrap:break-word;word-break:break-word;}",
            "tr.bold td{font-weight:bold;background:#e8f4f8;}",
            "tr.total td{font-weight:bold;background:#d9eaf2;"
            "border-top:2px solid #344d5f;border-bottom:2px solid #344d5f;}",
            ".sign{margin-top:10pt;page-break-inside:avoid;}",
            ".sign .for{color:#1e3a5f;margin-bottom:3pt;}",
            ".sign .entity{font-weight:bold;text-transform:uppercase;margin-bottom:4pt;}",
            ".sign .sign-media{margin:4pt 0 3pt 0;page-break-inside:avoid;}",
            ".sign .afg-stamp{max-height:96pt;max-width:96pt;margin-right:12pt;vertical-align:middle;}",
            ".sign .afg-signature{max-height:64pt;max-width:140pt;vertical-align:middle;}",
            ".sign .uline{border-bottom:2px solid #000;width:160pt;margin-bottom:2pt;}",
            ".sign .lab{font-weight:bold;}",
            "</style></head><body><div class='Section1'>",
        ]
        chapters_list = list(doc.get("chapters") or [])
        sign_last = bool(doc.get("sign_last_only"))
        n_ch = len(chapters_list)
        first = True
        for idx, ch in enumerate(chapters_list):
            def _ch_sign(i=idx):
                if sign_last and i < n_ch - 1:
                    return ""
                return _sign_html()
            if not first:
                # Explicit Word page break (CSS-only breaks often create blank pages)
                parts.append('<br clear="all" style="page-break-before:always"/>')
            first = False
            header = ch.get("header") or self._afg_print_header(
                ch.get("title") or "", ch.get("col_prior") or yp, ch.get("col_current") or yc
            )
            parts.append("<div class='chapter'>")
            parts.append(_hdr_html(header))
            kind = ch.get("kind")
            if kind == "cover":
                cov = ch.get("cover") or cover or {}
                if cov.get("subtitle"):
                    parts.append("<p>%s</p>" % _esc(cov.get("subtitle") or ""))
                if cov.get("disclaimer"):
                    parts.append(
                        "<div class='disc'>%s</div>" % _esc(cov.get("disclaimer") or "")
                    )
                parts.append("<h3>%s</h3><ul>" % _esc(_("Contents")))
                for t in ch.get("contents_titles") or []:
                    if t:
                        parts.append("<li>%s</li>" % _esc(t))
                parts.append("</ul></div>")
                continue
            if kind == "notes":
                for note in ch.get("notes") or []:
                    parts.append(
                        "<h3>%s</h3>%s"
                        % (_esc(note.get("title") or ""), note.get("body") or "")
                    )
                parts.append(_ch_sign())
                parts.append("</div>")
                continue
            if kind == "ppe_matrix":
                ppe = ch.get("ppe") or {}
                cats = list(ppe.get("categories") or [])
                n_cat = max(len(cats), 1)
                cat_w = 60.0 / n_cat
                is_ar = bool(doc.get("arabic") or doc.get("rtl")) or (
                    self._afg_export_report_pack() == 5
                )
                lab_part = self._afg_ar("Particulars") if is_ar else "Particulars"
                lab_tot = self._afg_ar("Total") if is_ar else "Total"
                for block in ppe.get("blocks") or []:
                    if block.get("is_section"):
                        parts.append("<h2>%s</h2>" % _esc(block.get("title") or ""))
                        continue
                    parts.append(
                        "<div class='block-title'>%s</div>" % _esc(block.get("title") or "")
                    )
                    parts.append(
                        "<table class='o_afg_ppe' style='table-layout:fixed;width:100%%;'>"
                        "<colgroup><col style='width:28%%;'/>"
                    )
                    for _cname in cats:
                        parts.append("<col style='width:%.4f%%;'/>" % cat_w)
                    parts.append("<col style='width:12%%;'/></colgroup>")
                    parts.append("<tr><th>%s</th>" % _esc(lab_part))
                    for name in cats:
                        parts.append("<th class='amt'>%s</th>" % _esc(name))
                    parts.append("<th class='amt'>%s</th></tr>" % _esc(lab_tot))
                    for prow in block.get("rows") or []:
                        cls_r = "total" if prow.get("is_total") else ""
                        disp_vals = list(prow.get("values_disp") or [])
                        if not disp_vals:
                            disp_vals = [
                                None if v is None else self._afg_fmt_amt(v)
                                for v in (prow.get("values") or [])
                            ]
                        while len(disp_vals) < len(cats):
                            disp_vals.append(None)
                        disp_vals = disp_vals[: len(cats)]
                        cells = "".join(
                            "<td class='amt'>%s</td>" % (
                                "—" if v is None else _esc(v)
                            )
                            for v in disp_vals
                        )
                        tot_s = prow.get("total_disp")
                        if tot_s is None:
                            tot = prow.get("total")
                            tot_s = "—" if tot is None else self._afg_fmt_amt(tot)
                        elif prow.get("total") is None:
                            tot_s = "—"
                        parts.append(
                            "<tr class='%s'><td>%s</td>%s<td class='amt'>%s</td></tr>"
                            % (
                                cls_r,
                                _esc(prow.get("label") or ""),
                                cells,
                                _esc(tot_s) if tot_s != "—" else "—",
                            )
                        )
                    parts.append("</table>")
                parts.append(_ch_sign())
                parts.append("</div>")
                continue

            if kind == "validation":
                parts.append(
                    "<p><strong>Overall status: %s</strong></p>"
                    % _esc(ch.get("overall") or "PASS")
                )
                if (ch.get("overall") or "") == "FAIL":
                    parts.append(
                        "<p style='color:#a94442;font-weight:bold;'>"
                        "FINANCIAL STATEMENTS NOT RECONCILED</p>"
                    )
                parts.append(
                    "<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>"
                )
                for v in ch.get("validations") or []:
                    if not isinstance(v, dict):
                        continue
                    parts.append(
                        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                        % (
                            _esc(v.get("name") or ""),
                            _esc(v.get("status") or ""),
                            _esc(v.get("detail") or ""),
                        )
                    )
                parts.append("</table>")
                parts.append(_ch_sign())
                parts.append("</div>")
                continue

            if kind == "fs_recon":
                recon = ch.get("recon") or {}
                parts.append(
                    "<table><tr><th>Type</th>"
                    "<th class='amt'>TB Prior</th><th class='amt'>Adj Prior</th>"
                    "<th class='amt'>FS Prior</th><th class='amt'>TB Current</th>"
                    "<th class='amt'>Adj Current</th><th class='amt'>FS Current</th>"
                    "<th>OK</th></tr>"
                )
                for rr in recon.get("rows") or []:
                    if not isinstance(rr, dict):
                        continue
                    parts.append(
                        "<tr><td>%s</td>"
                        "<td class='amt'>%s</td><td class='amt'>%s</td>"
                        "<td class='amt'>%s</td><td class='amt'>%s</td>"
                        "<td class='amt'>%s</td><td class='amt'>%s</td>"
                        "<td>%s</td></tr>"
                        % (
                            _esc(rr.get("label") or ""),
                            _esc("%.2f" % (rr.get("tb_prior") or 0.0)),
                            _esc("%.2f" % (rr.get("adj_prior") or 0.0)),
                            _esc("%.2f" % (rr.get("fs_prior") or 0.0)),
                            _esc("%.2f" % (rr.get("tb_current") or 0.0)),
                            _esc("%.2f" % (rr.get("adj_current") or 0.0)),
                            _esc("%.2f" % (rr.get("fs_current") or 0.0)),
                            "PASS" if rr.get("ok") else "FAIL",
                        )
                    )
                parts.append("</table>")
                gaps = recon.get("ledger_gaps") or []
                if gaps:
                    parts.append("<h3>Unmapped CoA ledgers included on FS</h3>")
                    parts.append(
                        "<table><tr><th>Section</th><th>Ledger</th>"
                        "<th class='amt'>Prior</th><th class='amt'>Current</th></tr>"
                    )
                    for lgrow in gaps:
                        if not isinstance(lgrow, dict):
                            continue
                        parts.append(
                            "<tr><td>%s</td><td>%s</td>"
                            "<td class='amt'>%s</td><td class='amt'>%s</td></tr>"
                            % (
                                _esc(lgrow.get("section") or ""),
                                _esc(lgrow.get("label") or ""),
                                _esc("%.2f" % (lgrow.get("prior") or 0.0)),
                                _esc("%.2f" % (lgrow.get("current") or 0.0)),
                            )
                        )
                    parts.append("</table>")
                parts.append(_ch_sign())
                parts.append("</div>")
                continue

            if kind == "equity_soce":
                soce = ch.get("soce") or {}
                cols = list(soce.get("columns") or [])
                years_desc = bool(ch.get("years_descending"))
                yp_s = str(soce.get("year_prior") or ch.get("col_prior") or yp)
                yc_s = str(soce.get("year_current") or ch.get("col_current") or yc)
                y1, y2 = (yc_s, yp_s) if years_desc else (yp_s, yc_s)
                n_amt = max(len(cols) * 2 + 2, 2)
                amt_w = 72.0 / float(n_amt)
                is_ar = bool(doc.get("arabic") or doc.get("rtl")) or (
                    self._afg_export_report_pack() == 5
                )
                lab_part = self._afg_ar("Particulars") if is_ar else "Particulars"
                lab_tot = self._afg_ar("Total") if is_ar else "Total"
                parts.append(
                    "<table class='o_afg_soce' style='table-layout:fixed;width:100%%;'>"
                    "<colgroup><col style='width:28%%;'/>"
                )
                for _i in range(n_amt):
                    parts.append("<col style='width:%.4f%%;'/>" % amt_w)
                parts.append("</colgroup>")
                parts.append("<tr><th rowspan='2'>%s</th>" % _esc(lab_part))
                for scol in cols:
                    parts.append(
                        "<th class='amt' colspan='2'>%s</th>"
                        % _esc(scol.get("name") or "")
                    )
                parts.append(
                    "<th class='amt' colspan='2'>%s</th></tr>" % _esc(lab_tot)
                )
                parts.append("<tr>")
                for _scol in cols:
                    parts.append("<th class='amt'>%s</th><th class='amt'>%s</th>" % (
                        _esc(y1), _esc(y2),
                    ))
                parts.append(
                    "<th class='amt'>%s</th><th class='amt'>%s</th></tr>"
                    % (_esc(y1), _esc(y2))
                )
                for srow in soce.get("rows") or []:
                    cls_r = "total" if srow.get("bold") else ""
                    cells_html = []
                    for scol in cols:
                        cell = (srow.get("cells") or {}).get(scol.get("key")) or {}
                        v1 = cell.get("current") if years_desc else cell.get("prior")
                        v2 = cell.get("prior") if years_desc else cell.get("current")
                        cells_html.append(
                            "<td class='amt'>%s</td><td class='amt'>%s</td>"
                            % (
                                _esc(self._afg_fmt_amt(v1)),
                                _esc(self._afg_fmt_amt(v2)),
                            )
                        )
                    stot = srow.get("total") or {}
                    t1 = stot.get("current") if years_desc else stot.get("prior")
                    t2 = stot.get("prior") if years_desc else stot.get("current")
                    cells_html.append(
                        "<td class='amt'>%s</td><td class='amt'>%s</td>"
                        % (
                            _esc(self._afg_fmt_amt(t1)),
                            _esc(self._afg_fmt_amt(t2)),
                        )
                    )
                    parts.append(
                        "<tr class='%s'><td>%s</td>%s</tr>"
                        % (cls_r, _esc(srow.get("label") or ""), "".join(cells_html))
                    )
                parts.append("</table>")
                parts.append(_ch_sign())
                parts.append("</div>")
                continue

            has_remark = kind == "cashflow"
            if kind == "tb_face":
                tb_cols = list(ch.get("tb_columns") or [])
                tb_meta = list(ch.get("tb_column_meta") or [])
                if not tb_cols:
                    tb_cols = [ch.get("col_prior") or yp, ch.get("col_current") or yc]
                parts.append(
                    "<table class='o_afg_tb_face o_afg_many_amts'>"
                    "<colgroup><col style='width:7%'/><col style='width:41%'/>"
                )
                for _lab in tb_cols:
                    parts.append("<col style='width:10%'/>")
                parts.append("</colgroup><tr><th>LG</th><th>Description</th>")
                if tb_meta:
                    for meta in tb_meta:
                        lab = _esc(meta.get("label") or "")
                        year = meta.get("year") or ""
                        if year:
                            parts.append(
                                "<th class='amt'>%s<br/>%s</th>" % (lab, _esc(year))
                            )
                        else:
                            parts.append("<th class='amt'>%s</th>" % lab)
                else:
                    for lab in tb_cols:
                        parts.append("<th class='amt'>%s</th>" % _esc(lab))
                parts.append("</tr>")
                for row in ch.get("rows") or []:
                    if row.get("is_section_banner"):
                        parts.append(
                            "<tr class='bold'><td colspan='%s'>%s</td></tr>"
                            % (
                                2 + len(tb_cols),
                                _esc(row.get("label_raw") or row.get("label") or ""),
                            )
                        )
                        continue
                    cls_r = "total" if row.get("is_total") else ("bold" if row.get("bold") else "")
                    label = row.get("label_raw") or row.get("label") or ""
                    lg = row.get("lg") or ""
                    lvl = int(row.get("level") or 0)
                    pad = "&nbsp;&nbsp;&nbsp;&nbsp;" if lvl >= 3 else ""
                    amts = list(row.get("tb_amounts_disp") or [])
                    if not amts:
                        raw = list(row.get("tb_amounts") or [])
                        if not raw and (row.get("prior") is not None or row.get("current") is not None):
                            raw = [row.get("prior"), row.get("current")]
                        amts = [
                            "—" if v is None else self._afg_fmt_amt(v)
                            for v in raw
                        ]
                    while len(amts) < len(tb_cols):
                        amts.append("—")
                    cells = "".join(
                        "<td class='amt'>%s</td>" % _esc(amts[i] if i < len(amts) else "—")
                        for i in range(len(tb_cols))
                    )
                    parts.append(
                        "<tr class='%s'><td>%s</td><td>%s%s</td>%s</tr>"
                        % (cls_r, _esc(lg), pad, _esc(label), cells)
                    )
                parts.append("</table>")
                parts.append(_ch_sign())
                parts.append("</div>")
                continue

            period_labs = list(ch.get("period_labels") or [])
            if not period_labs:
                if ch.get("hide_comparative"):
                    period_labs = [ch.get("col_current") or yc]
                else:
                    period_labs = [ch.get("col_prior") or yp, ch.get("col_current") or yc]
            parts.append("<table><tr><th>LG</th><th>Description</th>")
            for lab in period_labs:
                parts.append("<th class='amt'>%s</th>" % _esc(lab))
            if has_remark:
                parts.append("<th>Remark</th>")
            parts.append("</tr>")
            for row in ch.get("rows") or []:
                cls_r = "total" if row.get("is_total") else ("bold" if row.get("bold") else "")
                label = row.get("label_raw") or row.get("label") or ""
                lg = row.get("lg") or ""
                lvl = int(row.get("level") or 0)
                pad = "&nbsp;&nbsp;&nbsp;&nbsp;" if lvl >= 3 else ""
                pam_disp = list(row.get("period_amounts_disp") or [])
                if not pam_disp:
                    pam = list(row.get("period_amounts") or [])
                    if not pam:
                        if len(period_labs) == 1:
                            pam = [row.get("current")]
                        else:
                            pam = [row.get("prior"), row.get("current")]
                    pam_disp = [
                        "—" if v is None else self._afg_fmt_amt(v) for v in pam
                    ]
                while len(pam_disp) < len(period_labs):
                    pam_disp.append("—")
                pam_disp = pam_disp[: len(period_labs)]
                cells = "".join(
                    "<td class='amt'>%s</td>" % _esc(pam_disp[i])
                    for i in range(len(period_labs))
                )
                remark_td = (
                    "<td>%s</td>" % _esc(row.get("remark") or "")
                    if has_remark else ""
                )
                parts.append(
                    "<tr class='%s'><td>%s</td><td>%s%s</td>%s%s</tr>"
                    % (cls_r, _esc(lg), pad, _esc(label), cells, remark_td)
                )
            parts.append("</table>")
            parts.append(_ch_sign())
            parts.append("</div>")

        parts.append("</div></body></html>")
        html = "".join(parts).encode("utf-8")
        att = self.env["ir.attachment"].create({
            "name": "Audited_Financials_%s_%s.doc" % (self.id, self.year_current),
            "type": "binary",
            "datas": base64.b64encode(html),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/msword",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % att.id, "target": "self"}

    def _get_audit_report_payload(self):
        self.ensure_one()
        dash = self.afg_dashboard_data()
        if self.env.context.get("afg_simple_print"):
            section_order = ["pl", "bs", "equity"]
        else:
            section_order = ["fta", "pl", "bs", "equity", "cashflow", "fixed_assets", "tb"]
        sections = []
        labels = dash.get("section_labels") or {}
        for key in section_order:
            if key == "cashflow" and (dash.get("schedules") or {}).get("cashflow_statement"):
                continue
            if key == "fixed_assets" and (dash.get("schedules") or {}).get("fixed_assets_recon"):
                continue
            if key == "tb":
                continue  # handled via trial_balance.panels in print builder
            tree = (dash.get("sections") or {}).get(key)
            if tree or key in ("pl", "bs", "equity"):
                sections.append({"key": key, "title": labels.get(key, key), "tree": tree or []})
        return {
            "cover": {
                "title": _("Financial Statements"),
                "subtitle": _(
                    "Prepared based on accounting records and accounting policies adopted by management"
                ),
                "entity": self._afg_print_company_display(),
                "period": self._afg_period_caption_for_print(as_at=False),
                "currency": self.currency_id.name or "AED",
                "disclaimer": _(
                    "These financial statements have been prepared by the management of the Company "
                    "based on its accounting records and are intended for general business, regulatory, "
                    "statutory and management purposes. They are management-prepared financial "
                    "statements and have not been audited."
                ),
            },
            "signatory": self._afg_signatory_block(),
            "version": dash,
            "year_prior": self.year_prior,
            "year_current": self.year_current,
            "sections": sections,
            "notes": dash.get("notes") or [],
            "alerts": dash.get("alerts") or [],
            "validations": dash.get("validations") or [],
            "schedules": dash.get("schedules") or {},
            "trial_balance": dash.get("trial_balance") or {},
            "trial_balance2": dash.get("trial_balance2") or {},
            "hide_comparative": bool(dash.get("hide_comparative")),
            "first_period": bool(dash.get("first_period")),
        }


class AuditedFinancialLine(models.Model):
    _name = "audited.financial.line"
    _description = "Audited Financial Report Line"
    _order = "report_section, sequence, id"

    version_id = fields.Many2one("audited.financial.version", required=True, ondelete="cascade")
    group_id = fields.Many2one("audited.financial.group", ondelete="set null")
    parent_id = fields.Many2one(
        "audited.financial.line",
        string="Parent line",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many("audited.financial.line", "parent_id", string="Child lines")
    level = fields.Integer(
        string="Hierarchy level",
        default=1,
        help="1 = AFG caption, 2 = account group, 3 = ledger; level 4 is company drill-down on the dashboard only.",
    )
    odoo_group_id = fields.Many2one("account.group", string="Odoo account group", ondelete="set null", index=True)
    merged_leaf_account_ids = fields.Char(
        string="Merged ledger account ids",
        help="Comma-separated account.account ids folded into this line (multicompany: same code or same normalized name).",
    )
    account_id = fields.Many2one("account.account", string="Ledger account", ondelete="set null", index=True)
    sequence = fields.Integer(default=10)
    report_section = fields.Selection(AFG_REPORT_SECTION, required=True, index=True)
    label = fields.Char(string="Description", index=True)
    note = fields.Char(string="Note ref.")
    amount_prior = fields.Monetary(string="Prior year", currency_field="currency_id")
    amount_current = fields.Monetary(string="Current year", currency_field="currency_id")
    source_amount_prior = fields.Monetary(string="TB prior", currency_field="currency_id", readonly=True)
    source_amount_current = fields.Monetary(string="TB current", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="version_id.currency_id", store=True, readonly=True)

    def write(self, vals):
        Log = self.env["audited.financial.edit.log"]
        log_vals_list = []
        if not self.env.context.get("skip_afg_audit") and ("amount_prior" in vals or "amount_current" in vals):
            for line in self:
                sens = line.group_id.sensitivity_category if line.group_id else "none"
                if sens and sens != "none" and not self.env.context.get("afg_sensitive_ok"):
                    raise UserError(
                        _("This line is in a sensitive IFRS/FTA area (%s). Use the wizard 'Adjust sensitive amount' with a documented reason.")
                        % dict(AFG_SENSITIVITY).get(sens, sens)
                    )
                old_p = line.amount_prior
                old_c = line.amount_current
                new_p = vals.get("amount_prior", old_p)
                new_c = vals.get("amount_current", old_c)
                reason = self.env.context.get("afg_edit_reason") or ""
                if "amount_prior" in vals and new_p != old_p:
                    log_vals_list.append({
                        "version_id": line.version_id.id,
                        "line_id": line.id,
                        "field_name": "amount_prior",
                        "amount_old": old_p,
                        "amount_new": new_p,
                        "reason": reason,
                    })
                if "amount_current" in vals and new_c != old_c:
                    log_vals_list.append({
                        "version_id": line.version_id.id,
                        "line_id": line.id,
                        "field_name": "amount_current",
                        "amount_old": old_c,
                        "amount_new": new_c,
                        "reason": reason,
                    })
        res = super().write(vals)
        if log_vals_list:
            Log.create(log_vals_list)
        return res


class AuditedFinancialNote(models.Model):
    _name = "audited.financial.note"
    _description = "Audited Financial Note"
    _order = "version_id, sequence, id"

    version_id = fields.Many2one("audited.financial.version", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    title = fields.Char(required=True)
    body = fields.Html()


class AuditedFinancialEditLog(models.Model):
    _name = "audited.financial.edit.log"
    _description = "Audited Financial Manual Edit Log"
    _order = "create_date desc, id desc"

    version_id = fields.Many2one("audited.financial.version", required=True, ondelete="cascade")
    line_id = fields.Many2one("audited.financial.line", ondelete="set null")
    field_name = fields.Char()
    amount_old = fields.Monetary(currency_field="currency_id")
    amount_new = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="version_id.currency_id", store=True, readonly=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    reason = fields.Text()
    create_date = fields.Datetime(readonly=True)


class AuditedFinancialAlert(models.Model):
    _name = "audited.financial.alert"
    _description = "Audited Financial Compliance Alert"
    _order = "severity desc, id desc"

    version_id = fields.Many2one("audited.financial.version", required=True, ondelete="cascade")
    alert_type = fields.Selection([("ifrs", "IFRS"), ("fta", "FTA")], required=True, default="ifrs")
    severity = fields.Selection([("info", "Info"), ("warning", "Warning"), ("critical", "Critical")], default="warning")
    title = fields.Char(required=True)
    message = fields.Text()


class AuditedFinancialSensitiveWizard(models.TransientModel):
    _name = "audited.financial.sensitive.wizard"
    _description = "Confirm sensitive AFG adjustment"

    version_id = fields.Many2one("audited.financial.version", required=True)
    line_id = fields.Many2one("audited.financial.line", required=True, domain="[('version_id', '=', version_id)]")
    field_name = fields.Selection([("amount_prior", "Prior year"), ("amount_current", "Current year")], required=True, default="amount_current")
    new_amount = fields.Monetary(currency_field="currency_id", required=True)
    currency_id = fields.Many2one(related="version_id.currency_id", readonly=True)
    reason = fields.Text(string="Justification", required=True)

    @api.onchange("line_id", "field_name")
    def _onchange_line_amount(self):
        if self.line_id and self.field_name:
            self.new_amount = getattr(self.line_id, self.field_name, 0.0) or 0.0

    def action_apply(self):
        self.ensure_one()
        line = self.line_id
        sens = line.group_id.sensitivity_category if line.group_id else "none"
        if sens == "none":
            raise UserError(_("Select a line that belongs to a sensitive AFG category."))
        vals = {self.field_name: self.new_amount}
        line.with_context(afg_sensitive_ok=True, afg_edit_reason=self.reason).write(vals)
        return {"type": "ir.actions.act_window_close"}

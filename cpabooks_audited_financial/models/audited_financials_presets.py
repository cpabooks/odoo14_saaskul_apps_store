# -*- coding: utf-8 -*-
"""Default AFG (L1) preset definitions and keyword rules for auto-mapping chart accounts."""
import re

# Preset order: (code, name, report_section, sequence, sensitivity_category)
# report_section matches audited_financials.AFG_REPORT_SECTION keys
AFG_PRESET_GROUPS = [
    ("AFG_REV", "Revenue", "pl", 10, "revenue"),
    ("AFG_COR", "Cost of revenue", "pl", 20, "cost_of_revenue"),
    ("AFG_SELL", "Selling and distribution expenses", "pl", 30, "none"),
    ("AFG_GNA", "General and administrative expenses", "pl", 40, "none"),
    ("AFG_PAYROLL", "Employee costs", "pl", 50, "none"),
    ("AFG_DEPR_PL", "Depreciation and amortisation (P&L)", "pl", 55, "depreciation"),
    ("AFG_PPE", "Property, plant and equipment", "bs", 10, "fixed_assets"),
    ("AFG_INV", "Inventories", "bs", 20, "none"),
    ("AFG_AR", "Trade and other receivables", "bs", 30, "trade_receivables_payables"),
    ("AFG_PREP", "Deposits, prepayments and other receivables", "bs", 35, "none"),
    ("AFG_CASH", "Cash and cash equivalents", "bs", 40, "cash_bank"),
    ("AFG_EQ", "Owner equity", "bs", 50, "retained_earnings"),
    ("AFG_EOS", "Employees' end of service benefits", "bs", 60, "eos_benefits"),
    ("AFG_AP", "Trade and other payables", "bs", 70, "trade_receivables_payables"),
    ("AFG_TAX", "Tax balances (VAT / corporate tax)", "bs", 75, "tax_payable"),
    ("AFG_REL", "Related party balances", "bs", 80, "related_party"),
    ("AFG_CF", "Cash flow (working classification)", "cashflow", 10, "none"),
    ("AFG_EQ_CHG", "Changes in owner equity (detail)", "equity", 10, "owner_current_account"),
    ("AFG_FIXED", "Property and equipment (register detail)", "fixed_assets", 10, "fixed_assets"),
    ("AFG_UNGRP_PL", "Ungrouped / needs review (profit or loss)", "pl", 9000, "none"),
    ("AFG_UNGRP_BS", "Ungrouped / needs review (balance sheet)", "bs", 9001, "none"),
]

AFG_CODE_TO_SECTION = {code: section for code, _name, section, _seq, _cat in AFG_PRESET_GROUPS}

# Odoo CoA internal_group → which AFG report_section family is allowed.
# Keeps AFG P&L/BS conceptually aligned with Accounting → P&L / Balance Sheet.
_AFG_IG_ALLOWED_SECTIONS = {
    "income": frozenset({"pl"}),
    "expense": frozenset({"pl"}),
    "asset": frozenset({"bs", "fixed_assets", "cashflow"}),
    "liability": frozenset({"bs", "cashflow"}),
    "equity": frozenset({"bs", "equity"}),
}


# Rules evaluated in order: first matching rule with score > 0 wins (higher priority first).
# Each entry: (code, priority, internal_groups_tuple_or_None, keyword_tuple)
# internal_groups: None = do not filter by account.internal_group
AFG_MATCH_RULES = [
    # Tax / VAT — before generic payables (BS balances + P&L tax charge)
    ("AFG_TAX", 400, ("liability", "asset", "expense"), (
        "vat", "gst", "tax payable", "tax receivable", "corporate tax", "income tax",
        "withholding", "excise", "taxes paid", "taxes received",
    )),
    ("AFG_REL", 390, ("asset", "liability", "equity"), (
        "related party", "shareholder", "director loan", "intercompany", " ic0",
    )),
    # BS EOS provision / liability only — expense charge stays on P&L (see AFG_PAYROLL)
    ("AFG_EOS", 380, ("liability",), (
        "end of service", "gratuity provision", "eos provision", "indemnity provision",
        "eos payable", "gratuity payable", "eos liability",
        "provision for air ticket", "provision for leave", "leave salary provision",
    )),
    ("AFG_CASH", 360, ("asset",), (
        "bank", "petty cash", "cash on hand", "cash in hand", "liquidity",
    )),
    ("AFG_PREP", 350, ("asset",), (
        "prepaid", "prepayment", "deposit rent", "deposit -", "deposit —", "advance",
        "rent- deposit", "rent deposit", "rental deposit", "security deposit", "deposit",
        "pdc", "adv. employee", "adv employee", "advance employee", "outstanding payment",
    )),
    ("AFG_AR", 340, ("asset",), (
        "receivable", "accounts receivable", "debtors", "pdc receivable", "staff receivable",
        "provision for doubtful", "doubtful debt", "provision doubtful",
    )),
    ("AFG_AP", 330, ("liability",), (
        "payable", "accounts payable", "creditors", "accrued", "accrual",
        "vehicle loan", "loan payable",
    )),
    ("AFG_INV", 320, ("asset",), (
        "inventory", "stock", "consumables", "work in progress", "work in progrees", "wip",
        "stock valuation",
    )),
    ("AFG_PPE", 310, ("asset",), (
        "faa -", "motor vehicle", "furniture", "computer", "software", "it equipment",
        "tools", "equipment", "leasehold", "accumulated depreciation", "acc. depn",
        "fixed asset", "property, plant", "land & building", "building", " land",
    )),
    ("AFG_EQ", 300, ("equity",), (
        "capital", "owner", "share premium", "statutory reserve", "retained",
        "current year earning", "current year result", "previous year", "partnership",
        "drawings", "undistributed", "reserve account", "current account",
        "partner current", "owner current",
    )),
    ("AFG_EQ_CHG", 290, ("equity",), (
        "movement in equity", "capital contribution",
    )),
    ("AFG_DEPR_PL", 285, ("expense", "income"), (
        "depreciation", "amortisation", "amortization",
    )),
    ("AFG_REV", 280, ("income",), (
        "sales", "revenue", "service income", "operating revenue", "turnover",
        "other income", "gain on", "cash difference gain", "discount on sales",
        "loss on", "cash difference loss",
    )),
    # CPABooks direct-cost prefix (DC-/COS-) before generic selling rules
    ("AFG_COR", 275, ("expense",), (
        "dc -", "cos -", "cost of sales", "cogs", "cost of goods", "cost of material",
        "direct material", "direct shop", "direct labor", "direct labour",
        "manufacturing", "material cost", "sub-contractor", "sub contractor",
        "stock input", "stock output",
    )),
    ("AFG_SELL", 265, ("expense",), (
        "sad -", "sampling", "promotional", "commission", "delivery", "freight",
        "transport", "advertisement", "publicity", "marketing", "talabat",
        "platform fee", "distribution",
    )),
    # CPABooks GA-* admin prefix — before CTO/CTD staff rules so GA rent stays G&A
    ("AFG_GNA", 255, ("expense",), (
        "ga -", "office rent", "shop rent", "rent expense", "rent - office", "rent - warehouse",
        "rent shop", "trade license", "license", "permit", "utility", "water", "electricity",
        "cleaning", "stationery", "professional fee", "legal fee", "audit fee", "bank charge",
        "insurance", "general & admin", "general and admin", "g&a", "telephone", "internet",
        "loss on", "write off", "vehicle expense", "vehicle fuel", "vehicle repair",
        "interest expense", "fine expense", "courier", "hosting", "bookkeeping",
        "repair & maintenance", "security & guard", "gifts & donation", "convoyance",
        "meal & refreshment", "hotel & travelling", "po box", "software subscription",
        "it & networking", "office various", "office maintenance", "sponsorship",
        "income tax",
    )),
    # P&L employee / EOS expense charge (CTO-/CTD-/CTC- prefixes)
    ("AFG_PAYROLL", 250, ("expense",), (
        "cto -", "ctd -", "ctc -", "salary", "wages", "payroll", "staff cost", "leave salary",
        "end of service", "eos indemnity", "eos expense", "gratuity expense", "gratuity",
        "medical insurance", "accommodation", "visa expense", "director", "wps",
        "air ticket", "training", "uniform", "workmen compensation", "school allow",
        "schooling fees", "transportation allowance",
    )),
]


def _afg_section_ok_for_internal_group(section, internal_group):
    """True if mapping this account.internal_group into report_section matches Odoo P&L/BS."""
    if not section:
        return True
    allowed = _AFG_IG_ALLOWED_SECTIONS.get(internal_group)
    if allowed is None:
        return True
    return section in allowed


def _account_match_code(account, rules=AFG_MATCH_RULES):
    """Return best-matching AFG preset code for an account.account record.

    Income/expense accounts never map to Balance Sheet presets (and vice versa),
    so AFG Statement of Profit or Loss stays data-aligned with Accounting → P&L.
    """
    hay = ("%s %s" % (account.code or "", account.name or "")).lower()
    ig = account.internal_group
    # Same prefixes as Default P&L (SAD / GA / CTO / DC) — even if internal_group is empty.
    prefix = _account_name_prefix_code(account)
    if prefix:
        return prefix
    # CoA type Cost of Sales → Cost of revenue (no per-ledger mapping).
    # SAD- prefix stays selling even if the type was set to Cost of Sales.
    if (
        ig == "expense"
        and not _account_has_selling_prefix(hay)
        and _account_type_is_cost_of_sales(account)
    ):
        return "AFG_COR"
    best = (-1, -1, None)  # weighted score, priority, code
    for code, priority, groups, keywords in rules:
        if groups is not None and ig not in groups:
            if ig:
                continue
            if "expense" not in groups and "income" not in groups:
                continue
        section = AFG_CODE_TO_SECTION.get(code)
        if not _afg_section_ok_for_internal_group(section, ig):
            continue
        score = sum(1 for kw in keywords if kw in hay)
        if score <= 0:
            continue
        weighted = score * 1000 + priority
        cand = (weighted, priority, code)
        if cand > best:
            best = cand
    if best[2]:
        return best[2]
    if ig in ("income", "expense"):
        return "AFG_UNGRP_PL"
    return "AFG_UNGRP_BS"


def _account_name_prefix_code(account):
    """Map CPABooks ledger prefixes the same way Default P&L types do."""
    name = (account.name or "").strip().lower()
    name = re.sub(r"^[|\s]+", "", name)
    name = re.sub(r"^\s*[\d][\w./-]*\s*\|\s*", "", name)
    if name.startswith("sad -") or name.startswith("sad-") or name.startswith("sad "):
        return "AFG_SELL"
    if name.startswith("ga -") or name.startswith("ga-") or name.startswith("ga "):
        return "AFG_GNA"
    if name.startswith(("cto -", "cto-", "ctc -", "ctc-", "ctd -", "ctd-")):
        return "AFG_PAYROLL"
    if name.startswith(("dc -", "dc-", "cos -", "cos-", "com -", "com-")):
        return "AFG_COR"
    return None


def _account_has_selling_prefix(hay):
    hay = hay or ""
    return "sad -" in hay or hay.startswith("sad ") or hay.startswith("sad-")


def _account_type_is_cost_of_sales(account):
    """True for CoA type Cost of Sales / Cost of Revenue / Direct Costs."""
    ut = account.user_type_id
    if not ut:
        return False
    ref = account.env.ref("account.data_account_type_direct_costs", raise_if_not_found=False)
    if ref and ut.id == ref.id:
        return True
    name = (ut.name or "").strip().lower()
    return any(
        n in name
        for n in ("cost of sales", "cost of revenue", "direct costs", "direct cost")
    )

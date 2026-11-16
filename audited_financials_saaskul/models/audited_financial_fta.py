# -*- coding: utf-8 -*-
"""UAE FTA Corporate Tax Filing summary built from existing AFG P&L and SOFP."""

from odoo import _, models

from .account_account import CTF_CATEGORY_SELECTION

FTA_NID_TO_CTF = {
    "fta-op-rev": "op_rev",
    "fta-cogs": "cogs",
    "fta-salaries": "salaries",
    "fta-depr": "depreciation",
    "fta-fines": "fines",
    "fta-donations": "donations",
    "fta-ent": "entertainment",
    "fta-other-exp": "other_exp",
    "fta-div": "dividends",
    "fta-nor-other": "other_nor",
    "fta-interest-inc": "interest_inc",
    "fta-interest-exp": "interest_exp",
    "fta-interest": "interest",
    "fta-disp-g": "disposal_gain",
    "fta-disp-l": "disposal_loss",
    "fta-disposal": "disposal",
    "fta-fx-g": "fx_gain",
    "fta-fx-l": "fx_loss",
    "fta-fx": "fx",
    "fta-tax": "tax",
    "fta-ppe": "ppe",
    "fta-intangible": "intangible",
    "fta-fin-nca": "financial_nca",
    "fta-nca-oth": "nca_other",
    "fta-cap": "share_capital",
    "fta-re": "retained_earnings",
    "fta-oeq": "other_equity",
    "fta-cl": "current_liab",
    "fta-ncl": "ncl",
    "fta-ca": "current_assets",
}

_KEYWORD_TO_CTF = {
    "dividends": "dividends",
    "fines": "fines",
    "donations": "donations",
    "entertainment": "entertainment",
    "interest": "interest",
    "disposal": "disposal",
    "fx": "fx",
    "tax": "tax",
    "other_income": "other_nor",
}


class AuditedFinancialVersionFta(models.Model):
    _inherit = "audited.financial.version"

    def _afg_ctf_label(self, code, fallback):
        Group = self.env["audited.financial.ctf.group"].sudo()
        labels = Group.get_label_map() if hasattr(Group, "get_label_map") else {}
        return labels.get(code) or fallback

    def _afg_fta_walk(self, nodes):
        for node in nodes or []:
            yield node
            for child in self._afg_fta_walk(node.get("children") or []):
                yield child

    def _afg_fta_by_type(self, roots, type_key):
        for node in roots or []:
            if node.get("type_key") == type_key:
                return node
        return None

    def _afg_fta_by_code(self, roots, code):
        code = (code or "").strip().upper()
        for node in self._afg_fta_walk(roots):
            if (node.get("afg_code") or "").strip().upper() == code:
                return node
        return None

    def _afg_fta_width(self, *nodes):
        width = 0
        for node in nodes:
            if not node:
                continue
            pam = node.get("period_amounts") or []
            if pam:
                width = max(width, len(pam))
        return width or 2

    def _afg_fta_vec(self, node, width):
        out = [0.0] * width
        if not node:
            return out
        pam = list(node.get("period_amounts") or [])
        if pam:
            for i, val in enumerate(pam[:width]):
                out[i] = float(val or 0.0)
            if width == 2 and len(pam) == 1:
                out[1] = float(pam[0] or 0.0)
            return out
        if width >= 2:
            out[0] = float(node.get("prior") or 0.0)
            out[-1] = float(node.get("current") or 0.0)
        elif width == 1:
            out[0] = float(node.get("current") or 0.0)
        return out

    def _afg_fta_add(self, left, right, sign=1.0):
        return [float(a or 0.0) + sign * float(b or 0.0) for a, b in zip(left, right)]

    def _afg_fta_label_bucket(self, text):
        lab = (text or "").strip().lower()
        if any(k in lab for k in ("dividend",)):
            return "dividends"
        if any(k in lab for k in ("fine", "penalty", "penalties")):
            return "fines"
        if any(k in lab for k in ("donation", "gift & donation", "gifts & donation", "zakat", "charity")):
            return "donations"
        if any(k in lab for k in (
            "entertainment", "client entertain", "meal & refreshment",
            "meal and refreshment", "staff meal",
        )):
            return "entertainment"
        if any(k in lab for k in ("interest income", "interest expense", "net interest", "bank interest")):
            return "interest"
        if any(k in lab for k in (
            "disposal", "gain on sale", "loss on sale", "gain on disposal", "loss on disposal",
        )):
            return "disposal"
        if any(k in lab for k in ("foreign exchange", "exchange gain", "exchange loss", "forex", "fx gain", "fx loss")):
            return "fx"
        if any(k in lab for k in ("corporate tax", "income tax", "taxation")):
            return "tax"
        if any(k in lab for k in ("other income", "other revenue", "non-operating", "non operating")):
            return "other_income"
        return ""

    def _afg_fta_ctf_for_node(self, node):
        """CoA CT Filing field wins; otherwise keyword bucket."""
        aid = node.get("account_id")
        if aid:
            try:
                acc = self.env["account.account"].browse(int(aid))
                if acc.exists() and acc.ctf_category:
                    return acc.ctf_category
            except (TypeError, ValueError):
                pass
        kw = self._afg_fta_label_bucket(
            node.get("ledger_caption") or node.get("label") or node.get("afg_caption") or ""
        )
        return _KEYWORD_TO_CTF.get(kw) or ""

    def _afg_fta_as_child_ledger(self, node, width):
        vec = self._afg_fta_vec(node, width)
        label = node.get("ledger_caption") or node.get("label") or node.get("afg_caption") or ""
        row = self._afg_fta_row(
            node.get("id") or "fta-led-%s" % (node.get("account_id") or "x"),
            label,
            vec,
            level=3,
        )
        row["is_ledger"] = True
        row["is_computed"] = False
        row["account_id"] = node.get("account_id")
        row["ledger_caption"] = label
        ids = list(node.get("drill_account_ids") or [])
        if node.get("account_id") and node.get("account_id") not in ids:
            ids.append(node.get("account_id"))
        row["drill_account_ids"] = ids
        return row

    def _afg_fta_ledgers_under(self, node, width, skip_codes=None):
        skip_codes = {c.upper() for c in (skip_codes or [])}
        out = []
        seen = set()

        def _walk(nodes, skipped=False):
            for n in nodes or []:
                code = (n.get("afg_code") or "").strip().upper()
                skip = skipped or code in skip_codes
                kids = n.get("children") or []
                if skip:
                    _walk(kids, True)
                    continue
                if self._afg_fta_is_leaf(n):
                    key = n.get("account_id") or n.get("id")
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(self._afg_fta_as_child_ledger(n, width))
                else:
                    _walk(kids, False)

        _walk([node] if node else [], False)
        return out

    def _afg_fta_is_leaf(self, node):
        kids = node.get("children") or []
        lvl = int(node.get("level") if node.get("level") is not None else 0)
        return (not kids) or node.get("is_ledger") or lvl >= 3

    def _afg_fta_accumulate_leaves(self, roots, width, skip_codes=None):
        skip_codes = {c.upper() for c in (skip_codes or [])}
        buckets = {
            "dividends": [0.0] * width,
            "other_income": [0.0] * width,
            "fines": [0.0] * width,
            "donations": [0.0] * width,
            "entertainment": [0.0] * width,
            "interest": [0.0] * width,
            "interest_inc": [0.0] * width,
            "interest_exp": [0.0] * width,
            "disposal": [0.0] * width,
            "disposal_gain": [0.0] * width,
            "disposal_loss": [0.0] * width,
            "fx": [0.0] * width,
            "fx_gain": [0.0] * width,
            "fx_loss": [0.0] * width,
            "tax": [0.0] * width,
            "other": [0.0] * width,
        }

        def _walk(nodes, skipped=False):
            for node in nodes or []:
                code = (node.get("afg_code") or "").strip().upper()
                skip = skipped or code in skip_codes
                kids = node.get("children") or []
                if skip:
                    _walk(kids, True)
                    continue
                if self._afg_fta_is_leaf(node):
                    ctf = self._afg_fta_ctf_for_node(node)
                    vec = self._afg_fta_vec(node, width)
                    kw = _KEYWORD_TO_CTF.get(self._afg_fta_label_bucket(
                        node.get("ledger_caption") or node.get("label") or node.get("afg_caption") or ""
                    )) or ""
                    bucket = ctf or kw
                    vec_key = {
                        "dividends": "dividends",
                        "other_nor": "other_income",
                        "fines": "fines",
                        "donations": "donations",
                        "entertainment": "entertainment",
                        "interest": "interest",
                        "interest_inc": "interest_inc",
                        "interest_exp": "interest_exp",
                        "disposal": "disposal",
                        "disposal_gain": "disposal_gain",
                        "disposal_loss": "disposal_loss",
                        "fx": "fx",
                        "fx_gain": "fx_gain",
                        "fx_loss": "fx_loss",
                        "tax": "tax",
                    }.get(bucket)
                    if vec_key:
                        buckets[vec_key] = self._afg_fta_add(buckets[vec_key], vec)
                    elif bucket not in ("salaries", "depreciation", "op_rev", "cogs"):
                        buckets["other"] = self._afg_fta_add(buckets["other"], vec)
                    nodes_map = buckets.setdefault("_nodes", {})
                    nkey = bucket or "other_exp"
                    if nkey == "other":
                        nkey = "other_exp"
                    nodes_map.setdefault(nkey, []).append(node)
                else:
                    _walk(kids, False)

        _walk(roots, False)
        return buckets

    def _afg_fta_row(self, nid, label, vec, level=1, children=None, type_key="", computed=False):
        prior = float(vec[0] or 0.0) if vec else 0.0
        current = float(vec[-1] or 0.0) if vec else 0.0
        row = {
            "id": nid,
            "label": label,
            "afg_caption": label,
            "note": "",
            "level": level,
            "prior": prior,
            "current": current,
            "period_amounts": list(vec or []),
            "children": children or [],
            "type_key": type_key,
            "report_section": "fta",
            "is_computed": computed,
            "is_ledger": not children and level >= 1,
            "group_code": "",
            "group_caption": "",
            "ledger_code": "",
            "ledger_caption": "",
            "drill_account_ids": [],
            "group_id": False,
            "ctf_category": FTA_NID_TO_CTF.get(nid) if not computed else False,
        }
        if children:
            ids = []
            for ch in children:
                for i in ch.get("drill_account_ids") or []:
                    if i not in ids:
                        ids.append(i)
                if ch.get("account_id") and ch.get("account_id") not in ids:
                    ids.append(ch.get("account_id"))
            row["drill_account_ids"] = ids
        return row

    def _afg_fta_header(self, nid, label, children, type_key):
        width = self._afg_fta_width(*children) if children else 2
        row = self._afg_fta_row(
            nid, label, [0.0] * width, level=0, children=children, type_key=type_key, computed=True
        )
        row["is_ledger"] = False
        return row

    def _afg_fta_pl_tree(self, pl_roots):
        sales = self._afg_fta_by_type(pl_roots, "sales") or self._afg_fta_by_code(pl_roots, "AFG_REV")
        cor = self._afg_fta_by_type(pl_roots, "cost_of_revenue") or self._afg_fta_by_code(pl_roots, "AFG_COR")
        expenses = self._afg_fta_by_type(pl_roots, "expenses")
        net = self._afg_fta_by_type(pl_roots, "net_profit")
        payroll = self._afg_fta_by_code(pl_roots, "AFG_PAYROLL")
        depr = self._afg_fta_by_code(pl_roots, "AFG_DEPR_PL")
        width = self._afg_fta_width(sales, cor, expenses, net, payroll, depr)
        op_rev = self._afg_fta_vec(sales, width)
        cogs = self._afg_fta_vec(cor, width)
        gross = self._afg_fta_add(op_rev, cogs, sign=-1.0)
        salaries = self._afg_fta_vec(payroll, width)
        depreciation = self._afg_fta_vec(depr, width)
        buckets = self._afg_fta_accumulate_leaves(
            (expenses.get("children") if expenses else pl_roots) or [],
            width,
            skip_codes=("AFG_PAYROLL", "AFG_DEPR_PL"),
        )
        # Income-side splits that live under revenue, not expenses
        rev_leaves = self._afg_fta_accumulate_leaves(
            (sales.get("children") if sales else []) or [],
            width,
            skip_codes=(),
        )
        dividends = rev_leaves["dividends"]
        other_nor = rev_leaves["other_income"]
        if any(abs(v) > 0.004 for v in dividends) or any(abs(v) > 0.004 for v in other_nor):
            op_rev = self._afg_fta_add(self._afg_fta_add(op_rev, dividends, -1.0), other_nor, -1.0)
            gross = self._afg_fta_add(op_rev, cogs, sign=-1.0)
        fines = buckets["fines"]
        donations = buckets["donations"]
        entertainment = buckets["entertainment"]
        interest = buckets["interest"]
        disposal = buckets["disposal"]
        fx = buckets["fx"]
        tax = buckets["tax"]
        classified_other = buckets["other"]
        net_vec = self._afg_fta_vec(net, width)
        # Plug Other expenses so FTA net = existing P&L net profit
        # net = gross - (sal+depr+fines+don+ent+other) + nor + other_items - tax
        opex_known = salaries
        for part in (depreciation, fines, donations, entertainment):
            opex_known = self._afg_fta_add(opex_known, part)
        nor = self._afg_fta_add(dividends, other_nor)
        other_items = interest
        for part in (disposal, fx):
            other_items = self._afg_fta_add(other_items, part)
        implied_other = []
        for i in range(width):
            implied_other.append(
                float(gross[i] or 0.0)
                - float(opex_known[i] or 0.0)
                + float(nor[i] or 0.0)
                + float(other_items[i] or 0.0)
                - float(tax[i] or 0.0)
                - float(net_vec[i] or 0.0)
            )
        other_exp = implied_other if any(abs(v) > 0.004 for v in implied_other) else classified_other
        non_op_total = opex_known
        non_op_total = self._afg_fta_add(non_op_total, other_exp)
        net_after = net_vec

        def kids_for(*keys, extra=None):
            raw = []
            for k in keys:
                raw.extend(exp_nodes.get(k) or [])
                raw.extend(rev_nodes.get(k) or [])
            out = [self._afg_fta_as_child_ledger(n, width) for n in raw]
            if extra:
                out = list(extra) + out
            seen = set()
            uniq = []
            for r in out:
                key = r.get("account_id") or r.get("id")
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(r)
            return uniq

        def line(nid, label, vec, level=1, computed=False, kids=None):
            row = self._afg_fta_row(
                nid, label, vec, level=level, computed=computed, children=kids or [],
            )
            if kids:
                row["is_ledger"] = False
            return row

        exp_nodes = buckets.get("_nodes") or {}
        rev_nodes = rev_leaves.get("_nodes") or {}
        skip_rev = set()
        for k in ("dividends", "other_nor"):
            for n in rev_nodes.get(k) or []:
                skip_rev.add(n.get("account_id") or n.get("id"))
        op_kids = []
        for led in self._afg_fta_ledgers_under(sales, width):
            key = led.get("account_id") or led.get("id")
            if key in skip_rev:
                continue
            op_kids.append(led)
        op_kids = kids_for("op_rev", extra=op_kids)
        cogs_kids = kids_for("cogs", extra=self._afg_fta_ledgers_under(cor, width))
        sal_kids = kids_for("salaries", extra=self._afg_fta_ledgers_under(payroll, width))
        depr_kids = kids_for("depreciation", extra=self._afg_fta_ledgers_under(depr, width))

        L = self._afg_ctf_label
        children = [
            line("fta-op-rev", L("op_rev", _("Operating Revenue (AED)")), op_rev, kids=op_kids),
            line("fta-cogs", L("cogs", _("Expenditure incurred in deriving operating revenue (AED)")), cogs, kids=cogs_kids),
            line("fta-gross", L("gross", _("Gross Profit / Loss (AED)")), gross, computed=True),
            line("fta-noe-h", L("noe_h", _("Non-operating Expense")), [0.0] * width, level=1),
            line("fta-salaries", L("salaries", _("Salaries, wages and related charges (AED)")), salaries, level=2, kids=sal_kids),
            line("fta-depr", L("depreciation", _("Depreciation and amortisation (AED)")), depreciation, level=2, kids=depr_kids),
            line("fta-fines", L("fines", _("Fines and Penalties (AED)")), fines, level=2, kids=kids_for("fines")),
            line("fta-donations", L("donations", _("Donations (AED)")), donations, level=2, kids=kids_for("donations")),
            line("fta-ent", L("entertainment", _("Client entertainment expenses (AED)")), entertainment, level=2, kids=kids_for("entertainment")),
            line("fta-other-exp", L("other_exp", _("Other expenses (AED)")), other_exp, level=2, kids=kids_for("other_exp")),
            line("fta-noe-tot", L("noe_tot", _("Non-operating Expense (Excluding others item Listed below) (AED)")), non_op_total, computed=True),
            line("fta-nor-h", L("nor_h", _("Non-operating Revenue")), [0.0] * width, level=1),
            line("fta-div", L("dividends", _("Dividends received (AED)")), dividends, level=2, kids=kids_for("dividends")),
            line("fta-nor-other", L("other_nor", _("Other non-operating revenue (AED)")), other_nor, level=2, kids=kids_for("other_nor")),
            line("fta-oi-h", L("oi_h", _("Other items")), [0.0] * width, level=1),
            line("fta-interest-inc", L("interest_inc", _("Interest Income (AED)")), buckets.get("interest_inc") or [0.0] * width, level=2, kids=kids_for("interest_inc")),
            line("fta-interest-exp", L("interest_exp", _("Interest Expenditure (AED)")), buckets.get("interest_exp") or [0.0] * width, level=2, kids=kids_for("interest_exp")),
            line("fta-interest", L("interest", _("Net Interest Income / (Expense) (AED)")), interest, level=2, kids=kids_for("interest")),
            line("fta-disp-g", L("disposal_gain", _("Gains on Disposal of Assets (AED)")), buckets.get("disposal_gain") or [0.0] * width, level=2, kids=kids_for("disposal_gain")),
            line("fta-disp-l", L("disposal_loss", _("Losses on Disposal of Assets (AED)")), buckets.get("disposal_loss") or [0.0] * width, level=2, kids=kids_for("disposal_loss")),
            line("fta-disposal", L("disposal", _("Net gains / (losses) on disposal of assets (AED)")), disposal, level=2, kids=kids_for("disposal")),
            line("fta-fx-g", L("fx_gain", _("Foreign exchange gains (AED)")), buckets.get("fx_gain") or [0.0] * width, level=2, kids=kids_for("fx_gain")),
            line("fta-fx-l", L("fx_loss", _("Foreign exchange losses (AED)")), buckets.get("fx_loss") or [0.0] * width, level=2, kids=kids_for("fx_loss")),
            line("fta-fx", L("fx", _("Net Gains/(losses) on foreign exchange (AED)")), fx, level=2, kids=kids_for("fx")),
            line("fta-net", L("net", _("Net profit/(loss) (AED)")), net_vec, computed=True),
            line("fta-tax", L("tax", _("Less: Corporate Tax")), tax, kids=kids_for("tax")),
            line("fta-net-after", L("net_after", _("Net profit/(loss) (AED) after corporate tax")), net_after, computed=True),
        ]
        # Nest detail under section headers
        noe = children[3]
        noe["children"] = children[4:10]
        noe["is_ledger"] = False
        noe["current"] = float(non_op_total[-1] or 0.0)
        noe["prior"] = float(non_op_total[0] or 0.0)
        noe["period_amounts"] = list(non_op_total)
        nor_h = children[11]
        nor_h["children"] = children[12:14]
        nor_h["is_ledger"] = False
        nor_h["period_amounts"] = list(nor)
        nor_h["prior"] = float(nor[0] or 0.0)
        nor_h["current"] = float(nor[-1] or 0.0)
        oi = children[14]
        oi["children"] = children[15:24]
        oi["is_ledger"] = False
        oi["period_amounts"] = list(other_items)
        oi["prior"] = float(other_items[0] or 0.0)
        oi["current"] = float(other_items[-1] or 0.0)
        flat = [
            children[0], children[1], children[2],
            noe, children[10],
            nor_h, oi,
            children[24], children[25], children[26],
        ]
        return self._afg_fta_header(
            "fta-pl",
            self._afg_ctf_label("ctf_pl", _("Statement of Profit & Loss Account - CTF Format")),
            flat,
            "fta_pl",
        )

    def _afg_fta_is_ppe(self, node):
        code = (node.get("afg_code") or "").strip().upper()
        lab = (node.get("label") or node.get("afg_caption") or "").lower()
        return code == "AFG_PPE" or "property, plant" in lab or lab.startswith("property, plant")

    def _afg_fta_is_ncl(self, node):
        code = (node.get("afg_code") or "").strip().upper()
        lab = (node.get("label") or node.get("afg_caption") or node.get("ledger_caption") or "").lower()
        if code == "AFG_EOS":
            return True
        return any(k in lab for k in (
            "end of service", "gratuity provision", "long term", "long-term",
            "term loan", "non-current", "non current",
        ))

    def _afg_fta_is_intangible(self, node):
        lab = (node.get("label") or node.get("afg_caption") or node.get("ledger_caption") or "").lower()
        return any(k in lab for k in ("intangible", "goodwill"))

    def _afg_fta_is_financial_nca(self, node):
        lab = (node.get("label") or node.get("afg_caption") or node.get("ledger_caption") or "").lower()
        return any(k in lab for k in ("financial asset", "investment property", "investment in"))

    def _afg_fta_is_nca_other(self, node):
        if self._afg_fta_is_intangible(node) or self._afg_fta_is_financial_nca(node):
            return True
        lab = (node.get("label") or node.get("afg_caption") or node.get("ledger_caption") or "").lower()
        return "non-current" in lab or "non current" in lab

    def _afg_fta_bs_tree(self, bs_roots):
        assets = self._afg_fta_by_type(bs_roots, "asset")
        total_assets = self._afg_fta_by_type(bs_roots, "total_assets") or assets
        liab = self._afg_fta_by_type(bs_roots, "liability")
        total_liab = self._afg_fta_by_type(bs_roots, "total_liabilities") or liab
        equity = self._afg_fta_by_type(bs_roots, "equity")
        total_eq_liab = self._afg_fta_by_type(bs_roots, "total_equity_liabilities")
        ppe = self._afg_fta_by_code(bs_roots, "AFG_PPE")
        width = self._afg_fta_width(total_assets, total_liab, equity, ppe, total_eq_liab)
        ta = self._afg_fta_vec(total_assets, width)
        ppe_v = self._afg_fta_vec(ppe, width)
        intangible = [0.0] * width
        financial_nca = [0.0] * width
        other_nca = [0.0] * width
        for node in (assets.get("children") if assets else []) or []:
            if self._afg_fta_is_ppe(node):
                continue
            vec = self._afg_fta_vec(node, width)
            if self._afg_fta_is_intangible(node):
                intangible = self._afg_fta_add(intangible, vec)
            elif self._afg_fta_is_financial_nca(node):
                financial_nca = self._afg_fta_add(financial_nca, vec)
            elif self._afg_fta_is_nca_other(node):
                other_nca = self._afg_fta_add(other_nca, vec)
        nca_tot = self._afg_fta_add(self._afg_fta_add(ppe_v, intangible), self._afg_fta_add(financial_nca, other_nca))
        ca = self._afg_fta_add(ta, nca_tot, sign=-1.0)
        tl = self._afg_fta_vec(total_liab, width)
        ncl = [0.0] * width
        for node in (liab.get("children") if liab else []) or []:
            if self._afg_fta_is_ncl(node):
                ncl = self._afg_fta_add(ncl, self._afg_fta_vec(node, width))
        cl = self._afg_fta_add(tl, ncl, sign=-1.0)
        cap = [0.0] * width
        re = [0.0] * width
        oeq = [0.0] * width
        for node in (equity.get("children") if equity else []) or []:
            tk = node.get("type_key") or ""
            lab = (node.get("label") or "").lower()
            vec = self._afg_fta_vec(node, width)
            if tk == "share_capital" or "share capital" in lab or "capital" == lab.strip():
                cap = self._afg_fta_add(cap, vec)
            elif tk in ("retained_earnings", "cy_pnl") or any(
                k in lab for k in ("retained", "accumulated", "profit", "loss", "current year")
            ):
                re = self._afg_fta_add(re, vec)
            else:
                oeq = self._afg_fta_add(oeq, vec)
        te = self._afg_fta_vec(equity, width)
        tel = self._afg_fta_vec(total_eq_liab, width) if total_eq_liab else self._afg_fta_add(tl, te)

        def line(nid, label, vec, level=1, computed=False, kids=None):
            row = self._afg_fta_row(
                nid, label, vec, level=level, computed=computed, children=kids or [],
            )
            if kids:
                row["is_ledger"] = False
            return row

        L = self._afg_ctf_label
        assets_h = self._afg_fta_row("fta-assets", L("assets_h", _("Assets")), ta, level=1, children=[
            line("fta-ca", L("current_assets", _("Total current assets (AED)")), ca, computed=True),
            line("fta-ppe", L("ppe", _("Property, plant and equipment (AED)")), ppe_v, level=2,
                 kids=self._afg_fta_ledgers_under(ppe, width)),
            line("fta-intangible", L("intangible", _("Intangible assets (AED)")), intangible, level=2),
            line("fta-fin-nca", L("financial_nca", _("Financial assets (AED)")), financial_nca, level=2),
            line("fta-nca-oth", L("nca_other", _("Other non-current assets (AED)")), other_nca, level=2),
            line("fta-nca-tot", L("nca_tot", _("Total non-current assets (AED)")), nca_tot, level=2, computed=True),
            line("fta-ta", L("total_asset", _("Total Asset")), ta, computed=True),
        ])
        assets_h["is_ledger"] = False
        liab_h = self._afg_fta_row("fta-liab", L("liab_h", _("Liabilities")), tl, level=1, children=[
            line("fta-cl", L("current_liab", _("Total current liabilities (AED)")), cl, computed=True),
            line("fta-ncl", L("ncl", _("Total non-current liabilities (AED)")), ncl, computed=True),
            line("fta-tl", L("total_liab", _("Total liabilities (AED)")), tl, computed=True),
        ])
        liab_h["is_ledger"] = False
        eq_kids = [
            line("fta-cap", L("share_capital", _("Share capital (AED)")), cap, level=2),
            line("fta-re", L("retained_earnings", _("Retained earnings (AED)")), re, level=2),
            line("fta-oeq", L("other_equity", _("Other equity (AED)")), oeq, level=2),
            line("fta-te", L("total_eq", _("Total equity (AED)")), te, level=2, computed=True),
        ]
        eq = self._afg_fta_row("fta-eq", L("eq_h", _("Equity")), te, level=1, children=eq_kids)
        eq["is_ledger"] = False
        children = [
            assets_h,
            liab_h,
            eq,
            line("fta-tel", L("tel", _("Total equity and liabilities (AED)")), tel, computed=True),
        ]
        return self._afg_fta_header(
            "fta-bs",
            L("ctf_bs", _("Statement of Financial Position - CTF Format")),
            children,
            "fta_bs",
        )

    def _afg_fta_corporate_tax_filing_tree(self, pl_roots, bs_roots):
        """Summarize existing Income + SOFP into FTA Corporate Tax Filing lines."""
        roots = []
        if pl_roots:
            roots.append(self._afg_fta_pl_tree(pl_roots))
        if bs_roots:
            roots.append(self._afg_fta_bs_tree(bs_roots))
        return roots

    def _afg_fta_print_chapter_dict(self, payload, yp, yc, hide_lg=True,
                                    period_labels=None, period_span=None):
        """First-page Corporate Tax Filing chapter for PDF / Excel / Word."""
        tree = []
        for sec in payload.get("sections") or []:
            if sec.get("key") == "fta":
                tree = sec.get("tree") or []
                break
        if not tree:
            tree = ((payload.get("version") or {}).get("sections") or {}).get("fta") or []
        if not tree:
            return False
        rows = self.with_context(afg_fta_print=True)._afg_flatten_tree_for_export(
            tree, max_level=4
        )
        if hide_lg:
            cleaned = []
            for row in rows or []:
                nr = dict(row)
                nr["lg"] = ""
                cleaned.append(nr)
            rows = cleaned
        if not rows:
            return False
        period_labels = list(period_labels or [])
        single_period = (
            len(period_labels) <= 1
            or str(period_span or "").strip().lower() in ("1y", "1m")
            or bool(payload.get("hide_comparative"))
        )
        if single_period:
            for row in rows:
                row["prior"] = None
                row["prior_disp"] = ""
        period_labs_ch = (
            [period_labels[-1]] if single_period and period_labels else list(period_labels)
        )
        if single_period and not period_labs_ch:
            period_labs_ch = [str(yc)]
        rows = self._afg_ensure_print_period_disp(rows, period_labs_ch)
        title = self._afg_proper_case(_("CORPORATE TAX FILING- FTA"))
        return {
            "key": "fta",
            "title": title,
            "kind": "statement",
            "col_prior": "" if single_period else str(yp),
            "col_current": str(yc),
            "period_labels": period_labs_ch,
            "period_span": period_span,
            "hide_comparative": single_period,
            "rows": rows,
            "hide_lg": hide_lg,
            "header": self._afg_print_header(title, None if single_period else yp, yc),
        }

# -*- coding: utf-8 -*-
"""Full internal audit report export (PDF, Excel, Word) and IFRS schedules."""

import base64
import copy
import io
from collections import OrderedDict

from odoo import _, api, fields, models

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class AuditedFinancialVersionReport(models.Model):
    _inherit = "audited.financial.version"

    def _trial_balance_roots_from_statements(self, tree_by_section):
        """Build trial balance from loaded P&amp;L and balance sheet trees (working paper view)."""
        self.ensure_one()
        roots = []
        for sec_key, sec_label in (
            ("pl", _("Statement of Profit or Loss")),
            ("bs", _("Statement of Financial Position")),
        ):
            branches = tree_by_section.get(sec_key) or []
            if not branches:
                continue
            children = self._afg_consolidate_branch_tree(copy.deepcopy(branches))
            tp, tc, tco_p, tco_c = self._afg_sum_branch_nodes(children)
            if not self._afg_branch_has_balance(tp, tc, tco_p, tco_c):
                continue
            roots.append({
                "id": "tb-sec-%s" % sec_key,
                "type_key": sec_key,
                "label": sec_label,
                "note": "",
                "level": 0,
                "prior": tp,
                "current": tc,
                "co_prior": tco_p,
                "co_curr": tco_c,
                "is_computed": False,
                "children": children,
            })
        if len(roots) > 1:
            gp, gc, gcp, gcc = self._afg_sum_branch_nodes(roots)
            roots.append({
                "id": "tb-type-grand-total",
                "type_key": "grand_total",
                "label": _("Grand Total"),
                "note": "",
                "level": 0,
                "prior": gp,
                "current": gc,
                "co_prior": gcp,
                "co_curr": gcc,
                "is_computed": True,
                "children": [],
            })
        return roots

    def _dashboard_placeholder_notes(self):
        """SME UAE IFRS-style notes suitable for management / FTA packs (not a full listed-company annual report)."""
        entity = (self.company_id.display_name or _("the Company"))
        yc = self.year_current
        curr = self.currency_id.name or "AED"
        return [
            {
                "title": _("1. Reporting entity"),
                "body": (
                    "<p>%s</p>"
                    % _(
                        "%(entity)s (the \"Company\") is a limited liability company registered in the "
                        "United Arab Emirates. These financial statements present the financial position "
                        "and performance of the Company for the year ended 31 December %(year)s."
                    )
                    % {"entity": entity, "year": yc}
                ),
            },
            {
                "title": _("2. Basis of preparation"),
                "body": (
                    "<p>%s</p>"
                    % _(
                        "These financial statements have been prepared based on the Company's accounting "
                        "records and the accounting policies adopted by management. They are presented in "
                        "%(curr)s on the historical cost basis except where another measurement basis is "
                        "applied under those policies. Figures are derived from the Company's trial balance "
                        "and mapped chart of accounts. These statements are management-prepared and have "
                        "not been audited."
                    )
                    % {"curr": curr}
                ),
            },
            {
                "title": _("3. Significant accounting policies"),
                "body": (
                    "<p>%s</p><ul>"
                    "<li>%s</li><li>%s</li><li>%s</li><li>%s</li></ul>"
                )
                % (
                    _("The following policies have been applied consistently:"),
                    _("Revenue is recognised when control of goods or services transfers to the customer."),
                    _("Property, plant and equipment are stated at cost less accumulated depreciation and impairment."),
                    _("Depreciation is charged on a straight-line basis over estimated useful lives."),
                    _("Trade receivables are stated net of expected credit losses where material."),
                ),
            },
            {
                "title": _("4. Cash and bank"),
                "body": "<p>%s</p>" % _(
                    "Cash and cash equivalents comprise cash on hand and balances with banks that are "
                    "readily convertible to known amounts of cash."
                ),
            },
            {
                "title": _("5. Trade and other receivables"),
                "body": "<p>%s</p>" % _(
                    "Trade receivables arise in the ordinary course of business. Other receivables and "
                    "prepayments include amounts recoverable within twelve months."
                ),
            },
            {
                "title": _("6. Property, plant and equipment"),
                "body": "<p>%s</p>" % _(
                    "Movements in cost, accumulated depreciation and net book value are set out in the "
                    "Property, Plant and Equipment schedule. Additions, disposals and depreciation for "
                    "the year are linked to the trial balance."
                ),
            },
            {
                "title": _("7. Trade and other payables"),
                "body": "<p>%s</p>" % _(
                    "Trade and other payables are unsecured and are usually settled within normal credit terms."
                ),
            },
            {
                "title": _("8. Share capital / owners' equity"),
                "body": "<p>%s</p>" % _(
                    "Share capital (or capital accounts for an LLC) and retained earnings / accumulated "
                    "losses are presented in the Statement of Changes in Equity. Current year profit or "
                    "loss is transferred to equity."
                ),
            },
            {
                "title": _("9. Corporate Tax"),
                "body": "<p>%s</p>" % _(
                    "The Company is subject to UAE Corporate Tax under Federal Decree-Law No. 47 of 2022. "
                    "Current and deferred tax, where applicable, are recognised under the policies adopted "
                    "by management."
                ),
            },
            {
                "title": _("10. Value Added Tax (VAT)"),
                "body": "<p>%s</p>" % _(
                    "The Company accounts for UAE VAT in accordance with Federal Decree-Law No. 8 of 2017. "
                    "VAT receivable / payable balances are included within other receivables or payables."
                ),
            },
            {
                "title": _("11. Related parties"),
                "body": "<p>%s</p>" % _(
                    "Related party balances and transactions, if any, arise mainly from owners, key "
                    "management and group entities and are conducted on terms agreed between the parties."
                ),
            },
            {
                "title": _("12. Subsequent events"),
                "body": "<p>%s</p>" % _(
                    "There are no material non-adjusting events after the reporting date that require "
                    "disclosure, unless otherwise noted by management."
                ),
            },
            {
                "title": _("13. Going concern"),
                "body": "<p>%s</p>" % _(
                    "Management has assessed the Company's ability to continue as a going concern and "
                    "is satisfied that the Company has the resources to continue in business for the "
                    "foreseeable future. Accordingly, the financial statements continue to be prepared "
                    "on the going concern basis."
                ),
            },
        ]

    def _dashboard_placeholder_alerts(self):
        return [{
            "type": "review",
            "severity": "info",
            "title": _("Management review"),
            "message": _(
                "Confirm chart mapping, comparative figures and validation PASS/FAIL before FTA or bank use."
            ),
        }]

    def _afg_collect_l1_rows(self, roots, section_filter=None):
        """Flatten level-1 AFG lines from a statement tree for schedule tables."""
        rows = []

        def walk(nodes):
            for node in nodes or []:
                lvl = node.get("level")
                if lvl == 0:
                    walk(node.get("children"))
                elif lvl == 1:
                    if section_filter and node.get("report_section") not in section_filter:
                        continue
                    if self._afg_branch_has_balance(
                        node.get("prior"), node.get("current"),
                        node.get("co_prior"), node.get("co_curr"),
                    ):
                        rows.append({
                            "label": node.get("label") or "",
                            "prior": float(node.get("prior") or 0.0),
                            "current": float(node.get("current") or 0.0),
                        })
                    walk(node.get("children"))

        walk(roots)
        return rows

    def _afg_walk_find(self, nodes, predicate):
        for node in nodes or []:
            if predicate(node):
                return node
            found = self._afg_walk_find(node.get("children") or [], predicate)
            if found:
                return found
        return None

    def _afg_node_level(self, node, default=-1):
        """Integer tree level — do not use ``x or default`` (level 0 is valid)."""
        if not node:
            return int(default)
        raw = node.get("level")
        if raw is None:
            return int(default)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return int(default)

    def _afg_l1_by_code(self, roots, afg_code):
        code = (afg_code or "").strip()
        return self._afg_walk_find(
            roots,
            lambda n: self._afg_node_level(n) == 1 and (n.get("afg_code") or "").strip() == code,
        )

    def _afg_type_by_key(self, roots, type_key):
        return self._afg_walk_find(
            roots,
            lambda n: self._afg_node_level(n) == 0 and (n.get("type_key") or "") == type_key,
        )

    def _afg_amt_pair(self, node):
        if not node:
            return 0.0, 0.0
        return float(node.get("prior") or 0.0), float(node.get("current") or 0.0)

    def _afg_is_accum_dep_label(self, label):
        """True for Accumulated Depreciation ledgers (never PPE cost columns).

        CPABooks / ME charts often use ``FAA - Furniture`` for *cost* (Fixed Asset Account)
        and ``Acc. Depn. - Furniture`` for accum. Do **not** treat bare ``FAA -`` as Acc.Depn.
        """
        hay = (label or "").lower().strip()
        if not hay:
            return False
        if any(k in hay for k in (
            "accumulat",
            "accumulated depreciation",
            "accum. dep",
            "acc. depn",
            "acc depn",
            "acc.dep",
            "acc dep",
            "provision for depreciation",
            "depr. reserve",
            "depreciation reserve",
        )):
            return True
        # Only FAA + explicit dep wording (legacy odd captions) — not FAA cost assets
        compact = hay.replace("–", "-").replace("—", "-")
        if compact.startswith("faa") and any(
            k in compact for k in ("dep", "accum", "provision for")
        ):
            return True
        return False

    def _afg_ppe_find_l1(self, roots, afg_code, label_bits=None):
        """Find L1 AFG node by code, else by caption keywords."""
        node = self._afg_l1_by_code(roots, afg_code)
        if node:
            return node
        bits = [b.lower() for b in (label_bits or []) if b]
        if not bits:
            return None

        def _match(n):
            if self._afg_node_level(n) != 1:
                return False
            lab = (n.get("label") or n.get("afg_caption") or n.get("group_caption") or "").lower()
            return any(b in lab for b in bits)

        return self._afg_walk_find(roots, _match)

    def _afg_ppe_collect_bs_asset_leaves(self, bs_roots):
        """All FA / FAA / Acc.Depn ledger leaves under Assets (when AFG_PPE code missing)."""
        asset = self._afg_type_by_key(bs_roots, "asset")
        root = asset or {"children": bs_roots or [], "level": 0}
        leaves = self._afg_ppe_collect_leaves(root)
        out = []
        for leaf in leaves:
            lbl = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
            if not lbl:
                continue
            low = lbl.lower()
            if self._afg_is_accum_dep_label(lbl):
                out.append(leaf)
                continue
            if low.startswith("faa") or low.startswith("fa -") or low.startswith("fa-") or low.startswith("fa "):
                out.append(leaf)
                continue
            if any(k in low for k in (
                "furniture", "fixture", "computer", "vehicle", "equipment",
                "machinery", "leasehold", "building", "land", "ppe",
            )) and "receivable" not in low and "payable" not in low:
                out.append(leaf)
        return out

    def _afg_ppe_name_core(self, label):
        """Normalize asset / Acc. Depn. titles for pairing (Motor Vehicle ↔ Acc. Depn. Motor Vehicle)."""
        hay = (label or "").lower().replace("–", "-").replace("—", "-")
        for w in (
            "accumulated depreciation", "accumulated", "accum.",
            "acc. depn.", "acc. depn", "acc.dep", "acc depn", "acc dep",
            "depreciation", "depr.", "provision for",
            "faa -", "faa-", "faa ", "fa -", "fa-", "fa ",
        ):
            hay = hay.replace(w, " ")
        return " ".join(hay.replace("|", " ").replace("-", " ").split())

    def _afg_is_non_ppe_category(self, node_or_name):
        """Skip cash / WC / equity nodes that must not appear as PPE columns."""
        if isinstance(node_or_name, dict):
            code = (node_or_name.get("afg_code") or "").strip()
            if code in (
                "AFG_CASH", "AFG_AR", "AFG_INV", "AFG_PREP", "AFG_AP", "AFG_TAX",
                "AFG_EOS", "AFG_EQ", "AFG_REV", "AFG_COGS", "AFG_OPEX", "AFG_DEPR_PL",
            ):
                return True
            name = (
                node_or_name.get("group_caption")
                or node_or_name.get("ledger_caption")
                or node_or_name.get("label")
                or ""
            )
        else:
            name = node_or_name or ""
        hay = name.lower()
        if not hay.strip():
            return True
        if self._afg_is_accum_dep_label(name):
            return True
        skip = (
            "cash", "bank", "receivable", "payable", "inventory", "prepayment",
            "deposit", "equity", "capital", "current account", "vat", "tax payable",
        )
        return any(k in hay for k in skip)

    def _afg_ppe_cat_from_node(self, node, name=None):
        """Split cost vs accum. dep. ledgers under an L2 (or L1) into one PPE column."""
        cost_p = cost_c = dep_p = dep_c = 0.0
        ledgers = node.get("children") or []
        if not ledgers:
            cost_p = abs(float(node.get("prior") or 0.0))
            cost_c = abs(float(node.get("current") or 0.0))
        else:
            for l3 in ledgers:
                if int(l3.get("level") or 0) not in (2, 3, 4):
                    continue
                # Nested L2 under L2: recurse amounts only from leaf-ish nodes
                if int(l3.get("level") or 0) == 2 and (l3.get("children") or []):
                    sub = self._afg_ppe_cat_from_node(l3)
                    cost_p += float(sub.get("cost_prior") or 0.0)
                    cost_c += float(sub.get("cost_current") or 0.0)
                    dep_p += float(sub.get("dep_prior") or 0.0)
                    dep_c += float(sub.get("dep_current") or 0.0)
                    continue
                lbl = l3.get("ledger_caption") or l3.get("label") or ""
                p = abs(float(l3.get("prior") or 0.0))
                c = abs(float(l3.get("current") or 0.0))
                if self._afg_is_accum_dep_label(lbl):
                    dep_p += p
                    dep_c += c
                else:
                    cost_p += p
                    cost_c += c
            if cost_p == 0.0 and cost_c == 0.0 and dep_p == 0.0 and dep_c == 0.0:
                cost_p = abs(float(node.get("prior") or 0.0))
                cost_c = abs(float(node.get("current") or 0.0))
        label = (name or node.get("group_caption") or node.get("label") or _("Category")).strip()
        return {
            "name": label,
            "cost_prior": cost_p,
            "cost_current": cost_c,
            "additions": cost_c - cost_p,
            "dep_prior": dep_p,
            "dep_current": dep_c,
            "charge": dep_c - dep_p,
            "nbv_prior": cost_p - dep_p,
            "nbv_current": cost_c - dep_c,
        }

    def _afg_ppe_collect_leaves(self, node, out=None):
        """Collect ledger-like nodes (L3/L4) under an AFG / group branch."""
        if out is None:
            out = []
        if not node:
            return out
        lvl = self._afg_node_level(node)
        if lvl in (3, 4) or node.get("is_ledger") or node.get("account_id"):
            out.append(node)
        for ch in node.get("children") or []:
            self._afg_ppe_collect_leaves(ch, out)
        return out

    def _afg_ppe_leaf_account_ids(self, leaf):
        aids = []
        if leaf.get("account_id"):
            try:
                aids.append(int(leaf["account_id"]))
            except (TypeError, ValueError):
                pass
        for a in leaf.get("drill_account_ids") or []:
            try:
                aids.append(int(a))
            except (TypeError, ValueError):
                continue
        return [a for a in aids if a]

    def _afg_ppe_leaf_category_name(self, leaf, Account):
        """Samurai column title: Odoo account group name, else ledger asset name."""
        lbl = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
        if self._afg_is_accum_dep_label(lbl):
            return None
        aids = self._afg_ppe_leaf_account_ids(leaf)
        accounts = Account.browse(aids).exists() if aids else Account.browse()
        for acc in accounts:
            grp = acc.group_id
            if not grp:
                continue
            gname = self._afg_group_label(grp)
            if gname and not self._afg_is_non_ppe_category(gname) and not self._afg_is_accum_dep_label(gname):
                return gname
        # L2 caption carried on ledger after collapse
        gcap = (leaf.get("group_caption") or "").strip()
        if gcap and not self._afg_is_non_ppe_category(gcap) and not self._afg_is_accum_dep_label(gcap):
            # Avoid AFG register title used as a fake group
            low = gcap.lower()
            if "register detail" not in low and gcap.lower() != (leaf.get("afg_caption") or "").lower():
                return gcap
        if lbl and not self._afg_is_non_ppe_category(lbl):
            return lbl
        return None

    def _afg_ppe_is_generic_column_name(self, name):
        """True for bucket titles that must not be the only PPE column."""
        low = (name or "").strip().lower()
        if not low:
            return True
        if "register detail" in low:
            return True
        generics = (
            "fixed asset", "fixed assets", "fixed assets schedule",
            "property and equipment", "property, plant and equipment",
            "property plant and equipment", "ppe", "plant and equipment",
            "tangible assets", "non-current assets", "non current assets",
        )
        if low in generics:
            return True
        for g in generics:
            if low.startswith(g + " ") or low.startswith(g + "—") or low.startswith(g + "-"):
                return True
        return False

    def _afg_ppe_cat_has_value(self, cat):
        """Keep columns that have any cost / dep / NBV amount."""
        if not cat:
            return False
        if not (cat.get("name") or "").strip():
            return False
        for key in (
            "cost_prior", "cost_current", "additions",
            "dep_prior", "dep_current", "charge",
            "nbv_prior", "nbv_current",
        ):
            if abs(float(cat.get(key) or 0.0)) > 1e-9:
                return True
        return False

    def _afg_ppe_filter_valued_categories(self, categories):
        """Drop empty / zero columns; keep order."""
        return [c for c in (categories or []) if self._afg_ppe_cat_has_value(c)]

    def _afg_ppe_cat_blank(self, name):
        return {
            "name": name,
            "cost_prior": 0.0,
            "cost_current": 0.0,
            "additions": 0.0,
            "disposals": 0.0,
            "dep_prior": 0.0,
            "dep_current": 0.0,
            "charge": 0.0,
            "dep_disposals": 0.0,
            "nbv_prior": 0.0,
            "nbv_current": 0.0,
        }

    def _afg_ppe_cats_from_leaves(self, leaves):
        """One column per cost ledger with a name (Samurai multi-asset pattern)."""
        Account = self.env["account.account"].sudo()
        cost_leaves = []
        dep_leaves = []
        for leaf in leaves or []:
            lbl = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
            if self._afg_is_accum_dep_label(lbl):
                dep_leaves.append(leaf)
            elif not self._afg_is_non_ppe_category(lbl):
                cost_leaves.append(leaf)

        if not cost_leaves and not dep_leaves:
            return []

        buckets = OrderedDict()

        def _ensure(name):
            key = (name or "").strip() or _("Other equipment")
            if key not in buckets:
                buckets[key] = self._afg_ppe_cat_blank(key)
            return buckets[key]

        def _ledger_column_name(leaf):
            ledger = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
            # Pretty cost caption: "FAA - Furniture & Fixtures" → "Furniture & Fixtures"
            pretty = ledger
            low = pretty.lower()
            for prefix in ("faa - ", "faa-", "faa ", "fa - ", "fa-", "fa "):
                if low.startswith(prefix):
                    pretty = pretty[len(prefix):].strip()
                    break
            if pretty and not self._afg_ppe_is_generic_column_name(pretty):
                return pretty
            if ledger and not self._afg_ppe_is_generic_column_name(ledger):
                return ledger
            group_name = self._afg_ppe_leaf_category_name(leaf, Account)
            if group_name and not self._afg_ppe_is_generic_column_name(group_name):
                return group_name
            return pretty or ledger or group_name or _("Asset")

        for leaf in cost_leaves:
            name = _ledger_column_name(leaf)
            if not name or self._afg_is_non_ppe_category(name):
                continue
            if self._afg_ppe_is_generic_column_name(name) and len(cost_leaves) > 1:
                raw = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
                if raw and not self._afg_ppe_is_generic_column_name(raw):
                    name = raw
                else:
                    continue
            cat = _ensure(name)
            cat["cost_prior"] += abs(float(leaf.get("prior") or 0.0))
            cat["cost_current"] += abs(float(leaf.get("current") or 0.0))

        if not buckets and cost_leaves:
            for leaf in cost_leaves:
                name = (leaf.get("ledger_caption") or leaf.get("label") or _("Asset")).strip()
                if self._afg_ppe_is_generic_column_name(name):
                    continue
                cat = _ensure(name)
                cat["cost_prior"] += abs(float(leaf.get("prior") or 0.0))
                cat["cost_current"] += abs(float(leaf.get("current") or 0.0))

        cat_keys = list(buckets.keys())
        for leaf in dep_leaves:
            p = abs(float(leaf.get("prior") or 0.0))
            c = abs(float(leaf.get("current") or 0.0))
            lbl = (leaf.get("ledger_caption") or leaf.get("label") or "")
            lbl_low = lbl.lower()
            core = self._afg_ppe_name_core(lbl)
            target = None
            # 1) Exact / substring on display name
            for key in cat_keys:
                klow = key.lower()
                if klow and klow in lbl_low:
                    target = key
                    break
            # 2) Core token match (Acc. Depn. - Motor Vehicle ↔ FA Motor Vehicle)
            if not target and core:
                for key in cat_keys:
                    kcore = self._afg_ppe_name_core(key)
                    if kcore and (kcore in core or core in kcore):
                        target = key
                        break
            if not target and len(cat_keys) == 1:
                target = cat_keys[0]
            if not target and cat_keys:
                for acc in Account.browse(self._afg_ppe_leaf_account_ids(leaf)).exists():
                    if not acc.group_id:
                        continue
                    gn = self._afg_group_label(acc.group_id)
                    if gn in buckets:
                        target = gn
                        break
                    gcore = self._afg_ppe_name_core(gn)
                    if gcore:
                        for key in cat_keys:
                            if self._afg_ppe_name_core(key) == gcore:
                                target = key
                                break
                    if target:
                        break
            if not target and cat_keys:
                target = cat_keys[0]
            if target:
                buckets[target]["dep_prior"] += p
                buckets[target]["dep_current"] += c

        categories = []
        for cat in buckets.values():
            cat["additions"] = cat["cost_current"] - cat["cost_prior"]
            cat["charge"] = cat["dep_current"] - cat["dep_prior"]
            cat["nbv_prior"] = cat["cost_prior"] - cat["dep_prior"]
            cat["nbv_current"] = cat["cost_current"] - cat["dep_current"]
            categories.append(cat)
        return self._afg_ppe_filter_valued_categories(categories)

    def _afg_ppe_l2_categories(self, l1):
        """Expand L2 groups into ledger columns when multiple assets sit under one group."""
        if not l1:
            return []
        categories = []
        for l2 in l1.get("children") or []:
            if int(l2.get("level") or 0) != 2:
                continue
            if self._afg_is_non_ppe_category(l2):
                continue
            leaves = self._afg_ppe_collect_leaves(l2)
            cost_leaves = [
                leaf for leaf in leaves
                if not self._afg_is_accum_dep_label(
                    (leaf.get("ledger_caption") or leaf.get("label") or "")
                )
            ]
            if len(cost_leaves) > 1 or self._afg_ppe_is_generic_column_name(
                l2.get("group_caption") or l2.get("label") or ""
            ):
                categories.extend(self._afg_ppe_cats_from_leaves(leaves))
            else:
                cat = self._afg_ppe_cat_from_node(l2)
                if self._afg_ppe_cat_has_value(cat):
                    categories.append(cat)
        return self._afg_ppe_filter_valued_categories(categories)

    def _afg_ppe_cats_from_coa_tb(self):
        """Build PPE columns from CoA FAA / Acc.Depn. accounts using TB closing stock."""
        self.ensure_one()
        cids = self._afg_column_company_order() or self._tb_company_ids()
        if not cids:
            return []
        maps_by_cid = self._tb_coa_maps_by_cid(cids)
        Account = self._afg_account_sudo().with_context(allowed_company_ids=cids)
        accounts = Account.search([
            ("company_id", "in", cids),
            "|", "|", "|", "|",
            ("name", "=ilike", "FAA -%"),
            ("name", "=ilike", "FAA-%"),
            ("name", "=ilike", "FA -%"),
            ("name", "=ilike", "Acc. Depn.%"),
            ("name", "=ilike", "Accumulated Dep%"),
        ])
        if not accounts:
            return []
        leaves = []
        for acc in accounts:
            row = self._tb_account_period_amounts(acc, maps_by_cid, cids)
            # OTC pack: [op, tr_yp, cl_yp, tr_yc, cl_yc] — use closing prior / current
            prior = abs(float(row[2] if len(row) > 2 else 0.0) or 0.0)
            curr = abs(float(row[4] if len(row) > 4 else 0.0) or 0.0)
            if prior < 1e-9 and curr < 1e-9:
                continue
            leaves.append({
                "id": "coa-%s" % acc.id,
                "account_id": acc.id,
                "label": acc.name,
                "ledger_caption": acc.name,
                "prior": prior,
                "current": curr,
            })
        return self._afg_ppe_cats_from_leaves(leaves)

    def _afg_fixed_assets_recon_data(self, tree_by_section):
        """PPE reconciliation: one column per valued asset ledger; Samurai year blocks."""
        self.ensure_one()
        yp, yc = self.year_prior, self.year_current
        fa_roots = tree_by_section.get("fixed_assets") or []
        bs_roots = tree_by_section.get("bs") or []

        l1_fixed = self._afg_ppe_find_l1(
            fa_roots, "AFG_FIXED",
            ("fixed asset", "register detail", "property and equipment"),
        )
        l1_ppe = self._afg_ppe_find_l1(
            bs_roots, "AFG_PPE",
            ("property, plant", "plant and equipment", "fixed asset"),
        )
        categories = []

        leaves = []
        for l1 in (l1_fixed, l1_ppe):
            if l1:
                leaves.extend(self._afg_ppe_collect_leaves(l1))
        # BS Assets fallback when AFG_PPE L1 missing / emptied by prune
        if not leaves:
            leaves.extend(self._afg_ppe_collect_bs_asset_leaves(bs_roots))
        elif not any(
            not self._afg_is_accum_dep_label(
                (lf.get("ledger_caption") or lf.get("label") or "")
            )
            for lf in leaves
        ):
            # Only Acc.Depn leaves found (old FAA→accum bug residue) — merge BS cost ledgers
            leaves.extend(self._afg_ppe_collect_bs_asset_leaves(bs_roots))

        seen = set()
        uniq = []
        for leaf in leaves:
            # Prefer account_id — AFG Fixed + SOFP PPE often repeat the same CoA leaf
            # with different line ids (was double-counting NBV ≈ 2× Balance Sheet).
            aid = leaf.get("account_id")
            if aid:
                key = ("acc", int(aid))
            else:
                key = ("id", leaf.get("id") or id(leaf))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(leaf)
        categories = self._afg_ppe_cats_from_leaves(uniq)

        if not categories:
            for l1 in (l1_fixed, l1_ppe):
                cats = self._afg_ppe_l2_categories(l1)
                if cats:
                    categories = cats
                    break

        if not categories:
            source_rows = [
                r for r in self._afg_collect_l1_rows(fa_roots)
                if not self._afg_is_non_ppe_category(r.get("label") or "")
                and not self._afg_ppe_is_generic_column_name(r.get("label") or "")
            ]
            if not source_rows:
                source_rows = [
                    r for r in self._afg_collect_l1_rows(bs_roots)
                    if any(k in (r.get("label") or "").lower() for k in (
                        "ppe", "fixed", "property", "equipment", "vehicle", "furniture", "computer",
                    )) and not self._afg_is_non_ppe_category(r.get("label") or "")
                    and not self._afg_ppe_is_generic_column_name(r.get("label") or "")
                ]
            for row in source_rows:
                prior = abs(row["prior"])
                cur = abs(row["current"])
                if abs(prior) < 1e-9 and abs(cur) < 1e-9:
                    continue
                categories.append({
                    "name": row["label"],
                    "cost_prior": prior,
                    "cost_current": cur,
                    "additions": max(cur - prior, 0.0),
                    "disposals": max(prior - cur, 0.0),
                    "dep_prior": 0.0,
                    "dep_current": 0.0,
                    "charge": 0.0,
                    "dep_disposals": 0.0,
                    "nbv_prior": prior,
                    "nbv_current": cur,
                })

        categories = self._afg_ppe_filter_valued_categories(categories)
        # Drop nameless / placeholder ghost columns (cause blank gap before Total)
        categories = [
            c for c in categories
            if (c.get("name") or "").strip()
            and (c.get("name") or "").strip().lower() not in ("total", "amount", "-")
        ]

        # CoA fallback: FAA / Acc.Depn. with TB stock when AFG tree has no valued PPE columns
        # (Balance Sheet may show them under a mapped L1 while leaf collect missed them)
        if not categories:
            categories = self._afg_ppe_cats_from_coa_tb()
            categories = self._afg_ppe_filter_valued_categories(categories)
            categories = [
                c for c in categories
                if (c.get("name") or "").strip()
                and (c.get("name") or "").strip().lower() not in ("total", "amount", "-")
            ]

        # No blank skeleton columns — empty schedule when books have no PPE
        # (SOFP with FAA ledgers should have produced categories above)

        # Ensure disposal fields exist (SME packs; zero when not separately tracked)
        for cat in categories:
            cat.setdefault("disposals", 0.0)
            cat.setdefault("dep_disposals", 0.0)
            # Split net cost movement into additions vs disposals when only net was stored
            add = float(cat.get("additions") or 0.0)
            if abs(float(cat.get("disposals") or 0.0)) < 1e-9 and add < -1e-9:
                cat["disposals"] = abs(add)
                cat["additions"] = 0.0

        def totals(key):
            return sum(float(c.get(key) or 0.0) for c in categories)

        tot = {
            "cost_prior": totals("cost_prior"),
            "cost_current": totals("cost_current"),
            "additions": totals("additions"),
            "disposals": totals("disposals"),
            "dep_prior": totals("dep_prior"),
            "dep_current": totals("dep_current"),
            "charge": totals("charge"),
            "dep_disposals": totals("dep_disposals"),
            "nbv_prior": totals("nbv_prior"),
            "nbv_current": totals("nbv_current"),
        }
        year_schedules = [
            {
                "year": yp,
                "title": _("Property, Plant and Equipment — Year %s") % yp,
                "opening_year": yp - 1,
                "closing_year": yp,
                "has_opening": False,
                "keys": {
                    "cost_open": None,
                    "cost_move": None,
                    "cost_disp": None,
                    "cost_close": "cost_prior",
                    "dep_open": None,
                    "dep_move": None,
                    "dep_disp": None,
                    "dep_close": "dep_prior",
                    "nbv_close": "nbv_prior",
                    "nbv_open": None,
                },
            },
            {
                "year": yc,
                "title": _("Property, Plant and Equipment — Year %s") % yc,
                "opening_year": yp,
                "closing_year": yc,
                "has_opening": True,
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
            },
        ]
        # 1y / same-window print: prior==current → do NOT emit two identical "Year 20XX" blocks
        single_period = (
            int(yp or 0) == int(yc or 0)
            or str(self._afg_global_period_span_pref() or "").strip().lower() in ("1y", "1m")
            or bool(self.env.context.get("afg_ppe_single_year"))
        )
        if single_period:
            year_schedules = [year_schedules[-1]]
        return {
            "year_prior": yp,
            "year_current": yc,
            "currency": self.currency_id.name or "AED",
            "categories": [c["name"] for c in categories],
            "items": categories,
            "totals": tot,
            "year_schedules": year_schedules,
            "single_year": bool(single_period),
        }

    def _afg_cashflow_statement_data(self, tree_by_section):
        """Indirect-method cash flow rows (Particulars / years / Remark) for dashboard + PDF.

        All amounts are TB/SOFP-linked. Prior-year WC/PPE moves use Y−2 closing when
        account drills are available; financing comes from equity movements first.
        """
        self.ensure_one()
        pl = tree_by_section.get("pl") or []
        bs = tree_by_section.get("bs") or []
        yp, yc = self.year_prior, self.year_current
        curr_name = self.currency_id.name or "AED"
        cids = self._afg_column_company_order() or self._tb_company_ids()
        y2_end = False
        if yp:
            y2_end = fields.Date.from_string("%s-12-31" % (int(yp) - 1))
        tb_y2 = self._fetch_tb_closing(y2_end, cids) if y2_end and cids else {}

        def _node_closing(node, tb_map):
            aids = self._afg_leaf_account_ids_from_node(node) if node else []
            if not aids or not tb_map:
                return None
            return sum(float(tb_map.get(aid, 0.0) or 0.0) for aid in aids)

        net_node = self._afg_type_by_key(pl, "net_profit")
        if not net_node:
            tp, tc, _co_p, _co_c = self._afg_sum_branch_nodes(pl)
            net_p, net_c = tp, tc
        else:
            net_p, net_c = self._afg_amt_pair(net_node)

        depr = self._afg_l1_by_code(pl, "AFG_DEPR_PL")
        depr_p, depr_c = self._afg_amt_pair(depr)
        depr_p, depr_c = abs(depr_p), abs(depr_c)

        def asset_move(code):
            """Cash effect of asset change (increase uses cash)."""
            node = self._afg_l1_by_code(bs, code)
            p, c = self._afg_amt_pair(node)
            y2 = _node_closing(node, tb_y2)
            if y2 is None:
                prior_move = 0.0
            else:
                # Face SOFP uses presentation signs; use absolute stock for WC delta
                prior_move = abs(float(y2)) - abs(p)
            curr_move = abs(p) - abs(c)
            return prior_move, curr_move

        def liab_move(code):
            """Cash effect of liability change (increase provides cash)."""
            node = self._afg_l1_by_code(bs, code)
            p, c = self._afg_amt_pair(node)
            y2 = _node_closing(node, tb_y2)
            if y2 is None:
                prior_move = 0.0
            else:
                prior_move = abs(p) - abs(float(y2))
            curr_move = abs(c) - abs(p)
            return prior_move, curr_move

        ar_p, ar_c = asset_move("AFG_AR")
        inv_p, inv_c = asset_move("AFG_INV")
        prep_p, prep_c = asset_move("AFG_PREP")
        ap_p, ap_c = liab_move("AFG_AP")
        tax_p, tax_c = liab_move("AFG_TAX")
        eos_p, eos_c = liab_move("AFG_EOS")

        # Investing: PPE cost additions from FA schedule when available, else NBV Δ
        far = self._afg_fixed_assets_recon_data(tree_by_section)
        fa_tot = far.get("totals") or {}
        purchase_c = -abs(float(fa_tot.get("additions") or 0.0))
        purchase_p = 0.0
        if abs(purchase_c) < 1e-9:
            ppe_p_bal, ppe_c_bal = self._afg_amt_pair(self._afg_l1_by_code(bs, "AFG_PPE"))
            if abs(ppe_c_bal) > abs(ppe_p_bal):
                purchase_c = -(abs(ppe_c_bal) - abs(ppe_p_bal))
        disp_nbv = abs(float(fa_tot.get("disposals") or 0.0)) - abs(
            float(fa_tot.get("dep_disposals") or 0.0)
        )
        if disp_nbv < 0:
            disp_nbv = 0.0
        invest_p = purchase_p
        invest_c = purchase_c + (disp_nbv if disp_nbv > 1e-9 else 0.0)

        # Financing from equity SOCE movements (capital / drawings)
        soce = self._afg_equity_statement_data(tree_by_section)
        fin_p = 0.0
        fin_c = 0.0
        capital_c = drawings_c = cap_pri = draw_pri = 0.0
        for row in soce.get("rows") or []:
            key = row.get("key") or ""
            tot = row.get("total") or {}
            cur = float(tot.get("current") or 0.0)
            pri = float(tot.get("prior") or 0.0)
            if key == "capital":
                capital_c, cap_pri = cur, pri
                fin_c += cur
                fin_p += pri
            elif key == "drawings":
                # Cash outflow for distributions (SOCE equity reduction → negative cash)
                drawings_c = -abs(cur) if abs(cur) > 1e-9 else 0.0
                draw_pri = -abs(pri) if abs(pri) > 1e-9 else 0.0
                fin_c += drawings_c
                fin_p += draw_pri

        cash_p, cash_c = self._afg_amt_pair(self._afg_l1_by_code(bs, "AFG_CASH"))

        op_before_wc_p = net_p + depr_p + eos_p
        op_before_wc_c = net_c + depr_c + eos_c
        wc_p = ar_p + inv_p + prep_p + ap_p + tax_p
        wc_c = ar_c + inv_c + prep_c + ap_c + tax_c
        op_net_p = op_before_wc_p + wc_p
        op_net_c = op_before_wc_c + wc_c

        net_inc_p = op_net_p + invest_p + fin_p
        net_inc_c = op_net_c + invest_c + fin_c
        expected_inc_c = cash_c - cash_p
        cash_node = self._afg_l1_by_code(bs, "AFG_CASH")
        cash_y2 = _node_closing(cash_node, tb_y2)
        if cash_y2 is not None:
            expected_inc_p = cash_p - float(cash_y2)
            if abs(expected_inc_p - net_inc_p) > 0.005:
                fin_p += expected_inc_p - net_inc_p
                net_inc_p = expected_inc_p
        else:
            expected_inc_p = net_inc_p

        fin_balanced = False
        other_fin_c = 0.0
        if abs(expected_inc_c - net_inc_c) > 0.005:
            other_fin_c = expected_inc_c - net_inc_c
            # If residual equals drawings already shown, do not double-count
            if abs(abs(other_fin_c) - abs(drawings_c)) <= 0.505 and abs(drawings_c) > 1e-9:
                other_fin_c = 0.0
                net_inc_c = expected_inc_c
            elif abs(other_fin_c) <= 1.005:
                # Whole-AED rounding drift vs SOFP cash — absorb into drawings, no plug line
                if abs(float(drawings_c or 0.0)) > 1e-9:
                    drawings_c = float(drawings_c) + float(other_fin_c)
                    fin_c = float(fin_c) + float(other_fin_c)
                other_fin_c = 0.0
                fin_balanced = False
                net_inc_c = expected_inc_c
            else:
                fin_c += other_fin_c
                net_inc_c = expected_inc_c
                fin_balanced = abs(other_fin_c) > 0.005
        else:
            net_inc_c = expected_inc_c

        def cf_line(kind, label, prior=None, current=None, remark=""):
            return {
                "kind": kind,
                "label": label,
                "prior": prior,
                "current": current,
                "remark": remark or "",
            }

        rows = [
            cf_line("section", _("Cash flows from operating activities")),
            cf_line("ledger", _("Profit for the year"), net_p, net_c),
            cf_line("ledger", _("Adjustments for depreciation and amortisation"), depr_p, depr_c),
            cf_line("ledger", _("Provision for employees' terminal benefits"), eos_p, eos_c),
            cf_line("group", _("Operating cash flow before working capital changes"),
                    op_before_wc_p, op_before_wc_c),
            cf_line("ledger", _("(Increase)/decrease in trade and other receivables"), ar_p, ar_c),
            cf_line("ledger", _("(Increase)/decrease in inventories"), inv_p, inv_c),
            cf_line("ledger", _("(Increase)/decrease in deposits, prepayments and other receivables"),
                    prep_p, prep_c),
            cf_line("ledger", _("Increase/(decrease) in trade and other payables"), ap_p, ap_c),
            cf_line("ledger", _("Increase/(decrease) in tax balances"), tax_p, tax_c),
            cf_line("group", _("Net cash from/(used in) operating activities"), op_net_p, op_net_c),
            cf_line("section", _("Cash flows from investing activities")),
        ]
        if abs(purchase_c) > 1e-9 or abs(purchase_p) > 1e-9:
            rows.append(cf_line(
                "ledger", _("Purchase of property, plant and equipment"),
                purchase_p if abs(purchase_p) > 1e-9 else None,
                purchase_c if abs(purchase_c) > 1e-9 else None,
            ))
        if disp_nbv > 1e-9:
            rows.append(cf_line(
                "ledger", _("Proceeds from disposal of property, plant and equipment"),
                None, disp_nbv,
            ))
        rows.extend([
            cf_line("group", _("Net cash from/(used in) investing activities"), invest_p, invest_c),
            cf_line("section", _("Cash flows from financing activities")),
        ])
        if abs(capital_c) > 1e-9 or abs(cap_pri) > 1e-9:
            rows.append(cf_line(
                "ledger", _("Capital introduced/(repaid)"),
                cap_pri if abs(cap_pri) > 1e-9 else None,
                capital_c if abs(capital_c) > 1e-9 else None,
            ))
        if abs(drawings_c) > 1e-9 or abs(draw_pri) > 1e-9:
            rows.append(cf_line(
                "ledger", _("Drawings / distributions"),
                draw_pri if abs(draw_pri) > 1e-9 else None,
                drawings_c if abs(drawings_c) > 1e-9 else None,
            ))
        # Unexplained financing plug — only if SOCE did not already classify drawings
        if fin_balanced and abs(other_fin_c) > 1e-9:
            soce_has_drawings = any((r.get("key") or "") == "drawings" for r in (soce.get("rows") or []))
            if soce_has_drawings and abs(drawings_c) < 1e-9:
                rows.append(cf_line(
                    "ledger", _("Drawings / distributions"),
                    None, other_fin_c,
                ))
                fin_balanced = False
                other_fin_c = 0.0
            else:
                rows.append(cf_line(
                    "ledger", _("Other financing movements"),
                    None, other_fin_c,
                ))
        rows.extend([
            cf_line("group", _("Net cash from/(used in) financing activities"), fin_p, fin_c),
            cf_line("group", _("Net increase/(decrease) in cash and cash equivalents"),
                    net_inc_p, net_inc_c),
            cf_line("ledger", _("Cash and cash equivalents at 1 January %s") % yp,
                    float(cash_y2) if cash_y2 is not None else None, cash_p),
            cf_line("group", _("Cash and cash equivalents at 31 December %s") % yc, cash_p, cash_c),
        ])
        return {
            "year_prior": yp,
            "year_current": yc,
            "currency": curr_name,
            "rows": rows,
            "financing_balanced": bool(fin_balanced and abs(float(other_fin_c or 0.0)) > 1e-9),
            "financing_plug": float(other_fin_c or 0.0),
        }

    def _afg_finalize_soce_whole_units(self, soce, eq_prior_face, eq_current_face):
        """Round SOCE to whole AED and force Opening+moves=Closing = SOFP equity.

        Independent ROUND_HALF_UP on each SOCE cell can break the roll-forward by AED 1–2
        versus printed SOFP. Absorb the residual into Drawings (Accumulated Losses column)
        so DED print ties exactly with no Other Transfers plug.
        """
        self.ensure_one()
        soce = dict(soce or {})
        cols = list(soce.get("columns") or [])
        col_keys = [c.get("key") for c in cols if c.get("key")]
        if not col_keys:
            return soce
        rows = []
        for row in soce.get("rows") or []:
            r = dict(row)
            cells = {}
            for k in col_keys:
                cell = dict((r.get("cells") or {}).get(k) or {})
                for field in ("prior", "current"):
                    if cell.get(field) is None:
                        cell[field] = 0.0
                    else:
                        cell[field] = float(self._afg_round_amt(cell.get(field)) or 0)
                cells[k] = cell
            r["cells"] = cells
            r["total"] = {
                "prior": float(sum(float(cells[k]["prior"]) for k in col_keys)),
                "current": float(sum(float(cells[k]["current"]) for k in col_keys)),
            }
            rows.append(r)

        by_key = {r.get("key"): r for r in rows}
        eq_p = float(self._afg_round_amt(eq_prior_face) or 0)
        eq_c = float(self._afg_round_amt(eq_current_face) or 0)

        def _ensure_drawings():
            draw = by_key.get("drawings")
            if draw:
                return draw
            draw = {
                "key": "drawings",
                "label": _("Drawings / Distributions"),
                "cells": {k: {"prior": 0.0, "current": 0.0} for k in col_keys},
                "total": {"prior": 0.0, "current": 0.0},
            }
            # Insert before closing
            idx = next((i for i, r in enumerate(rows) if r.get("key") == "closing"), len(rows))
            rows.insert(idx, draw)
            by_key["drawings"] = draw
            soce["drawings_from_re_ledger"] = True
            return draw

        def _bump(row, which, amount, prefer="re"):
            if abs(float(amount or 0.0)) < 0.005:
                return
            bucket = prefer if prefer in (row.get("cells") or {}) else col_keys[0]
            cell = (row.get("cells") or {}).setdefault(bucket, {"prior": 0.0, "current": 0.0})
            cell[which] = float(cell.get(which) or 0.0) + float(amount)
            row["total"][which] = float(sum(
                float((row.get("cells") or {}).get(k, {}).get(which) or 0.0) for k in col_keys
            ))

        # Force closing totals to printed SOFP equity
        for which, target in (("prior", eq_p), ("current", eq_c)):
            close = by_key.get("closing")
            if not close:
                continue
            gap = float(target) - float((close.get("total") or {}).get(which) or 0.0)
            _bump(close, which, gap, prefer="re")

        # Opening (current col) = prior closing (continuity)
        opening = by_key.get("opening")
        closing = by_key.get("closing")
        if opening and closing:
            want_open_c = float((closing.get("total") or {}).get("prior") or 0.0)
            gap_open = want_open_c - float((opening.get("total") or {}).get("current") or 0.0)
            _bump(opening, "current", gap_open, prefer="re")

        # Opening + Capital + Profit + Drawings + Transfers = Closing (both years)
        for which in ("prior", "current"):
            move = 0.0
            for key in ("opening", "capital", "profit", "drawings", "transfers"):
                r = by_key.get(key)
                if r:
                    move += float((r.get("total") or {}).get(which) or 0.0)
            close_v = float((by_key.get("closing") or {}).get("total", {}).get(which) or 0.0)
            gap = close_v - move
            if abs(gap) < 0.005:
                continue
            _bump(_ensure_drawings(), which, gap, prefer="re")

        # Profit row: keep in sync with rounded SOFP/P&L when present on face
        # (already rounded individually; roll absorb handles AED1)

        soce["rows"] = rows
        soce["columns"] = cols
        soce["whole_units"] = True
        return soce

    def _afg_equity_statement_data(self, tree_by_section):
        """Statement of Changes in Equity matrix (TB-linked; no hardcoded figures)."""
        self.ensure_one()
        yp, yc = self.year_prior, self.year_current
        bs = tree_by_section.get("bs") or []
        pl = tree_by_section.get("pl") or []
        eq_root = self._afg_type_by_key(bs, "equity")
        if not eq_root:
            eq_root = self._afg_find_equity_shell(bs)
        leaves = self._afg_ppe_collect_leaves(eq_root) if eq_root else []
        # Equity statement section — only if SOFP equity had no ledger leaves (avoid double count)
        if not leaves:
            eq_sec = tree_by_section.get("equity") or []
            for root in eq_sec:
                leaves.extend(self._afg_ppe_collect_leaves(root))

        cols = OrderedDict([
            ("capital", {"key": "capital", "name": _("Share capital / Capital")}),
            ("current", {"key": "current", "name": _("Owners' current account")}),
            ("re", {"key": "re", "name": _("Retained earnings")}),
            ("other", {"key": "other", "name": _("Other equity")}),
        ])

        def _bucket(label):
            low = (label or "").lower()
            if any(k in low for k in ("drawing", "dividend", "distribution", "withdraw")):
                return "drawings_account"
            if any(k in low for k in ("capital", "share capital", "paid up", "paid-up")):
                return "capital"
            if any(k in low for k in ("current account", "partner current", "owner current", "propriet")):
                return "current"
            if any(k in low for k in (
                "retained", "accumulat", "profit for the year", "loss for the year",
                "current year earning", "undistributed",
            )):
                return "re"
            return "other"

        stock = {k: {"prior": 0.0, "current": 0.0} for k in cols}
        drawings_stock = {"prior": 0.0, "current": 0.0}
        seen = set()
        for leaf in leaves:
            # Dedupe by account when present — BS + Equity section often repeat the same ledger
            aid = leaf.get("account_id")
            if aid:
                key = "acc:%s" % int(aid)
            else:
                key = leaf.get("id") or id(leaf)
            if key in seen:
                continue
            seen.add(key)
            # Profit/(Loss) is a movement row — not part of opening/closing stock columns
            if leaf.get("type_key") == "cy_pnl" or leaf.get("id") == "bs-cy-pnl":
                continue
            if self._afg_node_looks_like_cy_pnl(leaf):
                continue
            lbl = (leaf.get("ledger_caption") or leaf.get("label") or "").strip()
            if not lbl:
                continue
            b = _bucket(lbl)
            p = float(leaf.get("prior") or 0.0)
            c = float(leaf.get("current") or 0.0)
            # Equity face often credit-positive; keep signed as presented on SOFP
            if b == "drawings_account":
                drawings_stock["prior"] += p
                drawings_stock["current"] += c
            elif b in stock:
                stock[b]["prior"] += p
                stock[b]["current"] += c

        # If nothing under equity leaves, use AFG_EQ L1 total in "other"
        if not any(abs(stock[k]["current"]) > 1e-9 or abs(stock[k]["prior"]) > 1e-9 for k in stock):
            eq_l1 = self._afg_l1_by_code(bs, "AFG_EQ")
            if eq_l1:
                stock["other"]["prior"], stock["other"]["current"] = self._afg_amt_pair(eq_l1)

        # Profit/(Loss) movement (SOFP cy_pnl preferred — same as Balance Sheet inject)
        net_node = self._afg_type_by_key(pl, "net_profit")
        if net_node:
            profit_p, profit_c = self._afg_amt_pair(net_node)
        else:
            tp, tc, _a, _b = self._afg_sum_branch_nodes(pl)
            profit_p, profit_c = tp, tc
        cy = None
        if eq_root:
            cy = self._afg_find_cy_pnl_node(eq_root.get("children") or [])
        if cy:
            profit_p = float(cy.get("prior") or 0.0)
            profit_c = float(cy.get("current") or 0.0)

        # Movement rows use period change; opening uses stock prior
        def _col_closing(k):
            # Closing RE = stock (UE / RE ledgers) + Profit/(Loss) for the year
            if k == "re":
                return stock[k]["current"] + profit_c
            return stock[k]["current"]

        capital_intro_c = stock["capital"]["current"] - stock["capital"]["prior"]
        capital_intro_p = 0.0
        # Historical MOA / paid-up capital often has nil prior in TB while current holds
        # the full balance — do NOT present that as "Capital introduced" in the *current* year.
        if abs(stock["capital"]["prior"]) < 0.505 and abs(stock["capital"]["current"]) >= 0.505:
            stock["capital"]["prior"] = float(stock["capital"]["current"])
            capital_intro_c = 0.0
        current_move_c = stock["current"]["current"] - stock["current"]["prior"]
        current_move_p = 0.0
        # Drawings movement (increase in drawings account reduces equity)
        drawings_c = drawings_stock["current"] - drawings_stock["prior"]
        drawings_p = 0.0
        # RE stock change excluding profit row (profit is separate movement)
        re_delta_c = stock["re"]["current"] - stock["re"]["prior"]
        re_delta_p = float(stock["re"]["prior"] or 0.0)
        other_delta_c = stock["other"]["current"] - stock["other"]["prior"]
        other_delta_p = 0.0
        # Retained Earnings / Accumulated Losses ledger YoY (face-signed)
        re_ledger_delta_c = float(re_delta_c or 0.0)
        re_ledger_delta_p = float(re_delta_p or 0.0)

        def _amt_map(prior_by_col, current_by_col):
            cells = {}
            tot_p = tot_c = 0.0
            for k in cols:
                pv = float(prior_by_col.get(k, 0.0) or 0.0)
                cv = float(current_by_col.get(k, 0.0) or 0.0)
                cells[k] = {"prior": pv, "current": cv}
                tot_p += pv
                tot_c += cv
            return cells, {"prior": tot_p, "current": tot_c}

        # Opening prior column = start of prior year. Without Y−2 TB we start at nil and
        # present Capital Introduced + Drawings in the prior column so the roll-forward ties.
        open_cells, open_tot = _amt_map(
            {k: 0.0 for k in cols},
            {k: stock[k]["prior"] for k in cols},
        )
        # Add drawings into opening/closing under current account if present
        if abs(drawings_stock["prior"]) > 1e-9 or abs(drawings_stock["current"]) > 1e-9:
            open_cells["current"]["current"] += drawings_stock["prior"]
            open_tot["current"] += drawings_stock["prior"]

        # Opening (current column) must equal SOFP equity prior (end of prior year).
        # Equity face prior includes Profit/(Loss) comparative (cy_pnl.prior), which is
        # excluded from stock leaves — fold that residual into opening RE so SOCE ties.
        eq_prior_face = float((eq_root or {}).get("prior") or 0.0)
        open_gap = eq_prior_face - float(open_tot.get("current") or 0.0)
        if abs(open_gap) > 1e-9:
            open_cells["re"]["current"] = float(open_cells["re"]["current"] or 0.0) + open_gap
            open_tot["current"] = float(open_tot.get("current") or 0.0) + open_gap

        # Prior-year capital introduced when opening prior is nil but capital existed at
        # end of prior (first comparative year / incorporation year).
        if abs(float(open_tot.get("prior") or 0.0)) < 0.505 and abs(
            float(stock["capital"]["prior"] or 0.0)
        ) >= 0.505:
            capital_intro_p = float(stock["capital"]["prior"] or 0.0)

        # Fold owners' current Δ into capital-introduced only when material; otherwise
        # keep Share Capital historical (opening = closing for capital column).
        capital_cells, capital_tot = _amt_map(
            {"capital": capital_intro_p, "current": current_move_p, "re": 0.0, "other": 0.0},
            {"capital": capital_intro_c, "current": current_move_c, "re": 0.0, "other": 0.0},
        )
        profit_cells, profit_tot = _amt_map(
            {"capital": 0.0, "current": 0.0, "re": profit_p, "other": 0.0},
            {"capital": 0.0, "current": 0.0, "re": profit_c, "other": 0.0},
        )

        # Other transfers = residual RE/other stock change (excl. profit). Prefer to
        # absorb into opening RE so DED SOCE shows Opening / Profit / Drawings / Closing.
        transfer_re = float(re_delta_c) - float(open_gap or 0.0)
        transfer_other = float(other_delta_c)
        transfer_material = abs(transfer_re) >= 0.505 or abs(transfer_other) >= 0.505
        if not transfer_material and (abs(transfer_re) > 1e-9 or abs(transfer_other) > 1e-9):
            # Immaterial residual — keep Opening + Profit + Drawings = Closing
            open_cells["re"]["current"] = float(open_cells["re"]["current"] or 0.0) + transfer_re
            open_cells["other"]["current"] = float(open_cells["other"]["current"] or 0.0) + transfer_other
            open_tot["current"] = float(open_tot.get("current") or 0.0) + transfer_re + transfer_other
            transfer_re = transfer_other = 0.0
        # Material residual that reduces equity with no separate drawings ledger →
        # classify as Drawings / Distributions (DED), not "Other Transfers".
        # Amount equals Retained Earnings / Accumulated Losses ledger movement (TB).
        drawings_from_residual = False
        drawings_from_ledger = abs(drawings_c) >= 0.505
        if abs(drawings_c) < 0.505 and abs(transfer_other) < 0.505 and abs(transfer_re) >= 0.505:
            drawings_c = float(drawings_c or 0.0) + float(transfer_re)
            transfer_re = 0.0
            transfer_material = False
            drawings_from_residual = True
        # Prior-year drawings from RE ledger build-up when opening prior was nil
        if abs(drawings_p) < 0.505 and abs(capital_intro_p) >= 0.505 and abs(re_ledger_delta_p) >= 0.505:
            drawings_p = float(re_ledger_delta_p)
            drawings_from_residual = True
        if drawings_from_residual or not drawings_from_ledger:
            # Keep Share Capital + Accumulated Losses columns; show drawings on RE
            drawings_cells, drawings_tot = _amt_map(
                {"capital": 0.0, "current": 0.0, "re": drawings_p, "other": 0.0},
                {"capital": 0.0, "current": 0.0, "re": drawings_c, "other": 0.0},
            )
        else:
            drawings_cells, drawings_tot = _amt_map(
                {"capital": 0.0, "current": drawings_p, "re": 0.0, "other": 0.0},
                {"capital": 0.0, "current": drawings_c, "re": 0.0, "other": 0.0},
            )
        transfer_cells, transfer_tot = _amt_map(
            {k: 0.0 for k in cols},
            {"capital": 0.0, "current": 0.0, "re": transfer_re, "other": transfer_other},
        )
        close_cells, close_tot = _amt_map(
            {
                k: (
                    stock[k]["prior"] + (profit_p if k == "re" else 0.0)
                    + (drawings_stock["prior"] if k == "current" else 0.0)
                )
                for k in cols
            },
            {
                k: (
                    _col_closing(k)
                    + (drawings_stock["current"] if k == "current" else 0.0)
                )
                for k in cols
            },
        )

        # Force SOCE closing total to SOFP equity face (both years)
        eq_curr_face = float((eq_root or {}).get("current") or 0.0)
        eq_prior_face2 = float((eq_root or {}).get("prior") or 0.0)
        close_gap_c = eq_curr_face - float(close_tot.get("current") or 0.0)
        close_gap_p = eq_prior_face2 - float(close_tot.get("prior") or 0.0)
        if abs(close_gap_c) >= 0.005 and "re" in close_cells:
            close_cells["re"]["current"] = float(close_cells["re"]["current"] or 0.0) + close_gap_c
            close_tot["current"] = float(close_tot.get("current") or 0.0) + close_gap_c
        if abs(close_gap_p) >= 0.005 and "re" in close_cells:
            close_cells["re"]["prior"] = float(close_cells["re"]["prior"] or 0.0) + close_gap_p
            close_tot["prior"] = float(close_tot.get("prior") or 0.0) + close_gap_p

        # Relabel RE column from closing face balance
        if close_tot["current"] < -1e-9 or stock["re"]["current"] < -1e-9:
            cols["re"]["name"] = _("Accumulated Losses")
        elif close_tot["current"] > 1e-9 or abs(stock["re"]["current"]) > 1e-9:
            cols["re"]["name"] = _("Retained Earnings")
        cols["capital"]["name"] = _("Share Capital")

        rows = [
            {"key": "opening", "label": _("Opening Balance"), "cells": open_cells, "total": open_tot, "bold": True},
        ]
        # Capital introduced only when there is a real in-year movement (not MOA history)
        if abs(float(capital_tot.get("current") or 0.0)) >= 0.505 or abs(
            float(capital_tot.get("prior") or 0.0)
        ) >= 0.505:
            rows.append({
                "key": "capital",
                "label": _("Capital Introduced/(Repaid)"),
                "cells": capital_cells,
                "total": capital_tot,
            })
        rows.append({
            "key": "profit",
            "label": _("Profit for the Year"),
            "cells": profit_cells,
            "total": profit_tot,
        })
        if abs(float(drawings_tot.get("current") or 0.0)) >= 0.505 or abs(
            float(drawings_tot.get("prior") or 0.0)
        ) >= 0.505:
            rows.append({
                "key": "drawings",
                "label": _("Drawings / Distributions"),
                "cells": drawings_cells,
                "total": drawings_tot,
            })
        # Other Transfers only when a material unexplained residual remains
        if abs(float(transfer_tot.get("current") or 0.0)) >= 0.505 or abs(
            float(transfer_tot.get("prior") or 0.0)
        ) >= 0.505:
            rows.append({
                "key": "transfers",
                "label": _("Other Transfers"),
                "cells": transfer_cells,
                "total": transfer_tot,
            })
        rows.append({
            "key": "closing",
            "label": _("Closing Balance"),
            "cells": close_cells,
            "total": close_tot,
            "bold": True,
        })

        # Drop unused equity heads (all-zero columns) for a clean DED face
        keep_keys = []
        for k in list(cols.keys()):
            used = False
            for row in rows:
                cell = (row.get("cells") or {}).get(k) or {}
                if abs(float(cell.get("prior") or 0.0)) >= 0.505 or abs(
                    float(cell.get("current") or 0.0)
                ) >= 0.505:
                    used = True
                    break
            if used:
                keep_keys.append(k)
        if not keep_keys:
            keep_keys = list(cols.keys())
        cols = OrderedDict((k, cols[k]) for k in keep_keys if k in cols)
        for row in rows:
            cells = row.get("cells") or {}
            row["cells"] = {k: cells.get(k) or {"prior": 0.0, "current": 0.0} for k in cols}
            tot_p = sum(float((row["cells"][k].get("prior") or 0.0)) for k in cols)
            tot_c = sum(float((row["cells"][k].get("current") or 0.0)) for k in cols)
            row["total"] = {"prior": tot_p, "current": tot_c}

        # Force Opening + Capital + Profit + Drawings + Transfers = Closing (both years).
        # Absorb residual into Drawings on Accumulated Losses (RE ledger-linked).
        by_key = {r.get("key"): r for r in rows}

        def _roll_gap(which):
            total = 0.0
            for key in ("opening", "capital", "profit", "drawings", "transfers"):
                r = by_key.get(key)
                if r:
                    total += float((r.get("total") or {}).get(which) or 0.0)
            close_v = float((by_key.get("closing") or {}).get("total", {}).get(which) or 0.0)
            return close_v - total

        for which in ("prior", "current"):
            gap = _roll_gap(which)
            if abs(gap) < 0.005:
                continue
            draw = by_key.get("drawings")
            if not draw:
                draw = {
                    "key": "drawings",
                    "label": _("Drawings / Distributions"),
                    "cells": {k: {"prior": 0.0, "current": 0.0} for k in cols},
                    "total": {"prior": 0.0, "current": 0.0},
                }
                rows.insert(max(len(rows) - 1, 0), draw)
                by_key["drawings"] = draw
                drawings_from_residual = True
            bucket = "re" if "re" in (draw.get("cells") or {}) else (
                next(iter(cols), None)
            )
            if not bucket:
                continue
            cell = (draw.get("cells") or {}).setdefault(
                bucket, {"prior": 0.0, "current": 0.0}
            )
            cell[which] = float(cell.get(which) or 0.0) + gap
            draw["total"][which] = float((draw.get("total") or {}).get(which) or 0.0) + gap

        for row in rows:
            cells = row.get("cells") or {}
            row["total"] = {
                "prior": sum(float((cells.get(k) or {}).get("prior") or 0.0) for k in cols),
                "current": sum(float((cells.get(k) or {}).get("current") or 0.0) for k in cols),
            }

        soce = {
            "year_prior": yp,
            "year_current": yc,
            "currency": self.currency_id.name or "AED",
            "columns": list(cols.values()),
            "rows": rows,
            "face_signed": True,
            "ded_style": True,
            "drawings_from_re_ledger": bool(drawings_from_residual or drawings_from_ledger),
            "drawings_re_delta_prior": float(re_ledger_delta_p or 0.0),
            "drawings_re_delta_current": float(
                drawings_c if drawings_from_residual else re_ledger_delta_c
            ),
        }
        return self._afg_finalize_soce_whole_units(soce, eq_prior_face2, eq_curr_face)

    def _afg_schedules_data(self, tree_by_section):
        """IFRS-style note schedules for fixed assets, cash flow, equity, revenue, admin, EOSB."""
        self.ensure_one()
        yp, yc = self.year_prior, self.year_current
        pl = tree_by_section.get("pl") or []
        fa_recon = self._afg_fixed_assets_recon_data(tree_by_section)
        fixed_assets = []
        for cat in fa_recon.get("items") or []:
            fixed_assets.append({
                "category": cat.get("name") or "",
                "cost_prior": cat.get("cost_prior") or 0.0,
                "cost_current": cat.get("cost_current") or 0.0,
                "dep_prior": cat.get("dep_prior") or 0.0,
                "dep_current": cat.get("dep_current") or 0.0,
                "nbv_prior": cat.get("nbv_prior") or 0.0,
                "nbv_current": cat.get("nbv_current") or 0.0,
            })

        revenue_rows = []
        admin_rows = []
        for type_node in pl:
            tk = type_node.get("type_key") or ""
            if tk == "sales":
                revenue_rows = self._afg_collect_l1_rows(type_node.get("children"))
            elif tk == "expenses":
                for row in self._afg_collect_l1_rows(type_node.get("children")):
                    lbl = (row.get("label") or "").lower()
                    if any(x in lbl for x in ("admin", "general", "gna", "office", "professional")):
                        admin_rows.append(row)

        eosb_rows = self._afg_eosb_schedule_rows()
        equity_statement = self._afg_equity_statement_data(tree_by_section)
        return {
            "years": [yp, yc],
            "fixed_assets": fixed_assets,
            "fixed_assets_recon": fa_recon,
            "cashflow_statement": self._afg_cashflow_statement_data(tree_by_section),
            "equity_statement": equity_statement,
            "revenue": revenue_rows,
            "admin_expenses": admin_rows,
            "eosb": eosb_rows,
        }

    def _afg_eosb_schedule_rows(self):
        """Employees' end-of-service benefits (EOSB) — from HR when available."""
        self.ensure_one()
        rows = []
        Employee = self.env.get("hr.employee")
        if Employee is not None:
            try:
                employees = Employee.search([
                    ("company_id", "in", self._tb_company_ids()),
                    ("active", "=", True),
                ], limit=200)
            except Exception:
                employees = Employee.browse()
            for emp in employees:
                name = emp.name or ""
                join = getattr(emp, "joining_date", False) or getattr(emp, "date_start", False)
                years = 0.0
                if join:
                    delta = self.date_to_current - fields.Date.to_date(join)
                    years = max(delta.days / 365.25, 0.0)
                gratuity = 0.0
                if hasattr(emp, "gratuity_amount"):
                    gratuity = float(emp.gratuity_amount or 0.0)
                rows.append({
                    "employee": name,
                    "join_date": fields.Date.to_string(join) if join else "",
                    "years_service": round(years, 1),
                    "prior": gratuity,
                    "current": gratuity,
                })
        if not rows:
            rows = [
                {"employee": _("Sample employee 1"), "join_date": "", "years_service": 5.0, "prior": 0.0, "current": 0.0},
                {"employee": _("Sample employee 2"), "join_date": "", "years_service": 3.0, "prior": 0.0, "current": 0.0},
            ]
        return rows

    def _afg_build_print_chapters(self, payload=None):
        """Print chapters gated by Report level L1–L4 (overrides base)."""
        self.ensure_one()
        payload = payload or self._get_audit_report_payload()
        pack = self._afg_export_report_pack()
        spec = self._afg_report_pack_spec(pack)
        max_level = self._afg_tree_depth_for_pack(pack)
        hide_lg = bool(spec.get('hide_lg'))
        cover = payload.get('cover') or {}
        ver = payload.get('version') or {}
        yp = ver.get('year_prior') or self.year_prior
        yc = ver.get('year_current') or self.year_current
        chapters = []
        allowed = set(spec.get('print_chapters') or [])

        def _strip_lg(rows):
            if not hide_lg:
                return rows
            out = []
            for r in rows or []:
                nr = dict(r)
                nr['lg'] = ''
                out.append(nr)
            return out

        def _append_tb_chapter():
            if not spec.get('show_tb'):
                return False
            tb = payload.get('trial_balance2') or payload.get('trial_balance') or {}
            panels = tb.get('panels') or []
            tb_rows = []
            if panels:
                for panel in panels:
                    tb_rows.append({
                        'lg': '',
                        'label': self._afg_proper_case(panel.get('title') or ''),
                        'label_raw': self._afg_proper_case(panel.get('title') or ''),
                        'prior': None, 'current': None,
                        'prior_disp': '—', 'current_disp': '—',
                        'tb_amounts': None, 'level': 0, 'bold': True,
                        'is_total': False, 'is_section_banner': True,
                    })
                    for root in panel.get('roots') or []:
                        if root.get('is_tb_section_total'):
                            continue
                        tree = self._afg_filter_tree_by_max_level([root], max_level)
                        tree = self._afg_round_tree_amounts(tree)
                        for tree_root in tree:
                            tb_rows.extend(self._afg_flatten_tree_for_export([tree_root], max_level=max_level))
            elif tb.get('roots'):
                tree = self._afg_filter_tree_by_max_level(tb.get('roots') or [], max_level)
                tree = self._afg_round_tree_amounts(tree)
                tb_rows = self._afg_flatten_tree_for_export(tree, max_level=max_level)
            if not tb_rows:
                return False
            title = self._afg_proper_case(_('Trial Balance'))
            chapters.append({
                'key': 'tb', 'title': title, 'kind': 'tb_face',
                'tb_columns': self._tb_period_column_labels_flat(),
                'tb_column_meta': self._tb_period_column_meta(),
                'col_prior': str(yp), 'col_current': str(yc),
                'rows': _strip_lg(tb_rows), 'hide_lg': hide_lg,
                'header': self._afg_print_header(title, yp, yc),
            })
            return True

        schedules = payload.get('schedules') or {}
        soce = schedules.get('equity_statement') or {}
        period_windows = self._afg_resolve_period_windows()
        period_labels = [w.get('label') or '' for w in period_windows]
        period_span = self._afg_global_period_span_pref()
        tb_appended = False
        equity_appended = False
        if 'fta' in allowed:
            fta_ch = self._afg_fta_print_chapter_dict(
                payload, yp, yc, hide_lg, period_labels, period_span,
            )
            if fta_ch:
                chapters.append(fta_ch)
        for sec in payload.get('sections') or []:
            sec_key = sec.get('key') or ''
            if sec_key not in ('pl', 'bs', 'equity'):
                continue
            if sec_key not in allowed:
                continue
            # Prefer SOCE matrix over stock equity tree for face / print
            if sec_key == 'equity':
                if soce.get('rows'):
                    title = self._afg_proper_case(_('Statement of Changes in Equity'))
                    soce_out = dict(soce)
                    single_period = (
                        len(period_labels) <= 1
                        or str(period_span or '').strip().lower() in ('1y', '1m')
                        or bool(payload.get('hide_comparative'))
                    )
                    soce_out['single_year'] = single_period
                    chapters.append({
                        'key': 'equity', 'title': title, 'kind': 'equity_soce',
                        'soce': soce_out,
                        'col_prior': '' if single_period else str(soce.get('year_prior') or yp),
                        'col_current': str(soce.get('year_current') or yc),
                        'hide_lg': True,
                        'hide_comparative': single_period,
                        'header': self._afg_print_header(
                            title, None if single_period else yp, yc
                        ),
                    })
                    equity_appended = True
                continue
            tree = sec.get('tree') or []
            if sec_key == 'bs':
                # Expand Owner Equity BEFORE L1 depth filter (else capital/RE disappear)
                tree = self._afg_bs_present_equity_components(tree)
            tree = self._afg_filter_tree_by_max_level(tree, max_level)
            tree = self._afg_round_tree_amounts(tree)
            if sec_key == 'bs':
                tree = self._afg_balance_bs_tree_after_round(tree)
            rows = _strip_lg(self._afg_flatten_tree_for_export(tree, max_level=max_level))
            if not rows:
                continue
            title = self._afg_proper_case(sec.get('title') or sec_key or '')
            single_period = (
                len(period_labels) <= 1
                or str(period_span or '').strip().lower() in ('1y', '1m')
            )
            hide_comp = bool(payload.get('hide_comparative')) or single_period
            if sec_key == 'bs':
                # DED / 1-year: SOFP shows current year only (no blank prior dashes)
                hide_comp_sec = hide_comp
            elif sec_key == 'pl':
                hide_comp_sec = hide_comp
            else:
                hide_comp_sec = False
            if hide_comp_sec:
                for r in rows:
                    r['prior'] = None
                    r['prior_disp'] = ''
            period_labs_ch = (
                [period_labels[-1]] if hide_comp_sec and period_labels
                else list(period_labels)
            )
            if hide_comp_sec and not period_labs_ch:
                period_labs_ch = [str(yc)]
            rows = self._afg_ensure_print_period_disp(rows, period_labs_ch)
            if sec_key in ('bs', 'pl'):
                rows = self._afg_force_statement_total_print_amounts(rows, period_labs_ch)
            chapters.append({
                'key': sec_key or 'sec', 'title': title, 'kind': 'statement',
                'col_prior': '' if hide_comp_sec else str(yp),
                'col_current': str(yc),
                'period_labels': period_labs_ch,
                'period_span': period_span,
                'hide_comparative': hide_comp_sec,
                'rows': rows, 'hide_lg': hide_lg,
                'header': self._afg_print_header(
                    title, None if hide_comp_sec else yp, yc
                ),
            })
            if sec_key == 'bs' and spec.get('show_tb') and not tb_appended:
                tb_appended = _append_tb_chapter()

        # Equity often lives under SOFP only — still print SOCE when schedule has rows
        if not equity_appended and 'equity' in allowed and soce.get('rows'):
            title = self._afg_proper_case(_('Statement of Changes in Equity'))
            soce_out = dict(soce)
            single_period = (
                len(period_labels) <= 1
                or str(period_span or '').strip().lower() in ('1y', '1m')
                or bool(payload.get('hide_comparative'))
            )
            soce_out['single_year'] = single_period
            chapters.append({
                'key': 'equity', 'title': title, 'kind': 'equity_soce',
                'soce': soce_out,
                'col_prior': '' if single_period else str(soce.get('year_prior') or yp),
                'col_current': str(soce.get('year_current') or yc),
                'hide_lg': True,
                'hide_comparative': single_period,
                'header': self._afg_print_header(
                    title, None if single_period else yp, yc
                ),
            })

        if not tb_appended and spec.get('show_tb'):
            _append_tb_chapter()

        cf = schedules.get('cashflow_statement') or {}
        if cf.get('rows') and 'cashflow' in allowed:
            hide_comp_cf = bool(payload.get('hide_comparative'))
            cf_rows = []
            for crow in cf.get('rows') or []:
                kind = crow.get('kind') or 'ledger'
                if kind == 'section':
                    lvl, lg = 0, 'L0'
                elif kind == 'group':
                    lvl, lg = 2, 'L2'
                else:
                    lvl, lg = 3, 'L3'
                # Pack depth: L1/L2 → section+group; L3 ledgers (no L2 groups); L4 full
                if pack <= 2 and kind == 'ledger':
                    continue
                if pack == 3 and kind == 'group':
                    continue
                if pack >= 4 and lvl > max_level:
                    continue
                lab = crow.get('label') or ''
                lab = self._afg_proper_case(lab) if kind != 'ledger' or lab.isupper() else lab
                prior = crow.get('prior')
                current = crow.get('current')
                if prior is not None:
                    prior = float(self._afg_round_amt(prior))
                if current is not None:
                    current = float(self._afg_round_amt(current))
                cf_rows.append({
                    'lg': '' if hide_lg else lg,
                    'label': lab, 'label_raw': lab,
                    'prior': None if hide_comp_cf else prior,
                    'current': current,
                    'prior_disp': '' if hide_comp_cf or prior is None else self._afg_fmt_amt(prior),
                    'current_disp': '' if current is None else self._afg_fmt_amt(current),
                    'level': lvl, 'bold': kind in ('section', 'group'),
                    'is_total': kind == 'group',
                    'remark': '' if pack <= 2 else (crow.get('remark') or ''),
                })
            if not cf_rows:
                pass
            else:
                title = self._afg_proper_case(_('Statement of Cash Flows'))
                chapters.append({
                    'key': 'cashflow', 'title': title, 'kind': 'cashflow',
                    'col_prior': '' if hide_comp_cf else str(cf.get('year_prior') or yp),
                    'col_current': str(cf.get('year_current') or yc),
                    'hide_comparative': hide_comp_cf,
                    'rows': cf_rows, 'hide_lg': hide_lg,
                    'header': self._afg_print_header(
                        title, None if hide_comp_cf else (cf.get('year_prior') or yp),
                        cf.get('year_current') or yc,
                    ),
                })

        far = schedules.get('fixed_assets_recon') or {}
        if far.get('items') and 'fixed_assets' in allowed:
            single_period = (
                len(period_labels) <= 1
                or str(period_span or '').strip().lower() in ('1y', '1m')
                or bool(payload.get('hide_comparative'))
                or int(yp or 0) == int(yc or 0)
            )
            far_use = dict(far)
            if single_period:
                far_use['single_year'] = True
                # Drop prior-year stub schedule when prior==current (duplicate "Year 2025")
                ysched = list(far_use.get('year_schedules') or [])
                if len(ysched) > 1:
                    far_use['year_schedules'] = [
                        s for s in ysched
                        if str(s.get('year')) == str(yc)
                    ] or ysched[-1:]
            matrix = self.with_context(
                afg_ppe_single_year=single_period
            )._afg_round_ppe_matrix(self._afg_ppe_matrix_from_recon(far_use))
            ppe_title = self._afg_proper_case(_('Property, Plant and Equipment'))
            chapters.append({
                'key': 'fixed_assets', 'title': ppe_title, 'kind': 'ppe_matrix',
                'col_prior': '' if single_period else str(matrix.get('year_prior') or yp),
                'col_current': str(matrix.get('year_current') or yc),
                'hide_comparative': single_period,
                'ppe': matrix,
                'header': self._afg_print_header(
                    ppe_title, None if single_period else yp, yc
                ),
            })

        notes = self._afg_resolve_statement_notes(payload.get('notes') or [])
        if notes and 'notes' in allowed:
            title = self._afg_proper_case(_('Notes to the Financial Statements'))
            chapters.append({
                'key': 'notes', 'title': title, 'kind': 'notes', 'notes': notes,
                'header': self._afg_print_header(title, yp, yc),
            })

        recon = schedules.get('fs_tb_reconciliation') or {}
        hp = int(spec.get('hierarchy_pack') or self._afg_hierarchy_pack(pack))
        if hp >= 4 and recon.get('rows') and 'fs_recon' in allowed:
            title = self._afg_proper_case(_('FS Adjustment / Reconciliation'))
            chapters.append({
                'key': 'fs_recon', 'title': title, 'kind': 'fs_recon',
                'recon': recon,
                'header': self._afg_print_header(title, yp, yc),
            })

        validations = payload.get('validations') or []
        if hp >= 4 and validations and 'validation' in allowed:
            title = self._afg_proper_case(_('Validation'))
            overall = 'PASS'
            if any((v.get('status') or '') == 'FAIL' for v in validations):
                overall = 'FAIL'
            elif any((v.get('status') or '') == 'WARN' for v in validations):
                overall = 'WARN'
            chapters.append({
                'key': 'validation', 'title': title, 'kind': 'validation',
                'validations': validations, 'overall': overall,
                'header': self._afg_print_header(title, yp, yc),
            })

        # Drop empty working-paper chapters (blank PDF pages)
        chapters = self._afg_filter_empty_print_chapters(chapters)

        chapters = self._afg_apply_years_order_to_chapters(chapters)
        chapters = self._afg_sync_print_soce_ppe_to_sofp(chapters)
        cover = dict(cover or {})
        cover['entity'] = self._afg_print_company_display()
        if not any((c.get('key') or '') == 'cover' for c in (chapters or [])):
            chapters = self._afg_prepend_cover_print_chapter(cover, chapters, yp, yc)
        chapters = self._afg_apply_print_page_include(chapters)
        flags = self._afg_print_page_setup_flags()
        doc = {
            'cover': cover, 'year_prior': yp, 'year_current': yc,
            'currency': cover.get('currency') or (self.currency_id.name or 'AED'),
            'chapters': chapters, 'alerts': payload.get('alerts') or [],
            'report_level': pack, 'report_pack': spec, 'hide_lg': hide_lg,
            'signatory': self._afg_signatory_block(),
            'signatory_label': _('Authorized Signatory'),
            'years_descending': self._afg_years_descending(),
            'period_span': period_span,
            'period_labels': list(period_labels),
            'arabic': bool(spec.get('arabic')),
            'rtl': bool(spec.get('rtl')),
            'print_page_setup': flags.get('print_page_setup') or 'default',
            'compact_hf': bool(flags.get('compact_hf')),
            'skip_empty_pages': bool(flags.get('skip_empty_pages')),
            'sign_last_only': bool(flags.get('sign_last_only')),
            'margin_header': int(flags.get('margin_header') or 10),
            'margin_footer': int(flags.get('margin_footer') or 10),
            'sign_gap_pt': int(flags.get('sign_gap_pt') or 28),
        }
        if spec.get('arabic'):
            doc = self._afg_apply_arabic_print_document(doc)
        if not self.env.context.get("afg_skip_statutory_face"):
            doc["chapters"] = self._afg_apply_statutory_face(doc.get("chapters") or [])
            doc["signatory_label"] = "(Managing Director)"
            doc["print_cover"] = False
        return doc

    def _afg_sync_print_soce_ppe_to_sofp(self, chapters):
        """Force printed SOCE closing / PPE NBV to match printed SOFP (zero AED drift)."""
        chapters = list(chapters or [])
        by = {c.get("key"): c for c in chapters}
        bs = by.get("bs") or {}
        eq_p = eq_c = None
        ppe_p = ppe_c = None
        for r in bs.get("rows") or []:
            tk = str(r.get("type_key") or "")
            lab = str(r.get("label_raw") or r.get("label") or "").lower()
            if tk == "equity" or lab == "equity":
                eq_p = r.get("prior")
                eq_c = r.get("current")
            if ("property" in lab and "plant" in lab) or lab in (
                "fixed assets", "ppe", "property, plant and equipment",
            ):
                ppe_p = r.get("prior")
                ppe_c = r.get("current")

        eq_ch = by.get("equity")
        if eq_ch and eq_ch.get("soce") and eq_c is not None:
            soce = self._afg_finalize_soce_whole_units(
                dict(eq_ch.get("soce") or {}),
                eq_p if eq_p is not None else 0.0,
                eq_c,
            )
            eq_ch = dict(eq_ch)
            eq_ch["soce"] = soce
            chapters = [eq_ch if c.get("key") == "equity" else c for c in chapters]

        fa = by.get("fixed_assets")
        if fa and fa.get("ppe") and (ppe_c is not None or ppe_p is not None):
            matrix = dict(fa.get("ppe") or {})
            targets = {
                str(matrix.get("year_prior") or ""): ppe_p,
                str(matrix.get("year_current") or ""): ppe_c,
            }
            # Also map empty year key to current
            if ppe_c is not None:
                targets[""] = ppe_c

            def _force_nbv(blocks, year_key):
                want = targets.get(str(year_key or ""), None)
                if want is None and year_key is None:
                    want = ppe_c
                if want is None:
                    return blocks
                want = float(want)
                out = []
                for block in blocks or []:
                    b = dict(block)
                    title = str(b.get("title") or "").lower()
                    if "net book" not in title:
                        out.append(b)
                        continue
                    rows = []
                    for prow in b.get("rows") or []:
                        pr = dict(prow)
                        lab = str(pr.get("label") or "").lower()
                        if "closing" in lab and pr.get("total") is not None:
                            old = float(pr.get("total") or 0.0)
                            gap = want - old
                            vals = list(pr.get("values") or [])
                            # Absorb into last non-null category
                            if vals and gap:
                                for i in range(len(vals) - 1, -1, -1):
                                    if vals[i] is not None:
                                        vals[i] = float(vals[i]) + gap
                                        break
                            pr["values"] = vals
                            pr["total"] = want
                            pr["values_disp"] = [
                                None if v is None else self._afg_fmt_amt(v) for v in vals
                            ]
                            pr["total_disp"] = self._afg_fmt_amt(want)
                        rows.append(pr)
                    b["rows"] = rows
                    out.append(b)
                return out

            if matrix.get("year_sections"):
                ysecs = []
                for ys in matrix.get("year_sections") or []:
                    y = dict(ys)
                    y["blocks"] = _force_nbv(y.get("blocks") or [], y.get("year"))
                    ysecs.append(y)
                matrix["year_sections"] = ysecs
            if matrix.get("blocks"):
                matrix["blocks"] = _force_nbv(matrix.get("blocks") or [], matrix.get("year_current"))
            fa = dict(fa)
            fa["ppe"] = matrix
            chapters = [fa if c.get("key") == "fixed_assets" else c for c in chapters]
        return chapters


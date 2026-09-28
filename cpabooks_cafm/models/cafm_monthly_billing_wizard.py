# -*- coding: utf-8 -*-
import base64
import csv
from io import StringIO

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.tools import html_escape


class CafmMonthlyBillingWizard(models.TransientModel):
    _name = "cafm.monthly.billing.wizard"
    _description = "CAFM Contract Monthly Billing Table"

    def _default_period_start(self):
        return (fields.Date.context_today(self) + relativedelta(months=-1)).replace(day=1)

    billing_scope = fields.Selection(
        [
            ("both", "Billed + Unbilled"),
            ("invoiced", "Invoiced"),
            ("pending", "Pending"),
        ],
        string="Billing scope",
        default="both",
        required=True,
        help="Billed + Unbilled = each client month shows invoiced (Billed) and "
             "not-yet-invoiced (Unbilled). Invoicing moves the amount from Unbilled "
             "to Billed in the same month. Pending = unbilled only. Invoiced = billed only.",
    )
    period_start = fields.Date(string="Period Start", default=_default_period_start, required=True)
    view_mode = fields.Selection(
        [
            ("all", "All"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("half_yearly", "Half Yearly"),
            ("yearly", "Yearly"),
            ("one_time", "One Time"),
        ],
        string="View",
        default="all",
        required=True,
    )
    hierarchy_all_projects = fields.Boolean(
        string="Show all projects",
        default=False,
        help="When enabled, project rows are visible for every customer.",
    )
    hierarchy_all_orders = fields.Boolean(
        string="Show all order lines",
        default=False,
        help="When enabled, contract order lines are visible under every project.",
    )
    report_html = fields.Html(string="Report", compute="_compute_report_html", sanitize=False)

    def _month_slots(self):
        self.ensure_one()
        start = fields.Date.to_date(self.period_start) if self.period_start else fields.Date.context_today(self)
        start = start.replace(day=1)
        return [
            {
                "start": start + relativedelta(months=index),
                "end": start + relativedelta(months=index + 1, days=-1),
                "label": (start + relativedelta(months=index)).strftime("%b"),
            }
            for index in range(12)
        ]

    def _format_amount(self, amount):
        return "{:,.2f}".format(amount or 0.0)

    def _empty_months(self):
        return [0.0 for _index in range(12)]

    def _empty_details(self):
        return [[] for _index in range(12)]

    def _month_index(self, target_date, months):
        target_date = fields.Date.to_date(target_date) if target_date else False
        if not target_date:
            return False
        for index, month in enumerate(months):
            if month["start"] <= target_date <= month["end"]:
                return index
        return False

    def _contract_frequency_domain(self):
        self.ensure_one()
        if self.view_mode == "all":
            return []
        if self.view_mode == "one_time":
            return [("id", "=", 0)]
        freq = "annually" if self.view_mode == "yearly" else self.view_mode
        return [("contract_id.invoice_frequency", "=", freq)]

    def _is_invoiced_order(self, order):
        return bool(order.invoice_id or order.state == "invoiced")

    def _show_split_amounts(self):
        return self.billing_scope == "both"

    def _bucket_date(self, order):
        if self.billing_scope == "both":
            # Keep billed and unbilled in the scheduled billing month so invoicing
            # moves the same cell from Unbilled to Billed.
            return order.invoice_date or order.date_order
        if self.billing_scope == "invoiced":
            if order.invoice_id and order.invoice_id.invoice_date:
                return order.invoice_id.invoice_date
            return order.invoice_date
        return order.invoice_date or order.date_order

    def _order_base_domain(self):
        self.ensure_one()
        base = [("company_id", "=", self.env.company.id)] + self._contract_frequency_domain()
        if self.billing_scope == "both":
            return expression.AND([base, [("state", "!=", "cancelled")]])
        if self.billing_scope == "invoiced":
            return expression.AND([
                base,
                expression.OR([
                    [("invoice_id", "!=", False)],
                    [("state", "=", "invoiced")],
                ]),
            ])
        return expression.AND([
            base,
            [
                ("invoice_id", "=", False),
                ("state", "not in", ("cancelled", "invoiced")),
            ],
        ])

    def _record_url(self, record):
        return "/web#id=%s&model=%s&view_type=form" % (record.id, record._name)

    def _append_source_detail(self, row, month_index, source, record, amount, kind="unbilled"):
        row["details"][month_index].append({
            "source": source,
            "name": record.display_name or record.name or source,
            "url": self._record_url(record),
            "amount": amount or 0.0,
            "kind": kind,
        })

    def _add_month_amount(self, node, month_index, amount, billed):
        amt = amount or 0.0
        node["months"][month_index] += amt
        node["billed" if billed else "unbilled"][month_index] += amt

    def _collect_hierarchy(self):
        """Return list of customer nodes: {partner_key, partner_id, name, partner_url, months, projects}."""
        self.ensure_one()
        if self.view_mode == "one_time":
            return []
        if self.billing_scope == "both":
            return self._collect_hierarchy_from_register()
        return self._collect_hierarchy_from_orders()

    def _date_in_month(self, target, month):
        target = fields.Date.to_date(target) if target else False
        if not target:
            return False
        return month["start"] <= target <= month["end"]

    def _order_month_rank(self, order, month):
        """Lower is better. Prefer invoice_date, then period end (Next Invoice), then start."""
        if self._date_in_month(order.invoice_date or order.date_order, month):
            rank = 1.0
        elif self._date_in_month(order.date_to, month):
            rank = 2.0
        elif self._date_in_month(order.date_from, month):
            rank = 3.0
        elif order.date_from and order.date_to:
            date_from = fields.Date.to_date(order.date_from)
            date_to = fields.Date.to_date(order.date_to)
            if date_from <= month["end"] and date_to >= month["start"]:
                rank = 4.0
            else:
                return 0.0
        else:
            return 0.0
        if self._is_invoiced_order(order):
            rank -= 0.5
        return rank

    def _assign_orders_to_month_keys(self, contracts, months_slots, month_line_keys):
        """Map (contract_id, YYYY-MM) → one contract order, each order used once."""
        assigned = {}
        if not contracts:
            return assigned
        orders = self.env["cpabooks.cafm.contract.order"].search([
            ("contract_id", "in", contracts.ids),
            ("state", "!=", "cancelled"),
        ])
        by_contract = {}
        for order in orders:
            by_contract.setdefault(order.contract_id.id, []).append(order)
        used = set()
        for contract in contracts:
            pending = list(by_contract.get(contract.id, []))
            for month in months_slots:
                month_key = month["start"].strftime("%Y-%m")
                if (contract.id, month_key) not in month_line_keys:
                    continue
                best = False
                best_rank = 99.0
                for order in pending:
                    if order.id in used:
                        continue
                    rank = self._order_month_rank(order, month)
                    if rank and rank < best_rank:
                        best_rank = rank
                        best = order
                if best:
                    assigned[(contract.id, month_key)] = best
                    used.add(best.id)
        return assigned

    def _customer_node(self, customers, partner):
        partner_key = partner.id if partner else 0
        return customers.setdefault(partner_key, {
            "partner_key": partner_key,
            "partner_id": partner.id if partner else False,
            "name": partner.display_name if partner else _("No Customer"),
            "partner_url": self._record_url(partner) if partner else "",
            "months": self._empty_months(),
            "billed": self._empty_months(),
            "unbilled": self._empty_months(),
            "projects": {},
        })

    def _project_node(self, cust, project):
        proj_key = project.id if project else 0
        return cust["projects"].setdefault(proj_key, {
            "project_key": proj_key,
            "project_id": project.id if project else False,
            "name": project.display_name if project else _("No Project"),
            "project_url": self._record_url(project) if project else "",
            "months": self._empty_months(),
            "billed": self._empty_months(),
            "unbilled": self._empty_months(),
            "orders": [],
        })

    def _sort_hierarchy(self, customers):
        out = sorted(customers.values(), key=lambda c: (c["name"] or "", c["partner_key"]))
        for cust in out:
            cust["projects"] = sorted(
                cust["projects"].values(),
                key=lambda p: (p["name"] or "", p["project_key"]),
            )
            for proj in cust["projects"]:
                proj["orders"].sort(key=lambda o: (o["contract_name"], o["task"], o["order_id"]))
        return out

    def _collect_hierarchy_from_register(self):
        """Billed + Unbilled from AMC Invoice Register Next Invoice months.

        Jul Next Invoice Amount on the register is invoicing_value per contract
        tagged for that month. The billing table uses the same rows so B + U
        matches that total. A matching Cont. Order marks the cell Billed.
        """
        months_slots = self._month_slots()
        month_keys = [month["start"].strftime("%Y-%m") for month in months_slots]
        key_index = {key: index for index, key in enumerate(month_keys)}
        domain = expression.AND([
            [
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
                ("month_key", "in", month_keys),
                ("contract_id.contract_status", "!=", "cancelled"),
            ],
            self._contract_frequency_domain(),
        ])
        month_lines = self.env["cpabooks.cafm.contract.month.line"].search(
            domain,
            order="client_id, project_id, name, month_sort, id",
        )
        contracts = month_lines.mapped("contract_id")
        line_keys = set((line.contract_id.id, line.month_key) for line in month_lines)
        assigned = self._assign_orders_to_month_keys(contracts, months_slots, line_keys)

        customers = {}
        contract_rows = {}
        for month_line in month_lines:
            month_index = key_index.get(month_line.month_key)
            if month_index is None:
                continue
            contract = month_line.contract_id
            partner = contract.client_id or month_line.client_id
            project = contract.project_id or month_line.project_id
            amt = month_line.invoicing_value or contract.invoicing_value or 0.0
            order = assigned.get((contract.id, month_line.month_key))
            billed = bool(order and self._is_invoiced_order(order))
            cust = self._customer_node(customers, partner)
            proj = self._project_node(cust, project)
            row_key = (cust["partner_key"], proj["project_key"], contract.id)
            line = contract_rows.get(row_key)
            if not line:
                line = {
                    "order_id": contract.id,
                    "task": contract.invoice_frequency or "",
                    "project_label": project.display_name if project else "",
                    "contract_id": contract.id,
                    "contract_name": contract.name or "",
                    "contract_url": self._record_url(contract),
                    "months": self._empty_months(),
                    "billed": self._empty_months(),
                    "unbilled": self._empty_months(),
                    "details": self._empty_details(),
                }
                contract_rows[row_key] = line
                proj["orders"].append(line)
            self._add_month_amount(line, month_index, amt, billed)
            self._add_month_amount(proj, month_index, amt, billed)
            self._add_month_amount(cust, month_index, amt, billed)
            if billed:
                src = _("Billed")
                kind = "billed"
                record = order
            elif order:
                src = _("Unbilled")
                kind = "unbilled"
                record = order
            else:
                src = _("Unbilled (no Cont. Order)")
                kind = "unbilled"
                record = contract
            self._append_source_detail(line, month_index, src, record, amt, kind=kind)
        return self._sort_hierarchy(customers)

    def _collect_hierarchy_from_orders(self):
        self.ensure_one()
        if self.view_mode == "one_time":
            return []
        months_slots = self._month_slots()
        orders = self.env["cpabooks.cafm.contract.order"].search(
            self._order_base_domain(),
            order="partner_id, project_id, contract_id, id",
        )
        customers = {}

        for order in orders:
            bucket = self._bucket_date(order)
            month_index = self._month_index(bucket, months_slots)
            if month_index is False:
                continue
            partner = order.partner_id
            partner_key = partner.id if partner else 0
            cust = customers.setdefault(partner_key, {
                "partner_key": partner_key,
                "partner_id": partner.id if partner else False,
                "name": partner.display_name if partner else _("No Customer"),
                "partner_url": self._record_url(partner) if partner else "",
                "months": self._empty_months(),
                "billed": self._empty_months(),
                "unbilled": self._empty_months(),
                "projects": {},
            })
            project = order.project_id
            proj_key = project.id if project else 0
            proj = cust["projects"].setdefault(proj_key, {
                "project_key": proj_key,
                "project_id": project.id if project else False,
                "name": project.display_name if project else _("No Project"),
                "project_url": self._record_url(project) if project else "",
                "months": self._empty_months(),
                "billed": self._empty_months(),
                "unbilled": self._empty_months(),
                "orders": [],
            })
            contract = order.contract_id
            amt = order.amount or 0.0
            billed = self._is_invoiced_order(order)
            line = {
                "order_id": order.id,
                "task": order.period_label or order.name or "",
                "project_label": project.display_name if project else "",
                "contract_id": contract.id,
                "contract_name": contract.name or "",
                "contract_url": self._record_url(contract),
                "months": self._empty_months(),
                "billed": self._empty_months(),
                "unbilled": self._empty_months(),
                "details": self._empty_details(),
            }
            self._add_month_amount(line, month_index, amt, billed)
            if billed:
                src = _("Billed")
                kind = "billed"
            else:
                src = _("Unbilled")
                kind = "unbilled"
            self._append_source_detail(line, month_index, src, order, amt, kind=kind)
            proj["orders"].append(line)
            self._add_month_amount(proj, month_index, amt, billed)
            self._add_month_amount(cust, month_index, amt, billed)

        out = sorted(customers.values(), key=lambda c: (c["name"] or "", c["partner_key"]))
        for cust in out:
            cust["projects"] = sorted(
                cust["projects"].values(),
                key=lambda p: (p["name"] or "", p["project_key"]),
            )
            for proj in cust["projects"]:
                proj["orders"].sort(key=lambda o: (o["contract_name"], o["task"], o["order_id"]))
        return out

    def _report_title(self):
        self.ensure_one()
        if self.billing_scope == "invoiced":
            return _("Monthly Billing Table - Invoiced")
        if self.billing_scope == "pending":
            return _("Monthly Billing Table - Unbilled")
        return _("Monthly Billing Table")

    def _report_empty_message(self):
        if self.billing_scope == "invoiced":
            return _("No invoiced CAFM contract orders found for this period.")
        if self.billing_scope == "pending":
            return _(
                "No pending billable contract orders found for this period. "
                "Create Cont. Orders from AMC Register (or Pending Cont. Orders) first."
            )
        return _(
            "No AMC Next Invoice amounts found for this period. "
            "Totals follow AMC Invoice Register (Next Invoice Amount)."
        )

    def _render_split_stack(self, billed, unbilled, pfx="o_cafm_mbt"):
        def _line(amount, kind, label):
            cls = "%s_%s" % (pfx, kind)
            extra = "" if amount else (" %s_zero" % pfx)
            val = self._format_amount(amount) if amount else "—"
            return (
                "<span class='%s%s'><span>%s</span> <strong>%s</strong></span>"
                % (cls, extra, html_escape(label), html_escape(val))
            )
        return (
            "<span class='%s_split'>%s%s</span>"
            % (pfx, _line(billed, "billed", "B"), _line(unbilled, "unbilled", "U"))
        )

    def _render_total_cell(self, total, pfx="o_cafm_mbt", billed=None, unbilled=None):
        if self._show_split_amounts() and billed is not None:
            return (
                "<td class='%s_amount %s_row_total %s_split_cell'>%s</td>"
                % (pfx, pfx, pfx, self._render_split_stack(billed, unbilled or 0.0, pfx))
            )
        return "<td class='%s_amount %s_row_total'>%s</td>" % (pfx, pfx, self._format_amount(total))

    def _render_month_cell(self, amount, details, pfx="o_cafm_mbt"):
        if not amount:
            return "<td class='%s_amount'></td>" % pfx
        detail_html = []
        for detail in details:
            detail_html.append(
                "<a class='%s_source' href='%s'>"
                "<span>%s</span><strong>%s</strong>"
                "</a>" % (
                    pfx,
                    html_escape(detail["url"]),
                    html_escape(detail["source"]),
                    html_escape(self._format_amount(detail["amount"])),
                )
            )
        return (
            "<td class='%s_amount'><details class='%s_drill'><summary>%s</summary>%s</details></td>"
            % (pfx, pfx, self._format_amount(amount), "".join(detail_html))
        )

    def _render_split_month_cell(self, billed, unbilled, billed_details, unbilled_details, pfx="o_cafm_mbt"):
        if not billed and not unbilled:
            return "<td class='%s_amount %s_split_cell'></td>" % (pfx, pfx)
        stack = self._render_split_stack(billed, unbilled, pfx)
        all_details = list(billed_details or []) + list(unbilled_details or [])
        if not all_details:
            return "<td class='%s_amount %s_split_cell'>%s</td>" % (pfx, pfx, stack)
        detail_html = []
        for detail in all_details:
            kind_cls = "%s_source %s_source_%s" % (pfx, pfx, detail.get("kind") or "unbilled")
            detail_html.append(
                "<a class='%s' href='%s'>"
                "<span>%s</span><strong>%s</strong>"
                "</a>" % (
                    kind_cls,
                    html_escape(detail["url"]),
                    html_escape(detail["source"]),
                    html_escape(self._format_amount(detail["amount"])),
                )
            )
        return (
            "<td class='%s_amount %s_split_cell'>"
            "<details class='%s_drill'><summary>%s</summary>%s</details></td>"
            % (pfx, pfx, pfx, stack, "".join(detail_html))
        )

    def _month_cells(self, months_row, details_rows, pfx, billed_row=None, unbilled_row=None):
        if self._show_split_amounts():
            billed_row = billed_row if billed_row is not None else self._empty_months()
            unbilled_row = unbilled_row if unbilled_row is not None else self._empty_months()
            cells = []
            for i in range(12):
                details = details_rows[i] or []
                cells.append(self._render_split_month_cell(
                    billed_row[i],
                    unbilled_row[i],
                    [d for d in details if d.get("kind") == "billed"],
                    [d for d in details if d.get("kind") != "billed"],
                    pfx,
                ))
            return "".join(cells)
        return "".join(
            self._render_month_cell(months_row[i], details_rows[i], pfx=pfx)
            for i in range(12)
        )

    def _table_colgroup(self, pfx="o_cafm_mbt"):
        return (
            "<colgroup>"
            "<col class='%(pfx)s_col_sr'/>"
            "<col class='%(pfx)s_col_customer'/>"
            "<col class='%(pfx)s_optional %(pfx)s_col_task'/>"
            "<col class='%(pfx)s_optional %(pfx)s_col_project'/>"
            "%(months)s"
            "<col class='%(pfx)s_col_total'/>"
            "</colgroup>"
        ) % {
            "pfx": pfx,
            "months": "".join("<col class='%s_col_month'/>" % pfx for _index in range(12)),
        }

    def _render_hierarchy_rows(self, hierarchy, pfx, serial_holder):
        """Build tbody HTML: L1 customer, L2 project, L3 orders."""
        self.ensure_one()
        rows = []
        grand_totals = self._empty_months()
        grand_billed = self._empty_months()
        grand_unbilled = self._empty_months()

        for ci, cust in enumerate(hierarchy):
            c_id = "cafm_c_%s" % ci
            for i, m in enumerate(cust["months"]):
                grand_totals[i] += m
                grand_billed[i] += cust["billed"][i]
                grand_unbilled[i] += cust["unbilled"][i]

            cust_open = self.hierarchy_all_projects
            l1_cls = (
                "%(pfx)s_l1 %(pfx)s_fold_header%(open)s"
                % {"pfx": pfx, "open": (" %s_open" % pfx) if cust_open else ""}
            )
            month_part = self._month_cells(
                cust["months"], [[] for _ in range(12)], pfx,
                billed_row=cust["billed"], unbilled_row=cust["unbilled"],
            )
            cust_label = html_escape(cust["name"] or "-")
            if cust.get("partner_url"):
                cust_cell = (
                    "<a class='%(pfx)s_customer_link' href='%(url)s'>%(name)s</a>"
                    % {"pfx": pfx, "url": html_escape(cust["partner_url"]), "name": cust_label}
                )
            else:
                cust_cell = "<span class='%s_customer_text'>%s</span>" % (pfx, cust_label)
            toggle_fn = "%s_toggle_l1" % pfx
            rows.append(
                "<tr class='%s' data-cafm-id='%s' data-cafm-level='1' "
                "onclick=\"%s(event, this)\">"
                "<td class='%s_sr'></td><td colspan='1'><span class='%s_fold_icon'></span>%s</td>"
                "<td class='%s_optional %s_col_task'></td><td class='%s_optional %s_col_project'></td>"
                "%s%s</tr>"
                % (
                    l1_cls,
                    c_id,
                    toggle_fn,
                    pfx,
                    pfx,
                    cust_cell,
                    pfx,
                    pfx,
                    pfx,
                    pfx,
                    month_part,
                    self._render_total_cell(
                        sum(cust["months"]),
                        pfx=pfx,
                        billed=sum(cust["billed"]),
                        unbilled=sum(cust["unbilled"]),
                    ),
                )
            )

            for pi, proj in enumerate(cust["projects"]):
                p_id = "cafm_p_%s_%s" % (ci, pi)
                proj_open = self.hierarchy_all_projects and self.hierarchy_all_orders
                l2_cls = (
                    "%(pfx)s_l2 %(pfx)s_child %(pfx)s_child_of_%(cid)s%(open)s"
                    % {
                        "pfx": pfx,
                        "cid": c_id,
                        "open": (" %s_open" % pfx) if proj_open else "",
                    }
                )
                if not self.hierarchy_all_projects:
                    l2_cls += " %s_hidden" % pfx
                proj_label = html_escape(proj["name"] or "-")
                if proj.get("project_url"):
                    proj_cell = (
                        "<span class='%s_indent'>&nbsp;&nbsp;</span><a class='%s_customer_link' href='%s'>%s</a>"
                        % (pfx, pfx, html_escape(proj["project_url"]), proj_label)
                    )
                else:
                    proj_cell = "<span class='%s_indent'>&nbsp;&nbsp;</span><span>%s</span>" % (pfx, proj_label)
                month_part_p = self._month_cells(
                    proj["months"], [[] for _ in range(12)], pfx,
                    billed_row=proj["billed"], unbilled_row=proj["unbilled"],
                )
                toggle_fn2 = "%s_toggle_l2" % pfx
                rows.append(
                    "<tr class='%s' data-cafm-id='%s' data-cafm-parent='%s' data-cafm-level='2' "
                    "onclick=\"%s(event, this)\">"
                    "<td class='%s_sr'></td><td colspan='1'><span class='%s_fold_icon'></span>%s</td>"
                    "<td class='%s_optional %s_col_task'></td><td class='%s_optional %s_col_project'></td>"
                    "%s%s</tr>"
                    % (
                        l2_cls,
                        p_id,
                        c_id,
                        toggle_fn2,
                        pfx,
                        pfx,
                        proj_cell,
                        pfx,
                        pfx,
                        pfx,
                        pfx,
                        month_part_p,
                        self._render_total_cell(
                            sum(proj["months"]),
                            pfx=pfx,
                            billed=sum(proj["billed"]),
                            unbilled=sum(proj["unbilled"]),
                        ),
                    )
                )

                for line in proj["orders"]:
                    serial_holder[0] += 1
                    sn = serial_holder[0]
                    detail_row_cls = "%s_l3 %s_child %s_child_of_%s %s_child_of_%s" % (pfx, pfx, pfx, c_id, pfx, p_id)
                    if not (self.hierarchy_all_projects and self.hierarchy_all_orders):
                        detail_row_cls += " %s_hidden" % pfx
                    task_h = html_escape(line["task"] or "-")
                    proj_h = html_escape(line["project_label"] or "-")
                    contract_html = (
                        "<a class='%s_customer_link' href='%s'>%s</a>"
                        % (pfx, html_escape(line["contract_url"]), html_escape(line["contract_name"] or _("Contract")))
                    )
                    cust_col = "%s <small class='%s_muted'>(%s)</small>" % (contract_html, pfx, task_h)
                    month_part_l = self._month_cells(
                        line["months"], line["details"], pfx,
                        billed_row=line["billed"], unbilled_row=line["unbilled"],
                    )
                    rows.append(
                        "<tr class='%s' data-cafm-parent='%s' data-cafm-level='3'>"
                        "<td class='%s_sr'>%s</td><td>%s</td>"
                        "<td class='%s_optional %s_col_task'>%s</td>"
                        "<td class='%s_optional %s_col_project'>%s</td>"
                        "%s%s</tr>"
                        % (
                            detail_row_cls,
                            p_id,
                            pfx,
                            sn,
                            cust_col,
                            pfx,
                            pfx,
                            task_h,
                            pfx,
                            pfx,
                            proj_h,
                            month_part_l,
                            self._render_total_cell(
                                sum(line["months"]),
                                pfx=pfx,
                                billed=sum(line["billed"]),
                                unbilled=sum(line["unbilled"]),
                            ),
                        )
                    )

        return rows, grand_totals, grand_billed, grand_unbilled

    def _render_footer_row(self, label, amounts, pfx, extra_cls=""):
        cells = "".join(
            "<td class='%s_amount'>%s</td>" % (pfx, self._format_amount(amount))
            for amount in amounts
        )
        return (
            "<tr class='%(cls)s'><td colspan='2'>%(label)s</td>"
            "<td class='%(pfx)s_optional %(pfx)s_col_task'></td>"
            "<td class='%(pfx)s_optional %(pfx)s_col_project'></td>%(cells)s"
            "<td class='%(pfx)s_amount'>%(sum)s</td></tr>"
            % {
                "cls": extra_cls or ("%s_grand" % pfx),
                "label": html_escape(label),
                "pfx": pfx,
                "cells": cells,
                "sum": self._format_amount(sum(amounts)),
            }
        )

    def _render_grid_html(self, hierarchy, report_title, empty_message, pfx):
        self.ensure_one()
        months = self._month_slots()
        header_months = "".join(
            "<th class='%s_amount'>%s</th>" % (pfx, html_escape(month["label"]))
            for month in months
        )
        serial_counter = [0]
        body_piece, grand_totals, grand_billed, grand_unbilled = self._render_hierarchy_rows(
            hierarchy, pfx, serial_counter
        )
        body_rows = body_piece

        if not hierarchy:
            body_rows = [
                "<tr><td colspan='17' class='%s_empty'>%s</td></tr>" % (pfx, html_escape(empty_message))
            ]
        else:
            if self._show_split_amounts():
                body_rows.extend([
                    self._render_footer_row(
                        _("Total Billed"), grand_billed, pfx, extra_cls="%s_total_billed" % pfx
                    ),
                    self._render_footer_row(
                        _("Total Unbilled"), grand_unbilled, pfx, extra_cls="%s_total_unbilled" % pfx
                    ),
                    self._render_footer_row(
                        _("Grand Total"),
                        [grand_billed[i] + grand_unbilled[i] for i in range(12)],
                        pfx,
                        extra_cls="%s_grand" % pfx,
                    ),
                ])
            else:
                body_rows.append(self._render_footer_row(_("Grand Total"), grand_totals, pfx, extra_cls="%s_grand" % pfx))

        period_label = "%s - %s" % (fields.Date.to_string(months[0]["start"]), fields.Date.to_string(months[-1]["end"]))
        legend = ""
        if self._show_split_amounts():
            legend = (
                '<span class="%s_legend">'
                '<span class="%s_legend_billed">B = Billed (invoiced)</span>'
                '<span class="%s_legend_unbilled">U = Unbilled</span>'
                '<span class="%s_legend_note">B+U = AMC Next Invoice Amount</span>'
                "</span>"
            ) % (pfx, pfx, pfx, pfx)
        wid = self.id or 0
        hwrap_id = "cafm_mbt_hwrap_%s" % wid
        ap_attr = "1" if self.hierarchy_all_projects else "0"
        ao_attr = "1" if self.hierarchy_all_orders else "0"

        # CSS/JS live in static assets (html widget strips <style>/<script> and shows them as text)
        inner = (
            '<div id="' + hwrap_id + '" class="' + pfx + '_wrap"'
            ' data-cafm-ap="' + ap_attr + '" data-cafm-ao="' + ao_attr + '">'
            '<input id="o_mbt_col_task_toggle" class="o_mbt_column_state" type="checkbox"/>'
            '<input id="o_mbt_col_project_toggle" class="o_mbt_column_state" type="checkbox"/>'
            '<div class="o_mbt_title">'
            "<h2>%s</h2>"
            '<div class="o_mbt_tools">'
            "<span>%s | %s</span>"
            "%s"
            '<details class="o_mbt_columns">'
            "<summary>...</summary>"
            '<div class="o_mbt_columns_menu">'
            '<label for="o_mbt_col_task_toggle">Task</label>'
            '<label for="o_mbt_col_project_toggle">Project</label>'
            "</div></details></div></div>"
            '<div class="o_mbt_scroll">'
            '<table class="o_mbt_table %s_table">'
            "%s"
            "<thead><tr><th>Sr.</th><th>Customer / Contract</th>"
            '<th class="o_mbt_optional o_mbt_col_task">Period</th>'
            '<th class="o_mbt_optional o_mbt_col_project">Project</th>'
            "%s"
            '<th class="o_mbt_amount">Total</th></tr></thead>'
            "<tbody>%s</tbody></table></div></div>"
        ) % (
            html_escape(report_title),
            html_escape(period_label),
            html_escape(dict(self._fields["view_mode"].selection).get(self.view_mode, self.view_mode)),
            legend,
            pfx,
            self._table_colgroup(pfx=pfx),
            header_months,
            "".join(body_rows),
        )
        return inner.replace("o_mbt", pfx)

    @api.depends(
        "period_start",
        "view_mode",
        "billing_scope",
        "hierarchy_all_projects",
        "hierarchy_all_orders",
    )
    def _compute_report_html(self):
        for wizard in self:
            wizard.report_html = wizard._render_report_html()

    def _render_report_html(self):
        self.ensure_one()
        hierarchy = self._collect_hierarchy()
        return self._render_grid_html(hierarchy, self._report_title(), self._report_empty_message(), "o_cafm_mbt")

    def action_apply(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self._report_title(),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_reset_period(self):
        self.ensure_one()
        self.write({
            "period_start": self._default_period_start(),
            "view_mode": "all",
            "hierarchy_all_projects": False,
            "hierarchy_all_orders": False,
        })
        return self.action_apply()

    def action_toggle_unfold_projects(self):
        self.ensure_one()
        self.hierarchy_all_projects = not self.hierarchy_all_projects
        if not self.hierarchy_all_projects:
            self.hierarchy_all_orders = False
        return self.action_apply()

    def action_toggle_unfold_orders(self):
        self.ensure_one()
        self.hierarchy_all_orders = not self.hierarchy_all_orders
        if self.hierarchy_all_orders:
            self.hierarchy_all_projects = True
        return self.action_apply()

    def _format_export_cell(self, billed, unbilled, total):
        if self._show_split_amounts():
            if not billed and not unbilled:
                return ""
            billed_txt = self._format_amount(billed) if billed else "—"
            unbilled_txt = self._format_amount(unbilled) if unbilled else "—"
            return "B %s / U %s" % (billed_txt, unbilled_txt)
        return self._format_amount(total) if total else ""

    def action_export_table(self):
        self.ensure_one()
        months = self._month_slots()
        hierarchy = self._collect_hierarchy()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["Level", "Customer", "Project", "Contract / Period"]
            + [month["label"] for month in months]
            + ["Total"],
        )
        grand_totals = self._empty_months()
        grand_billed = self._empty_months()
        grand_unbilled = self._empty_months()
        for cust in hierarchy:
            for i, amt in enumerate(cust["months"]):
                grand_totals[i] += amt
                grand_billed[i] += cust["billed"][i]
                grand_unbilled[i] += cust["unbilled"][i]
            writer.writerow(
                ["Customer", cust["name"], "", ""]
                + [
                    self._format_export_cell(cust["billed"][i], cust["unbilled"][i], cust["months"][i])
                    for i in range(12)
                ]
                + [self._format_export_cell(sum(cust["billed"]), sum(cust["unbilled"]), sum(cust["months"]))],
            )
            for proj in cust["projects"]:
                writer.writerow(
                    ["Project", cust["name"], proj["name"], ""]
                    + [
                        self._format_export_cell(proj["billed"][i], proj["unbilled"][i], proj["months"][i])
                        for i in range(12)
                    ]
                    + [self._format_export_cell(sum(proj["billed"]), sum(proj["unbilled"]), sum(proj["months"]))],
                )
                for line in proj["orders"]:
                    writer.writerow(
                        [
                            "Order",
                            cust["name"],
                            proj["name"],
                            "%s %s" % (line["contract_name"], line["task"]),
                        ]
                        + [
                            self._format_export_cell(line["billed"][i], line["unbilled"][i], line["months"][i])
                            for i in range(12)
                        ]
                        + [self._format_export_cell(sum(line["billed"]), sum(line["unbilled"]), sum(line["months"]))],
                    )
        writer.writerow(
            ["", "Total Billed", "", ""]
            + [self._format_amount(m) for m in grand_billed]
            + [self._format_amount(sum(grand_billed))],
        )
        writer.writerow(
            ["", "Total Unbilled", "", ""]
            + [self._format_amount(m) for m in grand_unbilled]
            + [self._format_amount(sum(grand_unbilled))],
        )
        writer.writerow(
            ["", "Grand Total", "", ""]
            + [self._format_amount(grand_billed[i] + grand_unbilled[i]) for i in range(12)]
            + [self._format_amount(sum(grand_billed) + sum(grand_unbilled))],
        )
        if self.billing_scope == "pending":
            fname = "cafm_monthly_billing_unbilled.csv"
        elif self.billing_scope == "invoiced":
            fname = "cafm_monthly_billing_invoiced.csv"
        else:
            fname = "cafm_monthly_billing_table.csv"
        attachment = self.env["ir.attachment"].create({
            "name": fname,
            "type": "binary",
            "datas": base64.b64encode(buffer.getvalue().encode("utf-8")),
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    @api.model
    def action_open_invoiced(self):
        wizard = self.create({"billing_scope": "invoiced"})
        return wizard.action_apply()

    @api.model
    def action_open_pending(self):
        wizard = self.create({"billing_scope": "both"})
        return wizard.action_apply()

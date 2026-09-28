# -*- coding: utf-8 -*-
import base64
import csv
from io import StringIO

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape


MONTH_LABELS = [
    ("1", "Jan"), ("2", "Feb"), ("3", "Mar"), ("4", "Apr"),
    ("5", "May"), ("6", "Jun"), ("7", "Jul"), ("8", "Aug"),
    ("9", "Sep"), ("10", "Oct"), ("11", "Nov"), ("12", "Dec"),
]


class CafmPpmSetupWizard(models.TransientModel):
    _name = "cafm.ppm.setup.wizard"
    _description = "PPM Bulk Planning"

    year = fields.Integer(string="Calendar year", required=True, default=lambda self: fields.Date.context_today(self).year)
    scope = fields.Selection(
        [
            (
                "all",
                "All customers & all projects (every active PPM)",
            ),
            ("customer", "By customer (AMC client, optional: all)"),
            ("project", "Single project (optional: all projects)"),
        ],
        default="all",
        required=True,
        help="Use the first option to apply the same planning to every active PPM in the company, "
        "across all AMC clients and projects. "
        "With By customer or Single project you can narrow to one record, or leave that field empty "
        "to include all customers (via AMC contracts) or all projects respectively.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer / AMC client",
        help="Optional when Scope is By customer: pick one AMC client, or leave empty for all clients "
        "(all projects that appear on any AMC contract).",
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        help="Optional when Scope is Single project: pick one project, or leave empty for every project.",
    )
    location_filter = fields.Char(
        string="Area filter",
        help="Optional: e.g. AUH to limit projects whose CAFM location contains this text.",
    )
    planning_mode = fields.Selection(
        [
            ("frequency", "By Frequency"),
            ("manual", "Manual months"),
        ],
        default="frequency",
        required=True,
    )
    frequency = fields.Selection([
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("half_yearly", "Half Yearly"),
        ("yearly", "Yearly"),
    ], default="quarterly", required=True)
    manual_jan = fields.Boolean(string="Jan")
    manual_feb = fields.Boolean(string="Feb")
    manual_mar = fields.Boolean(string="Mar")
    manual_apr = fields.Boolean(string="Apr")
    manual_may = fields.Boolean(string="May")
    manual_jun = fields.Boolean(string="Jun")
    manual_jul = fields.Boolean(string="Jul")
    manual_aug = fields.Boolean(string="Aug")
    manual_sep = fields.Boolean(string="Sep")
    manual_oct = fields.Boolean(string="Oct")
    manual_nov = fields.Boolean(string="Nov")
    manual_dec = fields.Boolean(string="Dec")
    supervisor_id = fields.Many2one("res.users", string="Set supervisor")
    regenerate_slots = fields.Boolean(string="Regenerate year slots after apply", default=True)

    def _manual_vals_from_wizard(self):
        self.ensure_one()
        return {f: self[f] for f in [
            "manual_jan", "manual_feb", "manual_mar", "manual_apr",
            "manual_may", "manual_jun", "manual_jul", "manual_aug",
            "manual_sep", "manual_oct", "manual_nov", "manual_dec",
        ]}

    def _search_target_ppms(self):
        self.ensure_one()
        domain = [("state", "=", "active")]
        if self.scope == "project":
            if self.project_id:
                domain.append(("project_id", "=", self.project_id.id))
        elif self.scope == "customer":
            contract_dom = []
            if self.partner_id:
                contract_dom.append(("client_id", "=", self.partner_id.id))
            contracts = self.env["cpabooks.cafm.contract"].search(contract_dom)
            pids = [p for p in contracts.mapped("project_id").ids if p]
            if not pids:
                raise UserError(
                    _("No projects linked to AMC contracts for this filter.")
                )
            domain.append(("project_id", "in", list(set(pids))))
        ppms = self.env["cpabooks.cafm.ppm"].search(domain)
        if self.location_filter:
            loc = self.location_filter.strip()
            ppms = ppms.filtered(
                lambda p: p.project_id
                and p.project_id.cafm_location
                and loc.lower() in (p.project_id.cafm_location or "").lower()
            )
        return ppms

    def action_apply(self):
        self.ensure_one()
        ppms = self._search_target_ppms()
        if not ppms:
            raise UserError(_("No PPM lines match this setup."))
        manual = self._manual_vals_from_wizard()
        wvals = {
            "planning_mode": self.planning_mode,
            "frequency": self.frequency,
            **manual,
        }
        if self.supervisor_id:
            wvals["supervisor_id"] = self.supervisor_id.id
        ppms.write(wvals)
        if self.regenerate_slots:
            ppms.action_regenerate_slots(self.year, replace=True)
        return {
            "type": "ir.actions.act_window",
            "name": _("PPM Schedule"),
            "res_model": "cpabooks.cafm.ppm",
            "view_mode": "tree,form",
            "domain": [("id", "in", ppms.ids)],
            "target": "current",
        }


class CafmPpmGenerateWizard(models.TransientModel):
    _name = "cafm.ppm.generate.wizard"
    _description = "Generate PPM Year Slots"

    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    include_next_year = fields.Boolean(
        string="Include next calendar year",
        default=True,
        help="When enabled, month slots are rebuilt for the selected year and the following year in one run.",
    )
    only_active = fields.Boolean(string="Active PPM only", default=True)
    project_id = fields.Many2one("project.project", string="Limit to project")

    def action_run(self):
        self.ensure_one()
        dom = []
        if self.only_active:
            dom.append(("state", "=", "active"))
        if self.project_id:
            dom.append(("project_id", "=", self.project_id.id))
        ppms = self.env["cpabooks.cafm.ppm"].search(dom)
        if not ppms:
            raise UserError(_("No PPM lines to generate."))
        years = [int(self.year)]
        if self.include_next_year:
            years.append(int(self.year) + 1)
        for y in years:
            ppms.action_regenerate_slots(y, replace=True)
        return {
            "type": "ir.actions.act_window",
            "name": _("PPM Slots"),
            "res_model": "cpabooks.cafm.ppm.slot",
            "view_mode": "tree,form",
            "domain": [("year", "in", years), ("ppm_id", "in", ppms.ids)],
            "target": "current",
        }


class CafmPpmMonthlyGridWizard(models.TransientModel):
    _name = "cafm.ppm.monthly.grid.wizard"
    _description = "Monthly PPM Grid"

    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    pending_only = fields.Boolean(string="Pending visits only", default=False)
    report_html = fields.Html(compute="_compute_report_html", sanitize=False)

    def _format_row(self, ppm, year, pending_only, serial):
        proj = ppm.project_id
        amc = proj.cafm_amc_ids[:1]
        typ = (amc.amc_contract_type or "amc").upper() if amc else "AMC"
        client = amc.client_id.name if amc and amc.client_id else (proj.partner_id.name or "") if proj.partner_id else ""
        area = proj.cafm_location or ""
        sup = ppm.supervisor_id.name if ppm.supervisor_id else ""
        start = amc.contract_date or ppm.start_date
        end = amc.contract_expiry or ppm.end_date
        slot_map = {s.month: s for s in ppm.slot_ids if s.year == year}
        today = fields.Date.context_today(self)
        cur_ym = (today.year, today.month)
        cells = []
        for m in range(1, 13):
            slot = slot_map.get(m)
            mark = ""
            cls = "ppm_cell_empty"
            if slot:
                if slot.state == "done":
                    mark = "✓"
                    cls = "ppm_cell_done"
                else:
                    mark = "X"
                    ym = (year, m)
                    is_pending = ym <= cur_ym
                    if pending_only and not is_pending:
                        mark = ""
                        cls = "ppm_cell_future"
                    elif is_pending:
                        cls = "ppm_cell_pending"
                    else:
                        cls = "ppm_cell_planned"
            cells.append("<td class='%s'>%s</td>" % (cls, mark))
        return (
            "<tr>"
            "<td class='ppm_sr'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td>"
            "%s"
            "</tr>"
            % (
                serial,
                typ,
                html_escape(proj.name or ""),
                html_escape(client),
                html_escape(area),
                html_escape(sup),
                html_escape(str(start or "")),
                html_escape(str(end or "")),
                "".join(cells),
            )
        )

    @api.depends("year", "pending_only")
    def _compute_report_html(self):
        for wiz in self:
            wiz.report_html = wiz._render_html()

    def _render_html(self):
        self.ensure_one()
        year = self.year
        ppms = self.env["cpabooks.cafm.ppm"].search([("state", "=", "active")], order="project_id, id")
        if self.pending_only:
            today = fields.Date.context_today(self)
            ppms = ppms.filtered(
                lambda p: any(
                    s.year == year
                    and s.state == "planned"
                    and (s.year, s.month) <= (today.year, today.month)
                    for s in p.slot_ids
                )
            )
        headers = "".join("<th>%s</th>" % lab for _n, lab in MONTH_LABELS)
        rows = []
        serial = 1
        for ppm in ppms:
            if not any(s.year == year for s in ppm.slot_ids):
                continue
            rows.append(self._format_row(ppm, year, self.pending_only, serial))
            serial += 1
        if not rows:
            rows.append(
                "<tr><td colspan='20' class='ppm_empty'>%s</td></tr>"
                % html_escape(_("No PPM data for this year. Generate slots first."))
            )
        # CSS lives in static/src/css/cafm_ppm_report.css (html widget strips <style>)
        thead = (
            "<tr><th>Sl</th><th>Type</th><th>Project</th><th>Client</th><th>Area</th>"
            "<th>Supervisor</th><th>Start</th><th>End</th>%s</tr>" % headers
        )
        return (
            "<div class='ppm_wrap'><table class='ppm_table'><thead>%s</thead><tbody>%s</tbody></table></div>"
            % (thead, "".join(rows))
        )

    def action_refresh(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Monthly PPM"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_export_csv(self):
        self.ensure_one()
        year = self.year
        ppms = self.env["cpabooks.cafm.ppm"].search([("state", "=", "active")], order="project_id, id")
        if self.pending_only:
            today = fields.Date.context_today(self)
            ppms = ppms.filtered(
                lambda p: any(
                    s.year == year
                    and s.state == "planned"
                    and (s.year, s.month) <= (today.year, today.month)
                    for s in p.slot_ids
                )
            )
        buf = StringIO()
        wr = csv.writer(buf)
        wr.writerow(
            ["Sl", "Type", "Project", "Client", "Area", "Supervisor", "Start", "End"]
            + [lab for _n, lab in MONTH_LABELS],
        )
        serial = 1
        today = fields.Date.context_today(self)
        cur_ym = (today.year, today.month)
        for ppm in ppms:
            if not any(s.year == year for s in ppm.slot_ids):
                continue
            proj = ppm.project_id
            amc = proj.cafm_amc_ids[:1]
            typ = (amc.amc_contract_type or "amc").upper() if amc else "AMC"
            client = amc.client_id.name if amc and amc.client_id else (proj.partner_id.name or "") if proj.partner_id else ""
            area = proj.cafm_location or ""
            sup = ppm.supervisor_id.name if ppm.supervisor_id else ""
            start = amc.contract_date or ppm.start_date
            end = amc.contract_expiry or ppm.end_date
            slot_map = {s.month: s for s in ppm.slot_ids if s.year == year}
            rowm = []
            for m in range(1, 13):
                slot = slot_map.get(m)
                cell = ""
                if slot:
                    if slot.state == "done":
                        cell = "Done"
                    else:
                        if self.pending_only and (year, m) > cur_ym:
                            cell = ""
                        else:
                            cell = "X"
                rowm.append(cell)
            wr.writerow([serial, typ, proj.name, client, area, sup, start or "", end or ""] + rowm)
            serial += 1
        att = self.env["ir.attachment"].create({
            "name": "ppm_monthly_%s.csv" % year,
            "type": "binary",
            "datas": base64.b64encode(buf.getvalue().encode("utf-8")),
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % att.id,
            "target": "self",
        }

    @api.model
    def action_open_full(self):
        w = self.create({"pending_only": False})
        return w.action_refresh()

    @api.model
    def action_open_pending(self):
        w = self.create({"pending_only": True})
        return w.action_refresh()


class CafmPpmDailyListWizard(models.TransientModel):
    _name = "cafm.ppm.daily.list.wizard"
    _description = "Technician Daily PPM List"

    report_date = fields.Date(required=True, default=fields.Date.context_today)
    supervisor_id = fields.Many2one("res.users", string="Supervisor filter")

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("cpabooks_cafm.action_report_cafm_ppm_daily_list").report_action(self)

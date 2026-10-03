# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError

from .faff_job import FAFF_STAGES


class FaffMisDetail(models.Model):
    """Line-level estimate vs material actuals (SQL view)."""

    _name = "cpabooks.faff.mis.detail"
    _description = "FAFF Comparison Detail"
    _auto = False
    _order = "job_id, id"

    job_id = fields.Many2one("cpabooks.faff.job", string="FAFF Job", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    job_type_id = fields.Many2one(
        "cpabooks.faff.job.type", string="Job Type", readonly=True
    )
    salesperson_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    stage = fields.Selection(FAFF_STAGES, readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    name = fields.Char(string="Description", readonly=True)
    qty_estimated = fields.Float(string="Est. Qty", readonly=True)
    estimated_cost = fields.Monetary(readonly=True)
    selling_amount = fields.Monetary(readonly=True)
    qty_required = fields.Float(string="Required Qty", readonly=True)
    qty_issued = fields.Float(string="Issued Qty", readonly=True)
    qty_purchased = fields.Float(string="Purchased Qty", readonly=True)
    actual_material_cost = fields.Monetary(string="Actual Material", readonly=True)
    cost_variance = fields.Monetary(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    el.id AS id,
                    job.id AS job_id,
                    job.partner_id AS partner_id,
                    job.job_type_id AS job_type_id,
                    job.salesperson_id AS salesperson_id,
                    job.stage AS stage,
                    job.company_id AS company_id,
                    job.currency_id AS currency_id,
                    el.product_id AS product_id,
                    el.name AS name,
                    el.product_uom_qty AS qty_estimated,
                    el.total_cost AS estimated_cost,
                    el.total_selling_price AS selling_amount,
                    COALESCE(mp.qty_required, 0.0) AS qty_required,
                    COALESCE(mp.issue_qty, 0.0) AS qty_issued,
                    COALESCE(mp.purchase_qty, 0.0) AS qty_purchased,
                    COALESCE(mp.material_cost, 0.0) AS actual_material_cost,
                    el.total_cost - COALESCE(mp.material_cost, 0.0) AS cost_variance
                FROM cpabooks_faff_estimate_line el
                JOIN cpabooks_faff_estimate est ON est.id = el.estimate_id
                JOIN cpabooks_faff_job job ON job.id = est.job_id
                LEFT JOIN LATERAL (
                    SELECT
                        SUM(p.qty_required) AS qty_required,
                        SUM(p.issue_qty) AS issue_qty,
                        SUM(p.purchase_qty) AS purchase_qty,
                        SUM(p.material_cost) AS material_cost
                    FROM cpabooks_faff_material_plan p
                    WHERE p.job_id = job.id
                      AND (
                            (el.product_id IS NOT NULL AND p.product_id = el.product_id)
                            OR (el.product_id IS NULL AND p.name = el.name)
                      )
                ) mp ON TRUE
            )
            """
            % self._table
        )


class FaffMisWizard(models.TransientModel):
    _name = "cpabooks.faff.mis.wizard"
    _description = "FAFF MIS Print Wizard"

    date_from = fields.Date(default=fields.Date.context_today)
    date_to = fields.Date(default=fields.Date.context_today)
    partner_id = fields.Many2one("res.partner", string="Customer")
    job_type_id = fields.Many2one("cpabooks.faff.job.type")
    salesperson_id = fields.Many2one("res.users")
    report_kind = fields.Selection(
        [
            ("comparison_summary", "Comparison Summary"),
            ("comparison_detail", "Comparison Detail"),
            ("daily", "Daily Activity"),
        ],
        default="comparison_summary",
        required=True,
    )

    def _job_domain(self):
        domain = []
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.job_type_id:
            domain.append(("job_type_id", "=", self.job_type_id.id))
        if self.salesperson_id:
            domain.append(("salesperson_id", "=", self.salesperson_id.id))
        if self.date_from:
            domain.append(
                ("create_date", ">=", datetime.combine(self.date_from, time.min))
            )
        if self.date_to:
            domain.append(
                ("create_date", "<=", datetime.combine(self.date_to, time.max))
            )
        return domain

    def action_print(self):
        self.ensure_one()
        if self.report_kind == "daily":
            domain = []
            if self.date_from:
                domain.append(("report_date", ">=", self.date_from))
            if self.date_to:
                domain.append(("report_date", "<=", self.date_to))
            if self.partner_id:
                domain.append(("partner_id", "=", self.partner_id.id))
            if self.job_type_id:
                domain.append(("job_type_id", "=", self.job_type_id.id))
            if self.salesperson_id:
                domain.append(("salesperson_id", "=", self.salesperson_id.id))
            records = self.env["cpabooks.faff.stage.history"].search(domain)
            return self.env.ref(
                "cpabooks_faff.action_report_faff_mis_daily"
            ).report_action(records)
        if self.report_kind == "comparison_detail":
            jobs = self.env["cpabooks.faff.job"].search(self._job_domain())
            lines = self.env["cpabooks.faff.mis.detail"].search(
                [("job_id", "in", jobs.ids)]
            )
            return self.env.ref(
                "cpabooks_faff.action_report_faff_mis_detail"
            ).report_action(lines)
        jobs = self.env["cpabooks.faff.job"].search(self._job_domain())
        return self.env.ref(
            "cpabooks_faff.action_report_faff_mis_summary"
        ).report_action(jobs)


class FaffDashboardBridge(models.TransientModel):
    """Open Project Dashboard / financial reports when that module is installed."""

    _name = "cpabooks.faff.dashboard.bridge"
    _description = "FAFF External Dashboard Bridge"

    @api.model
    def action_open(self):
        xmlid = self.env.context.get("faff_bridge_xmlid")
        if not xmlid:
            raise UserError(_("No dashboard configured."))
        action = self.env.ref(xmlid, raise_if_not_found=False)
        if not action:
            raise UserError(
                _(
                    "This report needs module project_dashboard_odoo. "
                    "Install it on this database, then open again."
                )
            )
        return action.read()[0]

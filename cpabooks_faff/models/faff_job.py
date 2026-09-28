# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


FAFF_STAGES = [
    ("crm", "CRM"),
    ("inspection", "Inspection"),
    ("estimation", "Estimation"),
    ("quotation", "Quotation"),
    ("confirmed", "Confirmed"),
    ("project", "Project"),
    ("material", "Material"),
    ("execution", "Execution"),
    ("testing", "Testing"),
    ("completion", "Completion"),
    ("invoice", "Invoice"),
    ("payment", "Payment"),
    ("done", "Done"),
    ("cancel", "Cancelled"),
]

STAGE_PROGRESS = {
    "crm": 5,
    "inspection": 12,
    "estimation": 20,
    "quotation": 28,
    "confirmed": 35,
    "project": 42,
    "material": 50,
    "execution": 65,
    "testing": 75,
    "completion": 85,
    "invoice": 92,
    "payment": 98,
    "done": 100,
    "cancel": 0,
}


class FaffJob(models.Model):
    _name = "cpabooks.faff.job"
    _description = "FAFF Job"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="FAFF Number",
        required=True,
        copy=False,
        default="New",
        tracking=True,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    crm_lead_id = fields.Many2one("crm.lead", string="CRM Opportunity", tracking=True)
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, tracking=True
    )
    contact_id = fields.Many2one("res.partner", string="Contact Person")
    mobile = fields.Char()
    email = fields.Char()
    site_name = fields.Char(string="Site Name", tracking=True)
    site_address = fields.Text(string="Site Location")
    job_type_id = fields.Many2one("cpabooks.faff.job.type", string="Job Type", tracking=True)
    salesperson_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        default=lambda self: self.env.user,
        tracking=True,
    )
    lead_source_id = fields.Many2one("utm.source", string="Lead Source")
    description = fields.Text(string="Description / Requirement")
    remarks = fields.Text()

    planned_start_date = fields.Date(string="Expected Start")
    expected_end_date = fields.Date(string="Expected Completion")
    actual_start_date = fields.Date()
    actual_end_date = fields.Date()

    stage = fields.Selection(
        FAFF_STAGES, default="crm", required=True, tracking=True, copy=False
    )
    progress = fields.Float(
        string="Progress %", compute="_compute_progress", store=True
    )
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("on_hold", "On Hold"),
            ("completed", "Completed"),
            ("paid", "Completed / Paid"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    wizard_step = fields.Integer(
        string="Wizard Step",
        default=0,
        help="Persisted wizard step so Continue FAFF Wizard can resume.",
    )

    visit_ids = fields.One2many("cpabooks.faff.visit", "job_id", string="Inspections")
    visit_id = fields.Many2one(
        "cpabooks.faff.visit",
        string="Primary Inspection",
        compute="_compute_primary_links",
        store=True,
    )
    estimate_ids = fields.One2many(
        "cpabooks.faff.estimate", "job_id", string="Estimations"
    )
    estimate_id = fields.Many2one(
        "cpabooks.faff.estimate",
        string="Primary Estimation",
        compute="_compute_primary_links",
        store=True,
    )
    sale_order_id = fields.Many2one("sale.order", string="Quotation / SO", tracking=True)
    project_id = fields.Many2one("project.project", string="Project", tracking=True)
    task_ids = fields.One2many(
        "project.task",
        "faff_job_id",
        string="Tasks",
    )
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "faff_job_id",
        string="Purchase Orders",
    )
    picking_ids = fields.One2many(
        "stock.picking",
        "faff_job_id",
        string="Stock Transfers",
    )
    invoice_ids = fields.One2many(
        "account.move",
        "faff_job_id",
        string="Invoices",
    )
    material_plan_ids = fields.One2many(
        "cpabooks.faff.material.plan", "job_id", string="Material Requirements"
    )
    testing_ids = fields.One2many(
        "cpabooks.faff.testing", "job_id", string="Testing Records"
    )
    testing_id = fields.Many2one(
        "cpabooks.faff.testing",
        compute="_compute_primary_links",
        store=True,
    )
    completion_ids = fields.One2many(
        "cpabooks.faff.completion", "job_id", string="Completion Notes"
    )
    completion_id = fields.Many2one(
        "cpabooks.faff.completion",
        compute="_compute_primary_links",
        store=True,
    )
    stage_history_ids = fields.One2many(
        "cpabooks.faff.stage.history", "job_id", string="Stage History"
    )
    notes = fields.Html(string="Internal Notes")

    # Financials (estimated)
    estimated_material_cost = fields.Monetary(compute="_compute_estimated_amounts", store=True)
    estimated_labour_cost = fields.Monetary(compute="_compute_estimated_amounts", store=True)
    estimated_other_cost = fields.Monetary(compute="_compute_estimated_amounts", store=True)
    estimated_cost = fields.Monetary(
        string="Total Estimated Cost", compute="_compute_estimated_amounts", store=True
    )
    selling_amount = fields.Monetary(
        string="Selling Amount", compute="_compute_estimated_amounts", store=True
    )
    expected_profit = fields.Monetary(compute="_compute_estimated_amounts", store=True)
    margin_percent = fields.Float(
        string="Margin %", compute="_compute_estimated_amounts", store=True
    )

    # Actuals
    actual_material_cost = fields.Monetary(compute="_compute_actual_amounts", store=True)
    actual_purchase_cost = fields.Monetary(compute="_compute_actual_amounts", store=True)
    actual_labour_cost = fields.Monetary(compute="_compute_actual_amounts", store=True)
    actual_other_cost = fields.Monetary(default=0.0)
    actual_total_cost = fields.Monetary(compute="_compute_actual_amounts", store=True)
    invoice_amount = fields.Monetary(compute="_compute_payment_amounts", store=True)
    paid_amount = fields.Monetary(compute="_compute_payment_amounts", store=True)
    balance_amount = fields.Monetary(compute="_compute_payment_amounts", store=True)
    payment_status = fields.Selection(
        [
            ("not_invoiced", "Not Invoiced"),
            ("invoiced", "Invoiced"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
        ],
        compute="_compute_payment_amounts",
        store=True,
        string="Payment Status",
    )
    actual_profit = fields.Monetary(compute="_compute_actual_profit", store=True)
    actual_margin_percent = fields.Float(
        string="Actual Margin %", compute="_compute_actual_profit", store=True
    )
    cost_variance = fields.Monetary(
        string="Cost Variance",
        compute="_compute_variances",
        store=True,
        help="Actual total cost minus estimated cost.",
    )
    revenue_variance = fields.Monetary(
        string="Revenue Variance",
        compute="_compute_variances",
        store=True,
        help="Invoice amount minus selling amount.",
    )
    profit_variance = fields.Monetary(
        string="Profit Variance",
        compute="_compute_variances",
        store=True,
        help="Actual profit minus estimated profit.",
    )

    # Counts for smart buttons (exact set from original FAFF instruction)
    crm_count = fields.Integer(compute="_compute_counts")
    visit_count = fields.Integer(compute="_compute_counts")
    estimate_count = fields.Integer(compute="_compute_counts")
    quotation_count = fields.Integer(compute="_compute_counts")
    project_count = fields.Integer(compute="_compute_counts")
    task_count = fields.Integer(compute="_compute_counts")
    purchase_count = fields.Integer(compute="_compute_counts")
    picking_count = fields.Integer(compute="_compute_counts")
    delivery_count = fields.Integer(compute="_compute_counts")
    invoice_count = fields.Integer(compute="_compute_counts")
    payment_count = fields.Integer(compute="_compute_counts")
    attachment_count = fields.Integer(compute="_compute_counts")

    override_reason = fields.Text(string="Last Override Reason")

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("cpabooks.faff.job") or "FAFF/00001"
            )
        job = super().create(vals)
        job._log_stage_change(False, job.stage, _("Job created"))
        return job

    def write(self, vals):
        stage_changes = []
        if "stage" in vals:
            for job in self:
                if job.stage != vals["stage"]:
                    stage_changes.append((job, job.stage, vals["stage"]))
        res = super().write(vals)
        for job, old, new in stage_changes:
            job._log_stage_change(old, new, vals.get("override_reason") or "")
            if "progress" not in vals:
                job.progress = STAGE_PROGRESS.get(new, job.progress)
        return res

    def _log_stage_change(self, from_stage, to_stage, remarks=""):
        self.ensure_one()
        self.env["cpabooks.faff.stage.history"].create(
            {
                "job_id": self.id,
                "from_stage": from_stage or False,
                "to_stage": to_stage,
                "user_id": self.env.user.id,
                "remarks": remarks,
            }
        )

    @api.depends("stage", "project_id.task_ids.progress")
    def _compute_progress(self):
        for job in self:
            if job.stage in ("execution", "testing", "completion") and job.project_id:
                tasks = job.project_id.task_ids
                if tasks:
                    job.progress = sum(tasks.mapped("progress")) / len(tasks)
                    continue
            job.progress = STAGE_PROGRESS.get(job.stage, 0.0)

    @api.depends("visit_ids", "estimate_ids", "testing_ids", "completion_ids")
    def _compute_primary_links(self):
        for job in self:
            job.visit_id = job.visit_ids[:1]
            job.estimate_id = job.estimate_ids[:1]
            job.testing_id = job.testing_ids[:1]
            job.completion_id = job.completion_ids[:1]

    @api.depends(
        "estimate_ids.state",
        "estimate_ids.total_material_cost",
        "estimate_ids.total_labour_cost",
        "estimate_ids.total_other_cost",
        "estimate_ids.total_cost",
        "estimate_ids.selling_amount",
        "estimate_ids.expected_profit",
        "estimate_ids.margin_percent",
    )
    def _compute_estimated_amounts(self):
        for job in self:
            est = job.estimate_ids.filtered(lambda e: e.state in ("approved", "done"))[:1]
            if not est:
                est = job.estimate_ids[:1]
            if est:
                job.estimated_material_cost = est.total_material_cost
                job.estimated_labour_cost = est.total_labour_cost
                job.estimated_other_cost = est.total_other_cost
                job.estimated_cost = est.total_cost
                job.selling_amount = est.selling_amount
                job.expected_profit = est.expected_profit
                job.margin_percent = est.margin_percent
            else:
                job.estimated_material_cost = 0.0
                job.estimated_labour_cost = 0.0
                job.estimated_other_cost = 0.0
                job.estimated_cost = 0.0
                job.selling_amount = 0.0
                job.expected_profit = 0.0
                job.margin_percent = 0.0

    @api.depends(
        "material_plan_ids.issue_qty",
        "material_plan_ids.material_cost",
        "material_plan_ids.purchase_order_ids.amount_total",
        "project_id.task_ids.effective_hours",
    )
    def _compute_actual_amounts(self):
        for job in self:
            mat = sum(job.material_plan_ids.mapped("material_cost"))
            pos = self.env["purchase.order"].search([("faff_job_id", "=", job.id)])
            purchase = sum(pos.mapped("amount_total"))
            hours = sum(job.project_id.task_ids.mapped("effective_hours")) if job.project_id else 0.0
            # labour rate not forced — store hours*0 unless timesheet cost available
            labour = hours  # placeholder monetary hours count; real cost via timesheet if installed
            job.actual_material_cost = mat
            job.actual_purchase_cost = purchase
            job.actual_labour_cost = labour
            job.actual_total_cost = mat + purchase + labour + (job.actual_other_cost or 0.0)

    @api.depends(
        "sale_order_id.invoice_ids",
        "sale_order_id.invoice_ids.amount_total",
        "sale_order_id.invoice_ids.amount_residual",
        "sale_order_id.invoice_ids.payment_state",
        "invoice_ids",
        "invoice_ids.amount_total",
        "invoice_ids.amount_residual",
        "invoice_ids.payment_state",
        "invoice_ids.state",
    )
    def _compute_payment_amounts(self):
        for job in self:
            invoices = job.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state != "cancel"
            )
            if not invoices and job.sale_order_id:
                invoices = job.sale_order_id.invoice_ids.filtered(
                    lambda m: m.move_type == "out_invoice" and m.state != "cancel"
                )
            total = sum(invoices.mapped("amount_total"))
            residual = sum(invoices.mapped("amount_residual"))
            paid = total - residual
            job.invoice_amount = total
            job.paid_amount = paid
            job.balance_amount = residual
            if not invoices:
                job.payment_status = "not_invoiced"
            elif residual <= 0.01:
                job.payment_status = "paid"
            elif paid > 0:
                job.payment_status = "partial"
            else:
                job.payment_status = "invoiced"

    @api.depends("invoice_amount", "actual_total_cost", "selling_amount")
    def _compute_actual_profit(self):
        for job in self:
            revenue = job.invoice_amount or job.selling_amount
            job.actual_profit = revenue - (job.actual_total_cost or 0.0)
            job.actual_margin_percent = (
                (job.actual_profit / revenue * 100.0) if revenue else 0.0
            )

    @api.depends(
        "estimated_cost",
        "actual_total_cost",
        "selling_amount",
        "invoice_amount",
        "expected_profit",
        "actual_profit",
    )
    def _compute_variances(self):
        for job in self:
            job.cost_variance = (job.actual_total_cost or 0.0) - (job.estimated_cost or 0.0)
            job.revenue_variance = (job.invoice_amount or 0.0) - (job.selling_amount or 0.0)
            job.profit_variance = (job.actual_profit or 0.0) - (job.expected_profit or 0.0)

    def _compute_counts(self):
        Att = self.env["ir.attachment"]
        Picking = self.env["stock.picking"]
        for job in self:
            job.crm_count = 1 if job.crm_lead_id else 0
            job.visit_count = len(job.visit_ids)
            job.estimate_count = len(job.estimate_ids)
            job.quotation_count = 1 if job.sale_order_id else 0
            job.project_count = 1 if job.project_id else 0
            tasks = job.task_ids
            if not tasks and job.project_id:
                tasks = job.project_id.task_ids
            job.task_count = len(tasks)
            job.purchase_count = len(job.purchase_order_ids)
            # Material Issues = internal / stock ops tagged to job
            issues = job.picking_ids.filtered(
                lambda p: p.picking_type_code in ("internal", "outgoing")
                and not p.sale_id
            )
            if not issues:
                issues = job.picking_ids.filtered(
                    lambda p: p.picking_type_code == "internal"
                )
            job.picking_count = len(issues) or len(
                job.picking_ids.filtered(lambda p: not p.sale_id)
            )
            # Delivery = customer DO from SO + handover notes
            so_pickings = Picking.browse()
            if job.sale_order_id:
                so_pickings = job.sale_order_id.picking_ids
            job_deliveries = job.picking_ids.filtered(
                lambda p: p.picking_type_code == "outgoing" and p.sale_id
            )
            delivery_pickings = so_pickings | job_deliveries
            job.delivery_count = len(delivery_pickings) + len(job.completion_ids)
            invoices = job.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state != "cancel"
            )
            if not invoices and job.sale_order_id:
                invoices = job.sale_order_id.invoice_ids.filtered(
                    lambda m: m.move_type == "out_invoice" and m.state != "cancel"
                )
            job.invoice_count = len(invoices)
            payment_ids = set()
            for inv in invoices.filtered(lambda m: m.state == "posted"):
                payments = (
                    inv._get_reconciled_payments()
                    if hasattr(inv, "_get_reconciled_payments")
                    else self.env["account.payment"]
                )
                payment_ids.update(payments.ids)
            job.payment_count = len(payment_ids)
            job.attachment_count = Att.search_count(
                [("res_model", "=", "cpabooks.faff.job"), ("res_id", "=", job.id)]
            )

    def action_continue_wizard(self):
        self.ensure_one()
        wizard = self.env["cpabooks.faff.job.wizard"].create(
            {
                "job_id": self.id,
                "step_index": self.wizard_step or 0,
            }
        )
        wizard._load_from_job()
        return wizard._reopen()

    def action_open_crm(self):
        self.ensure_one()
        if not self.crm_lead_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": self.crm_lead_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_visits(self):
        return self._action_open_o2m("cpabooks.faff.visit", "visit_ids")

    def action_open_estimates(self):
        return self._action_open_o2m("cpabooks.faff.estimate", "estimate_ids")

    def action_open_sale(self):
        self.ensure_one()
        if not self.sale_order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
        }

    def action_open_project(self):
        self.ensure_one()
        if not self.project_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.project",
            "res_id": self.project_id.id,
            "view_mode": "form",
        }

    def action_open_tasks(self):
        self.ensure_one()
        domain = [("faff_job_id", "=", self.id)]
        if self.project_id:
            domain = ["|", ("faff_job_id", "=", self.id), ("project_id", "=", self.project_id.id)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Tasks"),
            "res_model": "project.task",
            "view_mode": "tree,form,kanban",
            "domain": domain,
            "context": {
                "default_project_id": self.project_id.id if self.project_id else False,
                "default_faff_job_id": self.id,
            },
        }

    def action_open_purchases(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase"),
            "res_model": "purchase.order",
            "view_mode": "tree,form",
            "domain": [("faff_job_id", "=", self.id)],
            "context": {"default_faff_job_id": self.id},
        }

    def action_open_pickings(self):
        """Material Issues — stock transfers not driven by customer SO delivery."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Material Issues"),
            "res_model": "stock.picking",
            "view_mode": "tree,form",
            "domain": [
                ("faff_job_id", "=", self.id),
                "|",
                ("sale_id", "=", False),
                ("picking_type_code", "=", "internal"),
            ],
            "context": {"default_faff_job_id": self.id},
        }

    def action_open_deliveries(self):
        """Delivery — customer DOs + handover / completion notes."""
        self.ensure_one()
        picking_ids = self.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing" and p.sale_id
        ).ids
        if self.sale_order_id:
            picking_ids = list(set(picking_ids + self.sale_order_id.picking_ids.ids))
        # Prefer opening completions when no DO yet (handover is FAFF Delivery)
        if not picking_ids:
            return {
                "type": "ir.actions.act_window",
                "name": _("Delivery / Handover"),
                "res_model": "cpabooks.faff.completion",
                "view_mode": "tree,form",
                "domain": [("job_id", "=", self.id)],
                "context": {"default_job_id": self.id},
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery"),
            "res_model": "stock.picking",
            "view_mode": "tree,form",
            "domain": [("id", "in", picking_ids)],
            "context": {"default_faff_job_id": self.id},
        }

    def action_open_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(lambda m: m.move_type == "out_invoice")
        if not invoices and self.sale_order_id:
            invoices = self.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice"
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [("id", "in", invoices.ids)],
            "context": {
                "default_move_type": "out_invoice",
                "default_faff_job_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_open_payments(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type == "out_invoice" and m.state == "posted"
        )
        if not invoices and self.sale_order_id:
            invoices = self.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state == "posted"
            )
        payment_ids = set()
        for inv in invoices:
            payments = (
                inv._get_reconciled_payments()
                if hasattr(inv, "_get_reconciled_payments")
                else self.env["account.payment"]
            )
            payment_ids.update(payments.ids)
        return {
            "type": "ir.actions.act_window",
            "name": _("Payment"),
            "res_model": "account.payment",
            "view_mode": "tree,form",
            "domain": [("id", "in", list(payment_ids))],
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
            },
        }

    def action_open_attachments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attachments"),
            "res_model": "ir.attachment",
            "view_mode": "kanban,tree,form",
            "domain": [("res_model", "=", "cpabooks.faff.job"), ("res_id", "=", self.id)],
            "context": {
                "default_res_model": "cpabooks.faff.job",
                "default_res_id": self.id,
            },
        }

    def _action_open_o2m(self, model, field_name):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self._fields[field_name].string,
            "res_model": model,
            "view_mode": "tree,form",
            "domain": [("job_id", "=", self.id)],
            "context": {"default_job_id": self.id},
        }

    def action_manager_override_stage(self, to_stage, reason):
        """Allow FAFF Manager to skip stage with recorded reason."""
        self.ensure_one()
        if not self.env.user.has_group("cpabooks_faff.group_faff_manager"):
            raise UserError(_("Only FAFF Managers can override stages."))
        if not reason:
            raise UserError(_("Override reason is required."))
        self.write(
            {
                "override_reason": reason,
                "stage": to_stage,
                "status": "in_progress",
            }
        )
        return True

    def action_set_cancelled(self):
        self.write({"stage": "cancel", "status": "cancel"})

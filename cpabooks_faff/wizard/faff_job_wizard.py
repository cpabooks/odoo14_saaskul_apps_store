# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

from ..models.faff_job import FAFF_STAGES

# Blueprint: 1 CRM → 13 Job Closing (same-to-same process flow).
WIZARD_STEPS = [
    {
        "key": "crm",
        "label": "1. CRM Lead / Opportunity",
        "stage": "crm",
        "hint": "Customer, site and job type. Next → Site Visit / Inspection.",
    },
    {
        "key": "inspection",
        "label": "2. Site Visit / Inspection",
        "stage": "inspection",
        "hint": "Record observations, existing system and photos. Next → Estimation.",
    },
    {
        "key": "estimation",
        "label": "3. Estimation (BOQ + Costing)",
        "stage": "estimation",
        "hint": "Add BOQ lines, Save, Approve. Next → Quotation.",
    },
    {
        "key": "quotation",
        "label": "4. Quotation",
        "stage": "quotation",
        "hint": "Create Quotation from approved BOQ. Next → Confirm Quotation.",
    },
    {
        "key": "confirm",
        "label": "5. Confirm Quotation",
        "stage": "confirmed",
        "hint": "Customer approved — click Confirm. Next → Project + Tasks.",
    },
    {
        "key": "project",
        "label": "6. Project + Tasks",
        "stage": "project",
        "hint": "Create Project and default tasks. Next → Material Arrangement.",
    },
    {
        "key": "material",
        "label": "7. Material Arrangement",
        "stage": "material",
        "hint": "In stock → Issue. Not in stock → Purchase RFQ. Next → Execution.",
    },
    {
        "key": "execution",
        "label": "8. Execution (Job Work)",
        "stage": "execution",
        "hint": "Update task progress, manpower hours and photos. Next → Testing.",
    },
    {
        "key": "testing",
        "label": "9. Testing & Commissioning",
        "stage": "testing",
        "hint": "Record commissioning. Pass (or close rectification). Next → Delivery Note.",
    },
    {
        "key": "completion",
        "label": "10. Delivery Note / Completion",
        "stage": "completion",
        "hint": "Handover note + customer signature. Confirm Completion. Next → Invoice.",
    },
    {
        "key": "invoice",
        "label": "11. Invoice",
        "stage": "invoice",
        "hint": "Create Invoice from confirmed Sale Order. Next → Payment.",
    },
    {
        "key": "payment",
        "label": "12. Payment",
        "stage": "payment",
        "hint": "Register full or partial payment. Next → Job Closing.",
    },
    {
        "key": "closing",
        "label": "13. Job Closing",
        "stage": "done",
        "hint": "All documents linked. Click Finished to close the job.",
    },
]


class FaffJobWizard(models.TransientModel):
    _name = "cpabooks.faff.job.wizard"
    _description = "FAFF Job Wizard"

    job_id = fields.Many2one("cpabooks.faff.job", string="FAFF Job")
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )
    step_index = fields.Integer(default=0)
    step_key = fields.Char(compute="_compute_step")
    step_title = fields.Char(compute="_compute_step")
    step_hint = fields.Char(compute="_compute_step")
    progress_label = fields.Char(compute="_compute_step")
    progress_html = fields.Html(compute="_compute_step", sanitize=False)
    total_steps = fields.Integer(compute="_compute_step")
    is_first = fields.Boolean(compute="_compute_step")
    is_last = fields.Boolean(compute="_compute_step")
    is_finished = fields.Boolean(compute="_compute_step")

    # Step 1 — CRM
    crm_lead_id = fields.Many2one("crm.lead", string="Opportunity")
    create_new_opportunity = fields.Boolean(string="Create New Opportunity", default=True)
    opportunity_name = fields.Char()
    partner_id = fields.Many2one("res.partner", string="Customer")
    contact_id = fields.Many2one("res.partner", string="Contact Person")
    mobile = fields.Char()
    email = fields.Char()
    site_name = fields.Char()
    site_address = fields.Text(string="Site Location")
    salesperson_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    lead_source_id = fields.Many2one("utm.source")
    job_type_id = fields.Many2one("cpabooks.faff.job.type")
    description = fields.Text()
    planned_start_date = fields.Date()
    expected_end_date = fields.Date()

    # Step 2 — Inspection
    visit_id = fields.Many2one("cpabooks.faff.visit")
    inspection_date = fields.Date(default=fields.Date.context_today)
    site_engineer_id = fields.Many2one("hr.employee")
    site_contact = fields.Char()
    existing_system = fields.Char()
    existing_brand = fields.Char()
    panel_type = fields.Char()
    floor_count = fields.Integer()
    device_count = fields.Integer()
    problem_requirement = fields.Text()
    observation = fields.Text()
    technical_recommendation = fields.Text()
    scope_summary = fields.Text()
    inspection_remarks = fields.Text()
    visit_attachment_ids = fields.Many2many(
        "ir.attachment",
        "faff_wiz_visit_att_rel",
        "wizard_id",
        "attachment_id",
    )

    # Step 3 — Estimation
    estimate_id = fields.Many2one("cpabooks.faff.estimate")
    estimate_line_ids = fields.One2many(
        related="estimate_id.line_ids", readonly=False
    )
    estimated_cost = fields.Monetary(related="estimate_id.total_cost", readonly=True)
    selling_amount = fields.Monetary(related="estimate_id.selling_amount", readonly=True)
    expected_profit = fields.Monetary(related="estimate_id.expected_profit", readonly=True)
    margin_percent = fields.Float(related="estimate_id.margin_percent", readonly=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    # Step 4 — Quotation
    sale_order_id = fields.Many2one("sale.order")
    quotation_name = fields.Char(related="sale_order_id.name", readonly=True)
    quotation_amount = fields.Monetary(
        related="sale_order_id.amount_total", readonly=True
    )
    quotation_state = fields.Selection(related="sale_order_id.state", readonly=True)
    validity_date = fields.Date(related="sale_order_id.validity_date", readonly=True)

    # Step 5 — Project
    project_id = fields.Many2one("project.project")
    default_task_ids = fields.Many2many(
        "cpabooks.faff.default.task",
        "faff_wiz_default_task_rel",
        "wizard_id",
        "task_id",
        string="Tasks to Create",
    )

    # Step 6 — Material
    material_plan_ids = fields.One2many(
        related="job_id.material_plan_ids", readonly=False
    )

    # Step 7 — Execution
    task_ids = fields.One2many(related="project_id.task_ids", readonly=False)
    job_progress = fields.Float(related="job_id.progress", readonly=True)

    # Step 8 — Testing
    testing_id = fields.Many2one("cpabooks.faff.testing")
    testing_date = fields.Date(default=fields.Date.context_today)
    tested_by_id = fields.Many2one("hr.employee")
    system_status = fields.Selection(
        [
            ("passed", "Passed"),
            ("passed_remarks", "Passed with Remarks"),
            ("failed", "Failed"),
            ("rectification", "Rectification Required"),
        ],
        default="passed",
    )
    panel_tested = fields.Boolean()
    devices_tested = fields.Boolean()
    pump_tested = fields.Boolean()
    alarm_tested = fields.Boolean()
    cause_effect_tested = fields.Boolean()
    emergency_light_tested = fields.Boolean()
    testing_remarks = fields.Text()
    defects_found = fields.Text()
    rectification_required = fields.Boolean()

    # Step 9 — Completion
    completion_id = fields.Many2one("cpabooks.faff.completion")
    completion_date = fields.Date(default=fields.Date.context_today)
    work_completed = fields.Text()
    material_delivered = fields.Text()
    testing_result = fields.Text()
    outstanding_items = fields.Text()
    warranty = fields.Char()
    completion_remarks = fields.Text()
    customer_name = fields.Char()
    customer_designation = fields.Char()
    customer_signature = fields.Binary()
    sign_date = fields.Date()

    # Step 10 — Invoice
    invoice_id = fields.Many2one("account.move")
    invoice_name = fields.Char(related="invoice_id.name", readonly=True)
    invoice_date = fields.Date(related="invoice_id.invoice_date", readonly=True)
    invoice_untaxed = fields.Monetary(related="invoice_id.amount_untaxed", readonly=True)
    invoice_tax = fields.Monetary(related="invoice_id.amount_tax", readonly=True)
    invoice_total = fields.Monetary(related="invoice_id.amount_total", readonly=True)
    invoice_residual = fields.Monetary(related="invoice_id.amount_residual", readonly=True)
    invoice_payment_state = fields.Selection(
        related="invoice_id.payment_state", readonly=True
    )

    # Step 11 — Payment
    payment_status = fields.Selection(related="job_id.payment_status", readonly=True)
    paid_amount = fields.Monetary(related="job_id.paid_amount", readonly=True)
    balance_amount = fields.Monetary(related="job_id.balance_amount", readonly=True)

    override_reason = fields.Text(string="Manager Override Reason")

    @api.depends("step_index", "job_id", "job_id.payment_status", "job_id.stage")
    def _compute_step(self):
        total = len(WIZARD_STEPS)
        for wiz in self:
            idx = max(0, min(wiz.step_index or 0, total - 1))
            step = WIZARD_STEPS[idx]
            wiz.step_index = idx
            wiz.total_steps = total
            wiz.step_key = step["key"]
            wiz.step_title = step["label"]
            wiz.step_hint = step["hint"]
            wiz.is_first = idx == 0
            wiz.is_last = idx >= total - 1
            paid = bool(wiz.job_id and wiz.job_id.payment_status == "paid")
            done = bool(wiz.job_id and wiz.job_id.stage == "done")
            wiz.is_finished = wiz.is_last and (paid or done)
            wiz.progress_label = _("Step %s of %s") % (idx + 1, total)
            wiz.progress_html = wiz._build_progress_html(idx)

    def _build_progress_html(self, current_idx):
        rows = [
            '<div class="o_faff_wiz_progress">',
            '<div class="o_faff_wiz_progress_title">%s</div>'
            % (_("One job · One wizard"),),
            "<ol>",
        ]
        for i, step in enumerate(WIZARD_STEPS):
            if i < current_idx:
                css = "o_faff_wiz_step o_faff_wiz_done"
                mark = "✓"
            elif i == current_idx:
                css = "o_faff_wiz_step o_faff_wiz_current"
                mark = "●"
            else:
                css = "o_faff_wiz_step o_faff_wiz_todo"
                mark = str(i + 1)
            rows.append(
                '<li class="%s"><span class="o_faff_wiz_mark">%s</span>'
                '<span class="o_faff_wiz_label">%s</span></li>'
                % (css, mark, step["label"])
            )
        rows.append("</ol></div>")
        return "".join(rows)

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("FAFF Process — One Job"),
            "res_model": "cpabooks.faff.job.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, form_view_initial_mode="edit"),
        }

    def _load_from_job(self):
        self.ensure_one()
        job = self.job_id
        if not job:
            return
        vals = {
            "crm_lead_id": job.crm_lead_id.id,
            "create_new_opportunity": not bool(job.crm_lead_id),
            "opportunity_name": job.crm_lead_id.name if job.crm_lead_id else job.site_name,
            "partner_id": job.partner_id.id,
            "contact_id": job.contact_id.id,
            "mobile": job.mobile,
            "email": job.email,
            "site_name": job.site_name,
            "site_address": job.site_address,
            "salesperson_id": job.salesperson_id.id,
            "lead_source_id": job.lead_source_id.id,
            "job_type_id": job.job_type_id.id,
            "description": job.description,
            "planned_start_date": job.planned_start_date,
            "expected_end_date": job.expected_end_date,
            "visit_id": job.visit_id.id,
            "estimate_id": job.estimate_id.id,
            "sale_order_id": job.sale_order_id.id,
            "project_id": job.project_id.id,
            "testing_id": job.testing_id.id,
            "completion_id": job.completion_id.id,
            "currency_id": job.currency_id.id,
        }
        if job.visit_id:
            v = job.visit_id
            vals.update(
                {
                    "inspection_date": v.inspection_date,
                    "site_engineer_id": v.site_engineer_id.id,
                    "site_contact": v.site_contact,
                    "existing_system": v.existing_system,
                    "existing_brand": v.existing_brand,
                    "panel_type": v.panel_type,
                    "floor_count": v.floor_count,
                    "device_count": v.device_count,
                    "problem_requirement": v.problem_requirement,
                    "observation": v.observation,
                    "technical_recommendation": v.technical_recommendation,
                    "scope_summary": v.scope_summary,
                    "inspection_remarks": v.inspection_remarks,
                }
            )
        if job.testing_id:
            t = job.testing_id
            vals.update(
                {
                    "testing_date": t.testing_date,
                    "tested_by_id": t.tested_by_id.id,
                    "system_status": t.system_status,
                    "panel_tested": t.panel_tested,
                    "devices_tested": t.devices_tested,
                    "pump_tested": t.pump_tested,
                    "alarm_tested": t.alarm_tested,
                    "cause_effect_tested": t.cause_effect_tested,
                    "emergency_light_tested": t.emergency_light_tested,
                    "testing_remarks": t.remarks,
                    "defects_found": t.defects_found,
                    "rectification_required": t.rectification_required,
                }
            )
        if job.completion_id:
            c = job.completion_id
            vals.update(
                {
                    "completion_date": c.completion_date,
                    "work_completed": c.work_completed,
                    "material_delivered": c.material_delivered,
                    "testing_result": c.testing_result,
                    "outstanding_items": c.outstanding_items,
                    "warranty": c.warranty,
                    "completion_remarks": c.remarks,
                    "customer_name": c.customer_name,
                    "customer_designation": c.customer_designation,
                    "sign_date": c.sign_date,
                }
            )
        if job.sale_order_id:
            inv = job.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state != "cancel"
            )[:1]
            if inv:
                vals["invoice_id"] = inv.id
        if not self.default_task_ids:
            vals["default_task_ids"] = [
                (6, 0, self.env["cpabooks.faff.default.task"].search([]).ids)
            ]
        self.write(vals)

    def action_save(self):
        self.ensure_one()
        self._persist_current_step()
        return self._reopen()

    def action_save_close(self):
        self.ensure_one()
        self._persist_current_step()
        if self.job_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("FAFF Job"),
                "res_model": "cpabooks.faff.job",
                "res_id": self.job_id.id,
                "view_mode": "form",
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}

    def action_previous(self):
        self.ensure_one()
        self._persist_current_step()
        self.step_index = max(0, (self.step_index or 0) - 1)
        if self.job_id:
            self.job_id.wizard_step = self.step_index
        return self._reopen()

    def action_next(self):
        self.ensure_one()
        self._persist_current_step()
        self._validate_before_next()
        total = len(WIZARD_STEPS)
        if self.step_index < total - 1:
            self.step_index += 1
        if self.job_id:
            self.job_id.wizard_step = self.step_index
            step = WIZARD_STEPS[self.step_index]
            if self.job_id.stage not in ("done", "cancel"):
                stage_keys = [s[0] for s in FAFF_STAGES]
                cur = (
                    stage_keys.index(self.job_id.stage)
                    if self.job_id.stage in stage_keys
                    else 0
                )
                target = (
                    stage_keys.index(step["stage"])
                    if step["stage"] in stage_keys
                    else cur
                )
                if target > cur:
                    self.job_id.stage = step["stage"]
                    self.job_id.status = "in_progress"
            if step["key"] == "estimation":
                self._persist_estimation()
                self._load_from_job()
        return self._reopen()

    def action_finish(self):
        """Mark job Finished after payment step."""
        self.ensure_one()
        self._persist_current_step()
        job = self.job_id
        if not job:
            raise UserError(_("No FAFF Job linked."))
        if job.payment_status != "paid" and not self.env.user.has_group(
            "cpabooks_faff.group_faff_manager"
        ):
            raise UserError(
                _("Register full payment first (or Manager may finish with override).")
            )
        job.write(
            {
                "stage": "done",
                "status": "paid" if job.payment_status == "paid" else "completed",
                "wizard_step": len(WIZARD_STEPS) - 1,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("FAFF Job"),
            "res_model": "cpabooks.faff.job",
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def _validate_before_next(self):
        self.ensure_one()
        key = self.step_key
        job = self.job_id

        if key == "crm" and not self.partner_id:
            raise UserError(_("Customer is required."))
        if key == "estimation":
            est = (job and job.estimate_id) or self.estimate_id
            if not est:
                raise UserError(_("Save the estimation first."))
            if est.state not in ("approved", "done"):
                if not est.line_ids:
                    raise UserError(_("Add at least one BOQ line before Next."))
                est.action_approve_estimation()
        if key == "quotation":
            self._ensure_quotation()
        if key == "confirm":
            self._ensure_confirmed_order()
        if key == "project":
            self._ensure_project()
        if key == "completion":
            self._persist_completion()
            if self.completion_id and self.completion_id.state != "confirmed":
                try:
                    self.completion_id.action_confirm_completion()
                except Exception as exc:
                    _logger.warning("FAFF completion confirm skipped: %s", exc)
        if key == "invoice":
            self._ensure_invoice()

    def _persist_current_step(self):
        self.ensure_one()
        key = WIZARD_STEPS[self.step_index]["key"]
        method = getattr(self, "_persist_%s" % key, None)
        try:
            if method:
                method()
            if self.job_id:
                self.job_id.wizard_step = self.step_index
        except UserError:
            raise
        except Exception as exc:
            _logger.warning("FAFF wizard persist skipped on step %s: %s", key, exc)

    def _ensure_job(self):
        self.ensure_one()
        if self.job_id:
            return self.job_id
        if not self.partner_id:
            raise UserError(_("Select or create a Customer first."))
        job = self.env["cpabooks.faff.job"].create(
            {
                "partner_id": self.partner_id.id,
                "contact_id": self.contact_id.id,
                "mobile": self.mobile,
                "email": self.email,
                "site_name": self.site_name or self.opportunity_name,
                "site_address": self.site_address,
                "job_type_id": self.job_type_id.id,
                "salesperson_id": self.salesperson_id.id,
                "lead_source_id": self.lead_source_id.id,
                "description": self.description,
                "planned_start_date": self.planned_start_date,
                "expected_end_date": self.expected_end_date,
                "stage": "crm",
                "status": "in_progress",
                "wizard_step": 0,
            }
        )
        self.job_id = job.id
        return job

    def _persist_crm(self):
        job = self._ensure_job()
        lead = self.crm_lead_id
        if self.create_new_opportunity and not lead:
            lead = self.env["crm.lead"].create(
                {
                    "name": self.opportunity_name or self.site_name or job.name,
                    "partner_id": self.partner_id.id,
                    "type": "opportunity",
                    "user_id": self.salesperson_id.id,
                    "email_from": self.email,
                    "phone": self.mobile,
                    "description": self.description,
                    "source_id": self.lead_source_id.id,
                    "faff_job_id": job.id,
                }
            )
            self.crm_lead_id = lead.id
        elif lead:
            lead.write(
                {
                    "partner_id": self.partner_id.id or lead.partner_id.id,
                    "faff_job_id": job.id,
                }
            )
        job.write(
            {
                "crm_lead_id": lead.id if lead else False,
                "partner_id": self.partner_id.id,
                "contact_id": self.contact_id.id,
                "mobile": self.mobile,
                "email": self.email,
                "site_name": self.site_name,
                "site_address": self.site_address,
                "job_type_id": self.job_type_id.id,
                "salesperson_id": self.salesperson_id.id,
                "lead_source_id": self.lead_source_id.id,
                "description": self.description,
                "planned_start_date": self.planned_start_date,
                "expected_end_date": self.expected_end_date,
                "stage": "crm",
                "status": "in_progress",
            }
        )
        if lead:
            lead.faff_job_id = job.id

    def _persist_inspection(self):
        job = self._ensure_job()
        vals = {
            "job_id": job.id,
            "name": _("Inspection — %s") % (job.name,),
            "inspection_date": self.inspection_date,
            "site_engineer_id": self.site_engineer_id.id,
            "site_contact": self.site_contact,
            "existing_system": self.existing_system,
            "existing_brand": self.existing_brand,
            "panel_type": self.panel_type,
            "floor_count": self.floor_count,
            "device_count": self.device_count,
            "problem_requirement": self.problem_requirement,
            "observation": self.observation,
            "technical_recommendation": self.technical_recommendation,
            "scope_summary": self.scope_summary,
            "inspection_remarks": self.inspection_remarks,
            "attachment_ids": [(6, 0, self.visit_attachment_ids.ids)],
        }
        if self.visit_id:
            self.visit_id.write(vals)
        else:
            visit = self.env["cpabooks.faff.visit"].create(vals)
            self.visit_id = visit.id
        job.write({"stage": "inspection", "status": "in_progress"})

    def _persist_estimation(self):
        job = self._ensure_job()
        if not self.estimate_id:
            est = self.env["cpabooks.faff.estimate"].create(
                {"job_id": job.id, "name": "New"}
            )
            self.estimate_id = est.id
        job.write({"stage": "estimation", "status": "in_progress"})

    def action_save_estimation(self):
        self.ensure_one()
        self._persist_estimation()
        self.estimate_id.action_save_estimation()
        return self._reopen()

    def action_approve_estimation(self):
        self.ensure_one()
        self._persist_estimation()
        self.estimate_id.action_approve_estimation()
        return self._reopen()

    def _persist_quotation(self):
        so = self._ensure_quotation()
        job = self._ensure_job()
        job.write(
            {
                "sale_order_id": so.id,
                "stage": "quotation",
                "status": "in_progress",
            }
        )

    def _persist_confirm(self):
        self._ensure_confirmed_order()

    def _faff_fallback_product(self):
        Product = self.env["product.product"].sudo()
        product = Product.search([("default_code", "=", "FAFF-SVC")], limit=1)
        if product:
            return product
        return Product.search([("type", "=", "service")], limit=1) or Product.create(
            {
                "name": "FAFF Job Service",
                "default_code": "FAFF-SVC",
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "list_price": 0.0,
            }
        )

    def _ensure_quotation(self):
        """Create sale quotation from BOQ if the job has none yet."""
        job = self._ensure_job()
        so = job.sale_order_id or self.sale_order_id
        if so:
            self.sale_order_id = so.id
            return so
        est = job.estimate_id or self.estimate_id
        if not est:
            raise UserError(_("Save the estimation first."))
        if est.state not in ("approved", "done"):
            if not est.line_ids:
                raise UserError(_("Add at least one BOQ line first."))
            est.action_approve_estimation()
        fallback = self._faff_fallback_product()
        lines = []
        for line in est.line_ids:
            product = line.product_id or fallback
            lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": line.name or product.display_name,
                        "product_uom_qty": line.product_uom_qty or 1.0,
                        "product_uom": (line.product_uom_id or product.uom_id).id,
                        "price_unit": line.selling_price or 0.0,
                        "tax_id": [(6, 0, line.tax_ids.ids)],
                    },
                )
            )
        if not lines:
            lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": fallback.id,
                        "name": job.name or fallback.display_name,
                        "product_uom_qty": 1.0,
                        "product_uom": fallback.uom_id.id,
                        "price_unit": est.selling_amount or 0.0,
                    },
                )
            )
        so = self.env["sale.order"].create(
            {
                "partner_id": job.partner_id.id,
                "user_id": job.salesperson_id.id,
                "origin": job.name,
                "client_order_ref": job.name,
                "note": job.description or "",
                "faff_job_id": job.id,
                "order_line": lines,
            }
        )
        self.sale_order_id = so.id
        job.write(
            {
                "sale_order_id": so.id,
                "stage": "quotation",
                "status": "in_progress",
            }
        )
        return so

    def action_create_quotation(self):
        self.ensure_one()
        self._ensure_quotation()
        return self._reopen()

    def _ensure_confirmed_order(self):
        so = self._ensure_quotation()
        if so.state in ("draft", "sent"):
            try:
                so.action_confirm()
            except UserError:
                raise
            except Exception as exc:
                _logger.warning("FAFF quotation confirm skipped: %s", exc)
        job = self._ensure_job()
        self.sale_order_id = so.id
        job.write(
            {
                "sale_order_id": so.id,
                "stage": "confirmed",
                "status": "in_progress",
            }
        )
        return so

    def action_confirm_quotation(self):
        self.ensure_one()
        self._ensure_confirmed_order()
        return self._reopen()

    def action_open_quotation(self):
        self.ensure_one()
        so = self.sale_order_id or (self.job_id and self.job_id.sale_order_id)
        if not so:
            raise UserError(_("No quotation yet."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": so.id,
            "view_mode": "form",
            "target": "current",
        }

    def _persist_project(self):
        self._ensure_project()

    def _ensure_project(self):
        job = self._ensure_job()
        if job.project_id:
            self.project_id = job.project_id
            return job.project_id
        so = job.sale_order_id or self.sale_order_id
        if so and so.state in ("draft", "sent"):
            self._ensure_confirmed_order()
        project = self.env["project.project"].create(
            {
                "name": "%s — %s" % (job.name, job.site_name or job.partner_id.name),
                "partner_id": job.partner_id.id,
                "user_id": job.salesperson_id.id,
                "faff_job_id": job.id,
            }
        )
        tasks = self.default_task_ids or self.env["cpabooks.faff.default.task"].search(
            []
        )
        for tmpl in tasks:
            self.env["project.task"].create(
                {
                    "name": tmpl.name,
                    "project_id": project.id,
                    "faff_job_id": job.id,
                    "description": tmpl.description or "",
                }
            )
        est = job.estimate_id
        if est:
            Plan = self.env["cpabooks.faff.material.plan"]
            for line in est.line_ids.filtered("product_id"):
                Plan.create(
                    {
                        "job_id": job.id,
                        "product_id": line.product_id.id,
                        "name": line.name,
                        "product_uom_id": line.product_uom_id.id,
                        "qty_required": line.product_uom_qty,
                    }
                )
        self.project_id = project.id
        job.write(
            {
                "project_id": project.id,
                "stage": "project",
                "status": "in_progress",
                "actual_start_date": fields.Date.context_today(self),
            }
        )
        return project

    def action_create_project_tasks(self):
        self.ensure_one()
        self._ensure_project()
        return self._reopen()

    def _persist_material(self):
        job = self._ensure_job()
        job.write({"stage": "material", "status": "in_progress"})

    def _persist_execution(self):
        job = self._ensure_job()
        job.write({"stage": "execution", "status": "in_progress"})

    def _persist_testing(self):
        job = self._ensure_job()
        vals = {
            "job_id": job.id,
            "testing_date": self.testing_date,
            "tested_by_id": self.tested_by_id.id,
            "system_status": self.system_status,
            "panel_tested": self.panel_tested,
            "devices_tested": self.devices_tested,
            "pump_tested": self.pump_tested,
            "alarm_tested": self.alarm_tested,
            "cause_effect_tested": self.cause_effect_tested,
            "emergency_light_tested": self.emergency_light_tested,
            "remarks": self.testing_remarks,
            "defects_found": self.defects_found,
            "rectification_required": self.rectification_required,
        }
        if self.testing_id:
            self.testing_id.write(vals)
        else:
            testing = self.env["cpabooks.faff.testing"].create(vals)
            self.testing_id = testing.id
        job.write({"stage": "testing", "status": "in_progress"})

    def action_create_rectification_task(self):
        self.ensure_one()
        self._persist_testing()
        return self.testing_id.action_create_rectification_task()

    def _persist_completion(self):
        job = self._ensure_job()
        vals = {
            "job_id": job.id,
            "completion_date": self.completion_date,
            "work_completed": self.work_completed,
            "material_delivered": self.material_delivered,
            "testing_result": self.testing_result,
            "outstanding_items": self.outstanding_items,
            "warranty": self.warranty,
            "remarks": self.completion_remarks,
            "customer_name": self.customer_name,
            "customer_designation": self.customer_designation,
            "customer_signature": self.customer_signature,
            "sign_date": self.sign_date,
        }
        if self.completion_id:
            self.completion_id.write(vals)
        else:
            completion = self.env["cpabooks.faff.completion"].create(vals)
            self.completion_id = completion.id

    def action_confirm_completion(self):
        self.ensure_one()
        self._persist_completion()
        self.completion_id.action_confirm_completion()
        return self._reopen()

    def action_print_completion(self):
        self.ensure_one()
        self._persist_completion()
        return self.completion_id.action_print_handover()

    def _persist_invoice(self):
        self._ensure_invoice()

    def _ensure_invoice(self):
        job = self._ensure_job()
        so = self._ensure_confirmed_order()
        existing = so.invoice_ids.filtered(
            lambda m: m.move_type == "out_invoice" and m.state != "cancel"
        )
        if existing:
            invoice = existing[0]
        else:
            try:
                moves = so._create_invoices()
                invoice = moves[:1]
            except Exception as exc:
                _logger.warning("FAFF invoice create skipped: %s", exc)
                invoice = so.invoice_ids.filtered(
                    lambda m: m.move_type == "out_invoice" and m.state != "cancel"
                )[:1]
        if not invoice:
            return False
        invoice.faff_job_id = job.id
        self.invoice_id = invoice.id
        job.write({"stage": "invoice", "status": "in_progress"})
        return invoice

    def action_create_invoice(self):
        self.ensure_one()
        invoice = self._ensure_invoice()
        if not invoice:
            raise UserError(_("Could not create invoice from the Sale Order."))
        return self._reopen()

    def action_open_invoice(self):
        self.ensure_one()
        inv = self.invoice_id
        if not inv and self.job_id and self.job_id.sale_order_id:
            inv = self.job_id.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice"
            )[:1]
            self.invoice_id = inv.id
        if not inv:
            raise UserError(_("No invoice yet."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": inv.id,
            "view_mode": "form",
            "target": "current",
        }

    def _persist_payment(self):
        job = self._ensure_job()
        job.write({"stage": "payment", "status": "in_progress"})

    def _persist_closing(self):
        job = self._ensure_job()
        if job.payment_status == "paid":
            job.write({"stage": "done", "status": "paid"})
        else:
            job.write({"stage": "done", "status": "completed"})

    def action_register_payment(self):
        self.ensure_one()
        inv = self.invoice_id
        if not inv:
            raise UserError(_("Create / open invoice first."))
        if inv.state == "draft":
            inv.action_post()
        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payment"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": inv.ids,
            },
        }

    @api.model
    def action_open_new_wizard(self):
        defaults = self.env["cpabooks.faff.default.task"].search([])
        wiz = self.create(
            {
                "step_index": 0,
                "create_new_opportunity": True,
                "default_task_ids": [(6, 0, defaults.ids)],
            }
        )
        return wiz._reopen()

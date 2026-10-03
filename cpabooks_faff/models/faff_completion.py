# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FaffCompletion(models.Model):
    _name = "cpabooks.faff.completion"
    _description = "FAFF Completion / Handover Note"
    _order = "id desc"

    name = fields.Char(required=True, default="New")
    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    partner_id = fields.Many2one(related="job_id.partner_id", store=True)
    site_name = fields.Char(related="job_id.site_name")
    project_id = fields.Many2one(related="job_id.project_id")
    sale_order_id = fields.Many2one(related="job_id.sale_order_id")
    completion_date = fields.Date(default=fields.Date.context_today)
    work_completed = fields.Text()
    material_delivered = fields.Text(string="Material / Equipment Delivered")
    testing_result = fields.Text()
    outstanding_items = fields.Text()
    warranty = fields.Char()
    remarks = fields.Text()
    customer_name = fields.Char(string="Customer Signatory Name")
    customer_designation = fields.Char()
    customer_signature = fields.Binary(string="Signature")
    sign_date = fields.Date(string="Sign Date")
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("cpabooks.faff.completion")
                or "HANDOVER/00001"
            )
        return super().create(vals)

    def action_confirm_completion(self):
        for rec in self:
            testing = rec.job_id.testing_ids[:1]
            if testing and testing.system_status in ("failed", "rectification"):
                if not self.env.user.has_group("cpabooks_faff.group_faff_manager"):
                    raise UserError(
                        _(
                            "Testing failed / rectification open. "
                            "Manager override required to confirm completion."
                        )
                    )
            rec.state = "confirmed"
            rec.job_id.write(
                {
                    "stage": "completion",
                    "actual_end_date": rec.completion_date,
                    "status": "in_progress",
                }
            )

    def action_print_handover(self):
        self.ensure_one()
        return self.env.ref("cpabooks_faff.action_report_faff_completion").report_action(
            self
        )

# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class FaffTesting(models.Model):
    _name = "cpabooks.faff.testing"
    _description = "FAFF Testing & Commissioning"
    _order = "testing_date desc, id desc"

    name = fields.Char(required=True, default="Testing & Commissioning")
    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    testing_date = fields.Date(default=fields.Date.context_today)
    tested_by_id = fields.Many2one("hr.employee", string="Tested By")
    system_status = fields.Selection(
        [
            ("passed", "Passed"),
            ("passed_remarks", "Passed with Remarks"),
            ("failed", "Failed"),
            ("rectification", "Rectification Required"),
        ],
        string="System Status",
        default="passed",
    )
    panel_tested = fields.Boolean()
    devices_tested = fields.Boolean()
    pump_tested = fields.Boolean()
    alarm_tested = fields.Boolean()
    cause_effect_tested = fields.Boolean(string="Cause & Effect Tested")
    emergency_light_tested = fields.Boolean()
    remarks = fields.Text()
    defects_found = fields.Text()
    rectification_required = fields.Boolean()
    test_report_ids = fields.Many2many(
        "ir.attachment",
        "faff_testing_report_rel",
        "testing_id",
        "attachment_id",
        string="Test Reports",
    )
    before_photo_ids = fields.Many2many(
        "ir.attachment",
        "faff_testing_before_rel",
        "testing_id",
        "attachment_id",
        string="Before Photos",
    )
    after_photo_ids = fields.Many2many(
        "ir.attachment",
        "faff_testing_after_rel",
        "testing_id",
        "attachment_id",
        string="After Photos",
    )
    rectification_task_id = fields.Many2one("project.task", string="Rectification Task")

    def action_create_rectification_task(self):
        self.ensure_one()
        job = self.job_id
        if not job.project_id:
            raise UserError(_("Create the project before adding a rectification task."))
        task = self.env["project.task"].create(
            {
                "name": _("Rectification — %s") % (job.name,),
                "project_id": job.project_id.id,
                "faff_job_id": job.id,
                "description": self.defects_found or self.remarks or "",
            }
        )
        self.rectification_task_id = task.id
        self.system_status = "rectification"
        self.rectification_required = True
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.task",
            "res_id": task.id,
            "view_mode": "form",
        }

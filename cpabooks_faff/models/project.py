# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    faff_job_id = fields.Many2one(
        "cpabooks.faff.job", string="FAFF Job", copy=False, index=True
    )


class ProjectTask(models.Model):
    _inherit = "project.task"

    faff_job_id = fields.Many2one(
        "cpabooks.faff.job", string="FAFF Job", copy=False, index=True
    )
    faff_engineer_id = fields.Many2one("hr.employee", string="Engineer")
    faff_hours = fields.Float(string="Working Hours")
    faff_remarks = fields.Text(string="FAFF Remarks")
    faff_photo_ids = fields.Many2many(
        "ir.attachment",
        "faff_task_photo_rel",
        "task_id",
        "attachment_id",
        string="Photos",
    )

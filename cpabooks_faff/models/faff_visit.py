# -*- coding: utf-8 -*-
from odoo import fields, models


class FaffVisit(models.Model):
    _name = "cpabooks.faff.visit"
    _description = "FAFF Site Visit / Inspection"
    _order = "inspection_date desc, id desc"

    name = fields.Char(required=True, default="Site Inspection")
    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    inspection_date = fields.Date(default=fields.Date.context_today)
    site_engineer_id = fields.Many2one("hr.employee", string="Site Engineer")
    site_contact = fields.Char(string="Site Contact")
    existing_system = fields.Char()
    existing_brand = fields.Char()
    panel_type = fields.Char()
    floor_count = fields.Integer(string="Number of Floors")
    device_count = fields.Integer(string="Number of Devices")
    problem_requirement = fields.Text(string="Problem / Requirement")
    observation = fields.Text()
    technical_recommendation = fields.Text()
    scope_summary = fields.Text()
    inspection_remarks = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "faff_visit_attachment_rel",
        "visit_id",
        "attachment_id",
        string="Photos / Attachments",
    )
    line_ids = fields.One2many(
        "cpabooks.faff.visit.line", "visit_id", string="Inspection Lines"
    )


class FaffVisitLine(models.Model):
    _name = "cpabooks.faff.visit.line"
    _description = "FAFF Inspection Line"

    visit_id = fields.Many2one(
        "cpabooks.faff.visit", required=True, ondelete="cascade"
    )
    name = fields.Char(string="Area / Item", required=True)
    observation = fields.Text()
    recommendation = fields.Text()

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FaffStageHistory(models.Model):
    _name = "cpabooks.faff.stage.history"
    _description = "FAFF Stage History"
    _order = "create_date desc, id desc"

    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    partner_id = fields.Many2one(
        related="job_id.partner_id", store=True, string="Customer"
    )
    job_type_id = fields.Many2one(
        related="job_id.job_type_id", store=True, string="Job Type"
    )
    salesperson_id = fields.Many2one(
        related="job_id.salesperson_id", store=True, string="Salesperson"
    )
    job_stage = fields.Selection(
        related="job_id.stage", store=True, string="Current Stage"
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    from_stage = fields.Char()
    to_stage = fields.Char(required=True)
    user_id = fields.Many2one("res.users", string="Changed By", required=True)
    change_date = fields.Datetime(default=fields.Datetime.now, string="Date / Time")
    report_date = fields.Date(compute="_compute_report_date", store=True, index=True)
    remarks = fields.Text()
    is_override = fields.Boolean(string="Manager Override")

    @api.depends("change_date")
    def _compute_report_date(self):
        for rec in self:
            rec.report_date = rec.change_date.date() if rec.change_date else False

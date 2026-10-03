# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CafmPpmSlot(models.Model):
    _name = "cpabooks.cafm.ppm.slot"
    _description = "PPM Planned Visit (Month)"
    _order = "year desc, month desc, ppm_id, id"

    name = fields.Char(compute="_compute_name", store=True)
    ppm_id = fields.Many2one("cpabooks.cafm.ppm", string="PPM Activity", required=True, ondelete="cascade")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company,
    )
    project_id = fields.Many2one("project.project", related="ppm_id.project_id", store=True, readonly=True)
    unit_id = fields.Many2one("cpabooks.cafm.unit", related="ppm_id.unit_id", store=True, readonly=True)
    year = fields.Integer(string="Year", required=True)
    month = fields.Integer(string="Month", required=True)
    state = fields.Selection(
        [
            ("planned", "Planned"),
            ("done", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="planned",
        required=True,
    )
    maintenance_request_id = fields.Many2one(
        "maintenance.request",
        string="Service Call",
        domain="[('ppm_id', '=', ppm_id)]",
    )
    note = fields.Char()

    _sql_constraints = [
        ("ppm_year_month_uniq", "unique(ppm_id, year, month)", "This month is already planned for this PPM line."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("ppm_id") and not vals.get("company_id"):
                ppm = self.env["cpabooks.cafm.ppm"].browse(vals["ppm_id"])
                vals["company_id"] = (
                    ppm.project_id.company_id.id if ppm.project_id.company_id else self.env.company.id
                )
        return super().create(vals_list)

    @api.depends("ppm_id", "year", "month")
    def _compute_name(self):
        for rec in self:
            if rec.ppm_id and rec.year and rec.month:
                rec.name = "%s %04d-%02d" % (rec.ppm_id.name, rec.year, rec.month)
            else:
                rec.name = _("PPM Slot")

    def action_mark_done(self):
        self.write({"state": "done"})

    def action_mark_planned(self):
        self.write({"state": "planned"})

    def action_create_request(self):
        self.ensure_one()
        if self.maintenance_request_id:
            return self.maintenance_request_id.get_formview_action()
        vals = {
            "name": _("%s — %04d-%02d") % (self.ppm_id.name, self.year, self.month),
            "ppm_id": self.ppm_id.id,
            "cafm_project_id": self.project_id.id,
            "cafm_unit_id": self.unit_id.id if self.unit_id else False,
        }
        req = self.env["maintenance.request"].create(vals)
        self.maintenance_request_id = req.id
        return req.get_formview_action()

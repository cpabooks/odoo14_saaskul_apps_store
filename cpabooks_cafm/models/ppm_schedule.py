# -*- coding: utf-8 -*-

from datetime import date

from dateutil.rrule import MONTHLY, rrule

from odoo import api, fields, models


class CafmPpmSchedule(models.Model):
    _name = 'cpabooks.cafm.ppm'
    _description = 'PPM Schedule'
    _order = 'next_due_date, id'

    name = fields.Char(required=True)
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade')
    unit_id = fields.Many2one('cpabooks.cafm.unit', string='Villa / Flat', domain="[('project_id', '=', project_id)]")
    frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('half_yearly', 'Half Yearly'),
        ('yearly', 'Yearly'),
    ], string='Frequency', default='quarterly', required=True)
    planning_mode = fields.Selection(
        [
            ("frequency", "By Frequency"),
            ("manual", "Manual Months"),
        ],
        string="Planning mode",
        default="frequency",
        required=True,
    )
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
    supervisor_id = fields.Many2one("res.users", string="Supervisor")
    slot_ids = fields.One2many("cpabooks.cafm.ppm.slot", "ppm_id", string="Monthly plan")
    slot_planned_count = fields.Integer(compute="_compute_slot_counts")
    slot_done_count = fields.Integer(compute="_compute_slot_counts")
    service_type = fields.Selection([
        ('hvac', 'HVAC'),
        ('electrical', 'Electrical'),
        ('plumbing', 'Plumbing'),
        ('civil', 'Civil'),
        ('cleaning', 'Cleaning'),
        ('fire_safety', 'Fire Safety'),
        ('lift', 'Lift'),
        ('general', 'General'),
    ], string='Service Type', default='general', required=True)
    start_date = fields.Date(required=True)
    next_due_date = fields.Date(required=True)
    end_date = fields.Date()
    annual_visits = fields.Integer(string='Annual Visits', compute='_compute_annual_visits', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('done', 'Done'),
        ('hold', 'On Hold'),
    ], default='active', required=True)
    note = fields.Text(string='Notes')
    request_ids = fields.One2many('maintenance.request', 'ppm_id', string='Service Calls')
    request_count = fields.Integer(compute='_compute_request_count')

    def _manual_month_fields(self):
        return [
            "manual_jan", "manual_feb", "manual_mar", "manual_apr",
            "manual_may", "manual_jun", "manual_jul", "manual_aug",
            "manual_sep", "manual_oct", "manual_nov", "manual_dec",
        ]

    def _months_from_manual(self):
        self.ensure_one()
        months = []
        for index, fname in enumerate(self._manual_month_fields(), start=1):
            if self[fname]:
                months.append(index)
        return months

    def _rrule_interval(self):
        self.ensure_one()
        return {
            "monthly": 1,
            "quarterly": 3,
            "half_yearly": 6,
            "yearly": 12,
        }.get(self.frequency, 1)

    def _months_for_year_from_frequency(self, year):
        self.ensure_one()
        start = self.start_date
        if not start:
            return []
        interval = self._rrule_interval()
        dt_start = start.replace(day=1)
        until = date(int(year), 12, 31)
        if dt_start > until:
            return []
        months = set()
        for dt in rrule(MONTHLY, interval=interval, dtstart=dt_start, until=until):
            if dt.year == int(year):
                months.add(dt.month)
        return sorted(months)

    def get_months_for_year(self, year):
        self.ensure_one()
        if self.planning_mode == "manual":
            months = self._months_from_manual()
            if not months:
                return self._months_for_year_from_frequency(year)
            return months
        return self._months_for_year_from_frequency(year)

    def action_regenerate_slots(self, year, replace=True):
        year = int(year)
        Slot = self.env["cpabooks.cafm.ppm.slot"].sudo()
        for rec in self:
            if replace:
                Slot.search([("ppm_id", "=", rec.id), ("year", "=", year)]).unlink()
            months = rec.get_months_for_year(year)
            for m in months:
                Slot.create({
                    "ppm_id": rec.id,
                    "year": year,
                    "month": m,
                    "state": "planned",
                })

    @api.depends("slot_ids", "slot_ids.state")
    def _compute_slot_counts(self):
        for rec in self:
            rec.slot_planned_count = len(rec.slot_ids.filtered(lambda s: s.state == "planned"))
            rec.slot_done_count = len(rec.slot_ids.filtered(lambda s: s.state == "done"))

    @api.depends('frequency', 'planning_mode',
                 'manual_jan', 'manual_feb', 'manual_mar', 'manual_apr',
                 'manual_may', 'manual_jun', 'manual_jul', 'manual_aug',
                 'manual_sep', 'manual_oct', 'manual_nov', 'manual_dec')
    def _compute_annual_visits(self):
        mapping = {
            'monthly': 12,
            'quarterly': 4,
            'half_yearly': 2,
            'yearly': 1,
        }
        for rec in self:
            if rec.planning_mode == "manual":
                rec.annual_visits = len(rec._months_from_manual()) or mapping.get(rec.frequency, 0)
            else:
                rec.annual_visits = mapping.get(rec.frequency, 0)

    @api.depends('request_ids')
    def _compute_request_count(self):
        for rec in self:
            rec.request_count = len(rec.request_ids)

    def action_open_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Project',
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_unit(self):
        self.ensure_one()
        if not self.unit_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Villa / Flat',
            'res_model': 'cpabooks.cafm.unit',
            'res_id': self.unit_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Calls',
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('ppm_id', '=', self.id)],
            'context': {'default_ppm_id': self.id, 'default_cafm_project_id': self.project_id.id, 'default_cafm_unit_id': self.unit_id.id},
            'target': 'current',
        }

    def action_view_slots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'PPM Month Slots',
            'res_model': 'cpabooks.cafm.ppm.slot',
            'view_mode': 'tree,form',
            'domain': [('ppm_id', '=', self.id)],
            'context': {'default_ppm_id': self.id},
            'target': 'current',
        }

    def action_generate_slots_current_year(self):
        year = fields.Date.context_today(self).year
        self.action_regenerate_slots(year, replace=True)
        return True

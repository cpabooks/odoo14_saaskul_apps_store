# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    fsm_time_in = fields.Float(
        string='In',
        help='Check-in time (24-hour format, e.g. 08:30).',
    )
    fsm_time_out = fields.Float(
        string='Out',
        help='Check-out time (24-hour format, e.g. 17:30).',
    )
    fsm_employee_timesheet_cost = fields.Monetary(
        string='Timesheet Cost',
        currency_field='currency_id',
        compute='_compute_fsm_employee_timesheet_cost',
        compute_sudo=True,
        store=True,
        readonly=False,
    )
    fsm_cost_amount = fields.Monetary(
        string='Timesheet Amount',
        currency_field='currency_id',
        compute='_compute_fsm_cost_amount',
        compute_sudo=True,
        store=True,
    )

    def _get_employee_timesheet_cost(self):
        self.ensure_one()
        if self.employee_id and 'timesheet_cost' in self.employee_id._fields:
            return self.employee_id.timesheet_cost or 0.0
        return 0.0

    @api.depends('employee_id', 'employee_id.timesheet_cost')
    def _compute_fsm_employee_timesheet_cost(self):
        for line in self:
            line.fsm_employee_timesheet_cost = line._get_employee_timesheet_cost()

    def _get_fsm_cost_amount(self):
        self.ensure_one()
        if self.employee_id:
            return abs(self.unit_amount or 0.0) * (self.fsm_employee_timesheet_cost or 0.0)
        if self.amount:
            return abs(self.amount)
        return 0.0

    @api.depends('amount', 'unit_amount', 'employee_id', 'fsm_employee_timesheet_cost')
    def _compute_fsm_cost_amount(self):
        for line in self:
            line.fsm_cost_amount = line._get_fsm_cost_amount()

    def _fsm_duration_from_in_out(self, time_in=None, time_out=None):
        """Return hours between in/out floats (24h). Overnight shifts add 24h."""
        tin = time_in if time_in is not None else self.fsm_time_in
        tout = time_out if time_out is not None else self.fsm_time_out
        if tin is False or tin is None or tout is False or tout is None:
            return None
        diff = tout - tin
        if diff < 0:
            diff += 24.0
        return diff

    @api.onchange('fsm_time_in', 'fsm_time_out')
    def _onchange_fsm_time_in_out(self):
        for line in self:
            duration = line._fsm_duration_from_in_out()
            if duration is not None:
                line.unit_amount = duration

    def _fsm_prepare_time_duration_vals(self, vals):
        vals = dict(vals)
        tin = vals.get('fsm_time_in')
        tout = vals.get('fsm_time_out')
        if self and len(self) == 1:
            if tin is None and 'fsm_time_in' not in vals:
                tin = self.fsm_time_in
            if tout is None and 'fsm_time_out' not in vals:
                tout = self.fsm_time_out
        if (
            tin is not None
            and tout is not None
            and ('fsm_time_in' in vals or 'fsm_time_out' in vals)
        ):
            diff = tout - tin
            if diff < 0:
                diff += 24.0
            vals['unit_amount'] = diff
        return vals

    @api.onchange('employee_id')
    def _onchange_fsm_employee_timesheet_cost(self):
        for line in self:
            line.fsm_employee_timesheet_cost = line._get_employee_timesheet_cost()
            line.fsm_cost_amount = line._get_fsm_cost_amount()

    @api.onchange('amount', 'unit_amount', 'employee_id', 'fsm_employee_timesheet_cost')
    def _onchange_fsm_cost_amount(self):
        for line in self:
            line.fsm_cost_amount = line._get_fsm_cost_amount()

    @api.model
    def _prepare_task_project_vals(self, vals):
        vals = dict(vals)
        task_id = vals.get('task_id')
        if not task_id:
            return vals
        task = self.env['project.task'].browse(task_id)
        if task.exists():
            if task.project_id:
                vals['project_id'] = task.project_id.id
            if (
                task.analytic_account_id
                and 'account_id' in self._fields
                and not vals.get('account_id')
            ):
                vals['account_id'] = task.analytic_account_id.id
            if 'company_id' in self._fields and task.company_id:
                vals['company_id'] = task.company_id.id
        return vals

    @api.onchange('task_id')
    def _onchange_task_id_sync_project(self):
        if self.task_id:
            self.project_id = self.task_id.project_id
            if 'company_id' in self._fields and self.task_id.company_id:
                self.company_id = self.task_id.company_id

    @api.onchange('employee_id', 'project_id', 'task_id')
    def _onchange_keep_task_project_consistent(self):
        if self.task_id and self.project_id != self.task_id.project_id:
            self.project_id = self.task_id.project_id

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        task_id = self.env.context.get('default_task_id') or vals.get('task_id')
        if task_id:
            vals = self._prepare_task_project_vals(dict(vals, task_id=task_id))
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = self._prepare_task_project_vals(vals)
            vals = self._fsm_prepare_time_duration_vals(vals)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = self._prepare_task_project_vals(vals)
        if len(self) == 1:
            vals = self._fsm_prepare_time_duration_vals(vals)
        return super().write(vals)

    @api.model
    def action_recompute_fsm_cost_amounts(self):
        lines = self.sudo().search([('task_id', '!=', False)])
        lines._compute_fsm_cost_amount()
        tasks = lines.mapped('task_id').with_context(skip_project_planning_sync=True)
        tasks._compute_timesheet_cost_total()
        tasks._compute_total_service_cost()
        return True

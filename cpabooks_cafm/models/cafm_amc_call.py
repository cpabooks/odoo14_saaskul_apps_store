# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, fields, models, _


class MaintenanceRequestAmcCall(models.Model):
    _inherit = 'maintenance.request'

    call_no = fields.Char(string='Call No.', copy=False, index=True, readonly=True)
    call_no_tally = fields.Char(string='Call No. (Tally)', copy=False)
    call_type = fields.Selection([
        ('amc', 'AMC Call'),
        ('var', 'VAR Call'),
        ('ppm', 'PPM Call'),
    ], string='Call Type', default='amc')
    call_date = fields.Datetime(string='Call Date', default=fields.Datetime.now, tracking=True)
    call_date_weekday = fields.Char(string='Weekday', compute='_compute_call_date_weekday', store=True)

    l2_level_id = fields.Many2one('cpabooks.cafm.customer.group', string='L2 Level')
    l1_level_id = fields.Many2one('project.project', string='L1 Level')
    contract_id = fields.Many2one('cpabooks.cafm.contract', string='AMC Contract')
    contract_expiry = fields.Date(related='contract_id.contract_expiry', string='Contract Expiry', readonly=True)
    contract_no = fields.Char(related='contract_id.name', string='Contract No.', readonly=True)
    contact_name = fields.Char(string='Contact Name')
    contact_no = fields.Char(string='Contact No.')
    tenant_name = fields.Char(string='Tenant Name')

    job_type_id = fields.Many2one('cpabooks.cafm.job.type', string='Type of Job')
    work_type_id = fields.Many2one('cpabooks.cafm.work.type', string='Type of Work')
    problem_reported_id = fields.Many2one('cpabooks.cafm.problem.reported', string='Problem Reported')
    problem_description = fields.Text(string='Problem Description')
    priority_id = fields.Many2one('cpabooks.cafm.priority', string='Priority')
    technician_id = fields.Many2one('cpabooks.cafm.technician', string='Technician')
    client_manager_id = fields.Many2one('cpabooks.cafm.client.manager', string='Client Manager')
    required_materials = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Required Materials', default='no')
    cafm_remark = fields.Text(string='Remark')
    work_status = fields.Selection([
        ('pending', 'Pending'),
        ('work_ongoing', 'Work Ongoing'),
        ('waiting_lpo', 'Waiting LPO'),
        ('waiting_report', 'Waiting Report Completion'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Work Status', default='pending', tracking=True)
    work_completion_date = fields.Date(string='Work Completion Date')
    work_report_no = fields.Char(string='Work Report No.')
    invoice_id = fields.Many2one('account.move', string='Invoice', domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]")
    invoice_details = fields.Char(string='Invoice Details', compute='_compute_invoice_details', store=True)
    duration_days = fields.Integer(string='Duration (days)', compute='_compute_duration_days', store=True)
    var_work_ids = fields.One2many('cpabooks.cafm.var.work', 'call_id', string='VAR Works')
    stock_issue_ids = fields.One2many('cpabooks.cafm.stock.issue', 'call_id', string='Stock Issues')
    var_work_count = fields.Integer(compute='_compute_var_work_count')
    stock_issue_count = fields.Integer(compute='_compute_stock_issue_count')

    @api.depends('call_date')
    def _compute_call_date_weekday(self):
        for rec in self:
            if rec.call_date:
                rec.call_date_weekday = rec.call_date.strftime('%A')
            else:
                rec.call_date_weekday = False

    @api.depends('invoice_id', 'invoice_id.name', 'invoice_id.amount_total')
    def _compute_invoice_details(self):
        for rec in self:
            if rec.invoice_id:
                rec.invoice_details = '%s — %s' % (rec.invoice_id.name or '', rec.invoice_id.amount_total)
            else:
                rec.invoice_details = False

    @api.depends('call_date', 'work_completion_date')
    def _compute_duration_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            start = rec.call_date.date() if rec.call_date else today
            end = rec.work_completion_date or today
            rec.duration_days = max((end - start).days, 0)

    @api.depends('var_work_ids')
    def _compute_var_work_count(self):
        for rec in self:
            rec.var_work_count = len(rec.var_work_ids)

    @api.depends('stock_issue_ids')
    def _compute_stock_issue_count(self):
        for rec in self:
            rec.stock_issue_count = len(rec.stock_issue_ids)

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        contract = self.contract_id
        if not contract:
            return
        self.partner_id = contract.client_id
        self.l2_level_id = contract.customer_group_id
        self.l1_level_id = contract.project_id
        self.cafm_project_id = contract.project_id
        self.cafm_unit_id = contract.unit_id
        self.contact_name = contract.contact_person_id.name if contract.contact_person_id else False
        self.contact_no = contract.contact_no
        self.client_manager_id = self._map_user_to_client_manager(contract.client_manager_id)

    @api.onchange('cafm_unit_id')
    def _onchange_cafm_unit_id_amc(self):
        if self.cafm_unit_id:
            self.flat = self.cafm_unit_id.name
            if self.cafm_unit_id.tenant_partner_id:
                self.tenant_name = self.cafm_unit_id.tenant_partner_id.name

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        if self.work_type_id:
            self.work_type = self.work_type_id.name

    @api.onchange('problem_reported_id')
    def _onchange_problem_reported_id(self):
        if self.problem_reported_id:
            self.problem = self.problem_reported_id.name
            if not self.problem_description:
                self.problem_description = self.problem_reported_id.name

    @api.onchange('partner_id', 'cafm_project_id')
    def _onchange_partner_project_contract(self):
        if self.contract_id:
            return
        domain = []
        if self.partner_id:
            domain.append(('client_id', '=', self.partner_id.id))
        if self.cafm_project_id:
            domain.append(('project_id', '=', self.cafm_project_id.id))
        if not domain:
            return
        contract = self.env['cpabooks.cafm.contract'].search(domain, limit=1, order='contract_expiry desc')
        if contract:
            self.contract_id = contract

    def _map_user_to_client_manager(self, user):
        if not user:
            return False
        Manager = self.env['cpabooks.cafm.client.manager']
        manager = Manager.search([('user_id', '=', user.id)], limit=1)
        if manager:
            return manager
        return Manager.create({'name': user.name, 'user_id': user.id}).id

    @api.model
    def _generate_call_no(self):
        seq = self.env['ir.sequence'].next_by_code('cpabooks.cafm.amc.call') or '00001'
        year_suffix = datetime.now().strftime('%y')
        return '%sG%sA' % (year_suffix, seq)

    @api.model
    def create(self, vals):
        if vals.get('cafm_unit_id') and not vals.get('cafm_project_id'):
            unit = self.env['cpabooks.cafm.unit'].browse(vals['cafm_unit_id'])
            vals['cafm_project_id'] = unit.project_id.id
        if not vals.get('call_no'):
            vals['call_no'] = self._generate_call_no()
        if not vals.get('ticket_no'):
            vals['ticket_no'] = vals['call_no']
        if not vals.get('name') or vals.get('name') == '/':
            vals['name'] = vals['call_no']
        res = super().create(vals)
        if not res.ticket_no:
            res.ticket_no = res.call_no
        return res

    def action_open_var_works(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('VAR Work'),
            'res_model': 'cpabooks.cafm.var.work',
            'view_mode': 'tree,form',
            'domain': [('call_id', '=', self.id)],
            'context': {'default_call_id': self.id},
        }

    def action_open_stock_issues(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Issues'),
            'res_model': 'cpabooks.cafm.stock.issue',
            'view_mode': 'tree,form',
            'domain': [('call_id', '=', self.id)],
            'context': {'default_call_id': self.id},
        }

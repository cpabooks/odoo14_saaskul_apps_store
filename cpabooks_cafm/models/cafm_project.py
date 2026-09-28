# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    cafm_code = fields.Char(string='Project Code', copy=False)
    cafm_location = fields.Char(string='Location')
    cafm_service_partner_id = fields.Many2one('res.partner', string='Managed By')
    cafm_contract_detail = fields.Text(string='Contract Detail')
    cafm_unit_ids = fields.One2many('cpabooks.cafm.unit', 'project_id', string='Units')
    cafm_amc_ids = fields.One2many('cpabooks.cafm.contract', 'project_id', string='AMC Contracts')
    cafm_ppm_ids = fields.One2many('cpabooks.cafm.ppm', 'project_id', string='PPM Activities')
    cafm_request_ids = fields.One2many('maintenance.request', 'cafm_project_id', string='Service Calls')
    cafm_unit_count = fields.Integer(string='Units', compute='_compute_cafm_metrics')
    cafm_contract_count = fields.Integer(string='AMC Contracts', compute='_compute_cafm_metrics')
    cafm_ppm_count = fields.Integer(string='PPM Activities', compute='_compute_cafm_metrics')
    cafm_ticket_count = fields.Integer(string='Service Calls', compute='_compute_cafm_metrics')
    cafm_yearly_value = fields.Float(string='Yearly Contract Value', compute='_compute_cafm_metrics')
    cafm_monthly_value = fields.Float(string='Monthly Revenue', compute='_compute_cafm_metrics')

    @api.depends('cafm_unit_ids', 'cafm_amc_ids.yearly_contract_amount', 'cafm_amc_ids.monthly_revenue', 'cafm_ppm_ids', 'cafm_request_ids')
    def _compute_cafm_metrics(self):
        amc_model = self.env['cpabooks.cafm.contract']
        for project in self:
            project_level_amcs = amc_model.search([('project_id', '=', project.id)])
            project.cafm_unit_count = len(project.cafm_unit_ids)
            project.cafm_contract_count = len(project_level_amcs)
            project.cafm_ppm_count = len(project.cafm_ppm_ids)
            project.cafm_ticket_count = len(project.cafm_request_ids)
            project.cafm_yearly_value = sum(project_level_amcs.mapped('yearly_contract_amount'))
            project.cafm_monthly_value = sum(project_level_amcs.mapped('monthly_revenue'))

    def action_view_cafm_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Units',
            'res_model': 'cpabooks.cafm.unit',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
            'target': 'current',
        }

    def action_view_cafm_amc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'AMC Register',
            'res_model': 'cpabooks.cafm.contract',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
            'target': 'current',
        }

    def action_view_cafm_ppm(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'PPM Schedule',
            'res_model': 'cpabooks.cafm.ppm',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
            'target': 'current',
        }

    def action_view_cafm_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Calls',
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('cafm_project_id', '=', self.id)],
            'context': {'default_cafm_project_id': self.id},
            'target': 'current',
        }

    @api.model
    def get_cafm_dashboard_data(self):
        return self.env['cafm.dashboard'].get_dashboard_data()

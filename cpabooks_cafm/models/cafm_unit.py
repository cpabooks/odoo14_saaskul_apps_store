# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CafmUnit(models.Model):
    _name = 'cpabooks.cafm.unit'
    _description = 'CAFM Unit'
    _order = 'project_id, parent_path, code, id'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'display_name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    parent_id = fields.Many2one('cpabooks.cafm.unit', string='Parent Unit', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('cpabooks.cafm.unit', 'parent_id', string='Child Units')
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade')
    unit_type = fields.Selection([
        ('villa_group', 'Villa / Flat Group'),
        ('villa', 'Villa'),
        ('flat', 'Flat'),
        ('common', 'Common Area'),
    ], string='Unit Type', default='flat', required=True)
    owner_id = fields.Many2one('res.partner', string='Owner')
    tenant_partner_id = fields.Many2one('res.partner', string='Tenant / Occupant')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')
    amc_ids = fields.One2many('cpabooks.cafm.contract', 'unit_id', string='AMC Contracts')
    ppm_ids = fields.One2many('cpabooks.cafm.ppm', 'unit_id', string='PPM Activities')
    request_ids = fields.One2many('maintenance.request', 'cafm_unit_id', string='Service Calls')
    child_count = fields.Integer(compute='_compute_totals')
    amc_count = fields.Integer(compute='_compute_totals')
    ppm_count = fields.Integer(compute='_compute_totals')
    request_count = fields.Integer(compute='_compute_totals')
    yearly_value = fields.Float(string='Yearly Value', compute='_compute_totals')
    monthly_value = fields.Float(string='Monthly Value', compute='_compute_totals')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '[%s] %s' % (rec.code or '', rec.name or '')

    @api.depends('amc_ids.yearly_contract_amount', 'amc_ids.monthly_revenue', 'ppm_ids', 'request_ids')
    def _compute_totals(self):
        for rec in self:
            rec.child_count = len(rec.child_ids)
            rec.amc_count = len(rec.amc_ids)
            rec.ppm_count = len(rec.ppm_ids)
            rec.request_count = len(rec.request_ids)
            rec.yearly_value = sum(rec.amc_ids.mapped('yearly_contract_amount'))
            rec.monthly_value = sum(rec.amc_ids.mapped('monthly_revenue'))

    def action_view_child_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Child Units',
            'res_model': 'cpabooks.cafm.unit',
            'view_mode': 'tree,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_project_id': self.project_id.id, 'default_parent_id': self.id},
            'target': 'current',
        }

    def action_view_unit_amc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'AMC Register',
            'res_model': 'cpabooks.cafm.contract',
            'view_mode': 'tree,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_project_id': self.project_id.id, 'default_unit_id': self.id},
            'target': 'current',
        }

    def action_view_unit_ppm(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'PPM Schedule',
            'res_model': 'cpabooks.cafm.ppm',
            'view_mode': 'tree,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_project_id': self.project_id.id, 'default_unit_id': self.id},
            'target': 'current',
        }

    def action_view_unit_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Calls',
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('cafm_unit_id', '=', self.id)],
            'context': {'default_cafm_project_id': self.project_id.id, 'default_cafm_unit_id': self.id},
            'target': 'current',
        }

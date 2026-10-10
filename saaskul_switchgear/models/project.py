# -*- coding: utf-8 -*-


from odoo import models, fields


class ProjectProject(models.Model):
    _inherit = 'project.project'

    estimate_ids = fields.One2many('job.estimate', 'project_id', string='Estimations', copy=False)
    estimate_count = fields.Integer(string='# of Estimations', compute='_compute_all_count')
    bom_ids = fields.One2many('mrp.bom', 'project_id', string='BoMs', copy=False)
    bom_count = fields.Integer(string='# of BoMs', compute='_compute_all_count')
    mo_ids = fields.One2many('mrp.production', 'project_id', string='Manufacturing Orders', copy=False)
    mo_count = fields.Integer(string='# of Manufacturing Orders', compute='_compute_all_count')
    qc_ids = fields.One2many('quality.check', 'project_id', string='Quality Checks', copy=False)
    qc_count = fields.Integer(string='# of Quality Checks', compute='_compute_all_count')

    def _compute_all_count(self):
        for record in self:
            record.estimate_count = len(record.estimate_ids)
            record.bom_count = len(record.bom_ids)
            record.mo_count = len(record.mo_ids)
            record.qc_count = len(record.qc_ids)

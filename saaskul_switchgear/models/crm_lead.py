# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    enquiry_number = fields.Char(string='Enquiry Number', readonly=True, copy=False, default=lambda self: _('New'))
    project_id = fields.Many2one('project.project', string='Job Order', copy=False)
    estimation_count = fields.Integer(compute='_compute_estimation_count', string='No of Estimations')
    job_estimate_ids = fields.One2many('switchgear.estimate', 'opportunity_id', string='Estimations')
    bypass_estimation = fields.Boolean(
        string="Bypass Estimation",
        default=False,
        help="When enabled, use quick quotation flow instead of job estimates.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('enquiry_number', _('New')) == _('New'):
                vals['enquiry_number'] = self.env['ir.sequence'].next_by_code('switchgear.crm.enquiry') or _('New')
        return super().create(vals_list)

    @api.depends('job_estimate_ids')
    def _compute_estimation_count(self):
        for lead in self:
            lead.estimation_count = len(lead.job_estimate_ids)

    def button_new_estimation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("saaskul_switchgear.action_new_estimation")
        action['context'] = {
            'search_default_opportunity_id': self.id,
            'default_opportunity_id': self.id,
            'default_partner_id': self.partner_id.id,
        }
        return action

    def action_view_estimation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("saaskul_switchgear.action_job_estimate")
        action['context'] = {
            'default_opportunity_id': self.id,
            'default_partner_id': self.partner_id.id,
        }
        action['domain'] = [('opportunity_id', '=', self.id)]
        if len(self.job_estimate_ids) == 1:
            action['views'] = [(self.env.ref('saaskul_switchgear.job_estimate_form_view').id, 'form')]
            action['res_id'] = self.job_estimate_ids.id
        return action

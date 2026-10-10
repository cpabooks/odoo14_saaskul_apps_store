# -*- coding: utf-8 -*-

from odoo import api, fields, models


#
# class CustomCrmLead(models.Model):
#     _name = 'custom.crm.lead'
#     _description = 'Custom CRM Lead'
#     _inherit = 'crm.lead'
#
#     _order = 'id desc'

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    estimation_count = fields.Integer(compute='_compute_estimation_count', string='No of Estimations')
    job_estimate_ids = fields.One2many('job.estimate', 'opportunity_id', string='Estimations')
    bypass_estimation = fields.Boolean(
        string="Bypass Estimation",
        default=False,
        help="When enabled, use quick quotation flow instead of job estimates.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # cpabooks_crm_extend defaults bypass_estimation=True; switchgear needs estimates.
        res['bypass_estimation'] = False
        return res


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
        action = self.env["ir.actions.actions"]._for_xml_id("cost_estimate_customer_ld.action_job_estimate")
        action['context'] = {
            'default_opportunity_id': self.id
        }
        action['domain'] = [('opportunity_id', '=', self.id)]
        job_estimate_id = self.mapped('job_estimate_ids')
        if len(job_estimate_id) == 1:
            action['views'] = [(self.env.ref('cost_estimate_customer_ld.job_estimate_form_view').id, 'form')]
            action['res_id'] = job_estimate_id.id
        return action

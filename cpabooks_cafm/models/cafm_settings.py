# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cafm_default_priority_id = fields.Many2one('cpabooks.cafm.priority', string='Default Call Priority')
    cafm_company_title = fields.Char(
        string='CAFM Screen Title',
        help='Shown on Tally-style CAFM screens, e.g. CAFM - Green City - 2024 - 2026',
    )
    cafm_enable_department_security = fields.Boolean(string='Enable Department Security')

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        priority = icp.get_param('cpabooks_cafm.default_priority_id')
        res.update(
            cafm_default_priority_id=int(priority) if priority else False,
            cafm_company_title=icp.get_param('cpabooks_cafm.company_title') or '',
            cafm_enable_department_security=icp.get_param('cpabooks_cafm.enable_department_security') == 'True',
        )
        return res

    def set_values(self):
        super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('cpabooks_cafm.default_priority_id', self.cafm_default_priority_id.id or '')
        icp.set_param('cpabooks_cafm.company_title', self.cafm_company_title or '')
        icp.set_param('cpabooks_cafm.enable_department_security', self.cafm_enable_department_security)

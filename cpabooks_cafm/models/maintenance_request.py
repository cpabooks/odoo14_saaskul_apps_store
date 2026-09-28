from odoo import api, models, fields, _


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    tenant_id = fields.Many2one('maintenance.tenant', 'Tenant')
    building = fields.Char('Building')
    flat = fields.Char('Flat')
    work_type = fields.Char('Work Type')
    problem = fields.Char('Problem')
    property = fields.Char('Property')
    address = fields.Char('Address')
    partner_id = fields.Many2one('res.partner', 'Customer')
    project_id = fields.Many2one('project.project', "Legacy Project")
    cafm_project_id = fields.Many2one('project.project', string='CAFM Project')
    cafm_unit_id = fields.Many2one(
        'cpabooks.cafm.unit',
        string='Villa / Flat',
        domain="[('project_id', '=', cafm_project_id)]",
    )
    ppm_id = fields.Many2one('cpabooks.cafm.ppm', string='PPM Activity')
    city = fields.Char("City/Region")
    task_id = fields.Many2one("project.task", "Legacy Flat/Villa No.")
    ticket_no = fields.Char('Ticket No.')

    @api.onchange('cafm_unit_id')
    def _onchange_cafm_unit_id(self):
        if self.cafm_unit_id:
            self.cafm_project_id = self.cafm_unit_id.project_id
            self.flat = self.cafm_unit_id.name
            self.building = self.cafm_unit_id.project_id.name

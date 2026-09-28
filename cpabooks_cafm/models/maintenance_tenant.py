from odoo import api, fields, models


class MaintenanceTenant(models.Model):
    _name = 'maintenance.tenant'
    _description = 'Maintenance Tenant'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    email = fields.Char('Email')
    mobile = fields.Char('Mobile')
    partner_id = fields.Many2one('res.partner', string='Contact')
    project_id = fields.Many2one('project.project', string='Project')
    cafm_unit_id = fields.Many2one('cpabooks.cafm.unit', string='Villa / Flat', domain="[('project_id', '=', project_id)]")

    @api.model
    def create(self, vals):
        if not vals.get('partner_id'):
            partner = self.env['res.partner']
            if vals.get('email'):
                partner = partner.search([('email', '=', vals.get('email'))], limit=1)
            if not partner and vals.get('mobile'):
                partner = self.env['res.partner'].search([('mobile', '=', vals.get('mobile'))], limit=1)
            if not partner:
                partner = self.env['res.partner'].search([('name', '=', vals.get('name'))], limit=1)
            if partner:
                partner.write({
                    'name': vals.get('name'),
                    'email': vals.get('email'),
                    'mobile': vals.get('mobile'),
                })
            else:
                partner = self.env['res.partner'].create({
                    'name': vals.get('name'),
                    'email': vals.get('email'),
                    'mobile': vals.get('mobile'),
                })
            vals['partner_id'] = partner.id
        return super().create(vals)

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                rec.partner_id.write({
                    'name': rec.name,
                    'email': rec.email,
                    'mobile': rec.mobile,
                })
        return res

from odoo import api, models, fields, _

class SiteLocation(models.Model):
    _name = 'site.location'
    _description = 'Contact Person'

    name = fields.Char(string='Location', required=True)
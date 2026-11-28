from odoo import api, models, fields, _

class ComplaintList(models.Model):
    _name = 'contact.person'
    _description = 'Contact Person'

    name = fields.Char(string='Contact Person', required=True)
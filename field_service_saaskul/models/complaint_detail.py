from odoo import api, models, fields, _

class ComplaintList(models.Model):
    _name = 'complaint.detail'
    _description = 'Complaint Title'

    name = fields.Char(required=True)

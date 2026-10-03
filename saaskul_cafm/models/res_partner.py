# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    style = fields.Char(string='Style')
    delivery_instructions = fields.Text(string='Delivery Instructions')

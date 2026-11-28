# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class re_sequences_saaskul(models.Model):
#     _name = 're_sequences_saaskul.re_sequences_saaskul'
#     _description = 're_sequences_saaskul.re_sequences_saaskul'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

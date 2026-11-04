# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class chart_of_accounts_saaskul(models.Model):
#     _name = 'chart_of_accounts_saaskul.chart_of_accounts_saaskul'
#     _description = 'chart_of_accounts_saaskul.chart_of_accounts_saaskul'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

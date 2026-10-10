# -*- coding: utf-8 -*-
from odoo import fields, models


class InvoiceType(models.Model):
    _name = 'invoice.type'
    _description = 'Invoice Type'

    name = fields.Char(string='Invoice Type', required=True)


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_type = fields.Many2one('invoice.type', string='Invoice Type')
    project_id = fields.Many2one('project.project', string='Project / Job')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    guaranteed = fields.Boolean(string="Guaranteed", default=False)

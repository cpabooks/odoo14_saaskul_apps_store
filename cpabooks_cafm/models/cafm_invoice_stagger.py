# -*- coding: utf-8 -*-

from odoo import fields, models


class CafmInvoiceStagger(models.Model):
    _name = 'cpabooks.cafm.invoice.stagger'
    _description = 'CAFM AMC Invoice Schedule'
    _order = 'contract_id, sequence, invoice_date, id'

    contract_id = fields.Many2one(
        'cpabooks.cafm.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Stagger', required=True)
    sequence = fields.Integer(default=10)
    period_label = fields.Char(string='Period')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    invoice_date = fields.Date(string='Invoice Date')
    amount = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='contract_id.currency_id', store=True, readonly=True)
    company_id = fields.Many2one('res.company', related='contract_id.company_id', store=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('invoiced', 'Invoiced'),
        ('paid', 'Paid'),
    ], default='draft', required=True)
    remarks = fields.Text()

# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class CafmStockIssue(models.Model):
    _name = 'cpabooks.cafm.stock.issue'
    _description = 'CAFM Stock Issue'
    _inherit = ['mail.thread']
    _order = 'issue_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', copy=False, readonly=True, default=lambda self: _('New'))
    issue_type = fields.Selection([
        ('amc', 'AMC Stock Issue'),
        ('var', 'VAR Stock Issue'),
        ('transfer', 'Stock Transfer'),
        ('receipt', 'Stock Receipt'),
    ], string='Type', required=True, default='amc')
    issue_date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    call_id = fields.Many2one('maintenance.request', string='Call No.', ondelete='set null', index=True)
    call_no = fields.Char(related='call_id.call_no', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Party Name')
    cafm_unit_id = fields.Many2one('cpabooks.cafm.unit', string='Flat / Villa')
    flat_villa = fields.Char(string='Flat / Villa')
    technician_id = fields.Many2one('cpabooks.cafm.technician', string='Technician')
    warehouse = fields.Char(string='Store / Warehouse')
    remark = fields.Text(string='Remarks')
    line_ids = fields.One2many('cpabooks.cafm.stock.issue.line', 'issue_id', string='Items')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft')

    @api.onchange('call_id')
    def _onchange_call_id(self):
        call = self.call_id
        if not call:
            return
        self.partner_id = call.partner_id
        self.cafm_unit_id = call.cafm_unit_id
        self.flat_villa = call.flat or (call.cafm_unit_id.name if call.cafm_unit_id else False)
        self.technician_id = call.technician_id

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            code = {
                'amc': 'cpabooks.cafm.stock.issue.amc',
                'var': 'cpabooks.cafm.stock.issue.var',
                'transfer': 'cpabooks.cafm.stock.transfer',
                'receipt': 'cpabooks.cafm.stock.receipt',
            }.get(vals.get('issue_type'), 'cpabooks.cafm.stock.issue.amc')
            vals['name'] = self.env['ir.sequence'].next_by_code(code) or _('New')
        return super().create(vals)


class CafmStockIssueLine(models.Model):
    _name = 'cpabooks.cafm.stock.issue.line'
    _description = 'CAFM Stock Issue Line'
    _order = 'sequence, id'

    issue_id = fields.Many2one('cpabooks.cafm.stock.issue', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    item_name = fields.Char(string='Item', required=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    uom = fields.Char(string='Unit', default='Nos')
    remark = fields.Char(string='Line Remark')

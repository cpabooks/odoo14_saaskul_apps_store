# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SwitchgearDesignDocument(models.Model):
    _name = 'switchgear.design.document'
    _description = 'Design Document Register'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='/')
    date = fields.Date(string='Date', default=fields.Date.context_today, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    project_id = fields.Many2one('project.project', string='Job Order')
    sale_order_id = fields.Many2one('sale.order', string='Quotation')
    job_estimate_id = fields.Many2one('job.estimate', string='Estimation')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
    )
    notes = fields.Text(string='Notes')
    sent_line_ids = fields.One2many(
        'switchgear.design.document.sent.line',
        'register_id',
        string='Documents Sent',
        copy=True,
    )
    received_line_ids = fields.One2many(
        'switchgear.design.document.received.line',
        'register_id',
        string='Documents Received',
        copy=True,
    )
    sent_count = fields.Integer(compute='_compute_counts')
    received_count = fields.Integer(compute='_compute_counts')
    attachment_count = fields.Integer(compute='_compute_counts')

    @api.depends('sent_line_ids', 'received_line_ids')
    def _compute_counts(self):
        for rec in self:
            rec.sent_count = len(rec.sent_line_ids)
            rec.received_count = len(rec.received_line_ids)
            rec.attachment_count = sum(
                1 for line in rec.sent_line_ids if line.attachment
            ) + sum(
                1 for line in rec.received_line_ids if line.attachment
            )

    @api.model
    def create(self, vals):
        if vals.get('name', '/') in (False, '/'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'switchgear.design.document',
            ) or '/'
        return super().create(vals)


class SwitchgearDesignDocumentSentLine(models.Model):
    _name = 'switchgear.design.document.sent.line'
    _description = 'Design Document Sent Line'
    _order = 'sr, id'

    register_id = fields.Many2one(
        'switchgear.design.document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sr = fields.Integer(string='SR')
    document_name = fields.Char(string='Document Sent Name', required=True)
    remarks = fields.Char(string='Remarks')
    attachment = fields.Binary(string='Attachment', attachment=True)
    attachment_name = fields.Char(string='File Name')
    date_sent = fields.Date(string='Date Sent', default=fields.Date.context_today)

    @api.model
    def create(self, vals):
        if not vals.get('sr') and vals.get('register_id'):
            lines = self.search([('register_id', '=', vals['register_id'])])
            vals['sr'] = (max(lines.mapped('sr') or [0])) + 1
        return super().create(vals)


class SwitchgearDesignDocumentReceivedLine(models.Model):
    _name = 'switchgear.design.document.received.line'
    _description = 'Design Document Received Line'
    _order = 'sr, id'

    register_id = fields.Many2one(
        'switchgear.design.document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sr = fields.Integer(string='SR')
    document_name = fields.Char(string='Document Received Name', required=True)
    remarks = fields.Char(string='Remarks')
    attachment = fields.Binary(string='Attachment', attachment=True)
    attachment_name = fields.Char(string='File Name')
    date_received = fields.Date(string='Date Received', default=fields.Date.context_today)

    @api.model
    def create(self, vals):
        if not vals.get('sr') and vals.get('register_id'):
            lines = self.search([('register_id', '=', vals['register_id'])])
            vals['sr'] = (max(lines.mapped('sr') or [0])) + 1
        return super().create(vals)

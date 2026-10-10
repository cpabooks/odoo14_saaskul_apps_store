# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderDocumentSentLine(models.Model):
    _name = 'sale.order.document.sent.line'
    _description = 'Quotation Document Sent'
    _order = 'sr, id'

    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sr = fields.Integer(string='SR')
    document_name = fields.Char(string='Document Sent Name', required=True)
    attachment = fields.Binary(string='Attachment', attachment=True)
    attachment_name = fields.Char(string='File Name')
    remarks = fields.Char(string='Remarks')

    @api.model
    def create(self, vals):
        if not vals.get('sr') and vals.get('order_id'):
            lines = self.search([('order_id', '=', vals['order_id'])])
            vals['sr'] = (max(lines.mapped('sr') or [0])) + 1
        return super().create(vals)


class SaleOrderDocumentReceivedLine(models.Model):
    _name = 'sale.order.document.received.line'
    _description = 'Quotation Document Received'
    _order = 'sr, id'

    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sr = fields.Integer(string='SR')
    document_name = fields.Char(string='Document Received Name', required=True)
    attachment = fields.Binary(string='Attachment', attachment=True)
    attachment_name = fields.Char(string='File Name')
    date_received = fields.Date(string='Date Received')
    remarks = fields.Char(string='Remarks')

    @api.model
    def create(self, vals):
        if not vals.get('sr') and vals.get('order_id'):
            lines = self.search([('order_id', '=', vals['order_id'])])
            vals['sr'] = (max(lines.mapped('sr') or [0])) + 1
        return super().create(vals)

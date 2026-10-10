# -*- coding: utf-8 -*-


from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    job_quotation = fields.Boolean(string='Is Job Quotation', default=True)
    job_estimate_id = fields.Many2one('switchgear.estimate', string='Job Estimate', readonly=True, copy=False)
    bom_count = fields.Integer('# Bill of Material', compute='_compute_bom_count')
    bom_product_id = fields.Many2one('product.product', string='BOM Product')
    document_sent_ids = fields.One2many(
        'sale.order.document.sent.line',
        'order_id',
        string='Documents Sent',
        copy=True,
    )
    document_received_ids = fields.One2many(
        'sale.order.document.received.line',
        'order_id',
        string='Documents Received',
        copy=True,
    )
    direct_sale = fields.Boolean(string='Direct Sale')

    def _compute_bom_count(self):
        for order in self:
            order.bom_count = self.env['mrp.bom'].search_count([('sale_order_id', '=', order.id)])

    @api.onchange('direct_sale')
    def _onchange_direct_sale_job_quotation(self):
        for rec in self:
            rec.job_quotation = not bool(rec.direct_sale)

    def action_create_bom(self):
        if not self.bom_product_id:
            raise ValidationError(_('Please select BOM Product to create BOM'))
        if self.bom_product_id:
            bom_id = self.env['mrp.bom'].create({
                'product_id': self.bom_product_id.id,
                'product_tmpl_id': self.bom_product_id.product_tmpl_id.id,
                'product_qty': 1.0,
                'type': 'normal',
                'sale_order_id': self.id,
            })
            if bom_id:
                for line in self.order_line:
                    self.env['mrp.bom.line'].create({
                        'product_id': line.product_id.id,
                        'product_qty': line.product_uom_qty,
                        'bom_id': bom_id.id,
                        'product_uom_id': line.product_uom.id,
                    })

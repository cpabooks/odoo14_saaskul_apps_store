# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    remaining_qty = fields.Float(string='Remaining Qty', copy=False)
    job_order_qty = fields.Float(string='Job Order Qty', copy=False)

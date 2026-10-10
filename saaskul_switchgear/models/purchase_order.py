# -*- coding: utf-8 -*-

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    project_id = fields.Many2one('project.project', string='Job Order')
    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    sg_requisition_id = fields.Many2one('switchgear.purchase.requisition', string='Purchase Requisition',
                                     copy=False, index=True)

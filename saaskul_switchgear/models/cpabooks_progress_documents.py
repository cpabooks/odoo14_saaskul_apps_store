# -*- coding: utf-8 -*-

from odoo import models


class CrmLeadProgress(models.Model):
    _name = 'crm.lead'
    _inherit = ['crm.lead', 'cpabooks.document.progress.mixin']


class JobEstimateProgress(models.Model):
    _name = 'job.estimate'
    _inherit = ['job.estimate', 'cpabooks.document.progress.mixin']


class SaleOrderProgress(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'cpabooks.document.progress.mixin']


class MrpBomProgress(models.Model):
    _name = 'mrp.bom'
    _inherit = ['mrp.bom', 'cpabooks.document.progress.mixin']


class MrpProductionProgress(models.Model):
    _name = 'mrp.production'
    _inherit = ['mrp.production', 'cpabooks.document.progress.mixin']


class PurchaseOrderProgress(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'cpabooks.document.progress.mixin']


class StockPickingProgress(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'cpabooks.document.progress.mixin']


class QualityCheckProgress(models.Model):
    _name = 'quality.check'
    _inherit = ['quality.check', 'cpabooks.document.progress.mixin']


class SwitchgearDesignDocumentProgress(models.Model):
    _name = 'switchgear.design.document'
    _inherit = ['switchgear.design.document', 'cpabooks.document.progress.mixin']

    def _cpabooks_switchgear_pipeline_lead(self):
        self.ensure_one()
        if self.sale_order_id and self.sale_order_id.opportunity_id:
            return self.sale_order_id.opportunity_id
        if self.job_estimate_id and self.job_estimate_id.opportunity_id:
            return self.job_estimate_id.opportunity_id
        if self.partner_id:
            return self.env['crm.lead'].search([
                ('partner_id', '=', self.partner_id.id),
                ('type', '=', 'opportunity'),
            ], limit=1, order='id desc')
        return self.env['crm.lead']

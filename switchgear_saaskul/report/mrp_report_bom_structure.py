# -*- coding: utf-8 -*-

from odoo import models


class ReportBomStructure(models.AbstractModel):
    _inherit = 'report.mrp.report_bom_structure'

    def _get_bom(self, bom_id=False, product_id=False, line_qty=False, line_id=False, level=False):
        res = super(ReportBomStructure, self)._get_bom(bom_id, product_id, line_qty, line_id, level)
        bom = self.env['mrp.bom'].browse(bom_id)
        res['estimate_reference'] = bom.estimate_reference if bom.estimate_reference else ''
        res['project_id'] = bom.project_id.name if bom.project_id else ''
        res['partner_id'] = bom.partner_id.name if bom.partner_id else ''
        return res

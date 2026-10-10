# -*- coding: utf-8 -*-

from odoo import api, models


class TaskCustomReport(models.AbstractModel):
    _inherit = 'report.industry_fsm_report.worksheet_custom'

    @api.model
    def _get_report_values(self, docids, data=None):
        res = super()._get_report_values(docids, data)
        res['report_copy_label'] = 'TMC Internal'
        return res


class TaskCustomCustomerCopyReport(models.AbstractModel):
    _inherit = 'report.saaskul_field_service.worksheet_custom_customer'

    @api.model
    def _get_report_values(self, docids, data=None):
        res = super()._get_report_values(docids, data)
        res['report_copy_label'] = 'TMC Customer'
        return res

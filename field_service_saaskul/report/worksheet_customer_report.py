# -*- coding: utf-8 -*-

from odoo import api, models


class TaskJcrInternalReport(models.AbstractModel):
    _name = 'report.field_service_saaskul.worksheet_custom_internal'
    _description = 'Job Completion Report (Internal Copy)'

    _copy_label = 'TMC Internal'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            'doc_ids': docids,
            'doc_model': 'project.task',
            'docs': self.env['project.task'].browse(docids).sudo(),
            'report_copy_label': self._copy_label,
        }


class TaskJcrCustomerReport(models.AbstractModel):
    _name = 'report.field_service_saaskul.worksheet_custom_customer'
    _inherit = 'report.field_service_saaskul.worksheet_custom_internal'
    _description = 'Job Completion Report (Customer Copy)'

    _copy_label = 'TMC Customer'

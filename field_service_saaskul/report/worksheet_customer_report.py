# -*- coding: utf-8 -*-

from odoo import api, models


class TaskCustomCustomerCopyReport(models.AbstractModel):
    _name = 'report.field_service_saaskul.worksheet_custom_customer'
    _description = 'Task Worksheet Customer Copy Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['project.task'].browse(docids).sudo()

        worksheet_map = {}
        for task in docs:
            if task.worksheet_template_id:
                x_model = task.worksheet_template_id.model_id.model
                worksheet = self.env[x_model].search(
                    [('x_task_id', '=', task.id)],
                    limit=1,
                    order='create_date DESC',
                )
                worksheet_map[task.id] = worksheet

        return {
            'doc_ids': docids,
            'doc_model': 'project.task',
            'docs': docs,
            'worksheet_map': worksheet_map,
            'report_copy_label': 'TMC Customer',
        }

# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CpabooksProgressStatusWizard(models.TransientModel):
    _name = 'cpabooks.progress.status.wizard'
    _description = 'Document progress status popup'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    progress_html = fields.Html(compute='_compute_progress_html', sanitize=False)

    @api.depends('res_model', 'res_id')
    def _compute_progress_html(self):
        for wizard in self:
            record = wizard._get_source_record()
            if record and hasattr(record, '_cpabooks_progress_render_html'):
                wizard.progress_html = record._cpabooks_progress_render_html()
            else:
                wizard.progress_html = False

    def _get_source_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return self.env[self._name]
        if self.res_model not in self.env:
            return self.env[self._name]
        return self.env[self.res_model].browse(self.res_id).exists()

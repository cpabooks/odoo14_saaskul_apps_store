# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_PT_DEFAULT_KEYS = (
    'professional_templates_v1.report_defaults_initialized',
    'professional_templates_v1.common_boxed_defaults_applied',
    'professional_templates_v1.professional_defaults_v73',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Style = env.get('report.template.settings')
    if not Style or not Style.sudo().search_count([]):
        return
    param = env['ir.config_parameter'].sudo()
    marked = []
    for pt_key in _PT_DEFAULT_KEYS:
        if not param.get_param(pt_key):
            param.set_param(pt_key, '1')
            marked.append(pt_key)
    if marked:
        _logger.info(
            'cpabooks_sequences 1.21: marked PT default flags: %s',
            ', '.join(marked),
        )

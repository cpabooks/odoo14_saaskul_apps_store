# -*- coding: utf-8 -*-
"""Upgrade-safe sequence bootstrap + preserve existing invoice/report defaults."""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_PT_DEFAULT_KEYS = (
    'professional_templates_v1.report_defaults_initialized',
    'professional_templates_v1.common_boxed_defaults_applied',
    'professional_templates_v1.professional_defaults_v73',
)


def _sequence_snapshot(sequences):
    snapshot = {}
    for row in sequences:
        company_id = row.company_id.id
        snapshot[(company_id, row.sequence_for)] = (row.prefix, row.number_next)
    return snapshot


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sequence = env['ir.sequence'].sudo()
    before = _sequence_snapshot(
        Sequence.search([('sequence_for', '!=', False)]),
    )

    Sequence.with_context(cpabooks_sequences_force_rebuild=False).action_create_sequence()

    after = _sequence_snapshot(
        Sequence.search([('sequence_for', '!=', False)]),
    )
    for key, (old_prefix, old_next) in before.items():
        if key not in after:
            continue
        new_prefix, new_next = after[key]
        if old_prefix != new_prefix or old_next != new_next:
            _logger.warning(
                'cpabooks_sequences 1.20: sequence changed company=%s type=%s '
                'prefix %r→%r next %s→%s',
                key[0], key[1], old_prefix, new_prefix, old_next, new_next,
            )
    _logger.info(
        'cpabooks_sequences 1.20: upgrade-safe bootstrap (%s to %s sequence rows)',
        len(before), len(after),
    )

    param = env['ir.config_parameter'].sudo()
    Style = env.get('report.template.settings')
    if Style and Style.sudo().search_count([]):
        for pt_key in _PT_DEFAULT_KEYS:
            if not param.get_param(pt_key):
                param.set_param(pt_key, '1')
        _logger.info(
            'cpabooks_sequences 1.20: PT defaults marked initialized (styles preserved)',
        )

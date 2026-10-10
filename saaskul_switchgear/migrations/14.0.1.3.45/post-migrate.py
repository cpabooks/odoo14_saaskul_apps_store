# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    loader = env['switchgear.demo.loader']
    for company in env['res.company'].search([]):
        try:
            done = loader._ensure_demo_mo_done_minimums(company, min_count=6)
            if done:
                _logger.info(
                    'saaskul_switchgear 14.0.1.3.45: marked %s MO(s) done for %s',
                    done, company.display_name,
                )
        except Exception:
            _logger.exception(
                'saaskul_switchgear 14.0.1.3.45 MO done backfill skipped for %s',
                company.display_name,
            )

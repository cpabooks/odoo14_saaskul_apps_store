# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    loader = env['switchgear.demo.loader']
    for company in env['res.company'].search([]):
        try:
            fixed = loader._backfill_demo_project_financials(company)
            if fixed:
                _logger.info(
                    'saaskul_switchgear 14.0.1.3.49: synced %s demo project(s) for %s',
                    fixed, company.display_name,
                )
        except Exception:
            _logger.exception(
                'saaskul_switchgear 14.0.1.3.49 project financial backfill skipped for %s',
                company.display_name,
            )

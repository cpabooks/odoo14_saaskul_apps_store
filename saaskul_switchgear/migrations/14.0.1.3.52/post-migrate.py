# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    loader = env['switchgear.demo.loader']
    partners = env['res.partner'].sudo().search([
        '|',
        ('name', '=like', 'Switchgear Demo % Customer'),
        ('name', '=like', 'Furniture Demo % Customer'),
    ])
    vendor_partners = env['res.partner'].sudo().search([
        ('name', 'ilike', 'Demo Vendor'),
    ])
    restore_ids = (partners | vendor_partners).ids
    if hasattr(env['res.partner'], 'cpabooks_restore_missing_account_properties') and restore_ids:
        restored = env['res.partner'].cpabooks_restore_missing_account_properties(restore_ids)
        if restored:
            _logger.info(
                'saaskul_switchgear 14.0.1.3.52: restored accounts on %s demo partner(s)',
                restored,
            )
    for company in partners.mapped('company_id'):
        try:
            fixed = loader._backfill_demo_project_financials(company)
            if fixed:
                _logger.info(
                    'saaskul_switchgear 14.0.1.3.52: synced %s demo project(s) for %s',
                    fixed, company.display_name,
                )
        except Exception:
            _logger.exception(
                'saaskul_switchgear 14.0.1.3.52 project financial backfill skipped for %s',
                company.display_name,
            )

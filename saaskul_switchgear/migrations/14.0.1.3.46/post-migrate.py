# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    loader = env['switchgear.demo.loader']
    Bom = env['mrp.bom'].sudo()
    for company in env['res.company'].search([]):
        try:
            boms = Bom.search([
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
                ('final_product_ids', '=', False),
                ('bom_line_ids', '!=', False),
            ])
            for bom in boms:
                loader._ensure_bom_final_products(bom)
            done = loader._ensure_demo_mo_done_minimums(company, min_count=6)
            if done:
                _logger.info(
                    'saaskul_switchgear 14.0.1.3.46: marked %s MO(s) done for %s',
                    done, company.display_name,
                )
        except Exception:
            _logger.exception(
                'saaskul_switchgear 14.0.1.3.46 MO done backfill skipped for %s',
                company.display_name,
            )

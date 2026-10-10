# -*- coding: utf-8 -*-
import traceback

company = env['res.company'].search([('name', 'ilike', 'Demo Data%')], limit=1) or env.company
loader = env['switchgear.demo.loader'].sudo().with_company(company)
catalog = loader._ensure_demo_catalog('switchgear', company)
try:
    stack = loader._create_single_stack(
        99, 'switchgear', company, catalog,
        full_cycle=False, load_activities=False, create_pr=False,
    )
    print('OK estimate=', stack.get('estimate') and stack['estimate'].name)
    print('OK sale=', stack.get('sale_order') and stack['sale_order'].name)
except Exception:
    traceback.print_exc()

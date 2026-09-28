# -*- coding: utf-8 -*-
"""Backfill Client Name (partner_id) on VAR work from L3 Level (Project) name."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    VarWork = env['cpabooks.cafm.var.work']
    Partner = env['res.partner']

    # Prefer legacy Char client_name if column still exists
    has_client_name = False
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cpabooks_cafm_var_work' AND column_name = 'client_name'
    """)
    has_client_name = bool(cr.fetchone())

    works = VarWork.search([('partner_id', '=', False), ('l3_level_id', '!=', False)])
    for work in works:
        name = ''
        if has_client_name:
            cr.execute(
                'SELECT client_name FROM cpabooks_cafm_var_work WHERE id = %s',
                (work.id,),
            )
            row = cr.fetchone()
            name = (row[0] or '').strip() if row else ''
        if not name and work.l3_level_id:
            name = (work.l3_level_id.name or '').strip()
        if not name:
            continue
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({'name': name})
        work.partner_id = partner.id

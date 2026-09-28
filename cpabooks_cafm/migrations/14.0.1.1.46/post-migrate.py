# -*- coding: utf-8 -*-
"""Backfill partner_id on VAR work from client_name or L3 project name."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    VarWork = env['cpabooks.cafm.var.work']
    Partner = env['res.partner']

    empty = VarWork.search([('partner_id', '=', False)])
    for work in empty:
        name = (work.client_name or '').strip()
        if not name and work.l3_level_id:
            name = (work.l3_level_id.name or '').strip()
        if not name:
            continue
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({'name': name})
        work.partner_id = partner.id

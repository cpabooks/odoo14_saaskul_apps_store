# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Force Switchgear sidebar mode + hide top navbar secondary menus."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].sudo().set_param('app_web_ui_mode', 'switchgear')
    # Hide leftover top-bar menus even if XML noupdate skipped them.
    xmlids = [
        'saaskul_switchgear.menu_flowchart_kanban',
        'saaskul_switchgear.menu_switchgear_processing_cycle',
        'saaskul_switchgear.menu_switchgear_tutorial_wizard',
        'saaskul_switchgear.menu_switchgear_projects_root',
        'saaskul_switchgear.menu_switchgear_activities_root',
        'saaskul_switchgear.menu_switchgear_configuration',
    ]
    for xmlid in xmlids:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.sudo().write({'active': False})
    root = env.ref('saaskul_switchgear.menu_flowchart_kanban_root', raise_if_not_found=False)
    dash = env.ref('saaskul_switchgear.action_switchgear_dashboard', raise_if_not_found=False)
    if root and dash:
        root.sudo().write({'action': 'ir.actions.client,%s' % dash.id})

# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    """Make the Switchgear app visible to every internal user."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    menu = env.ref('switchgear_saaskul.menu_flowchart_kanban_root', raise_if_not_found=False)
    user_group = env.ref('base.group_user', raise_if_not_found=False)
    flowchart = env.ref('switchgear_saaskul.group_flowchart', raise_if_not_found=False)
    if menu and user_group:
        menu.write({'groups_id': [(6, 0, [user_group.id])]})
    if user_group and flowchart and flowchart not in user_group.implied_ids:
        user_group.write({'implied_ids': [(4, flowchart.id)]})

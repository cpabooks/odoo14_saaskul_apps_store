# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.saaskul_switchgear.hooks import (
        _ensure_switchgear_menu_visibility,
        _ensure_switchgear_web_ui_mode,
    )
    _ensure_switchgear_menu_visibility(env)
    _ensure_switchgear_web_ui_mode(env)
    # Ensure existing Internal Users pick up implied flowchart group now.
    flowchart = env.ref(
        'saaskul_switchgear.group_flowchart',
        raise_if_not_found=False,
    )
    user_group = env.ref('base.group_user', raise_if_not_found=False)
    if flowchart and user_group:
        missing = user_group.users - flowchart.users
        if missing:
            flowchart.sudo().write({'users': [(4, u.id) for u in missing]})
            _logger.info(
                'saaskul_switchgear 3.63: granted group_flowchart to %s user(s)',
                len(missing),
            )
    _logger.info('saaskul_switchgear 3.63: menu visibility + switchgear UI mode')

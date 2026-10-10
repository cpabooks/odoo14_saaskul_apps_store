# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    root = env.ref("facility_management_saaskul.menu_saaskul_cafm_root", raise_if_not_found=False)
    action = env.ref(
        "facility_management_saaskul.action_saaskul_cafm_dashboard", raise_if_not_found=False
    )
    if root and action:
        root.sudo().write({"action": "ir.actions.client,%d" % action.id})
        _logger.info("CAFM: root menu action set to dashboard (migration 14.0.1.1.37)")

    try:
        from odoo.addons.saaskul_settings_extend.hooks_web_assets import (
            repair_web_client_assets,
        )

        repair_web_client_assets(env, full=True)
    except Exception:
        _logger.exception(
            "CAFM: web asset rebuild failed in migration 14.0.1.1.37"
        )

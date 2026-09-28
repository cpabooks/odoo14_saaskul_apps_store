# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    root = env.ref("cpabooks_cafm.menu_cpabooks_cafm_root", raise_if_not_found=False)
    action = env.ref(
        "cpabooks_cafm.action_cpabooks_cafm_dashboard", raise_if_not_found=False
    )
    if root and action:
        root.sudo().write({"action": "ir.actions.client,%d" % action.id})
        _logger.info("CPABooks CAFM: root menu action set to dashboard (migration 14.0.1.1.37)")

    try:
        from odoo.addons.cpabooks_settings_extend.hooks_web_assets import (
            repair_web_client_assets,
        )

        repair_web_client_assets(env, full=True)
    except Exception:
        _logger.exception(
            "CPABooks CAFM: web asset rebuild failed in migration 14.0.1.1.37"
        )

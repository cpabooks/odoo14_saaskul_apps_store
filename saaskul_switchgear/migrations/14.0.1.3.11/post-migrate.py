# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID

from odoo.addons.saaskul_switchgear.hooks import _cleanup_demo_setup


def migrate(cr, version):
    """Legacy hook — cleanup is idempotent; failures must not block upgrades."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _cleanup_demo_setup(env)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'saaskul_switchgear 14.0.1.3.11 post-migrate skipped',
        )

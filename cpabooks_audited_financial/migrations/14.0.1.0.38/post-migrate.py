# -*- coding: utf-8 -*-
"""Scrub AFG lines that still point at deleted account.account rows (e.g. after CoA Factory Reset)."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    if "audited.financial.version" not in env:
        return
    try:
        env["audited.financial.version"]._afg_scrub_orphan_account_refs()
    except Exception:
        _logger.exception(
            "cpabooks_audited_financial 14.0.1.0.38: orphan account scrub failed"
        )

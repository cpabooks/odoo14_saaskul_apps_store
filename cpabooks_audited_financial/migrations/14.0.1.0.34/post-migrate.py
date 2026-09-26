# -*- coding: utf-8 -*-
"""Remap AFG chart so income/expense (e.g. EOS indemnity) stay on P&L."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    if "audited.financial.version" not in env:
        return
    Version = env["audited.financial.version"]
    for ver in Version.search([]):
        try:
            with cr.savepoint():
                ver.action_load_default_data()
        except Exception:
            _logger.exception(
                "cpabooks_audited_financial 14.0.1.0.34: remap failed for version id=%s",
                ver.id,
            )

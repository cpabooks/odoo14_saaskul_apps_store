# -*- coding: utf-8 -*-
"""Re-apply expanded AFG keyword rules so ledgers leave UNGRP buckets."""

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
                ver.action_auto_map_chart()
        except Exception:
            _logger.exception(
                "cpabooks_audited_financial 14.0.1.0.56: AFG remap failed for version id=%s",
                ver.id,
            )

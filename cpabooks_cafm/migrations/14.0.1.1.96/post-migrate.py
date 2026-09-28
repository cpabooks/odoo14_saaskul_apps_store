# -*- coding: utf-8 -*-
"""Rebuild invoice-month lines (groupby-safe) from frequency schedule."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Contract = env['cpabooks.cafm.contract']
    if not hasattr(Contract, '_rebuild_invoice_month_schedule'):
        return
    # Only IDs that exist in SQL (avoids ORM cache / FK surprises mid-upgrade).
    cr.execute("SELECT id FROM cpabooks_cafm_contract ORDER BY id")
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return
    for cid in ids:
        try:
            with cr.savepoint():
                Contract.browse(cid).with_context(
                    active_test=False,
                    cafm_skip_invoice_month_sync=True,
                )._rebuild_invoice_month_schedule()
        except Exception:
            _logger.exception(
                'CAFM 14.0.1.1.96: skip invoice-month rebuild for contract id=%s',
                cid,
            )

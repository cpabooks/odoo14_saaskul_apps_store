# -*- coding: utf-8 -*-
"""Ensure audited.financial.line columns exist (ORM upgrade sometimes skipped in dev DBs)."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, installed_version):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'audited_financial_line'
        )
        """
    )
    if not cr.fetchone()[0]:
        return
    cr.execute(
        """
        ALTER TABLE audited_financial_line
        ADD COLUMN IF NOT EXISTS merged_leaf_account_ids character varying
        """
    )
    _logger.info("cpabooks_audited_financial: ensured audited_financial_line.merged_leaf_account_ids column")

# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'cpabooks_cafm_amc_wizard'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'cpabooks_cafm_amc_wizard'
        """
    )
    cols = {r[0] for r in cr.fetchall()}
    if "step_index" not in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard "
            "ADD COLUMN step_index INTEGER DEFAULT 0"
        )
        _logger.info("CAFM: added step_index on amc wizard")
    if "step" in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard "
            "ALTER COLUMN step DROP NOT NULL"
        )
        cr.execute(
            "UPDATE cpabooks_cafm_amc_wizard SET step = NULL "
            "WHERE step IS NOT NULL"
        )

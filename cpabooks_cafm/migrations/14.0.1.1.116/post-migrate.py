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
        SELECT column_name, is_nullable, data_type
          FROM information_schema.columns
         WHERE table_name = 'cpabooks_cafm_amc_wizard'
        """
    )
    meta = {r[0]: (r[1], r[2]) for r in cr.fetchall()}
    if "step_index" not in meta:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard "
            "ADD COLUMN step_index INTEGER DEFAULT 0"
        )
    if "step" in meta and meta["step"][0] == "NO":
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard ALTER COLUMN step DROP NOT NULL"
        )
        _logger.info("CAFM: step column nullable on amc wizard")

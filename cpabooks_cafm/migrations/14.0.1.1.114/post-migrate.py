# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Drop stale wizard table so registry recreates all columns cleanly."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'cpabooks_cafm_amc_wizard'
        """
    )
    cols = {row[0] for row in cr.fetchall()}
    needed = {"material_mode", "sale_order_id", "path_type", "step"}
    if cols and not needed.issubset(cols):
        cr.execute("DROP TABLE IF EXISTS cpabooks_cafm_amc_wizard CASCADE")
        _logger.info(
            "CAFM: dropped incomplete cpabooks_cafm_amc_wizard (had %s)",
            sorted(cols),
        )
        return
    if not cols:
        return
    if "material_mode" not in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard "
            "ADD COLUMN material_mode VARCHAR DEFAULT 'issue'"
        )
    if "sale_order_id" not in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard "
            "ADD COLUMN sale_order_id INTEGER"
        )

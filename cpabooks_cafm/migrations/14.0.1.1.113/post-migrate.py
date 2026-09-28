# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure AMC wizard transient columns exist (schema drift after field add)."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'cpabooks_cafm_amc_wizard'
        """
    )
    cols = {row[0] for row in cr.fetchall()}
    if not cols:
        _logger.info("CAFM: wizard table missing — registry will recreate on load")
        return
    if "material_mode" not in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard ADD COLUMN material_mode VARCHAR"
        )
        _logger.info("CAFM: added cpabooks_cafm_amc_wizard.material_mode")
    if "sale_order_id" not in cols:
        cr.execute(
            "ALTER TABLE cpabooks_cafm_amc_wizard ADD COLUMN sale_order_id INTEGER"
        )
        _logger.info("CAFM: added cpabooks_cafm_amc_wizard.sale_order_id")

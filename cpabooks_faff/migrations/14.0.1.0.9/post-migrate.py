# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Insert Confirm (4) + Closing (12) into persisted wizard_step index."""
    cr.execute(
        """
        UPDATE cpabooks_faff_job
           SET wizard_step = wizard_step + 1
         WHERE wizard_step >= 4
        """
    )
    _logger.info("FAFF: remapped wizard_step for confirm + closing steps")

# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'ir_sequence'
           AND column_name = 'cpabooks_start_new_sequence'
        """
    )
    if not cr.fetchone():
        cr.execute(
            "ALTER TABLE ir_sequence "
            "ADD COLUMN cpabooks_start_new_sequence bool DEFAULT false"
        )
    cr.execute(
        """
        UPDATE ir_sequence
           SET cpabooks_start_new_sequence = false
         WHERE sequence_for IS NOT NULL
           AND cpabooks_start_new_sequence IS NULL
        """
    )

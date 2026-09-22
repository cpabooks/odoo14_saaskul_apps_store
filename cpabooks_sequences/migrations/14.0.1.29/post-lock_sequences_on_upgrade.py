# -*- coding: utf-8 -*-
"""Lock all CPABooks document sequences after upgrade (user must unlock to reset)."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'ir_sequence'
           AND column_name = 'cpabooks_sequence_locked'
        """
    )
    if not cr.fetchone():
        cr.execute(
            "ALTER TABLE ir_sequence ADD COLUMN cpabooks_sequence_locked bool"
        )
    cr.execute(
        """
        UPDATE ir_sequence
           SET cpabooks_sequence_locked = true
         WHERE sequence_for IS NOT NULL
        """
    )

# -*- coding: utf-8 -*-
"""Ensure CPABooks sequences default to locked (NULL/false -> true)."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_sequence
           SET cpabooks_sequence_locked = true
         WHERE sequence_for IS NOT NULL
           AND COALESCE(cpabooks_sequence_locked, false) = false
        """
    )

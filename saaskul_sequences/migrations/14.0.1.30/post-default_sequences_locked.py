# -*- coding: utf-8 -*-
"""Ensure Saaskul sequences default to locked (NULL/false -> true)."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_sequence
           SET saaskul_sequence_locked = true
         WHERE sequence_for IS NOT NULL
           AND COALESCE(saaskul_sequence_locked, false) = false
        """
    )

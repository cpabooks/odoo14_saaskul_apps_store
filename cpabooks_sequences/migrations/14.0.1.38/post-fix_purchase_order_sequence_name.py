# -*- coding: utf-8 -*-
"""Fix ir.sequence name typo: Puchase Order -> Purchase Order."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_sequence
           SET name = 'Purchase Order'
         WHERE sequence_for = 'purchase'
           AND name ILIKE 'Puchase Order'
        """
    )

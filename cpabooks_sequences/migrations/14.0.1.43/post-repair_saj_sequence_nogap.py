# -*- coding: utf-8 -*-
"""Repair SAJ sequences created by SQL without matching PostgreSQL sequences.

implementation=standard needs ir_sequence_<id>; raw INSERT skipped that and
Validate Inventory failed with UndefinedTable: relation ir_sequence_223.
Switch those rows to no_gap (uses number_next on ir_sequence row).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_sequence
           SET implementation = 'no_gap'
         WHERE sequence_for = 'stock_adjustment'
           AND implementation = 'standard'
        RETURNING id
        """
    )
    ids = [row[0] for row in cr.fetchall()]
    if ids:
        _logger.info(
            'Repaired SAJ ir.sequence to no_gap (missing PG seq): %s', ids
        )

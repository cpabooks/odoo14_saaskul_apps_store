# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure Manufacturing picking types have a sequence (fixes Create MO)."""
    cr.execute(
        """
        SELECT id FROM ir_sequence
         WHERE code = 'mrp.production'
         LIMIT 1
        """
    )
    row = cr.fetchone()
    if not row:
        cr.execute(
            """
            SELECT id FROM ir_sequence
             WHERE name ILIKE 'Manufacturing Order%%'
               AND (code IS NULL OR code = '')
             ORDER BY id
             LIMIT 1
            """
        )
        row = cr.fetchone()
        if row:
            cr.execute(
                "UPDATE ir_sequence SET code = 'mrp.production' WHERE id = %s",
                (row[0],),
            )
    if not row:
        cr.execute(
            """
            INSERT INTO ir_sequence (
                name, code, implementation, prefix, padding,
                number_next, number_increment, company_id, active, create_uid, create_date, write_uid, write_date
            ) VALUES (
                'Manufacturing Orders', 'mrp.production', 'standard', 'WH/MO/', 5,
                1, 1, NULL, TRUE, 1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC'
            )
            RETURNING id
            """
        )
        row = cr.fetchone()

    seq_id = row[0]
    cr.execute(
        """
        UPDATE stock_picking_type
           SET sequence_id = %s
         WHERE code = 'mrp_operation'
           AND sequence_id IS NULL
        """,
        (seq_id,),
    )
    _logger.info(
        'saaskul_switchgear 1.3.68: linked %s mrp_operation picking type(s) '
        'to sequence %s',
        cr.rowcount,
        seq_id,
    )

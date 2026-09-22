# -*- coding: utf-8 -*-
"""Ensure SAJ (stock_adjustment) ir.sequence exists for every company."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT c.id,
               COALESCE(
                   (SELECT split_part(s.prefix, '/', 2)
                    FROM ir_sequence s
                    WHERE s.company_id = c.id
                      AND s.sequence_for = 'outgoing'
                      AND s.prefix IS NOT NULL
                    LIMIT 1),
                   ''
               ) AS company_code
        FROM res_company c
        WHERE NOT EXISTS (
            SELECT 1 FROM ir_sequence s
            WHERE s.sequence_for = 'stock_adjustment'
              AND s.company_id = c.id
        )
        """
    )
    rows = cr.fetchall()
    for company_id, company_code in rows:
        if company_code:
            prefix = 'SAJ/%s/%%(year)s/' % company_code
        else:
            prefix = 'SAJ/%(year)s/'
        cr.execute(
            """
            INSERT INTO ir_sequence (
                name, implementation, prefix, padding,
                number_next, number_increment, company_id,
                sequence_for, sequence_pattern, cpabooks_year_digits,
                cpabooks_sequence_locked, active, create_uid, write_uid,
                create_date, write_date
            ) VALUES (
                %s, 'no_gap', %s, 5,
                1, 1, %s,
                'stock_adjustment', 'year_yearly', '4',
                TRUE, TRUE, 1, 1,
                (NOW() AT TIME ZONE 'UTC'), (NOW() AT TIME ZONE 'UTC')
            )
            """,
            ('Stock Adjustment Journal', prefix, company_id),
        )
        _logger.info('Created SAJ ir.sequence for company_id=%s prefix=%s', company_id, prefix)

# -*- coding: utf-8 -*-
"""Add per-sequence year digits; do not rewrite existing sequence prefixes on upgrade."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'ir_sequence'
           AND column_name = 'saaskul_year_digits'
        """
    )
    if not cr.fetchone():
        cr.execute("ALTER TABLE ir_sequence ADD COLUMN saaskul_year_digits varchar")

    cr.execute(
        """
        UPDATE ir_sequence s
           SET saaskul_year_digits = CASE
               WHEN s.sequence_pattern = 'year' THEN '2'
               WHEN s.sequence_pattern = 'year_yearly' THEN '4'
               WHEN s.sequence_pattern IN ('month_year', 'month_year_monthly') THEN '2'
               ELSE COALESCE(
                   (SELECT c.saaskul_sequence_year_digits
                      FROM res_company c
                     WHERE c.id = s.company_id),
                   '4'
               )
           END
         WHERE s.sequence_for IS NOT NULL
           AND s.saaskul_year_digits IS NULL
        """
    )

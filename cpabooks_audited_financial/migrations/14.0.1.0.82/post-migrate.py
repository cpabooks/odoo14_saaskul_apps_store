# -*- coding: utf-8 -*-
"""Map legacy print_max_level=5 (L1 with ledgers) → 4; set global ICP default."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE audited_financial_version
           SET print_max_level = 4
         WHERE print_max_level IS NULL
            OR print_max_level = 5
            OR print_max_level > 4
        """
    )
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
        SELECT 'cpabooks_afg.print_max_level', '4', 1, NOW(), 1, NOW()
         WHERE NOT EXISTS (
            SELECT 1 FROM ir_config_parameter WHERE key = 'cpabooks_afg.print_max_level'
         )
        """
    )
    cr.execute(
        """
        UPDATE ir_config_parameter
           SET value = '4'
         WHERE key = 'cpabooks_afg.print_max_level'
           AND value IN ('5', '')
        """
    )

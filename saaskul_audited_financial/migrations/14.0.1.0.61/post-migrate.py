# -*- coding: utf-8 -*-
"""Default View/print depth to L4 for existing AFG versions."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE audited_financial_version
           SET print_max_level = 4
         WHERE print_max_level IS NULL
            OR print_max_level < 4
        """
    )

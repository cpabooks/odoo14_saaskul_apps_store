# -*- coding: utf-8 -*-
"""Default AFG column order: prior year then current (ascending)."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE audited_financial_version
           SET print_years_descending = false
         WHERE print_years_descending IS DISTINCT FROM false
        """
    )

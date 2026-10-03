# -*- coding: utf-8 -*-
"""Legacy expand-next-invoice migrate (superseded by 14.0.1.1.96).

Kept as a no-op so upgrades from older DB versions do not call removed
helpers or double-run ``_rebuild_invoice_month_schedule`` before related
tables are fully ready.
"""


def migrate(cr, version):
    return

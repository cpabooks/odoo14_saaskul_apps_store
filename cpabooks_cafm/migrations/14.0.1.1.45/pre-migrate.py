# -*- coding: utf-8 -*-
"""Drop old Char tenant_name before Many2one tenant_unit_id is created."""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'cpabooks_cafm_flat_detail'
           AND column_name = 'tenant_name'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE cpabooks_cafm_flat_detail DROP COLUMN IF EXISTS tenant_name")

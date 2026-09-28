# -*- coding: utf-8 -*-
"""Clear old res.users FKs before gfs_* fields switch to cpabooks.cafm.gfs.staff."""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE cpabooks_cafm_contract
           SET gfs_supervisor_id = NULL,
               gfs_admin_id = NULL
         WHERE gfs_supervisor_id IS NOT NULL
            OR gfs_admin_id IS NOT NULL
        """
    )
    cr.execute(
        """
        UPDATE cpabooks_cafm_contract_order
           SET gfs_supervisor_id = NULL,
               gfs_admin_id = NULL
         WHERE gfs_supervisor_id IS NOT NULL
            OR gfs_admin_id IS NOT NULL
        """
    )
    # Drop old FKs so ORM can recreate them against the new comodel.
    cr.execute(
        """
        ALTER TABLE cpabooks_cafm_contract
            DROP CONSTRAINT IF EXISTS cpabooks_cafm_contract_gfs_supervisor_id_fkey,
            DROP CONSTRAINT IF EXISTS cpabooks_cafm_contract_gfs_admin_id_fkey
        """
    )
    cr.execute(
        """
        ALTER TABLE cpabooks_cafm_contract_order
            DROP CONSTRAINT IF EXISTS cpabooks_cafm_contract_order_gfs_supervisor_id_fkey,
            DROP CONSTRAINT IF EXISTS cpabooks_cafm_contract_order_gfs_admin_id_fkey
        """
    )

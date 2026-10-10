# -*- coding: utf-8 -*-
"""Revert gfs_* Many2one targets from saaskul.cafm.gfs.staff back to res.users."""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE saaskul_cafm_contract
           SET gfs_supervisor_id = NULL,
               gfs_admin_id = NULL
         WHERE gfs_supervisor_id IS NOT NULL
            OR gfs_admin_id IS NOT NULL
        """
    )
    cr.execute(
        """
        UPDATE saaskul_cafm_contract_order
           SET gfs_supervisor_id = NULL,
               gfs_admin_id = NULL
         WHERE gfs_supervisor_id IS NOT NULL
            OR gfs_admin_id IS NOT NULL
        """
    )
    cr.execute(
        """
        ALTER TABLE saaskul_cafm_contract
            DROP CONSTRAINT IF EXISTS saaskul_cafm_contract_gfs_supervisor_id_fkey,
            DROP CONSTRAINT IF EXISTS saaskul_cafm_contract_gfs_admin_id_fkey
        """
    )
    cr.execute(
        """
        ALTER TABLE saaskul_cafm_contract_order
            DROP CONSTRAINT IF EXISTS saaskul_cafm_contract_order_gfs_supervisor_id_fkey,
            DROP CONSTRAINT IF EXISTS saaskul_cafm_contract_order_gfs_admin_id_fkey
        """
    )

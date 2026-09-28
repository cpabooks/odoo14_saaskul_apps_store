# -*- coding: utf-8 -*-
"""Normalize Contract Check Status Char values → Selection keys."""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cpabooks_cafm_contract'
          AND column_name = 'contract_check_status'
        """
    )
    if not cr.fetchone():
        return

    # Map legacy free-text → selection keys
    cr.execute(
        """
        UPDATE cpabooks_cafm_contract
           SET contract_check_status = 'check_verified'
         WHERE contract_check_status IS NOT NULL
           AND contract_check_status NOT IN ('check_verified', 'auto_renewed_no_copy')
           AND (
                lower(contract_check_status) LIKE '%%check%%verif%%'
             OR lower(contract_check_status) LIKE '%%checked%%verif%%'
           )
        """
    )
    cr.execute(
        """
        UPDATE cpabooks_cafm_contract
           SET contract_check_status = 'auto_renewed_no_copy'
         WHERE contract_check_status IS NOT NULL
           AND contract_check_status NOT IN ('check_verified', 'auto_renewed_no_copy')
           AND (
                lower(contract_check_status) LIKE '%%auto renew%%'
             OR lower(contract_check_status) LIKE '%%auto-renew%%'
             OR lower(contract_check_status) LIKE '%%no cont%%copy%%'
           )
        """
    )
    # Clear unknown free-text leftovers so Selection stays clean
    cr.execute(
        """
        UPDATE cpabooks_cafm_contract
           SET contract_check_status = NULL
         WHERE contract_check_status IS NOT NULL
           AND contract_check_status NOT IN ('check_verified', 'auto_renewed_no_copy')
        """
    )

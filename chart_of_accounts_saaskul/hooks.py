# -*- coding: utf-8 -*-
import logging

from odoo.tools.sql import column_exists, create_column

_logger = logging.getLogger(__name__)


def _ensure_account_account_cpabooks_columns(cr):
    """Ensure stored COA helper columns exist before old migrations use them."""
    specs = (
        ("identity_id", "int4"),
        ("identity_code", "varchar"),
        ("is_show_code", "bool"),
        ("get_previous", "bool"),
        ("previous", "int4"),
        ("qid", "varchar"),
        ("is_duplicate", "bool"),
        ("cpabooks_previous_code", "varchar"),
        ("cpabooks_previous_name", "varchar"),
        ("cpabooks_ifrs_code", "varchar"),
        ("cpabooks_ifrs_name", "varchar"),
        ("cpabooks_default_seed_key", "varchar"),
        ("cpabooks_default_manually_modified", "bool"),
        ("cpabooks_sync_name_all_companies", "bool"),
        ("correspondent_account_id", "int4"),
        ("cpabooks_l1_type_code", "varchar"),
        ("cpabooks_l1_type_label", "varchar"),
        ("cpabooks_group_code", "varchar"),
        ("cpabooks_group_series_code", "varchar"),
    )
    for col, col_type in specs:
        if not column_exists(cr, "account_account", col):
            create_column(cr, "account_account", col, col_type)

    if not column_exists(cr, "account_group", "identity_id"):
        create_column(cr, "account_group", "identity_id", "int4")


def _ensure_res_company_coa_code_digits(cr):
    if not column_exists(cr, "res_company", "cpabooks_coa_code_digits"):
        create_column(cr, "res_company", "cpabooks_coa_code_digits", "varchar")
    cr.execute(
        """
        UPDATE res_company
           SET cpabooks_coa_code_digits = '6'
         WHERE cpabooks_coa_code_digits IS NULL
            OR cpabooks_coa_code_digits = ''
        """
    )


def _restore_partner_accounts(env):
    try:
        fixed = env['res.partner'].action_cpabooks_restore_partner_accounts()
        _logger.info(
            'Saaskul CoA: restored receivable/payable on %s partner(s)',
            fixed,
        )
    except Exception:
        _logger.exception('Saaskul CoA: partner account restore skipped')


def _init_coa_wizard_tables(env):
    """No-op on fresh install: ORM already created tables during module load.

    Calling ``_auto_init`` from ``post_init_hook`` fails on stock Odoo 14 because
    ``Registry._post_init_queue`` is removed before hooks run.
    """
    return


def _drop_account_code_unique_per_company(cr):
    """Allow duplicate ledger codes per company (IFRS XXXC series / mirrored ledgers)."""
    cr.execute(
        """
        SELECT con.conname
          FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
          JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
         WHERE nsp.nspname = 'public'
           AND rel.relname = 'account_account'
           AND con.contype = 'u'
           AND pg_get_constraintdef(con.oid) ILIKE '%code%'
           AND pg_get_constraintdef(con.oid) ILIKE '%company%'
        """
    )
    for (conname,) in cr.fetchall():
        cr.execute('ALTER TABLE account_account DROP CONSTRAINT IF EXISTS "%s"' % conname.replace('"', ''))
        _logger.info('Saaskul CoA: dropped unique account code constraint %s', conname)


def _recover_ifrs_temp_codes(env):
    try:
        engine = env['coa.ifrs.coding']
        recovered = engine.recover_stuck_temp_ifrs_codes()
        if recovered:
            _logger.info(
                'Saaskul CoA: recovered IFRS codes on %s ledger(s) stuck on temp codes',
                recovered,
            )
        companies = env['res.company'].search([])
        engine.migrate_coa_structure_all_companies()
    except Exception:
        _logger.exception('Saaskul CoA: IFRS temp-code recovery skipped')


def _ensure_default_coa_for_companies(env):
    result = env['account.account'].cpabooks_ensure_default_coa_all_companies()
    env['account.account'].cpabooks_ensure_unaffected_earnings_all_companies()
    _logger.info(
        'Saaskul CoA: all-company defaults created=%s updated=%s preserved=%s',
        result['created'],
        result['updated'],
        result['preserved'],
    )


def _cleanup_stale_account_account_fields(cr):
    """Remove ORM field entries whose columns were never created on account_account."""
    stale = (
        'cpabooks_sync_name_all_companies',
    )
    for field_name in stale:
        if not column_exists(cr, 'account_account', field_name):
            cr.execute(
                "DELETE FROM ir_model_fields WHERE model = 'account.account' AND name = %s",
                (field_name,),
            )
            if cr.rowcount:
                _logger.info('Saaskul CoA: removed stale field entry account.account.%s', field_name)


def post_init_hook(cr, registry):
    from odoo import api, SUPERUSER_ID

    _ensure_account_account_cpabooks_columns(cr)
    _drop_account_code_unique_per_company(cr)
    _ensure_res_company_coa_code_digits(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    _init_coa_wizard_tables(env)
    _restore_partner_accounts(env)
    _recover_ifrs_temp_codes(env)
    try:
        _ensure_default_coa_for_companies(env)
    except Exception:
        _logger.exception('Saaskul CoA: default COA seed skipped')
    try:
        env['account.group'].action_cpa_reset_account_groups()
    except Exception:
        _logger.exception('Saaskul CoA: group reset on install skipped')

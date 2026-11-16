# -*- coding: utf-8 -*-

from odoo.modules.module import get_module_path

from . import models
from . import report

_AFG_ORPHAN_REL_TABLES = (
    "audited_financial_version_company_rel",
    "audited_financial_version_report_col_rel",
)


def _table_exists(cr, table):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = %s
        )
        """,
        (table,),
    )
    return bool(cr.fetchone()[0])


def _ensure_afg_account_ctf_column(cr):
    if not _table_exists(cr, "account_account"):
        return
    cr.execute(
        """
        ALTER TABLE account_account
        ADD COLUMN IF NOT EXISTS ctf_category character varying
        """
    )


def _ensure_afg_version_print_columns(cr):
    if not _table_exists(cr, "audited_financial_version"):
        return
    cr.execute(
        """
        ALTER TABLE audited_financial_version
            ADD COLUMN IF NOT EXISTS internal_action_notes text,
            ADD COLUMN IF NOT EXISTS print_years_descending boolean,
            ADD COLUMN IF NOT EXISTS print_company_name character varying,
            ADD COLUMN IF NOT EXISTS print_show_page_numbers boolean,
            ADD COLUMN IF NOT EXISTS print_exclude_keys character varying
        """
    )


def _ensure_afg_line_merged_leaf_column(cr):
    if not _table_exists(cr, "audited_financial_line"):
        return
    cr.execute(
        """
        ALTER TABLE audited_financial_line
        ADD COLUMN IF NOT EXISTS merged_leaf_account_ids character varying
        """
    )


OLD_MODULE = "audited_financials"
NEW_MODULE = "audited_financials_saaskul"


def _adopt_old_module(cr):
    """Take over the records of the old technical name audited_financials.

    Without this, installing under the new name would create every menu, view and
    preset a second time. Records keep their ids, so data and links stay as they are.
    """
    cr.execute(
        "SELECT 1 FROM ir_module_module WHERE name = %s AND state IN ('installed', 'to upgrade', 'to remove')",
        [OLD_MODULE],
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE ir_model_data d
           SET module = %s
         WHERE d.module = %s
           AND NOT EXISTS (SELECT 1 FROM ir_model_data n WHERE n.module = %s AND n.name = d.name)
        """,
        [NEW_MODULE, OLD_MODULE, NEW_MODULE],
    )
    cr.execute(
        "UPDATE ir_ui_view SET key = %s || substr(key, %s) WHERE key LIKE %s",
        [NEW_MODULE + ".", len(OLD_MODULE) + 2, OLD_MODULE + ".%"],
    )
    if not get_module_path(OLD_MODULE, display_warning=False):
        # The old code is gone and all its records now belong to this module.
        cr.execute("UPDATE ir_module_module SET state = 'uninstalled' WHERE name = %s", [OLD_MODULE])
    if _table_exists(cr, "audited_financial_version"):
        # Data fix of the old 19.0.1.0.257 upgrade: statements use the company currency.
        cr.execute(
            """
            UPDATE audited_financial_version v
               SET currency_id = c.currency_id
              FROM res_company c
             WHERE c.id = v.company_id
               AND v.currency_id IS DISTINCT FROM c.currency_id
            """
        )


def _drop_legacy_student_loan_account_views(cr):
    """The first release of cpabooks_student_loan left chart of accounts views that use
    fields it no longer defines. Installing this module validates the account form with
    every view on top of it, so those views must go first. That module recreates its
    current views when it is upgraded.
    """
    cr.execute(
        """
        SELECT v.id
          FROM ir_ui_view v
          JOIN ir_model_data d
            ON d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = 'cpabooks_student_loan'
         WHERE v.model = 'account.account'
           AND NOT EXISTS (SELECT 1 FROM ir_ui_view child WHERE child.inherit_id = v.id)
           AND EXISTS (
                SELECT 1
                  FROM jsonb_each_text(v.arch_db) arch
                 WHERE arch.value ~ 'name="(closing_balance|cpabooks_school|cpabooks_control)"'
           )
        """
    )
    view_ids = [row[0] for row in cr.fetchall()]
    if view_ids:
        cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = ANY(%s)", [view_ids])
        cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", [view_ids])


def pre_init_hook(env):
    """Take over the old module, then drop stale relation tables left by a partial install."""
    cr = env.cr
    _adopt_old_module(cr)
    _drop_legacy_student_loan_account_views(cr)
    _ensure_afg_account_ctf_column(cr)
    _ensure_afg_version_print_columns(cr)
    _ensure_afg_line_merged_leaf_column(cr)
    if _table_exists(cr, "audited_financial_version"):
        return
    for table in _AFG_ORPHAN_REL_TABLES:
        cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % table)


def post_init_hook(env):
    import logging

    _logger = logging.getLogger(__name__)
    cr = env.cr
    _ensure_afg_version_print_columns(cr)
    _ensure_afg_line_merged_leaf_column(cr)

    if "account.account.type" in env:
        env["account.account.type"]._afg_ensure_standard_types()
    if "audited.financial.group" not in env:
        _logger.error(
            "audited_financials post_init: model audited.financial.group missing from registry."
        )
        return
    if "audited.financial.version" not in env:
        _logger.error(
            "audited_financials post_init: model audited.financial.version missing from registry."
        )
        return

    env["audited.financial.group"]._setup_default_afg_presets()
    if "audited.financial.ctf.group" in env:
        env["audited.financial.ctf.group"]._setup_default_ctf_groups()
    if "account.account" in env:
        env["account.account"]._cpa_apply_saved_ctf()
    env["audited.financial.version"]._afg_mirror_schedule_mappings()
    if "audited.financial.menu.cleanup" in env:
        env["audited.financial.menu.cleanup"].refresh_afg_menus()

# -*- coding: utf-8 -*-

from . import models
from . import controllers

# Orphaned after a failed/partial uninstall when the main version table was dropped.
_AFG_ORPHAN_REL_TABLES = (
    "audited_financial_version_company_rel",
    "audited_financial_version_report_col_rel",
)


def _mark_project_dashboard_odoo_for_upgrade(cr):
    """Ensure multico PL/BS report xmlids exist before AFG menus load."""
    cr.execute(
        """
        UPDATE ir_module_module
        SET state = 'to upgrade'
        WHERE name = 'project_dashboard_odoo'
          AND state = 'installed'
        """
    )


def _ensure_afg_account_ctf_column(cr):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'account_account'
        )
        """
    )
    if not cr.fetchone()[0]:
        return
    cr.execute(
        """
        ALTER TABLE account_account
        ADD COLUMN IF NOT EXISTS ctf_category character varying
        """
    )


def pre_init_hook(cr):
    """Drop stale M2M tables so reinstall can recreate FK constraints cleanly."""
    _ensure_afg_account_ctf_column(cr)
    _mark_project_dashboard_odoo_for_upgrade(cr)
    _ensure_afg_version_print_columns(cr)
    _ensure_afg_line_merged_leaf_column(cr)
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'audited_financial_version'
        )
        """
    )
    if cr.fetchone()[0]:
        return
    for table in _AFG_ORPHAN_REL_TABLES:
        cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % table)


def _ensure_afg_version_print_columns(cr):
    """Stale DBs (e.g. ctvt_03 on 14.0.1.0.147) miss columns the dashboard SELECT always reads."""
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'audited_financial_version'
        )
        """
    )
    if not cr.fetchone()[0]:
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
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'audited_financial_line'
        )
        """
    )
    if not cr.fetchone()[0]:
        return
    cr.execute(
        """
        ALTER TABLE audited_financial_line
        ADD COLUMN IF NOT EXISTS merged_leaf_account_ids character varying
        """
    )


def post_init_hook(cr, registry):
    import logging

    from odoo import api, SUPERUSER_ID

    _logger = logging.getLogger(__name__)
    _ensure_afg_version_print_columns(cr)
    _ensure_afg_line_merged_leaf_column(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})

    if "audited.financial.group" not in env:
        _logger.error(
            "cpabooks_audited_financial post_init: model audited.financial.group missing from registry. "
            "Restart Odoo and upgrade this module."
        )
        return
    if "audited.financial.version" not in env:
        _logger.error(
            "cpabooks_audited_financial post_init: model audited.financial.version missing from registry. "
            "Restart Odoo and upgrade this module."
        )
        return

    env["audited.financial.group"]._setup_default_afg_presets()
    if "audited.financial.ctf.group" in env:
        env["audited.financial.ctf.group"]._setup_default_ctf_groups()
    env["audited.financial.version"]._afg_mirror_schedule_mappings()

    if "audited.financial.menu.cleanup" in env:
        cleanup = env["audited.financial.menu.cleanup"]
        if not env.ref(
            "project_dashboard_odoo.account_financial_html_report_action_bs",
            raise_if_not_found=False,
        ):
            mod = env["ir.module.module"].search(
                [("name", "=", "project_dashboard_odoo"), ("state", "=", "installed")],
                limit=1,
            )
            if mod:
                mod.write({"state": "to upgrade"})
                _logger.warning(
                    "cpabooks_audited_financial: project_dashboard_odoo marked to upgrade; "
                    "upgrade it then upgrade cpabooks_audited_financial again for multico menus."
                )
        cleanup.refresh_afg_menus()

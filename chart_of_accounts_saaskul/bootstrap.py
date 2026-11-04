# -*- coding: utf-8 -*-
"""Ensure account_account CPABooks columns exist before registry serves ORM reads."""
import logging

from .hooks import _ensure_account_account_cpabooks_columns

_logger = logging.getLogger(__name__)

_REGISTRY_PATCH_DONE = False


def _coa_before_registry(db_name, cr, update_module=False):
    _ensure_account_account_cpabooks_columns(cr)


def patch_registry_schema_after_load():
    global _REGISTRY_PATCH_DONE
    if _REGISTRY_PATCH_DONE:
        return
    _REGISTRY_PATCH_DONE = True
    try:
        from odoo.addons.cpabooks_settings_extend.registry_guard import (
            register_before_registry_hook,
        )
    except ImportError:
        return
    register_before_registry_hook(
        _coa_before_registry,
        priority=35,
        owner='chart_of_accounts_saaskul',
    )


def apply_bootstraps():
    patch_registry_schema_after_load()

# -*- coding: utf-8 -*-
"""Recover blank Audited Financial screen from stale numeric action ids (e.g. 15088)."""

import logging
import re

from odoo import http
from odoo.addons.web.controllers.main import Action as WebAction
from odoo.http import request


_logger = logging.getLogger(__name__)

AFG_DASHBOARD_XMLID = "cpabooks_audited_financial.action_audited_financials_dashboard_client"
TRANSPORT_DASHBOARD_XMLID = "cpabooks_transport_dashboard.action_transport_dashboard"


class AfgActionLoadGuard(WebAction):
    """When /web/action/load gets a dead id, Odoo returns False → blank client.

    Bookmarks sometimes keep a corrupted / migrated id that no longer matches the
    live AFG dashboard id (e.g. 15088 after the real id moved to 936). Remap those
    to the live xmlid when the URL/menu is Audited Financial (or Transport).
    """

    def _cpabooks_menu_id_hint(self, additional_context=None):
        ctx = dict(additional_context or {})
        for key in ("menu_id", "afg_menu_id"):
            raw = ctx.get(key)
            if raw in (False, None, "", 0, "0"):
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        referer = request.httprequest.headers.get("Referer") or ""
        match = re.search(r"[#&?]menu_id[=:](\d+)", referer)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return None
        return None

    def _cpabooks_menu_name(self, menu_id):
        if not menu_id:
            return ""
        try:
            menu = request.env["ir.ui.menu"].browse(int(menu_id)).exists()
            return (menu.name or "") if menu else ""
        except Exception:
            return ""

    def _cpabooks_load_xmlid(self, xmlid, additional_context=None):
        try:
            return super(AfgActionLoadGuard, self).load(
                xmlid, additional_context=additional_context
            )
        except Exception as err:
            _logger.warning("afg_action_load_guard: remap %s failed: %s", xmlid, err)
            return False

    def _cpabooks_remap_dashboard(self, action_id, additional_context=None):
        env = request.env
        try:
            requested = int(action_id)
        except (TypeError, ValueError):
            requested = None

        menu_id = self._cpabooks_menu_id_hint(additional_context)
        menu_name = self._cpabooks_menu_name(menu_id).lower()

        candidates = (
            (AFG_DASHBOARD_XMLID, ("audited", "financial")),
            (TRANSPORT_DASHBOARD_XMLID, ("transport",)),
        )
        for xmlid, name_bits in candidates:
            dash = env.ref(xmlid, raise_if_not_found=False)
            if not dash:
                continue
            real_id = int(dash.id)
            id_hit = requested is not None and (
                requested == real_id
                or str(requested).startswith(str(real_id))
                or str(real_id).startswith(str(requested))
            )
            menu_hit = bool(menu_name) and all(bit in menu_name for bit in name_bits)
            # Dead bookmark id (e.g. 15088) while URL still has Audited Financial menu
            # → force live xmlid. Prefix match alone is not enough after id renumbers.
            if id_hit or menu_hit:
                remapped = self._cpabooks_load_xmlid(xmlid, additional_context)
                if remapped:
                    _logger.info(
                        "afg_action_load_guard: remapped action_id=%s → %s (menu_id=%s)",
                        action_id,
                        xmlid,
                        menu_id,
                    )
                    return remapped
        return False

    @http.route("/web/action/load", type="json", auth="user")
    def load(self, action_id, additional_context=None):
        try:
            value = super().load(action_id, additional_context=additional_context)
        except Exception as err:
            _logger.warning(
                "afg_action_load_guard: super load failed (action_id=%s): %s",
                action_id,
                err,
            )
            value = False
        if value:
            return value
        remapped = self._cpabooks_remap_dashboard(action_id, additional_context=additional_context)
        if remapped:
            return remapped
        if isinstance(action_id, str) and action_id in (
            AFG_DASHBOARD_XMLID,
            TRANSPORT_DASHBOARD_XMLID,
        ):
            return self._cpabooks_load_xmlid(action_id, additional_context)
        return value

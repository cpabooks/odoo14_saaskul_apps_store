# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure CAFM shell/dashboard assets stay active (sidebar + dashboard JS)."""
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET active = TRUE,
               write_date = (now() at time zone 'UTC')
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = 'cpabooks_cafm'
           AND d.name IN ('assets_backend', 'webclient_bootstrap_cafm_shell')
           AND v.active IS DISTINCT FROM TRUE
        """
    )
    if cr.rowcount:
        _logger.info(
            "CPABooks CAFM: reactivated %s backend asset view(s) for left sidebar shell",
            cr.rowcount,
        )
    # Force backend asset bundles to rebuild on next request.
    cr.execute(
        """
        DELETE FROM ir_attachment
         WHERE name LIKE 'web.assets_backend%%'
            OR url LIKE '/web/content/%%assets_backend%%'
        """
    )

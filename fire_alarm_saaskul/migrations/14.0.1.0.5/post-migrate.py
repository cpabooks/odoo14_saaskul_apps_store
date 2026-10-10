# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Point FAFF root/dashboard menus at the new client action; retire old act_window."""
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'fire_alarm_saaskul'
           AND name = 'action_faff_dashboard_client'
           AND model = 'ir.actions.client'
        """
    )
    row = cr.fetchone()
    if not row:
        _logger.info("FAFF: dashboard client action not found yet (will bind on XML load)")
        return
    client_id = row[0]
    cr.execute(
        """
        UPDATE ir_ui_menu m
           SET action = %s
          FROM ir_model_data d
         WHERE d.module = 'fire_alarm_saaskul'
           AND d.model = 'ir.ui.menu'
           AND d.res_id = m.id
           AND d.name IN ('menu_faff_root', 'menu_faff_dashboard')
        """,
        ("ir.actions.client,%s" % client_id,),
    )
    _logger.info("FAFF: dashboard menus bound to client action %s", client_id)

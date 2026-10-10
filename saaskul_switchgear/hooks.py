# -*- coding: utf-8 -*-

import logging

from odoo import api, SUPERUSER_ID
from odoo.tools import sql

_logger = logging.getLogger(__name__)

_LEGACY_DEMO_XMLIDS = (
    'group_switchgear_demo_admin',
    'view_switchgear_configuration_form',
)


def _unlink_module_xmlid(env, name, module='saaskul_switchgear'):
    rec = env.ref('%s.%s' % (module, name), raise_if_not_found=False)
    if not rec:
        return
    if rec._name == 'res.groups':
        env['ir.model.access'].sudo().search([
            ('group_id', '=', rec.id),
        ]).unlink()
    rec.unlink()


def _cleanup_orphan_switchgear_configuration_actions(env):
    """Remove server actions still bound to deleted switchgear.configuration model."""
    env.cr.execute("""
        SELECT s.id
        FROM ir_act_server s
        JOIN ir_model m ON m.id = s.model_id
        WHERE m.model = 'switchgear.configuration'
    """)
    action_ids = [row[0] for row in env.cr.fetchall()]
    if action_ids:
        env['ir.actions.server'].sudo().browse(action_ids).unlink()
        _logger.info(
            'saaskul_switchgear: removed %s orphan configuration action(s)',
            len(action_ids),
        )


def _cleanup_demo_setup(env):
    """Remove legacy demo loader; keep configuration menu (uses switchgear.dashboard)."""
    for name in _LEGACY_DEMO_XMLIDS:
        _unlink_module_xmlid(env, name)

    _cleanup_orphan_switchgear_configuration_actions(env)

    cr = env.cr
    if sql.table_exists(cr, 'switchgear_configuration'):
        cr.execute('DROP TABLE IF EXISTS switchgear_configuration CASCADE')
        _logger.info('saaskul_switchgear: dropped legacy switchgear_configuration table')

    for model_name in ('switchgear.configuration',):
        model = env['ir.model'].search([('model', '=', model_name)], limit=1)
        if not model:
            continue
        env['ir.model.access'].search([('model_id', '=', model.id)]).unlink()
        try:
            env['ir.model.data'].search([
                ('model', '=', 'ir.model'),
                ('res_id', '=', model.id),
            ]).unlink()
            model.unlink()
        except Exception as exc:
            # ir.model may still be referenced by module metadata; table drop is enough.
            _logger.warning(
                'saaskul_switchgear: kept ir.model %s (%s)',
                model_name,
                exc,
            )


def pre_init_hook(cr):
    """Drop orphan MRP system_admin views before switchgear MO inherits validate."""
    try:
        from odoo.addons.cpabooks_addons_issues.hooks import (
            _deactivate_orphan_mrp_system_admin_views,
        )
        _deactivate_orphan_mrp_system_admin_views(cr)
    except Exception:
        cr.execute(
            """
            SELECT 1
              FROM ir_module_module
             WHERE name IN ('cpabooks_sequences_mrp', 'cpabooks_dedicated_gp')
               AND state IN ('installed', 'to upgrade', 'to remove')
             LIMIT 1
            """
        )
        if cr.fetchone():
            return
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE
             WHERE model = 'mrp.production'
               AND COALESCE(active, TRUE) IS TRUE
               AND (
                    COALESCE(arch_db, '') ILIKE %s
                 OR name = 'mo.order.extend'
               )
            """,
            ('%system_admin%',),
        )
        if cr.rowcount:
            _logger.warning(
                'saaskul_switchgear: deactivated %s orphan '
                'mrp.production system_admin view(s)',
                cr.rowcount,
            )


def _ensure_switchgear_menu_visibility(env):
    """Root Switchgear app must be visible to internal users on Community home."""
    menu = env.ref(
        'saaskul_switchgear.menu_flowchart_kanban_root',
        raise_if_not_found=False,
    )
    user_group = env.ref('base.group_user', raise_if_not_found=False)
    flowchart = env.ref(
        'saaskul_switchgear.group_flowchart',
        raise_if_not_found=False,
    )
    if menu and user_group:
        menu.sudo().write({'groups_id': [(6, 0, [user_group.id])]})
    if user_group and flowchart and flowchart not in user_group.implied_ids:
        user_group.sudo().write({'implied_ids': [(4, flowchart.id)]})
        _logger.info(
            'saaskul_switchgear: base.group_user now implies group_flowchart',
        )


def _ensure_switchgear_web_ui_mode(env):
    """Keep sidebar mode on for Switchgear DBs (shell also works without it)."""
    icp = env['ir.config_parameter'].sudo()
    icp.set_param('app_web_ui_mode', 'switchgear')
    _logger.info('saaskul_switchgear: set app_web_ui_mode=switchgear')


def post_init_hook(cr, registry):
    """Remove broken menus and legacy demo setup records."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        from odoo.addons.cpabooks_admin_power.user_menu_rules import (
            migrate_legacy_user_permission_groups,
        )
        migrate_legacy_user_permission_groups(env)
    except ImportError:
        _logger.debug(
            'saaskul_switchgear: cpabooks_admin_power not loaded for group migration',
        )
    cr.execute("DELETE FROM ir_ui_menu WHERE name IS NULL OR name = ''")
    if cr.rowcount:
        _logger.info(
            'saaskul_switchgear: removed %s broken menu row(s)',
            cr.rowcount,
        )
    demo_mod = env['ir.module.module'].search([('name', '=', 'cpabooks_demo_data')], limit=1)
    if demo_mod and demo_mod.state in ('to install', 'to upgrade'):
        demo_mod.write({'state': 'uninstalled'})
        _logger.info(
            'saaskul_switchgear: reset cpabooks_demo_data to uninstalled (deprecated)',
        )
    _cleanup_demo_setup(env)
    _ensure_switchgear_menu_visibility(env)
    _ensure_switchgear_web_ui_mode(env)

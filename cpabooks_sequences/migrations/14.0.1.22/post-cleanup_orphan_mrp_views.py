# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

_ORPHAN_XMLIDS = (
    ('cpabooks_sequences', 'mo_order_extend'),
    ('cpabooks_sequences', 'mrp_bom_form_view_inherit_switchgear_custom'),
)


def _unlink_views_safe(View, views):
    """Delete inherited child views before parents (ir_ui_view inherit_id FK)."""
    views = views.exists()
    if not views:
        return 0
    children = View.search([('inherit_id', 'in', views.ids)])
    removed = _unlink_views_safe(View, children)
    removed += len(views)
    views.unlink()
    return removed


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    sequences_mrp = env['ir.module.module'].search(
        [('name', '=', 'cpabooks_sequences_mrp')], limit=1
    )
    View = env['ir.ui.view'].sudo()
    Imd = env['ir.model.data'].sudo()

    if sequences_mrp.state == 'installed':
        for module, name in _ORPHAN_XMLIDS:
            orphan = Imd.search([
                ('module', '=', module),
                ('name', '=', name),
                ('model', '=', 'ir.ui.view'),
            ], limit=1)
            if not orphan:
                continue
            canonical = Imd.search([
                ('module', '=', 'cpabooks_sequences_mrp'),
                ('name', '=', name),
                ('model', '=', 'ir.ui.view'),
            ], limit=1)
            if canonical and orphan.res_id != canonical.res_id:
                _unlink_views_safe(View, View.browse(orphan.res_id))
                orphan.unlink()
            elif not canonical:
                orphan.write({'module': 'cpabooks_sequences_mrp'})
        return

    removed = 0
    for module, name in _ORPHAN_XMLIDS:
        orphan = Imd.search([
            ('module', '=', module),
            ('name', '=', name),
        ], limit=1)
        if orphan and orphan.model == 'ir.ui.view':
            removed += _unlink_views_safe(View, View.browse(orphan.res_id))
        if orphan:
            orphan.unlink()

    extra = View.search([
        ('name', '=', 'mo.order.extend'),
        ('model', '=', 'mrp.production'),
    ])
    if extra:
        removed += _unlink_views_safe(View, extra)

    if removed:
        _logger.info(
            'CPABooks Sequences: removed %s orphan MRP view(s) '
            '(cpabooks_sequences_mrp not installed)',
            removed,
        )

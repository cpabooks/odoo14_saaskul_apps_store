# -*- coding: utf-8 -*-


def mrp_installed(env):
    """True when the Manufacturing (mrp) app is installed."""
    return bool(
        env['ir.module.module'].sudo().search_count([
            ('name', '=', 'mrp'),
            ('state', '=', 'installed'),
        ])
    )

MRP_SEQUENCE_FOR = frozenset({'bom', 'manufacturing'})

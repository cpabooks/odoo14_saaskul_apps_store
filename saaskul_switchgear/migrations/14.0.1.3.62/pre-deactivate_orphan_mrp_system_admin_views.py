# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    try:
        from odoo.addons.cpabooks_addons_issues.hooks import (
            _deactivate_orphan_mrp_system_admin_views,
        )
        _deactivate_orphan_mrp_system_admin_views(cr)
    except Exception:
        from odoo.addons.saaskul_switchgear.hooks import pre_init_hook
        pre_init_hook(cr)
    _logger.info(
        'saaskul_switchgear 3.62 pre: orphan mrp system_admin views cleaned',
    )

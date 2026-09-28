# -*- coding: utf-8 -*-

import logging
import sys

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def reload_python_module(module_name):
    """Force Odoo to re-import a module on upgrade (Apps UI keeps stale Python)."""
    import odoo.modules.module as mod_module
    from odoo import models

    if module_name in mod_module.loaded:
        mod_module.loaded.remove(module_name)
    prefix = 'odoo.addons.%s' % module_name
    for key in list(sys.modules.keys()):
        if key == prefix or key.startswith(prefix + '.'):
            del sys.modules[key]
    models.MetaModel.module_to_models.pop(module_name, None)
    _logger.info('CPABooks CAFM: cleared Python cache for %s before upgrade', module_name)


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    manager_group = env.ref('cpabooks_cafm.group_cafm_manager', raise_if_not_found=False)
    if manager_group:
        users = env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        manager_group.write({'users': [(4, user.id) for user in users]})
    if 'cpabooks.cafm.amc.invoice.reg' in env:
        env['cpabooks.cafm.amc.invoice.reg'].ensure_amc_follow_up_users()

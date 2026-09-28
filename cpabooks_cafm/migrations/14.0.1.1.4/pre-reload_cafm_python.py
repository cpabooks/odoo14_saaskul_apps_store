# -*- coding: utf-8 -*-
import logging
import sys

_logger = logging.getLogger(__name__)


def _reload_python_module(module_name):
    import odoo.modules.module as mod_module
    from odoo import models

    if module_name in mod_module.loaded:
        mod_module.loaded.remove(module_name)
    prefix = 'odoo.addons.%s' % module_name
    for key in list(sys.modules.keys()):
        if key == prefix or key.startswith(prefix + '.'):
            del sys.modules[key]
    models.MetaModel.module_to_models.pop(module_name, None)


def migrate(cr, version):
    _reload_python_module('cpabooks_cafm')
    import odoo.addons.cpabooks_cafm  # noqa: F401 — re-register models after cache clear
    _logger.info('cpabooks_cafm %s: pre-reload Python module for new CAFM models', version)

# -*- coding: utf-8 -*-
import logging

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.tools import config
from odoo.addons.web.controllers.database import Database

_logger = logging.getLogger(__name__)

UNLOCK_OPTION = 'db_manager_unlock'


def _manager_unlocked():
    """The database manager stays blocked unless the server config says
    ``db_manager_unlock = True`` (in odoo.conf / odoo-server.conf)."""
    value = config.get(UNLOCK_OPTION)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _blocked(route):
    _logger.info('Database manager route %s blocked (set %s = True to allow).', route, UNLOCK_OPTION)
    raise NotFound()


class LockedDatabase(Database):

    @http.route('/web/database/selector', type='http', auth="none")
    def selector(self, **kw):
        if not _manager_unlocked():
            _blocked('/web/database/selector')
        return super().selector(**kw)

    @http.route('/web/database/manager', type='http', auth="none")
    def manager(self, **kw):
        if not _manager_unlocked():
            _blocked('/web/database/manager')
        return super().manager(**kw)

    @http.route('/web/database/create', type='http', auth="none", methods=['POST'], csrf=False)
    def create(self, master_pwd, name, lang, password, **post):
        if not _manager_unlocked():
            _blocked('/web/database/create')
        return super().create(master_pwd, name, lang, password, **post)

    @http.route('/web/database/duplicate', type='http', auth="none", methods=['POST'], csrf=False)
    def duplicate(self, master_pwd, name, new_name, neutralize_database=False):
        if not _manager_unlocked():
            _blocked('/web/database/duplicate')
        return super().duplicate(master_pwd, name, new_name, neutralize_database=neutralize_database)

    @http.route('/web/database/drop', type='http', auth="none", methods=['POST'], csrf=False)
    def drop(self, master_pwd, name):
        if not _manager_unlocked():
            _blocked('/web/database/drop')
        return super().drop(master_pwd, name)

    @http.route('/web/database/backup', type='http', auth="none", methods=['POST'], csrf=False)
    def backup(self, master_pwd, name, backup_format='zip', filestore=True):
        if not _manager_unlocked():
            _blocked('/web/database/backup')
        return super().backup(master_pwd, name, backup_format=backup_format, filestore=filestore)

    @http.route('/web/database/restore', type='http', auth="none", methods=['POST'], csrf=False,
                max_content_length=None)
    def restore(self, master_pwd, backup_file, name, copy=False, neutralize_database=False):
        if not _manager_unlocked():
            _blocked('/web/database/restore')
        return super().restore(master_pwd, backup_file, name, copy=copy,
                               neutralize_database=neutralize_database)

    @http.route('/web/database/change_password', type='http', auth="none", methods=['POST'], csrf=False)
    def change_password(self, master_pwd, master_pwd_new):
        if not _manager_unlocked():
            _blocked('/web/database/change_password')
        return super().change_password(master_pwd, master_pwd_new)

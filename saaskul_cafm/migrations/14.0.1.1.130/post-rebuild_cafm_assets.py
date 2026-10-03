# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_attachment
         WHERE name LIKE 'web.assets_backend%%'
            OR url LIKE '/web/content/%%assets_backend%%'
        """
    )

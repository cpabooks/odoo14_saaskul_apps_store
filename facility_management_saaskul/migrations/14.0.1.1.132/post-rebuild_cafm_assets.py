# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_attachment
         WHERE name LIKE 'web.assets_backend%%'
            OR url LIKE '/web/content/%%assets_backend%%'
        """
    )

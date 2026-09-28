# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_attachment
        WHERE url LIKE '/web/content/%'
          AND (
              name LIKE '%assets%'
              OR url LIKE '%/web/assets/%'
              OR url LIKE '%cafm_dashboard%'
          )
        """
    )
    _logger.info(
        'cpabooks_cafm %s: bust cached dashboard QWeb/assets (cafm_dashboard_main.xml)',
        version,
    )

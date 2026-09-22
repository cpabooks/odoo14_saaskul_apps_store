# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Do NOT leave arch empty — NULL arch breaks inheritance while upgrading
    # unrelated modules (XMLSyntaxError: Document is empty).
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET arch_fs = NULL
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = 'cpabooks_sequences'
           AND d.name = 'sale_order_extend'
        """
    )
    if cr.rowcount:
        _logger.info('cpabooks_sequences 42: cleared sale_order_extend arch_fs only')

# -*- coding: utf-8 -*-
"""Restore sale_order_extend after 14.0.1.42 left arch_db NULL (breaks other module upgrades)."""
import logging

_logger = logging.getLogger(__name__)

_ARCH = """<?xml version="1.0"?>
<data>
    <field name="name" position="attributes">
        <attribute name="readonly">0</attribute>
    </field>
    <field name="name" position="attributes">
        <attribute name="attrs">{'readonly': [('system_admin', '=', False)]}</attribute>
    </field>
    <field name="name" position="after">
        <field name="system_admin" invisible="1"/>
    </field>
</data>
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET arch_db = %s,
               arch_fs = 'cpabooks_sequences/views/sale_order.xml'
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = 'cpabooks_sequences'
           AND d.name = 'sale_order_extend'
           AND (v.arch_db IS NULL OR btrim(v.arch_db::text) = '')
        """,
        (_ARCH,),
    )
    if cr.rowcount:
        _logger.info(
            'cpabooks_sequences 1.50: restored sale_order_extend arch on %s row(s)',
            cr.rowcount,
        )

# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Keep Process Flow AMC / VAR menu labels in sync after XML refresh."""
    renames = [
        ("cpabooks_cafm.menu_cafm_guide_organogram", "Process Flow AMC"),
        ("cpabooks_cafm.menu_cafm_guide_process_cycle", "Process Flow VAR"),
        ("cpabooks_cafm.menu_cafm_guide_amc_wizard", "AMC / VAR Wizard"),
    ]
    for xmlid, name in renames:
        module, _, name_xml = xmlid.partition(".")
        cr.execute(
            """
            UPDATE ir_ui_menu m
               SET name = %s,
                   active = true
              FROM ir_model_data d
             WHERE d.model = 'ir.ui.menu'
               AND d.res_id = m.id
               AND d.module = %s
               AND d.name = %s
            """,
            (name, module, name_xml),
        )
        if cr.rowcount:
            _logger.info("CAFM: renamed menu %s → %s", xmlid, name)

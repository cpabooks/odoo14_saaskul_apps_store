# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Reload project_dashboard_odoo multico report data before AFG menus wire up."""
    cr.execute(
        """
        UPDATE ir_module_module
        SET state = 'to upgrade'
        WHERE name = 'project_dashboard_odoo'
          AND state = 'installed'
        """
    )

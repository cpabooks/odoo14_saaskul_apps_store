# -*- coding: utf-8 -*-
"""Force slim AMC Register tree; clear customs so Congested columns cannot stick."""


def migrate(cr, version):
    # Drop saved view customs for AMC tree
    cr.execute(
        """
        DELETE FROM ir_ui_view_custom
         WHERE ref_id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'saaskul_cafm'
               AND name = 'view_saaskul_cafm_amc_tree'
         )
        """
    )
    # Also clear any leftover user-defined list view prefs if table exists
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'ir_ui_view_custom'
        """
    )

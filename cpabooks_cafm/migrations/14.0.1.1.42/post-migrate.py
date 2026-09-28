# -*- coding: utf-8 -*-
"""Remove leftover GFS Staff master UI/model after reverting to res.users."""


def migrate(cr, version):
    if not version:
        return
    # Drop obsolete XML data (menu/action/views/access) if still present.
    cr.execute(
        """
        DELETE FROM ir_ui_menu
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'menu_cafm_master_gfs_staff'
               AND model = 'ir.ui.menu'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_act_window
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'action_cpabooks_cafm_gfs_staff'
               AND model = 'ir.actions.act_window'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name IN (
                    'view_cpabooks_cafm_gfs_staff_tree',
                    'view_cpabooks_cafm_gfs_staff_form'
               )
               AND model = 'ir.ui.view'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_access
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'access_cpabooks_cafm_gfs_staff'
               AND model = 'ir.model.access'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'cpabooks_cafm'
           AND name IN (
                'menu_cafm_master_gfs_staff',
                'action_cpabooks_cafm_gfs_staff',
                'view_cpabooks_cafm_gfs_staff_tree',
                'view_cpabooks_cafm_gfs_staff_form',
                'access_cpabooks_cafm_gfs_staff',
                'model_cpabooks_cafm_gfs_staff'
           )
        """
    )
    # Drop obsolete model registry row + table if present.
    cr.execute("DELETE FROM ir_model WHERE model = 'cpabooks.cafm.gfs.staff'")
    cr.execute("DROP TABLE IF EXISTS cpabooks_cafm_gfs_staff CASCADE")

# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view
           SET mode = 'extension'
         WHERE id IN (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'view_cpabooks_cafm_amc_invoice_tree'
               AND model = 'ir.ui.view'
         )
        """
    )
    cr.execute(
        """
        UPDATE ir_act_window
           SET view_id = (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'account'
               AND name = 'view_invoice_tree'
               AND model = 'ir.ui.view'
         )
         WHERE id IN (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'action_cpabooks_cafm_amc_invoices'
               AND model = 'ir.actions.act_window'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_attachment
         WHERE name LIKE 'web.assets_backend%%'
            OR url LIKE '/web/content/%%assets_backend%%'
        """
    )

# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'facility_management_saaskul'
               AND name = 'view_saaskul_cafm_contract_order_form_sale'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'facility_management_saaskul'
           AND name = 'view_saaskul_cafm_contract_order_form_sale'
        """
    )

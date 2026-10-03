# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    obsolete_view = env.ref(
        'cpabooks_cafm.view_cpabooks_cafm_contract_order_form_sale',
        raise_if_not_found=False,
    )
    if obsolete_view:
        obsolete_view.unlink()

    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'cpabooks_cafm_contract_order'
           AND column_name = 'sale_order_id'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE cpabooks_cafm_contract_order
               SET sale_order_id = NULL
             WHERE sale_order_id IS NOT NULL
            """
        )

    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'sale_order'
           AND column_name = 'cafm_contract_order_id'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE sale_order
               SET cafm_contract_order_id = NULL
             WHERE cafm_contract_order_id IS NOT NULL
            """
        )

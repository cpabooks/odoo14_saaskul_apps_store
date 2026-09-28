# -*- coding: utf-8 -*-
"""Recompute Next Invoice labels (Mon YYYY) and drop stale AMC tree customs."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'cpabooks_cafm_contract'
          AND column_name = 'next_invoice_label'
        """
    )
    if not cr.fetchone():
        return

    # Drop saved optional-column overrides so slim default columns apply.
    cr.execute(
        """
        DELETE FROM ir_ui_view_custom
         WHERE ref_id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'cpabooks_cafm'
               AND name = 'view_cpabooks_cafm_amc_tree'
         )
        """
    )

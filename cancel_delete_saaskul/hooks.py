# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Do not add these to depends. Do not uninstall them from post_init (nested
# Registry.new during install causes long hangs and m2m setup TypeError).
CPA_CD_OLD_CANCEL_MODULES = [
    "cpabooks_all_cancel_extend",
    "bi_order_cancel_all",
    "dev_picking_cancel",
    "om_mass_confirm_cancel",
    "acc_invoice_payment_cancel_app",
    "bi_inventory_adjustment_cancel_reverse",
    "eq_payslip_cancel",
    "stock_picking_cancel_extended",
    "pos_order_cancel",
]


def post_init_hook(cr, registry):
    """Drop the old cancel apps once the global module is in place."""
    cr.execute(
        """
        DELETE FROM ir_module_module_dependency d
         USING ir_module_module m
         WHERE d.module_id = m.id
           AND m.name = 'stock_no_negative'
           AND d.name = 'stock_picking_cancel_extended'
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    Module = env["ir.module.module"].sudo()
    still = Module.search([
        ("name", "in", CPA_CD_OLD_CANCEL_MODULES),
        ("state", "=", "installed"),
    ])
    if still:
        _logger.info(
            "cancel_delete_saaskul: uninstalling old cancel apps: %s",
            ", ".join(still.mapped("name")),
        )
        still.button_uninstall()

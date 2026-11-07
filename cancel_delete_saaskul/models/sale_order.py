# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        orders = self._cpa_cd_target()
        for order in orders:
            if order.state != "cancel":
                order.with_context(**self._cpa_cd_ctx()).action_cancel()
            order._cpa_cd_chatter(_("Cancel: document cancelled."))
        return orders._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        orders = self._cpa_cd_target()
        for order in orders:
            names = order.order_line.mapped("name")
            order.order_line.with_context(**self._cpa_cd_ctx()).unlink()
            if order.state != "cancel":
                order.with_context(**self._cpa_cd_ctx()).action_cancel()
            order._cpa_cd_chatter(
                _("Cancel - Lines: removed %s line(s): %s")
                % (len(names), ", ".join(names[:20]))
            )
        return orders._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        orders = self._cpa_cd_target()
        invoices = orders.mapped("invoice_ids")
        payments = self._cpa_cd_payments_from_moves(invoices)
        self._cpa_cd_force_cancel_payment(payments)
        self._cpa_cd_force_cancel_move(invoices)
        pickings = orders.mapped("picking_ids").filtered(lambda p: p.state != "cancel")
        if pickings:
            pickings.action_cpa_cd_cancel()
        for order in orders:
            if order.state != "cancel":
                order.with_context(**self._cpa_cd_ctx()).action_cancel()
            order._cpa_cd_chatter(_("Cancel - Linked Docs: sale, deliveries, invoices, payments."))
        return orders._cpa_cd_web_action()

    def action_cpa_cd_confirm_post(self):
        orders = self._cpa_cd_target()
        for order in orders:
            if order.state in ("draft", "sent"):
                order.action_confirm()
        return orders._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected sale document(s)?"),
        )

    def _cpa_cd_delete_do(self):
        orders = self._cpa_cd_target()
        orders.action_cpa_cd_cancel()
        leftover = orders.exists()
        leftover.with_context(**self._cpa_cd_ctx()).unlink()
        return leftover._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_linked_do",
            _("Delete sale and linked deliveries, invoices, payments?"),
        )

    def _cpa_cd_delete_linked_do(self):
        orders = self._cpa_cd_target()
        invoices = orders.mapped("invoice_ids")
        payments = orders._cpa_cd_payments_from_moves(invoices)
        pickings = orders.mapped("picking_ids")
        orders._cpa_cd_force_cancel_payment(payments)
        payments.sudo().unlink()
        orders._cpa_cd_delete_moves(invoices)
        if pickings:
            pickings.action_cpa_cd_cancel()
            pickings.sudo().unlink()
        leftover = orders.exists()
        leftover.action_cpa_cd_cancel()
        leftover = leftover.exists()
        leftover.with_context(**self._cpa_cd_ctx()).unlink()
        return leftover._cpa_cd_web_action()

    def unlink(self):
        if self.env.context.get("force_delete") or self.env.context.get("force_quotation_delete"):
            blocked = self.filtered(lambda o: o.state not in ("draft", "cancel"))
            if blocked:
                blocked.sudo().write({"state": "cancel"})
        return super().unlink()

    def action_cpa_cd_reset_draft(self):
        orders = self._cpa_cd_target()
        for order in orders:
            if order.state == "cancel":
                order.action_draft()
            order._cpa_cd_chatter(_("Reset to Draft."))
        return orders._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        pickings = self._cpa_cd_target().mapped("picking_ids").filtered(lambda p: p.state == "done")
        if not pickings:
            raise UserError(_("No done delivery to reverse. Confirm and deliver first."))
        return pickings.action_cpa_cd_reverse()

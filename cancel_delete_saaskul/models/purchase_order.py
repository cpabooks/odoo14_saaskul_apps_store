# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        orders = self._cpa_cd_target()
        for order in orders:
            if order.state != "cancel":
                order.with_context(**self._cpa_cd_ctx()).button_cancel()
            order._cpa_cd_chatter(_("Cancel: document cancelled."))
        return orders._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        for order in self:
            names = order.order_line.mapped("name")
            order.order_line.unlink()
            if order.state != "cancel":
                order.button_cancel()
            order._cpa_cd_chatter(
                _("Cancel - Lines: removed %s line(s).") % len(names)
            )
        return self._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        invoices = self.mapped("invoice_ids")
        payments = self._cpa_cd_payments_from_moves(invoices)
        self._cpa_cd_force_cancel_payment(payments)
        self._cpa_cd_force_cancel_move(invoices)
        pickings = self.mapped("picking_ids").filtered(lambda p: p.state != "cancel")
        if pickings:
            pickings.action_cpa_cd_cancel()
        self.action_cpa_cd_cancel()
        self._cpa_cd_chatter(_("Cancel - Linked Docs: purchase, receipts, bills, payments."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_confirm_post(self):
        for order in self:
            if order.state in ("draft", "sent", "to approve"):
                order.button_confirm()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected purchase document(s)?"),
        )

    def _cpa_cd_delete_do(self):
        self.action_cpa_cd_cancel()
        leftover = self.exists()
        leftover.with_context(**self._cpa_cd_ctx()).unlink()
        return leftover._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_linked_do",
            _("Delete purchase and linked receipts, bills, payments?"),
        )

    def _cpa_cd_delete_linked_do(self):
        invoices = self.mapped("invoice_ids")
        payments = self._cpa_cd_payments_from_moves(invoices)
        pickings = self.mapped("picking_ids")
        self._cpa_cd_force_cancel_payment(payments)
        payments.sudo().unlink()
        self._cpa_cd_delete_moves(invoices)
        if pickings:
            pickings.action_cpa_cd_cancel()
            pickings.sudo().unlink()
        orders = self._cpa_cd_target()
        orders.action_cpa_cd_cancel()
        leftover = orders.exists()
        leftover.with_context(**self._cpa_cd_ctx()).unlink()
        return leftover._cpa_cd_web_action()

    def unlink(self):
        if self.env.context.get("force_delete") or self.env.context.get("force_quotation_delete"):
            blocked = self.filtered(lambda o: o.state != "cancel")
            if blocked:
                blocked.sudo().write({"state": "cancel"})
        return super().unlink()

    def action_cpa_cd_reset_draft(self):
        for order in self:
            if order.state == "cancel":
                order.button_draft()
            order._cpa_cd_chatter(_("Reset to Draft."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        pickings = self.mapped("picking_ids").filtered(lambda p: p.state == "done")
        if not pickings:
            raise UserError(_("No done receipt to reverse."))
        return pickings.action_cpa_cd_reverse()

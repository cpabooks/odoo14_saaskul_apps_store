# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        moves = self._cpa_cd_target()
        moves._cpa_cd_force_cancel_move(moves)
        moves._cpa_cd_chatter(_("Cancel: entry cancelled."))
        return moves._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        moves = self._cpa_cd_target()
        moves._cpa_cd_remove_move_lines_and_cancel(moves)
        moves._cpa_cd_chatter(_("Cancel - Lines: amounts cleared, lines scratched, document cancelled."))
        return moves._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        moves = self._cpa_cd_target()
        payments = moves._cpa_cd_payments_from_moves(moves)
        moves._cpa_cd_force_cancel_payment(payments)
        moves._cpa_cd_force_cancel_move(moves)
        origin_orders = moves.mapped("invoice_line_ids.sale_line_ids.order_id")
        pickings = origin_orders.mapped("picking_ids")
        if pickings:
            pickings.filtered(lambda p: p.state != "cancel").action_cpa_cd_cancel()
        moves._cpa_cd_chatter(_("Cancel - Linked Docs: invoice/bill and payments."))
        return moves._cpa_cd_web_action()

    def action_cpa_cd_confirm_post(self):
        moves = self._cpa_cd_target()
        draft = moves.filtered(lambda m: m.state == "draft")
        if draft:
            draft.action_post()
        return moves._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected invoice / bill / entry?"),
        )

    def _cpa_cd_delete_do(self):
        moves = self._cpa_cd_target()
        moves._cpa_cd_delete_moves(moves)
        return moves._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_linked_do",
            _("Delete invoice/bill and linked payments?"),
        )

    def _cpa_cd_delete_linked_do(self):
        moves = self._cpa_cd_target()
        payments = moves._cpa_cd_payments_from_moves(moves)
        moves._cpa_cd_force_cancel_payment(payments)
        payments.sudo().unlink()
        moves._cpa_cd_delete_moves(moves)
        return moves._cpa_cd_web_action()

    def action_cpa_cd_reset_draft(self):
        moves = self._cpa_cd_target()
        for move in moves:
            if move.state == "posted":
                moves._cpa_cd_force_cancel_move(move)
            if move.state == "cancel":
                moves._cpa_cd_force_button_draft(move)
            move._cpa_cd_chatter(_("Reset to Draft."))
        return moves._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        posted = self._cpa_cd_target().filtered(lambda m: m.state == "posted")
        if not posted:
            raise UserError(_("Reverse needs a posted entry."))
        return posted[0].action_reverse()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    cpa_cd_scratched = fields.Boolean(string="Scratched", copy=False)

    def _auto_init(self):
        res = super()._auto_init()
        self.env.cr.execute(
            "ALTER TABLE account_move_line "
            "ADD COLUMN IF NOT EXISTS cpa_cd_scratched boolean"
        )
        return res

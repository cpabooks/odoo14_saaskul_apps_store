# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "cpa.cancel.delete.mixin"]
    _cpa_cd_hidden_header_buttons = ("action_cancel",)

    def action_cpa_cd_cancel(self):
        pickings = self._cpa_cd_target()
        for picking in pickings:
            if picking.state == "done":
                picking._cpa_cd_cancel_done()
            elif picking.state != "cancel":
                picking.action_cancel()
            picking._cpa_cd_chatter(_("Cancel: picking cancelled."))
        return pickings._cpa_cd_web_action()

    def _cpa_cd_cancel_done(self):
        """Undo done stock by returning, then cancel origin if still open."""
        self.ensure_one()
        Return = self.env["stock.return.picking"]
        wiz = Return.with_context(
            active_id=self.id,
            active_ids=self.ids,
            active_model="stock.picking",
        ).create({"picking_id": self.id})
        # Odoo 19 return lines start at 0: return everything that was done.
        for line in wiz.product_return_moves:
            line.quantity = line.move_id.quantity
        result = wiz.action_create_returns()
        ret = self.browse(result.get("res_id"))
        if ret:
            if ret.state == "draft":
                ret.action_confirm()
            if ret.state in ("confirmed", "assigned", "waiting"):
                ret.action_assign()
            for move in ret.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            ret.with_context(skip_backorder=True).button_validate()
        moves = self.env["account.move"].search([("ref", "=", self.name)])
        self._cpa_cd_force_cancel_move(moves)
        if self.state != "cancel":
            # The return above moved the stock back. Odoo refuses to cancel done
            # moves, so mark the original moves cancelled directly.
            self.move_ids.filtered(lambda m: m.state == "done").sudo().write({"state": "cancel"})
            if self.state != "cancel":
                try:
                    with self.env.cr.savepoint():
                        self.action_cancel()
                except Exception:
                    self.move_ids.sudo().write({"state": "cancel"})

    def action_cpa_cd_cancel_lines(self):
        for picking in self:
            if picking.state == "done":
                raise UserError(_("Cancel lines on a done picking is not allowed. Use Reverse or Cancel."))
            picking.move_ids.with_context(force_delete=True)._action_cancel()
            picking.move_ids.unlink()
            if picking.state != "cancel":
                picking.action_cancel()
            picking._cpa_cd_chatter(_("Cancel - Lines: stock moves removed."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        for picking in self:
            moves = self.env["account.move"].search([("ref", "=", picking.name)])
            self._cpa_cd_force_cancel_move(moves)
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_confirm_post(self):
        for picking in self:
            if picking.state == "draft":
                picking.action_confirm()
            if picking.state in ("confirmed", "waiting", "assigned"):
                picking.action_assign()
                for move in picking.move_ids:
                    if not move.quantity:
                        move.quantity = move.product_uom_qty
                    move.picked = True
                result = picking.with_context(skip_backorder=True).button_validate()
                if isinstance(result, dict):
                    return result
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected picking(s)?"),
        )

    def _cpa_cd_delete_do(self):
        pickings = self._cpa_cd_target()
        pickings.action_cpa_cd_cancel()
        kept = pickings._cpa_cd_unlink_pickings(pickings)
        return pickings._cpa_cd_kept_notification(kept) or pickings._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_linked_do",
            _("Delete picking and linked journal items?"),
        )

    def _cpa_cd_delete_linked_do(self):
        for picking in self:
            moves = self.env["account.move"].search([("ref", "=", picking.name)])
            self._cpa_cd_delete_moves(moves)
        pickings = self._cpa_cd_target()
        pickings.action_cpa_cd_cancel()
        kept = pickings._cpa_cd_unlink_pickings(pickings)
        return pickings._cpa_cd_kept_notification(kept) or pickings._cpa_cd_web_action()

    def action_cpa_cd_reset_draft(self):
        for picking in self:
            if picking.state == "cancel":
                picking.move_ids.write({"state": "draft"})
                picking.write({"state": "draft"})
            picking._cpa_cd_chatter(_("Reset to Draft."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        done = self.filtered(lambda p: p.state == "done")
        if not done:
            raise UserError(_("Reverse needs a done picking."))
        picking = done[0]
        return {
            "name": _("Reverse"),
            "type": "ir.actions.act_window",
            "res_model": "stock.return.picking",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_id": picking.id,
                "active_ids": picking.ids,
                "active_model": "stock.picking",
            },
        }

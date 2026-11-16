# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "cpa.cancel.delete.mixin"]

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
        ).create({})
        if hasattr(wiz, "_onchange_picking_id"):
            wiz._onchange_picking_id()
        result = wiz.create_returns()
        ret = self.browse(result.get("res_id"))
        if ret:
            if ret.state == "draft":
                ret.action_confirm()
            if ret.state in ("confirmed", "assigned", "waiting"):
                ret.action_assign()
            try:
                ret.with_context(skip_immediate=True, skip_backorder=True).button_validate()
            except Exception:
                ret.button_validate()
        moves = self.env["account.move"].search([("ref", "=", self.name)])
        self._cpa_cd_force_cancel_move(moves)
        if self.state != "cancel":
            try:
                self.action_cancel()
            except Exception:
                self.write({"state": "cancel"})

    def action_cpa_cd_cancel_lines(self):
        for picking in self:
            if picking.state == "done":
                raise UserError(_("Cancel lines on a done picking is not allowed. Use Reverse or Cancel."))
            picking.move_lines.unlink()
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
            if picking.state in ("confirmed", "waiting", "assigned", "partially_available"):
                picking.action_assign()
                try:
                    picking.with_context(skip_immediate=True, skip_backorder=True).button_validate()
                except Exception:
                    picking.button_validate()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected picking(s)?"),
        )

    def _cpa_cd_delete_do(self):
        self.action_cpa_cd_cancel()
        self.unlink()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_linked_do",
            _("Delete picking and linked journal items?"),
        )

    def _cpa_cd_delete_linked_do(self):
        for picking in self:
            moves = self.env["account.move"].search([("ref", "=", picking.name)])
            self._cpa_cd_delete_moves(moves)
        self.action_cpa_cd_cancel()
        self.unlink()
        return self._cpa_cd_web_action()

    def action_cpa_cd_reset_draft(self):
        for picking in self:
            if picking.state == "cancel":
                picking.move_lines.write({"state": "draft"})
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

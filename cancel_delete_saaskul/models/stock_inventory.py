# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockInventory(models.Model):
    _name = "stock.inventory"
    _inherit = ["stock.inventory", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        for inv in self:
            if inv.state == "done" and inv.move_ids:
                try:
                    inv.move_ids._action_cancel()
                except Exception:
                    inv.move_ids.write({"state": "cancel"})
            inv.write({"state": "cancel"})
            inv._cpa_cd_chatter(_("Cancel: inventory adjustment cancelled."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        for inv in self:
            if inv.state == "done":
                raise UserError(_("Use Reverse or Cancel on a validated inventory."))
            inv.line_ids.unlink()
            inv.write({"state": "cancel"})
            inv._cpa_cd_chatter(_("Cancel - Lines: inventory lines removed."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        for inv in self:
            moves = self.env["account.move"]
            if inv.move_ids:
                moves = self.env["account.move"].search([
                    ("stock_move_id", "in", inv.move_ids.ids),
                ])
            self._cpa_cd_force_cancel_move(moves)
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_confirm_post(self):
        for inv in self:
            if inv.state == "draft":
                inv.action_start()
            if inv.state == "confirm":
                inv.action_validate()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete inventory adjustment?"),
        )

    def _cpa_cd_delete_do(self):
        self.action_cpa_cd_cancel()
        self.unlink()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self.action_cpa_cd_delete()

    def _cpa_cd_delete_linked_do(self):
        return self._cpa_cd_delete_do()

    def action_cpa_cd_reset_draft(self):
        for inv in self:
            inv.write({"state": "draft"})
            inv._cpa_cd_chatter(_("Reset to Draft."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        done = self.filtered(lambda i: i.state == "done")
        if not done:
            raise UserError(_("Reverse needs a validated inventory."))
        new_invs = self.env["stock.inventory"]
        for inv in done:
            copy = inv.copy({
                "name": _("Reverse of %s") % (inv.name or inv.id),
                "state": "draft",
            })
            for line in copy.line_ids:
                line.product_qty = line.theoretical_qty
            new_invs |= copy
        return {
            "type": "ir.actions.act_window",
            "name": _("Reverse"),
            "res_model": "stock.inventory",
            "view_mode": "form",
            "res_id": new_invs[:1].id,
            "target": "current",
        }

# -*- coding: utf-8 -*-
from odoo import models, _


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "cpa.cancel.delete.mixin"]

    # Odoo 19: expense state is computed from approval_state and the journal entry.

    def _cpa_cd_refuse(self, reason):
        for exp in self.sudo():
            if exp.state == "refused":
                continue
            try:
                with self.env.cr.savepoint():
                    exp._do_refuse(reason)
            except Exception:
                exp.write({"approval_state": "refused"})

    def action_cpa_cd_cancel(self):
        expenses = self._cpa_cd_target()
        moves = expenses.mapped("account_move_id")
        if moves:
            expenses._cpa_cd_force_cancel_move(moves)
        expenses._cpa_cd_refuse(_("Cancelled from Cancel / Delete Global"))
        expenses._cpa_cd_chatter(_("Cancel: expense refused."))
        return expenses._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_cancel_linked(self):
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_confirm_post(self):
        expenses = self._cpa_cd_target()
        draft = expenses.filtered(lambda e: e.state == "draft")
        if draft:
            draft.action_submit()
        return expenses._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected expense(s)?"),
        )

    def _cpa_cd_delete_do(self):
        expenses = self._cpa_cd_target()
        moves = expenses.mapped("account_move_id")
        if moves:
            expenses._cpa_cd_delete_moves(moves)
        leftover = expenses.exists()
        leftover.write({"approval_state": False})
        leftover.unlink()
        return leftover._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self.action_cpa_cd_delete()

    def _cpa_cd_delete_linked_do(self):
        return self._cpa_cd_delete_do()

    def action_cpa_cd_reset_draft(self):
        expenses = self._cpa_cd_target()
        moves = expenses.mapped("account_move_id")
        if moves:
            expenses._cpa_cd_force_cancel_move(moves)
        for exp in expenses:
            try:
                with self.env.cr.savepoint():
                    exp.action_reset()
            except Exception:
                exp.write({"approval_state": False})
            exp._cpa_cd_chatter(_("Reset to Draft."))
        return expenses._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        return self.action_cpa_cd_cancel()

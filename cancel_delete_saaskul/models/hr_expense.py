# -*- coding: utf-8 -*-
from odoo import models, _


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        for exp in self:
            if hasattr(exp, "refuse_expense") and exp.state not in ("refused", "cancel"):
                try:
                    exp.refuse_expense(_("Cancelled from Cancel / Delete Global"))
                except Exception:
                    exp.write({"state": "refused"})
            elif exp.state not in ("refused", "cancel"):
                exp.write({"state": "refused"})
            exp._cpa_cd_chatter(_("Cancel: expense refused."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_cancel_linked(self):
        sheets = self.mapped("sheet_id")
        moves = sheets.mapped("account_move_id")
        self._cpa_cd_force_cancel_move(moves)
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_confirm_post(self):
        for exp in self:
            if exp.state == "draft":
                exp.action_submit_expenses()
        return self._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected expense(s)?"),
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
        for exp in self:
            if hasattr(exp, "action_reset") and exp.state == "refused":
                try:
                    exp.action_reset()
                except Exception:
                    exp.write({"state": "draft"})
            else:
                exp.write({"state": "draft"})
            exp._cpa_cd_chatter(_("Reset to Draft."))
        return self._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        return self.action_cpa_cd_cancel()

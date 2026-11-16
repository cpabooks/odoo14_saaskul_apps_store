# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "cpa.cancel.delete.mixin"]

    def action_cpa_cd_cancel(self):
        pays = self._cpa_cd_target()
        pays._cpa_cd_force_cancel_payment(pays)
        pays._cpa_cd_chatter(_("Cancel: payment cancelled."))
        return pays._cpa_cd_web_action()

    def action_cpa_cd_cancel_lines(self):
        pays = self._cpa_cd_target()
        pays._cpa_cd_cancel_payment_lines(pays)
        pays._cpa_cd_chatter(_("Cancel - Lines: payment lines removed."))
        return pays._cpa_cd_web_action()

    def action_cpa_cd_cancel_linked(self):
        return self.action_cpa_cd_cancel()

    def action_cpa_cd_confirm_post(self):
        pays = self._cpa_cd_target()
        draft = pays.filtered(lambda p: p.state == "draft")
        if draft:
            draft.action_post()
        return pays._cpa_cd_web_action()

    def action_cpa_cd_delete(self):
        return self._cpa_cd_open_confirm(
            "_cpa_cd_delete_do",
            _("Delete selected payment(s)?"),
        )

    def _cpa_cd_delete_do(self):
        pays = self._cpa_cd_target()
        pays._cpa_cd_force_cancel_payment(pays)
        pays.sudo().unlink()
        return pays._cpa_cd_web_action()

    def action_cpa_cd_delete_linked(self):
        return self.action_cpa_cd_delete()

    def _cpa_cd_delete_linked_do(self):
        return self._cpa_cd_delete_do()

    def action_cpa_cd_reset_draft(self):
        pays = self._cpa_cd_target()
        pays._cpa_cd_force_cancel_payment(pays)
        for pay in pays:
            if pay.move_id and pay.move_id.state == "cancel":
                pays._cpa_cd_force_button_draft(pay.move_id)
            if hasattr(pay, "action_draft"):
                try:
                    pay.action_draft()
                except Exception:
                    pass
            pay._cpa_cd_chatter(_("Reset to Draft."))
        return pays._cpa_cd_web_action()

    def action_cpa_cd_reverse(self):
        posted = self._cpa_cd_target().filtered(lambda p: p.state == "posted")
        if not posted or not posted[0].move_id:
            raise UserError(_("Reverse needs a posted payment."))
        return posted[0].move_id.action_reverse()

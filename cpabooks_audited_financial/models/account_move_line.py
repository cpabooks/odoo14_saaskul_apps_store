# -*- coding: utf-8 -*-
from odoo import _, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def get_formview_action(self, access_uid=None):
        """AFG journal-items drill: open the parent voucher / journal entry."""
        if self.env.context.get("afg_drill_open_move"):
            self.ensure_one()
            move = self.move_id
            if move:
                return {
                    "type": "ir.actions.act_window",
                    "name": move.display_name or _("Journal Entry"),
                    "res_model": "account.move",
                    "res_id": move.id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    # Nested dialog keeps AFG underneath; form is editable for changes.
                    "target": "new",
                    "context": {
                        "allowed_company_ids": self.env.context.get("allowed_company_ids")
                        or [move.company_id.id],
                    },
                }
        return super().get_formview_action(access_uid=access_uid)

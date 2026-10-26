# -*- coding: utf-8 -*-

from odoo import _, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    def action_open_coa_actions2(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Actions 2"),
            "res_model": "cpabooks.coa.actions2",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.account",
                "active_ids": self.ids,
                "active_id": self[:1].id,
            },
        }


class CpaCoaActions2(models.TransientModel):
    _name = "cpabooks.coa.actions2"
    _description = "Chart of accounts actions"

    def _accounts(self):
        ids = self.env.context.get("active_ids") or []
        records = self.env["account.account"].browse(ids).exists()
        if not records and self.env.context.get("active_id"):
            records = self.env["account.account"].browse(self.env.context["active_id"]).exists()
        return records

    def _run(self, method):
        return getattr(self._accounts(), method)()

    def action_set_coa_4_digits(self):
        return self._run("action_set_coa_4_digits")

    def action_set_coa_6_digits(self):
        return self._run("action_set_coa_6_digits")

    def reset_all(self):
        return self._run("reset_all")

    def delete_wizard(self):
        return self._run("delete_wizard")

    def action_cpabooks_add_opening_balance(self):
        return self._run("action_cpabooks_add_opening_balance")

    def action_view_rules(self):
        return self._run("action_view_rules")

    def action_remove_group(self):
        return self._run("action_remove_group")

    def reset_group(self):
        return self._run("reset_group")

    def cpa_coa_menu_update_all_groups(self):
        return self._run("cpa_coa_menu_update_all_groups")

    def action_cpa_reset_afg(self):
        return self._run("action_cpa_reset_afg")

    def action_cpa_reset_ctf(self):
        return self._run("action_cpa_reset_ctf")

    def cpa_coa_menu_delete_unused_coa(self):
        return self._run("cpa_coa_menu_delete_unused_coa")

    def cpa_coa_menu_archive_unused_coa(self):
        return self._run("cpa_coa_menu_archive_unused_coa")

    def action_view_duplicate_codes(self):
        return self._run("action_view_duplicate_codes")

    def action_fix_duplicate_codes(self):
        return self._run("action_fix_duplicate_codes")

    def create_deferred_expense_model(self):
        return self._run("create_deferred_expense_model")

    def action_toggle_code(self):
        return self._run("action_toggle_code")

    def action_show_code_true(self):
        return self._run("action_show_code_true")

    def action_update_selected(self):
        return self._run("action_update_selected")

    def action_create_far_rules(self):
        return self._run("action_create_far_rules")

    def action_create_journals_from_coa(self):
        return self._run("action_create_journals_from_coa")

    def action_open_coa_merge_coa(self):
        return self._run("action_open_coa_merge_coa")

    def action_open_delete_unused_coa(self):
        return self._run("action_open_delete_unused_coa")

    def action_open_ifrs_coding_wizard(self):
        return self._run("action_open_ifrs_coding_wizard")

# -*- coding: utf-8 -*-

from odoo import api, models

LEGACY_STATEMENT_MENU_XMLIDS = (
    'audited_financials_saaskul.menu_audited_financials_pl',
    'audited_financials_saaskul.menu_audited_financials_bs',
    'audited_financials_saaskul.menu_audited_financials_equity',
    'audited_financials_saaskul.menu_audited_financials_cashflow',
    'audited_financials_saaskul.menu_audited_financials_notes',
    'audited_financials_saaskul.menu_audited_financials_fa',
    'audited_financials_saaskul.menu_audited_financials_review',
)


class AuditedFinancialMenuCleanup(models.AbstractModel):
    _name = 'audited.financial.menu.cleanup'
    _description = 'Audited Financial menu maintenance'

    @api.model
    def sync_root_menu_action(self):
        root = self.env.ref(
            'audited_financials_saaskul.menu_audited_financials_root',
            raise_if_not_found=False,
        )
        action = self.env.ref(
            'audited_financials_saaskul.action_audited_financials_dashboard_client',
            raise_if_not_found=False,
        )
        if root and action and not root.action:
            root.sudo().write({'action': 'ir.actions.client,%d' % action.id})
        return True

    @api.model
    def refresh_afg_menus(self):
        self.sync_root_menu_action()
        self.deactivate_legacy_statement_menus()
        return True

    @api.model
    def deactivate_legacy_statement_menus(self):
        for menu_xid in LEGACY_STATEMENT_MENU_XMLIDS:
            menu = self.env.ref(menu_xid, raise_if_not_found=False)
            if menu:
                menu.write({'active': False})
        return True

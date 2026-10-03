# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

LEGACY_STATEMENT_MENU_XMLIDS = (
    'cpabooks_audited_financial.menu_audited_financials_pl',
    'cpabooks_audited_financial.menu_audited_financials_bs',
    'cpabooks_audited_financial.menu_audited_financials_equity',
    'cpabooks_audited_financial.menu_audited_financials_cashflow',
    'cpabooks_audited_financial.menu_audited_financials_notes',
    'cpabooks_audited_financial.menu_audited_financials_fa',
    'cpabooks_audited_financial.menu_audited_financials_review',
)

_AFG_MULTICO_ACTION_SPECS = (
    {
        'xmlid': 'action_afg_multico_profit_loss',
        'name': 'Profit and Loss_x',
        'source_xmlids': (
            'project_dashboard_odoo.account_financial_html_report_action_4',
        ),
        'report_xmlid': 'project_dashboard_odoo.account_financial_report_project_pl_multi_company',
        'kind': 'pl',
    },
    {
        'xmlid': 'action_afg_multico_balance_sheet',
        'name': 'Balance Sheet_x',
        'source_xmlids': (
            'project_dashboard_odoo.account_financial_html_report_action_bs',
        ),
        'report_xmlid': 'project_dashboard_odoo.account_financial_report_project_bs_multi_company',
        'kind': 'bs',
    },
)

_AFG_MULTICO_MENU_SPECS = (
    {
        'menu_xmlid': 'menu_audited_financials_profit_loss_multico',
        'name': 'Profit and Loss_x',
        'sequence': 1,
        'action_xmlids': (
            'cpabooks_audited_financial.action_afg_multico_profit_loss',
            'project_dashboard_odoo.account_financial_html_report_action_4',
        ),
        'report_xmlid': 'project_dashboard_odoo.account_financial_report_project_pl_multi_company',
        'kind': 'pl',
    },
    {
        'menu_xmlid': 'menu_audited_financials_balance_sheet_multico',
        'name': 'Balance Sheet_x',
        'sequence': 2,
        'action_xmlids': (
            'cpabooks_audited_financial.action_afg_multico_balance_sheet',
            'project_dashboard_odoo.account_financial_html_report_action_bs',
        ),
        'report_xmlid': 'project_dashboard_odoo.account_financial_report_project_bs_multi_company',
        'kind': 'bs',
    },
)


class AuditedFinancialMenuCleanup(models.AbstractModel):
    _name = 'audited.financial.menu.cleanup'
    _description = 'Audited Financial menu maintenance'

    @api.model
    def _resolve_multico_client_action(self, action_xmlids, report_xmlid, kind):
        for xmlid in action_xmlids:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                return action
        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            return self.env['ir.actions.client']
        return self.env['ir.actions.client'].create({
            'name': report.name,
            'tag': 'account_report',
            'context': {
                'model': 'account.financial.html.report',
                'id': report.id,
                'project_multicompany_no_session': True,
                'project_multicompany_kind': kind,
            },
        })

    @api.model
    def ensure_multico_client_actions(self):
        """Stable AFG xmlids for dashboard JS/sidebar (no XML eval refs)."""
        imd = self.env['ir.model.data'].sudo()
        for spec in _AFG_MULTICO_ACTION_SPECS:
            full_xmlid = 'cpabooks_audited_financial.%s' % spec['xmlid']
            action = self.env.ref(full_xmlid, raise_if_not_found=False)
            source = self._resolve_multico_client_action(
                spec['source_xmlids'],
                spec['report_xmlid'],
                spec['kind'],
            )
            if not source:
                _logger.warning(
                    'cpabooks_audited_financial: multico action %s unavailable; upgrade project_dashboard_odoo.',
                    spec['xmlid'],
                )
                continue
            vals = {
                'name': spec['name'],
                'tag': source.tag,
                'context': source.context,
            }
            if action:
                action.write(vals)
            else:
                action = self.env['ir.actions.client'].sudo().create(vals)
                imd.create({
                    'name': spec['xmlid'],
                    'module': 'cpabooks_audited_financial',
                    'model': 'ir.actions.client',
                    'res_id': action.id,
                })
        return True

    @api.model
    def sync_root_menu_action(self):
        root = self.env.ref(
            'cpabooks_audited_financial.menu_audited_financials_root',
            raise_if_not_found=False,
        )
        action = self.env.ref(
            'cpabooks_audited_financial.action_audited_financials_dashboard_client',
            raise_if_not_found=False,
        )
        if root and action and not root.action:
            root.sudo().write({'action': 'ir.actions.client,%d' % action.id})
        return True

    @api.model
    def wire_multico_report_menus(self):
        """Create AFG multico menus after project_dashboard_odoo data is available."""
        parent = self.env.ref(
            'cpabooks_audited_financial.menu_audited_financials_financial_reports',
            raise_if_not_found=False,
        )
        if not parent:
            return False

        for spec in _AFG_MULTICO_MENU_SPECS:
            action = self._resolve_multico_client_action(
                spec['action_xmlids'],
                spec['report_xmlid'],
                spec['kind'],
            )
            menu_xmlid = 'cpabooks_audited_financial.%s' % spec['menu_xmlid']
            menu = self.env.ref(menu_xmlid, raise_if_not_found=False)
            if not action:
                _logger.warning(
                    'cpabooks_audited_financial: skip multico menu %s; upgrade project_dashboard_odoo first.',
                    spec['menu_xmlid'],
                )
                if menu:
                    menu.active = False
                continue

            if menu:
                menu.write({'active': False})
        return True

    @api.model
    def refresh_afg_menus(self):
        self.sync_root_menu_action()
        self.ensure_multico_client_actions()
        self.wire_multico_report_menus()
        self.deactivate_legacy_statement_menus()
        return True

    @api.model
    def deactivate_legacy_statement_menus(self):
        for menu_xid in LEGACY_STATEMENT_MENU_XMLIDS:
            menu = self.env.ref(menu_xid, raise_if_not_found=False)
            if menu:
                menu.write({'active': False})
        return True

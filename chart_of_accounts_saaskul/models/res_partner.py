# -*- coding: utf-8 -*-

from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _cpabooks_default_partner_accounts_for_company(self, company):
        """Return receivable/payable accounts for a company (may be empty)."""
        Account = self.env['account.account'].sudo()
        receivable = Account.search([
            ('company_id', '=', company.id),
            ('internal_type', '=', 'receivable'),
            ('deprecated', '=', False),
        ], limit=1, order='code asc')
        if not receivable:
            receivable = Account.search([
                ('company_id', '=', company.id),
                ('name', '=ilike', 'accounts receivable%'),
                ('deprecated', '=', False),
            ], limit=1, order='code asc')

        payable = Account.search([
            ('company_id', '=', company.id),
            ('internal_type', '=', 'payable'),
            ('deprecated', '=', False),
        ], limit=1, order='code asc')
        if not payable:
            payable = Account.search([
                ('company_id', '=', company.id),
                ('name', 'in', ('Payables', 'Accounts Payable')),
                ('deprecated', '=', False),
            ], limit=1, order='code asc')
        return receivable, payable

    @api.model
    def action_cpabooks_restore_partner_accounts(self):
        """Fill missing receivable/payable only; keep existing partner accounts."""
        if 'property_account_receivable_id' not in self._fields:
            return 0

        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        account_cache = {}
        fixed = 0

        for partner in Partner.search([]):
            company = partner.company_id or self.env.company
            partner_co = partner.with_company(company)
            vals = {}

            if not partner_co.property_account_receivable_id:
                if company.id not in account_cache:
                    account_cache[company.id] = self._cpabooks_default_partner_accounts_for_company(
                        company,
                    )
                receivable = account_cache[company.id][0]
                if receivable:
                    vals['property_account_receivable_id'] = receivable.id

            if not partner_co.property_account_payable_id:
                if company.id not in account_cache:
                    account_cache[company.id] = self._cpabooks_default_partner_accounts_for_company(
                        company,
                    )
                payable = account_cache[company.id][1]
                if payable:
                    vals['property_account_payable_id'] = payable.id

            if vals:
                partner_co.write(vals)
                fixed += 1
        return fixed

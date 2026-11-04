# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    pdc_customer = fields.Many2one(
        'account.account',
        string='PDC Account for customer',
        check_company=True,
    )
    pdc_vendor = fields.Many2one(
        'account.account',
        string='PDC Account for Vendor',
        check_company=True,
    )
    cpabooks_coa_code_digits = fields.Selection(
        [('4', 'COA 4 Digits'), ('6', 'COA 6 Digits')],
        string='COA Code Digits',
        copy=False,
        help='Company preference only. Changing it never rewrites existing ledger codes.',
    )

    @api.model
    def _cpabooks_initialize_coa_code_digits(self):
        """Set an unset company once from its dominant existing code length."""
        companies = self.sudo().search([('cpabooks_coa_code_digits', '=', False)])
        if not companies:
            return True

        self.env.cr.execute(
            """
            SELECT company_id,
                   COUNT(*) FILTER (
                       WHERE LENGTH(REGEXP_REPLACE(COALESCE(code, ''), '[^0-9]', '', 'g')) = 4
                   ) AS four_digit_count,
                   COUNT(*) FILTER (
                       WHERE LENGTH(REGEXP_REPLACE(COALESCE(code, ''), '[^0-9]', '', 'g')) = 6
                   ) AS six_digit_count
              FROM account_account
             WHERE company_id = ANY(%s)
             GROUP BY company_id
            """,
            [companies.ids],
        )
        counts = {
            company_id: (four_count, six_count)
            for company_id, four_count, six_count in self.env.cr.fetchall()
        }
        for company in companies:
            four_count, six_count = counts.get(company.id, (0, 0))
            company.cpabooks_coa_code_digits = (
                '6'
                if not four_count and not six_count or six_count > four_count
                else '4'
            )
        return True

    def _cpabooks_ensure_coa_code_digits(self):
        unset = self.filtered(lambda company: not company.cpabooks_coa_code_digits)
        if unset:
            unset._cpabooks_initialize_coa_code_digits()
        return self

    def _find_pdc_account(self, payment_type):
        self.ensure_one()
        name = (
            'PDC Receivable'
            if payment_type == 'receive_money'
            else 'PDC Payable'
        )
        seed_key = (
            'qid:5'
            if payment_type == 'receive_money'
            else 'qid:43'
        )
        Account = self.env['account.account'].sudo().with_company(self)
        return (
            Account.search([
                ('company_id', '=', self.id),
                ('cpabooks_default_seed_key', '=', seed_key),
            ], limit=1)
            or Account.search([
                ('company_id', '=', self.id),
                ('name', '=ilike', name),
            ], limit=1)
        )

    def ensure_pdc_accounts(self):
        """Assign the standard COA-owned PDC defaults without replacing choices."""
        for company in self.sudo():
            values = {}
            if not company.pdc_customer:
                account = company._find_pdc_account('receive_money')
                if account:
                    values['pdc_customer'] = account.id
            if not company.pdc_vendor:
                account = company._find_pdc_account('send_money')
                if account:
                    values['pdc_vendor'] = account.id
            if values:
                company.with_context(cpabooks_skip_company_coa=True).write(values)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if not self.env.context.get('cpabooks_skip_company_coa'):
            for company in companies:
                company.cpabooks_coa_code_digits = '6'
                self.env['account.account'].with_company(company).with_context(
                    allowed_company_ids=[company.id],
                ).cpabooks_ensure_default_coa(company)
        return companies


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pdc_customer = fields.Many2one(
        'account.account',
        string='PDC Account for customer',
        related='company_id.pdc_customer',
        readonly=False,
    )
    pdc_vendor = fields.Many2one(
        'account.account',
        string='PDC Account for Vendor',
        related='company_id.pdc_vendor',
        readonly=False,
    )

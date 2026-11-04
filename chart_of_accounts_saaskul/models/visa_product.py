import base64
import csv
import io

from psycopg2 import IntegrityError

from odoo import _, api, fields, models, modules
from odoo.exceptions import UserError, ValidationError

class VisaProductShow(models.TransientModel):
    _name="visa.product.show"

    visa_product_show_id=fields.Many2one('product.analytic.acc.conf')
    visa_product=fields.Char(string="Visa Product")
    expense_ledger_id=fields.Many2one('account.account',string="Expense Ledger", default=lambda self:self.env['account.account'].sudo().search([('name','=ilike','prepaid visa expenses%'),('company_id','=',self.env.company.id)],limit=1))
    company_id = fields.Many2one('res.company')
    item_id = fields.Many2one('product.template', string="Item Name")


class VisaProduct(models.Model):
    _name = "visa.product"

    visa_product_id = fields.Many2one('product.analytic.acc.conf')
    visa_product = fields.Char(string="Visa Product")
    expense_ledger_id=fields.Many2one('account.account',string="Expense Ledger", default=lambda self:self.env['account.account'].sudo().search([('name','=ilike','prepaid visa expenses%'),('company_id','=',self.env.company.id)],limit=1))
    company_id = fields.Many2one('res.company')
    item_id = fields.Many2one('product.template', string="Item Name")

    _PREPAID_VISA_EXPENSE_CODE = '565006PVE'
    _PREPAID_VISA_EXPENSE_NAME = 'Prepaid Visa Expenses'

    _VISA_PRODUCT_NAMES = (
        "Visa - Visa Application Fee",
        "Visa - Security Deposit",
        "Visa - Medical Examination Fee",
        "Visa - Emirates ID Card Fee",
        "Visa - Insurance Fee",
        "Visa - Typing Centers Fee",
        "Visa - Express or Urgent Processing Fee",
        "Visa - Change of Status Fee",
        "Visa - Overstay Fine",
        "Visa - Visa Renewal Fee",
        "Visa - Others",
    )

    @api.model
    def _get_prepaid_visa_expense_account(self, company):
        Account = self.env['account.account'].sudo()
        domain = [('company_id', '=', company.id)]
        account = Account.search(
            domain + [('name', '=ilike', 'prepaid visa expenses%')], limit=1,
        )
        if not account:
            account = Account.search(
                domain + [('code', '=', self._PREPAID_VISA_EXPENSE_CODE)], limit=1,
            )
        return account

    @api.model
    def _get_or_create_prepaid_visa_expense_account(self, company):
        account = self._get_prepaid_visa_expense_account(company)
        if account:
            return account
        expense_type = self.env['account.account.type'].sudo().search(
            [('name', '=', 'Expenses')], limit=1,
        )
        vals = {
            'name': self._PREPAID_VISA_EXPENSE_NAME,
            'code': self._PREPAID_VISA_EXPENSE_CODE,
            'company_id': company.id,
            'user_type_id': expense_type.id if expense_type else False,
        }
        try:
            with self.env.cr.savepoint():
                return self.env['account.account'].sudo().create(vals)
        except (IntegrityError, ValidationError):
            account = self._get_prepaid_visa_expense_account(company)
            if account:
                return account
            raise

    @api.model
    def action_create_default_visa_product(self):
        ProductTemplate = self.env['product.template'].sudo()
        VisaProduct = self.env['visa.product'].sudo()
        visa_product_val = []
        all_create_product = ProductTemplate.browse()

        for company in self.env['res.company'].sudo().search([]):
            for product_name in self._VISA_PRODUCT_NAMES:
                existing_product = ProductTemplate.search([
                    ('name', '=ilike', product_name),
                    '|',
                    ('company_id', '=', company.id),
                    ('company_id', '=', False),
                ], limit=1)
                if existing_product:
                    if not VisaProduct.search([
                        ('item_id', '=', existing_product.id),
                        ('company_id', '=', company.id),
                    ], limit=1):
                        visa_product_val.append({
                            'visa_product': product_name,
                            'company_id': company.id,
                            'item_id': existing_product.id,
                        })
                    continue

                create_vals = ProductTemplate._cpabooks_default_product_vals(
                    product_name, company,
                )
                # Some databases enforce global unique product names.
                # In that case, reuse any already existing template instead of failing the upgrade.
                try:
                    create_product = ProductTemplate.create(create_vals)
                except (UserError, ValidationError, ValueError):
                    create_product = ProductTemplate.search([
                        ('name', '=ilike', product_name),
                    ], limit=1)
                    if not create_product:
                        raise
                all_create_product += create_product
                visa_product_val.append({
                    'visa_product': product_name,
                    'company_id': company.id,
                    'item_id': create_product.id,
                })

        for row in visa_product_val:
            if VisaProduct.search([
                ('item_id', '=', row['item_id']),
                ('company_id', '=', row['company_id']),
            ], limit=1):
                continue
            VisaProduct.create(row)

        for company in self.env['res.company'].sudo().search([]):
            expense_account = self._get_or_create_prepaid_visa_expense_account(company)
            visa_products = VisaProduct.search([('company_id', '=', company.id)])
            templates = visa_products.mapped('item_id')
            if all_create_product:
                templates |= all_create_product
            for template in templates:
                template.with_company(company.id).sudo().write({
                    'property_account_expense_id': expense_account.id,
                })

    @api.model
    def action_attach_existing_vehicle_product(self):
        get_all_company = self.env['res.company'].sudo().search([])
        val_list=[]
        for com in get_all_company:
            get_all_vehicle_related_product=self.env['product.product'].sudo().search([('name','=ilike',"Vehicle Fuel Exp # %"),('company_id','=',com.id)])
            get_all_vehicle_related_product+=self.env['product.product'].sudo().search([('name','=ilike',"Vehicle Maint. # %"),('company_id','=',com.id)])
            get_all_vehicle_setup=self.env['product.analytic.acc.conf.line'].search([('company_id','=',com.id)])
            for product in get_all_vehicle_related_product:
                if product.id not in get_all_vehicle_setup.item_id.ids:
                    v_no=product.name.split("#")[1]
                    get_analytic_acc=self.env['account.analytic.account'].sudo().search([('name','=',product.name),('company_id','=',com.id)],limit=1)
                    val_list.append({
                        'vehicle_no': v_no.strip(),
                        'item_id':  product.id,
                        'analytic_acc_id':get_analytic_acc.id if get_analytic_acc else None,
                        'analytic_group_id': get_analytic_acc.group_id.id if get_analytic_acc else None,
                        'company_id': com.id,
                        'expense_ledger_id':product.product_tmpl_id.with_company(com.id).property_account_expense_id.id
                    })
        if val_list:
            self.env['product.analytic.acc.conf.line'].sudo().create(val_list)


    @api.model
    def action_attach_existing_visa_analytic_acc(self):
        # Optional HR hook — skip cleanly on Community installs without Employees.
        if 'hr.employee' not in self.env:
            return
        get_all_company = self.env['res.company'].sudo().search([])
        val_list = []
        for com in get_all_company:
            get_all_emp = self.env['hr.employee'].sudo().search([('company_id', '=', com.id)])
            for emp in get_all_emp:
                get_analytic_acc = self.env['account.analytic.account'].sudo().search([
                    ('company_id', '=', com.id),
                    ('name', '=ilike', 'Visa - ' + emp.name + '%'),
                ], limit=1)
                if get_analytic_acc and not self.env['visa.analytic.acc'].sudo().search([
                    ('analytic_acc_id', '=', get_analytic_acc.id),
                ]):
                    val_list.append({
                        'analytic_acc_id': get_analytic_acc.id,
                        'analytic_group_id': get_analytic_acc.group_id.id,
                        'company_id': com.id,
                    })
        if val_list:
            self.env['visa.analytic.acc'].sudo().create(val_list)

class VisaAnalyticAcc(models.Model):
    _name = "visa.analytic.acc"

    visa_ana_acc_id = fields.Many2one('product.analytic.acc.conf')
    analytic_acc_id=fields.Many2one('account.analytic.account',string="Analytical Account")
    company_id = fields.Many2one('res.company')
    analytic_group_id = fields.Many2one('account.analytic.group', string="Analytical Group")




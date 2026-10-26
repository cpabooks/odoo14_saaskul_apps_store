import base64
import csv
import io

from odoo import models, fields, api, modules,_
from odoo.exceptions import ValidationError

class ProductWithAnalyticAcc(models.Model):
    _name="product.analytic.acc.conf"

    vehicle_coa=fields.One2many('product.analytic.acc.conf.line.show','show_id',string="Vehicle CoA")

    created_coa=fields.One2many('product.analytic.acc.conf.line','conf_id',string="Created CoA" ,default=lambda self:self.env['product.analytic.acc.conf.line'].sudo().search([('company_id','=',self.env.company.id)]))

    visa_products=fields.One2many('visa.product.show','visa_product_show_id',string="Visa Products")

    created_visa_products=fields.One2many('visa.product','visa_product_id',string="Created Visa Products",default=lambda self:self.env['visa.product'].sudo().search([('company_id','=',self.env.company.id)]))

    created_visa_ana_acc=fields.One2many('visa.analytic.acc','visa_ana_acc_id',string="Created Visa Analytic Accounts",default=lambda self:self.env['visa.analytic.acc'].sudo().search([('company_id','=',self.env.company.id)]))

    def create_vehicle_coa(self):
        for rec in self:
            val_list=[]
            all_company=self.env['res.company'].sudo().search([])

            for line in rec.vehicle_coa:
                if line.vehicle_no:
                    fuel_exp_get_product_exists_or_not=self.env['product.product'].sudo().search([('name','=ilike',"Vehicle Fuel Exp # "+line.vehicle_no),('company_id','=',self.env.company.id)])
                    if fuel_exp_get_product_exists_or_not:
                        continue
                    else:
                        create_vals = self.env['product.template']._cpabooks_default_product_vals(
                            "Vehicle Fuel Exp # " + line.vehicle_no,
                            self.env.company,
                        )
                        create_product1 = self.env['product.product'].sudo().create(create_vals)

                        # for com in all_company:
                        get_expense_id = self.env['account.account'].sudo().search(
                            [('name', '=ilike', line.expense_ledger_id.name + '%'), ('company_id', '=', self.env.company.id)],
                            limit=1)
                        if not get_expense_id:
                            get_expense_id = self.env['account.account'].sudo().create({
                                'name': 'Vehicle Expenses',
                                'code': '565005VE',
                                'company_id': self.env.company.id,
                                'user_type_id': self.env['account.account.type'].sudo().search(
                                    [('name', '=', 'Expenses')]).id
                            })
                        # create_ir_property_expense_data=self.env['ir.property'].sudo().search([('value_reference','=','account.account,'+str(get_expense_id.id)),
                        #                                                                        ('res_id','=','product.template,'+str(create_product1.id)),
                        #                                                                        ('name','=','property_account_expense_id')],limit=1)
                        # if not create_ir_property_expense_data:
                        #     create_expense_for_product=self.env['ir.property'].sudo().create({
                        #         'name':'property_account_expense_id',
                        #         'res_id':'product.template,'+str(create_product1.id),
                        #         'company_id':com.id,
                        #         'fields_id':self.env['ir.model.fields'].sudo().search([('model','=','account.chart.template'),('name','=','property_account_expense_id')],limit=1).id,
                        #         'value_reference':'account.account,'+str(get_expense_id.id),
                        #         'type':'many2one',
                        #     })
                        create_product1.with_company(self.env.company.id).write({'property_account_expense_id':get_expense_id.id})
                        serch_analytic_group_exists_or_not = self.env['account.analytic.group'].sudo().search(
                            [('name', '=', line.expense_ledger_id.name), ('company_id', '=', self.env.company.id)], limit=1)
                        if not serch_analytic_group_exists_or_not:
                            create_anlytic_group = self.env['account.analytic.group'].sudo().create({
                                'name': line.expense_ledger_id.name,
                                'company_id': self.env.company.id
                            })
                            analytic_acc_val = {
                                'name': create_product1.name,
                                'group_id': create_anlytic_group.id,
                                'company_id': self.env.company.id
                            }
                        else:
                            analytic_acc_val = {
                                'name': create_product1.name,
                                'group_id': serch_analytic_group_exists_or_not.id,
                                'company_id': self.env.company.id
                            }

                        create_analytic_acc = self.env['account.analytic.account'].sudo().create(analytic_acc_val)
                        create_analytic_account_default = self.env['account.analytic.default'].sudo().create({
                            'analytic_id': create_analytic_acc.id,
                            'product_id': create_product1.id,
                            'company_id': self.env.company.id
                        })

                        val_list.append({
                            'vehicle_no': line.vehicle_no,
                            'item_id': create_product1.id,
                            'analytic_acc_id':create_analytic_acc.id,
                            'analytic_group_id':create_analytic_acc.group_id.id,
                            'company_id':self.env.company.id,
                            'expense_ledger_id':line.expense_ledger_id.id
                        })






                    maint_get_product_exists_or_not = self.env['product.product'].sudo().search(
                        [('name', '=ilike', "Vehicle Maint. # " + line.vehicle_no),('company_id','=',self.env.company.id)])

                    if maint_get_product_exists_or_not:
                        continue
                    else:
                        create_vals = self.env['product.template']._cpabooks_default_product_vals(
                            "Vehicle Maint. # " + line.vehicle_no,
                            self.env.company,
                        )
                        create_product2 = self.env['product.product'].sudo().create(create_vals)
                        # for com in all_company:
                        get_expense_id = self.env['account.account'].sudo().search(
                            [('name', '=ilike', line.expense_ledger_id.name + '%'), ('company_id', '=', self.env.company.id)],
                            limit=1)
                        if not get_expense_id:
                            get_expense_id = self.env['account.account'].sudo().create({
                                'name': 'Vehicle Expenses',
                                'code': '565005VE',
                                'company_id': self.env.company.id,
                                'user_type_id': self.env['account.account.type'].sudo().search(
                                    [('name', '=', 'Expenses')]).id
                            })
                        create_product2.with_company(self.env.company.id).write(
                            {'property_account_expense_id': get_expense_id.id})
                        serch_analytic_group_exists_or_not = self.env['account.analytic.group'].sudo().search(
                            [('name', '=', line.expense_ledger_id.name), ('company_id', '=', self.env.company.id)],
                            limit=1)
                        if not serch_analytic_group_exists_or_not:
                            create_anlytic_group = self.env['account.analytic.group'].sudo().create({
                                'name': line.expense_ledger_id.name,
                                'company_id': self.env.company.id
                            })
                            analytic_acc_val = {
                                'name': create_product2.name,
                                'group_id': create_anlytic_group.id,
                                'company_id': self.env.company.id
                            }
                        else:
                            analytic_acc_val = {
                                'name': create_product2.name,
                                'group_id': serch_analytic_group_exists_or_not.id,
                                'company_id': self.env.company.id
                            }

                        create_analytic_acc = self.env['account.analytic.account'].sudo().create(analytic_acc_val)
                        create_analytic_account_default = self.env['account.analytic.default'].sudo().create({
                            'analytic_id': create_analytic_acc.id,
                            'product_id': create_product2.id,
                            'company_id': self.env.company.id
                        })

                        val_list.append({
                            'vehicle_no': line.vehicle_no,
                            'item_id': create_product2.id,
                            'analytic_acc_id': create_analytic_acc.id,
                            'analytic_group_id': create_analytic_acc.group_id.id,
                            'company_id': self.env.company.id,
                            'expense_ledger_id':line.expense_ledger_id.id
                        })


                        # serch_analytic_group_exists_or_not = self.env['account.analytic.group'].sudo().search(
                        #     [('name', '=', line.expense_ledger_id.name)], limit=1)
                        # if not serch_analytic_group_exists_or_not:
                        #     create_anlytic_group = self.env['account.analytic.group'].sudo().create({
                        #         'name': line.expense_ledger_id.name
                        #     })
                        #     analytic_acc_val = {
                        #         'name': create_product2.name,
                        #         'group_id': create_anlytic_group.id,
                        #     }
                        #     # extra_line.analytic_group_id = create_anlytic_group.id
                        # else:
                        #     analytic_acc_val = {
                        #         'name': create_product2.name,
                        #         'group_id': serch_analytic_group_exists_or_not.id,
                        #     }
                        #     # extra_line.analytic_group_id = serch_analytic_group_exists_or_not.id
                        # create_analytic_acc = self.env['account.analytic.account'].sudo().create(analytic_acc_val)
                        # # extra_line.analytic_acc_id = create_analytic_acc.id
                        # create_analytic_account_default = self.env['account.analytic.default'].sudo().create({
                        #     'analytic_id': create_analytic_acc.id,
                        #     'product_id': create_product2.id
                        # })
                        # val_list.append({
                        #     'vehicle_no': line.vehicle_no,
                        #     'analytic_acc_id': create_analytic_acc.id,
                        #     'analytic_group_id': create_analytic_acc.group_id.id,
                        #     'item_id': create_product2.id
                        # })

            if val_list:
                self.env['product.analytic.acc.conf.line'].sudo().create(val_list)

    def create_visa_coa(self):
        for rec in self:
            val_list = []
            all_company = self.env['res.company'].sudo().search([])

            for line in rec.visa_products:
                if line.visa_product:
                    visa_product_exists_or_not = self.env['product.template'].sudo().search(
                        [('name', '=ilike', line.visa_product),('company_id','=',self.env.company.id)])
                    if visa_product_exists_or_not:
                        continue
                    else:
                        create_vals = self.env['product.template']._cpabooks_default_product_vals(
                            line.visa_product,
                            self.env.company,
                        )
                        create_product1 = self.env['product.product'].sudo().create(create_vals)

                        # for com in all_company:
                        get_expense_id = self.env['account.account'].sudo().search(
                            [('name', '=ilike', line.expense_ledger_id.name + '%'),
                             ('company_id', '=', self.env.company.id)],
                            limit=1)
                        if not get_expense_id:
                            get_expense_id = self.env['account.account'].sudo().create({
                                'name': 'prepaid visa expenses',
                                'code': '565006PVE',
                                'company_id': self.env.company.id,
                                'user_type_id': self.env['account.account.type'].sudo().search(
                                    [('name', '=', 'Expenses')]).id
                            })
                        # create_ir_property_expense_data=self.env['ir.property'].sudo().search([('value_reference','=','account.account,'+str(get_expense_id.id)),
                        #                                                                        ('res_id','=','product.template,'+str(create_product1.id)),
                        #                                                                        ('name','=','property_account_expense_id')],limit=1)
                        # if not create_ir_property_expense_data:
                        #     create_expense_for_product=self.env['ir.property'].sudo().create({
                        #         'name':'property_account_expense_id',
                        #         'res_id':'product.template,'+str(create_product1.id),
                        #         'company_id':com.id,
                        #         'fields_id':self.env['ir.model.fields'].sudo().search([('model','=','account.chart.template'),('name','=','property_account_expense_id')],limit=1).id,
                        #         'value_reference':'account.account,'+str(get_expense_id.id),
                        #         'type':'many2one',
                        #     })
                        create_product1.with_company(self.env.company.id).write(
                            {'property_account_expense_id': get_expense_id.id})
                        serch_analytic_group_exists_or_not = self.env['account.analytic.group'].sudo().search(
                            [('name', '=', line.expense_ledger_id.name), ('company_id', '=', self.env.company.id)],
                            limit=1)
                        if not serch_analytic_group_exists_or_not:
                            create_anlytic_group = self.env['account.analytic.group'].sudo().create({
                                'name': line.expense_ledger_id.name,
                                'company_id': self.env.company.id
                            })
                            analytic_acc_val = {
                                'name': create_product1.name,
                                'group_id': create_anlytic_group.id,
                                'company_id': self.env.company.id
                            }
                        else:
                            analytic_acc_val = {
                                'name': create_product1.name,
                                'group_id': serch_analytic_group_exists_or_not.id,
                                'company_id': self.env.company.id
                            }

                        create_analytic_acc = self.env['account.analytic.account'].sudo().create(analytic_acc_val)
                        create_analytic_account_default = self.env['account.analytic.default'].sudo().create({
                            'analytic_id': create_analytic_acc.id,
                            'product_id': create_product1.id,
                            'company_id': self.env.company.id
                        })

                        val_list.append({
                            'visa_product': line.visa_product,
                            'item_id': create_product1.product_tmpl_id.id,
                            'company_id': self.env.company.id
                        })



            if val_list:
                self.env['visa.product'].sudo().create(val_list)


    def action_create_default_visa_analytic_acc(self):
        get_all_company = self.env['res.company'].sudo().search([])
        get_all_employee = self.env['hr.employee'].sudo().search(
            [('company_id', '=', self.env.company.id), ('active', '=', True)])
        val_list = []
        for emp in get_all_employee:
            chk_emp_has_visa_ana_acc = self.env['account.analytic.account'].sudo().search(
                [('name', '=ilike', 'Visa - ' + emp.name + "%"), ('company_id', '=', self.env.company.id)], limit=1)
            if not chk_emp_has_visa_ana_acc:
                serch_analytic_group_exists_or_not = self.env['account.analytic.group'].sudo().search(
                    [('name', '=ilike', "prepaid visa expenses%"), ('company_id', '=', self.env.company.id)],
                    limit=1)
                if not serch_analytic_group_exists_or_not:
                    create_anlytic_group = self.env['account.analytic.group'].sudo().create({
                        'name': "Prepaid Visa Expenses",
                        'company_id': self.env.company.id
                    })
                    analytic_acc_val = {
                        'name': 'Visa - '+emp.name,
                        'group_id': create_anlytic_group.id,
                        'company_id': self.env.company.id
                    }
                else:
                    analytic_acc_val = {
                        'name': 'Visa - '+emp.name,
                        'group_id': serch_analytic_group_exists_or_not.id,
                        'company_id': self.env.company.id
                    }

                create_analytic_acc = self.env['account.analytic.account'].sudo().create(analytic_acc_val)
                val_list.append({
                    'analytic_acc_id': create_analytic_acc.id,
                    'analytic_group_id': create_analytic_acc.group_id.id,
                    'company_id': self.env.company.id
                })
        if val_list:
            self.env['visa.analytic.acc'].sudo().create(val_list)




class ProductWithAnalyticAccLine(models.Model):
    _name="product.analytic.acc.conf.line"


    conf_id=fields.Many2one('product.analytic.acc.conf')
    vehicle_no=fields.Char(string="Vehicle No.")
    expense_ledger_id=fields.Many2one('account.account',string="Expense Ledger")
    analytic_acc_id=fields.Many2one('account.analytic.account',string="Analytical Account")
    analytic_group_id=fields.Many2one('account.analytic.group',string="Analytical Group")
    item_id=fields.Many2one('product.product',string="Item Name")
    company_id=fields.Many2one('res.company')

    # @api.depends("vehicle_no")
    # def _get_defaults(self):
    #     for rec in self:
    #         get_vehicle=self.env['product.template'].sudo().search([('name','=',rec.vehicle_no)],limit=1)
    #         rec.analytic_acc_id=get_vehicle.


class ProductWithAnalyticAccShowLine(models.TransientModel):
    _name="product.analytic.acc.conf.line.show"


    show_id=fields.Many2one('product.analytic.acc.conf')
    vehicle_no=fields.Char(string="Vehicle No.")
    expense_ledger_id=fields.Many2one('account.account',string="Expense Ledger", default=lambda self:self.env['account.account'].sudo().search([('name','=ilike','vehicle expenses%'),('company_id','=',self.env.company.id)],limit=1),required=True)
    analytic_acc_id=fields.Many2one('account.analytic.account',string="Analytical Account")
    analytic_group_id=fields.Many2one('account.analytic.group',string="Analytical Group")
    item_id=fields.Many2one('product.product',string="Item Name")
    company_id=fields.Many2one('res.company')


import base64
import csv
import io
import os

from odoo import models, fields, api, modules,_
from odoo.exceptions import ValidationError


class COACreate(models.Model):
    _name="coa.create"

    coa_csv_file=fields.Binary(string="File Name", compute='_default_csv')
    group_csv_file=fields.Binary(string="File Name", compute='_default_csv')
    not_delete_csv_file=fields.Binary(string="File Name", compute='_default_csv')
    company_id=fields.Many2one("res.company",string="Company", required=True,default=lambda x:x.env.company.id)
    delete_unlink_account=fields.Boolean(string="Delete Unlink Account")
    #
    # bin_field = fields.Binary(string="Binary Field", compute='_default_coa_csv')

    def update_existing_coas(self):
        warnings = []
        existing_cos = self.env['account.account'].search([
            ('company_id', '=', self.company_id.id)
        ])
        csv_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'data', 'coa_seed', 'account_group_type.csv',
        ))
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)

            for row in csv_reader:
                if not (
                    (row.get('code_auto') or '').strip()
                    and (row.get('account_name_revise') or '').strip()
                    and (row.get('type_revise') or '').strip()
                ):
                    continue
                name = row['account_name']
                revise_name = row['account_name_revise']
                auto_code = row['code_auto']
                user_type = row['type_revise']
                identity_code = row['code']
                user_type_id = self.env['account.account.type'].search([('name', 'like', user_type)], limit=1)
                reconcile = user_type_id.internal_group in ('asset', 'liability')

                get_coa = self.env['account.account'].search([
                    '|', ('name', 'in', (name, revise_name)),
                    ('code', 'in', (auto_code, identity_code)),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)

                if get_coa in existing_cos and (
                        get_coa.code != auto_code or get_coa.name != revise_name or get_coa.user_type_id != user_type_id or get_coa.identity_code != identity_code):
                    try:
                        with self.env.cr.savepoint():
                            # Do not restore ledger names here — only Factory Reset
                            # (force=True) may overwrite names after explicit user action.
                            get_coa.with_context(
                                cpabooks_skip_ifrs_auto_setup=True,
                                cpabooks_skip_ifrs_name_wizard=True,
                            ).write({
                                'code': auto_code,
                                'user_type_id': user_type_id.id,
                                'reconcile': reconcile,
                                'identity_code': identity_code
                            })
                    except Exception as error:
                        warnings.append('%s: %s' % (get_coa.display_name, error))
        return warnings





    # def delete_coa(self):
    #     not_delete_csv_data = base64.b64decode(self.not_delete_csv_file)
    #     data_file = io.StringIO(not_delete_csv_data.decode("utf-8"))
    #     data_file.seek(0)
    #     file_reader = []
    #     csv_reader = csv.reader(data_file, delimiter=',')
    #     file_reader.extend(csv_reader)
    #     not_deleted_accounts = []
    #     #for deleted account csv file
    #     # for idx, rec in enumerate(file_reader):
    #     #     get_account=self.env['account.account'].sudo().search([('name','ilike',rec[0])])
    #     #     if get_account:
    #     #         for acc_id in get_account:
    #     #             not_deleted_accounts.append(acc_id.id)
    #     # if not_deleted_accounts:
    #     #     not_deleted_ids=str(tuple(not_deleted_accounts)).replace(',)', ')')
    #     # else:
    #     #     not_deleted_ids='(0)'
    #
    #     # get_account = self.env['account.account']
    #     # for idx, rec in enumerate(file_reader):
    #     #     if rec[0]!='':
    #     #         get_account=self.env['account.account'].sudo().search([('code','=',rec[1])])
    #     #         if get_account:
    #     #             for acc_id in get_account:
    #     #                 not_deleted_accounts.append(acc_id.id)
    #
    #     not_deleted_accounts=self.env['account.account'].sudo().search([('company_id','=',self.company_id.id),('identity_code','not in',('New','NEW','new',False))]).ids
    #     if not_deleted_accounts:
    #         not_deleted_ids=tuple(not_deleted_accounts)
    #     else:
    #         not_deleted_ids='(0)'
    #     q1="""select acc_id from
    #                 (select default_account_id as acc_id,company_id as company from account_journal where default_account_id is not null  group by default_account_id,company_id
    #                 union all
    #                 select suspense_account_id as acc_id,company_id as company from account_journal where suspense_account_id is not null group by suspense_account_id,company_id
    #                 union all
    #                 select payment_debit_account_id as acc_id,company_id as company from account_journal where payment_debit_account_id is not null group by payment_debit_account_id,company_id
    #                 union all
    #                 select payment_credit_account_id as acc_id,company_id as company from account_journal where payment_credit_account_id is not null group by payment_credit_account_id,company_id
    #                 union all
    #                 select aml.account_id as acc_id,aml.company_id as company from account_move_line aml
    #                 left join account_partial_reconcile apr on aml.id=apr.credit_move_id
    #                 left join account_partial_reconcile apr1 on aml.id=apr1.debit_move_id group by aml.account_id,aml.company_id
    #                 union all
    #                 select id as acc_id,company_id as company from account_account where code  in ('100011','100012') group by id,company_id
    #                 union all
    #                 select id as acc_id,company_id as company from account_account where id in {} group by id,company_id
    #                 )
    #                  as acc_tabl where company={} group by acc_id""".format(not_deleted_ids,self.company_id.id)
    #     self._cr.execute(query=q1)
    #     result=self._cr.fetchall()
    #
    #     if result:
    #         not_deleted_ids = tuple([data[0] if data[0]!=None else 0 for data in result])
    #
    #     else:
    #         not_deleted_ids = '(0)'
    #
    #     q2="""select id from account_account where id not in {} and company_id={}""".format(not_deleted_ids,self.company_id.id)
    #     self._cr.execute(query=q2)
    #     result=self._cr.fetchall()
    #
    #     if result:
    #         deleted_ids = tuple([data[0] for data in result])
    #
    #     else:
    #         deleted_ids = '(0)'
    #
    #     query="""delete from account_account where id in {}""".format(deleted_ids)
    #
    #     # query = """delete from account_account where id not in(select acc_id from
    #     #             (select default_account_id as acc_id,company_id as company from account_journal where default_account_id is not null  group by default_account_id,company_id
    #     #             union all
    #     #             select suspense_account_id as acc_id,company_id as company from account_journal where suspense_account_id is not null group by suspense_account_id,company_id
    #     #             union all
    #     #             select payment_debit_account_id as acc_id,company_id as company from account_journal where payment_debit_account_id is not null group by payment_debit_account_id,company_id
    #     #             union all
    #     #             select payment_credit_account_id as acc_id,company_id as company from account_journal where payment_credit_account_id is not null group by payment_credit_account_id,company_id
    #     #             union all
    #     #             select aml.account_id as acc_id,aml.company_id as company from account_move_line aml
    #     #             left join account_partial_reconcile apr on aml.id=apr.credit_move_id
    #     #             left join account_partial_reconcile apr1 on aml.id=apr1.debit_move_id group by aml.account_id,aml.company_id
    #     #             union all
    #     #             select id as acc_id,company_id as company from account_account where code  in ('100011','100012') group by id,company_id
    #     #             union all
    #     #             select id as acc_id,company_id as company from account_account where id in {} group by id,company_id
    #     #             )
    #     #              as acc_tabl where company={} group by acc_id) and company_id={}""".format(not_deleted_ids,self.company_id.id, self.company_id.id)
    #     self._cr.execute(query=query)
    #     message_id = self.env['success.message.wizard'].create({'message': 'Your action is complete.'})
    #
    #     self.update_existing_coas()
    #
    #     return {
    #         'name': 'Message',
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'form',
    #         'res_model': 'success.message.wizard',
    #         'res_id': message_id.id,
    #         'target': 'new'
    #     }

    def delete_coa(self):
        """Factory Reset: wipe unused ledgers and force-restore factory seed (+ PDC)."""
        company = self.company_id.sudo()._cpabooks_ensure_coa_code_digits()
        result = self.env['account.account'].with_company(company).with_context(
            allowed_company_ids=[company.id],
        ).cpabooks_factory_reset_coa(company)
        message = _(
            'Factory Reset completed for %(company)s.\n'
            'Deleted %(deleted)s unused ledger(s), archived %(archived)s that could not be deleted, '
            'kept %(kept)s ledger(s) still linked to journals/entries, '
            'restored %(created)s missing factory ledger(s), '
            'refreshed %(updated)s factory ledger(s) to seed values '
            '(user edits on factory ledgers were overwritten). '
            'PDC Receivable / PDC Payable were ensured.\n\n'
            'Click OK to open a fresh Chart of Accounts list (clears deleted selection).'
        ) % {
            'company': company.display_name,
            'deleted': result.get('deleted', 0),
            'archived': result.get('archived', 0),
            'kept': result.get('kept_in_use', 0),
            'created': result.get('created', 0),
            'updated': result.get('updated', 0),
        }
        message_id = self.env['success.message.wizard'].create({'message': message})
        return {
            'name': _('Factory Reset'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'success.message.wizard',
            'res_id': message_id.id,
            'target': 'new',
            'context': {
                'active_id': False,
                'active_ids': [],
                'cpabooks_coa_factory_reset': True,
                'redirect_coa_company_id': company.id,
            },
        }

    def read_file(self):

        #***************************************************create group********************************************
        group_csv_data=base64.b64decode(self.group_csv_file)
        data_file = io.StringIO(group_csv_data.decode("utf-8"))
        data_file.seek(0)
        file_reader = []
        csv_reader = csv.reader(data_file, delimiter=',')
        file_reader.extend(csv_reader)
        group_create=[]
        for idx, rec in enumerate(file_reader):
            if idx==0:
                continue
            else:
                get_previous_data = self.env['account.group'].sudo().search([('identity_id', '=', int(rec[0])),('company_id','=',self.company_id.id)])
                if get_previous_data:
                    get_previous_data.name=rec[1]
                else:
                    vals={
                        'identity_id':int(rec[0]),
                        'name':rec[1],
                        'company_id':self.company_id.id
                    }
                    group_create.append(vals)
        self.env['account.group'].sudo().create(group_create)
        #***************************************************create group********************************************

        #***************************************************create COA********************************************
        csv_data = base64.b64decode(self.coa_csv_file)
        data_file = io.StringIO(csv_data.decode("utf-8"))
        data_file.seek(0)
        file_reader = []
        csv_reader = csv.reader(data_file, delimiter=',')
        file_reader.extend(csv_reader)
        create_list, update_list = [], []
        for idx, rec in enumerate(file_reader):
            if idx == 0:
                continue
            else:
                # get_previous_data by identity_id
                get_previous_data = self.env['account.account'].sudo().search(
                    [('identity_id', '=', int(rec[0])), ('company_id', '=', self.company_id.id)])
                # get_previous_data by name
                # if not get_previous_data:
                   # get_previous_data = self.env['account.account'].sudo().search(
                       # [('name', 'ilike', rec[1]), ('company_id', '=', self.company_id.id)])
                if get_previous_data:
                    get_previous_data.name = rec[1]
                    get_previous_data.code = rec[2]
                    get_previous_data.user_type_id = self.env['account.account.type'].sudo().search([('name','=',rec[3])]).id
                    get_previous_data.group_id = self.env['account.group'].sudo().search([('identity_id','=',int(rec[4])),('company_id','=',self.company_id.id)]).id,
                    get_previous_data.reconcile = 0 if rec[5] == "False" else 1
                else:
                    vals = {
                        "identity_id":rec[0],
                        "name": rec[1],
                        "code":rec[2],
                        "user_type_id":self.env['account.account.type'].sudo().search([('name','=',rec[3])]).id,
                        "group_id":self.env['account.group'].sudo().search([('identity_id','=',int(rec[4])),('company_id','=',self.company_id.id)]).id,
                        "reconcile": 0 if rec[5] == "False" else 1,
                        'company_id':self.company_id.id

                    }
                    create_list.append(vals)
        if len(create_list) > 0:
            self.env["account.account"].sudo().create(create_list)
        # ************************************gain loss account set******************************
        get_gain_account = self.env['account.account'].sudo().search(
            [('identity_id', '=', 143), ('company_id', '=', self.company_id.id)])
        get_loss_account = self.env['account.account'].sudo().search(
            [('identity_id', '=', 147), ('company_id', '=', self.company_id.id)])

        if get_gain_account:
            query = "UPDATE res_company SET income_currency_exchange_account_id={} where id={}".format(get_gain_account.id, self.company_id.id)
            self._cr.execute(query)
        else:
            raise ValidationError(_("Create Gain account in chart of account for your company"))
        if get_loss_account:
            query = "UPDATE res_company SET expense_currency_exchange_account_id={} where id={}".format(get_loss_account.id, self.company_id.id)
            self._cr.execute(query)
        else:
            raise ValidationError(_("Create Loss account in chart of account for your company"))
        # ************************************gain loss account set******************************
        message_id = self.env['success.message.wizard'].create({'message': 'Your action is complete.'})
        return {
            'name': 'Message',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'success.message.wizard',
            'res_id': message_id.id,
            'target': 'new'
        }

    def _default_csv(self):
        coa_csv_path = modules.get_module_resource(
            'chart_of_accounts_saaskul', 'data/coa_seed', 'account.account.csv',
        )
        group_csv_path = modules.get_module_resource(
            'chart_of_accounts_saaskul', 'data/coa_seed', 'account.group.csv',
        )
        not_delete_csv_path = modules.get_module_resource(
            'chart_of_accounts_saaskul', 'data/coa_seed', 'account_group_type.csv',
        )
        self.coa_csv_file = base64.b64encode(open(coa_csv_path, 'rb').read())
        self.group_csv_file = base64.b64encode(open(group_csv_path, 'rb').read())
        self.not_delete_csv_file = base64.b64encode(open(not_delete_csv_path, 'rb').read())
        # return tools.image_resize_image_big(base64.b64encode(open(image_path, 'rb').read()))


class TestMessageWizard(models.TransientModel):
    _name = 'success.message.wizard'
    _description = "Show Message"

    message = fields.Text('Message', required=True)
    redirect_coa_company_id = fields.Many2one(
        'res.company',
        string='Reload COA for company',
        help='When set, OK opens a fresh Chart of Accounts list (no stale active_ids).',
    )

    def _cpabooks_redirect_company(self):
        company_id = self.env.context.get('redirect_coa_company_id')
        if company_id:
            return self.env['res.company'].browse(company_id).exists()
        if 'redirect_coa_company_id' in self._fields:
            return self.redirect_coa_company_id
        return self.env['res.company']

    def action_close(self):
        self.ensure_one()
        company = self._cpabooks_redirect_company()
        if company:
            xml_action = self.env.ref('account.action_account_form', raise_if_not_found=False)
            if xml_action:
                action = xml_action.read()[0]
            else:
                action = {
                    'type': 'ir.actions.act_window',
                    'name': _('Chart of Accounts'),
                    'res_model': 'account.account',
                    'view_mode': 'tree,kanban,form',
                    'views': [(False, 'tree'), (False, 'kanban'), (False, 'form')],
                }
            action['domain'] = [('company_id', '=', company.id)]
            action['target'] = 'main'
            # Drop stale searchpanel / selection that may still point at deleted account.root rows.
            ctx = {
                'allowed_company_ids': [company.id],
                'default_company_id': company.id,
                'active_id': False,
                'active_ids': [],
                'search_default_activeacc': True,
                'cpabooks_coa_factory_reset': False,
            }
            action['context'] = ctx
            return action
        return {'type': 'ir.actions.act_window_close'}

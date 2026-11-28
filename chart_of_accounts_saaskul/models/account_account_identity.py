from odoo import models, fields, api
from odoo.tools.sql import column_exists, create_column


class AccountAccountInherit(models.Model):
    _inherit="account.account"

    # current_loged_user=fields.Many2one('res.users', default=lambda self:self.env.user.id)
    identity_id=fields.Integer()
    identity_code=fields.Char()

    def _auto_init(self):
        specs = (
            ("identity_id", "int4"),
            ("identity_code", "varchar"),
            ("is_show_code", "bool"),
            ("get_previous", "bool"),
            ("previous", "int4"),
            ("qid", "varchar"),
            ("is_duplicate", "bool"),
        )
        for col, col_type in specs:
            if not column_exists(self.env.cr, "account_account", col):
                create_column(self.env.cr, "account_account", col, col_type)
        return super()._auto_init()

    # @api.model
    # def create(self,val_list):
    #     company=self.env.user.company_id.id
    #     print("*************")



    # def write(self, vals):
    #     if 'from_file' in vals and vals["from_file"]==True:
    #         super(AccountAccountInherit, self).write(vals)
    #         companies=self.env["res.company"].search([("id","not in",self.company_id.ids)])
    #         for rec in companies:
    #             vals["company_id"]=rec.id
    #             self.env['account.account'].sudo().create(vals)
    #     else:
    #         super(AccountAccountInherit, self).write(vals)

    # @api.model
    # def delete_account_coa(self):
    #     query="""delete from account_account where id not in (select default_account_id from account_journal where
	# 										 default_account_id is not null) and id not in
	# 										 (select suspense_account_id from account_journal where
	# 										 suspense_account_id is not null) and id not in
	# 										 (select aml.account_id from account_move_line aml
	# 										  left join account_partial_reconcile apr on aml.id=apr.credit_move_id
	# 										  left join account_partial_reconcile apr1 on aml.id=apr1.debit_move_id
	# 										  ) and company_id in (select id from res_company)"""
    #     self._cr.execute(query=query)

class AccountGroupInherit(models.Model):
    _inherit="account.group"

    identity_id = fields.Integer()

    def _auto_init(self):
        if not column_exists(self.env.cr, "account_group", "identity_id"):
            create_column(self.env.cr, "account_group", "identity_id", "int4")
        return super()._auto_init()
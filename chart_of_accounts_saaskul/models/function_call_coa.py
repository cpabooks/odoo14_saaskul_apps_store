from odoo import models, fields, api

class FunctionCall(models.Model):
    _name="function.call"

    @api.model
    def delete_account_coa(self):
        user=self.env.user
        query = """delete from account_account where id not in (select default_account_id from account_journal where 
    											 default_account_id is not null) and id not in 
    											 (select suspense_account_id from account_journal where 
    											 suspense_account_id is not null) and id not in 
    											 (select aml.account_id from account_move_line aml
    											  left join account_partial_reconcile apr on aml.id=apr.credit_move_id
    											  left join account_partial_reconcile apr1 on aml.id=apr1.debit_move_id
    											  ) and company_id in (select id from res_company)"""
        self._cr.execute(query=query)
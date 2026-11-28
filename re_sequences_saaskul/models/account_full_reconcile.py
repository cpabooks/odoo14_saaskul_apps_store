from odoo import models, fields, api,_
from odoo.exceptions import ValidationError

class AccountFullReconcileInherit(models.Model):
    _inherit = "account.full.reconcile"

    name = fields.Char(string='Number', required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_sequence_for('reconcile'))

    # def create(self,vals):
    #     vals['name']=self.env['ir.sequence'].next_by_code('account.reconcile')
    #     return super(AccountFullReconcileInherit, self).create(vals)

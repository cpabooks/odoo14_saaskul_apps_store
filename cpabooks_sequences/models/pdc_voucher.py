from odoo import models, fields, api,_
from odoo.exceptions import ValidationError


class AccountPaymentInheritance(models.Model):
    _inherit = 'pdc.wizard'

    @api.model
    def create(self, vals_list):
        res=super(AccountPaymentInheritance, self).create(vals_list)

        if res.payment_type=='receive_money':
            get_sequence = self.env['ir.sequence'].next_by_sequence_for('pdc_receipt')
        else:
            get_sequence = self.env['ir.sequence'].next_by_sequence_for('pdc_payment')
        if not get_sequence:
            if res.payment_type == 'receive_money':
                raise ValidationError(_("Sequence is not set for PDC Received voucher"))
            else:
                raise ValidationError(_("Sequence is not set for PDC Payment voucher"))
        res.name = get_sequence or _('/')
        print(get_sequence)
        return res
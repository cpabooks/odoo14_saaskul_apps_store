from odoo import models, fields, api,_
from odoo.exceptions import ValidationError


class HelpdeskTicketExtend(models.Model):
    _inherit = 'helpdesk.ticket'

    sequence_no = fields.Char(default='/')

    @api.model
    def create(self, vals_list):
        print(vals_list)
        res = super(HelpdeskTicketExtend, self).create(vals_list)
        get_sequence = self.env['ir.sequence'].next_by_sequence_for('helpdesk_ticket')
        if not get_sequence:
            raise ValidationError(_("Sequence is not set for purchase order"))
        res.sequence_no = get_sequence or _('/')
        return res
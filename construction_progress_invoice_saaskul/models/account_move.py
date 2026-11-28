# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

CUSTOMER_MOVE_TYPES = ('out_invoice', 'out_refund')


class AccountMove(models.Model):
    _inherit = 'account.move'

    cpi_invoice_kind = fields.Selection(
        [
            ('labour', 'Labour Supply Invoice'),
            ('construction', 'Construction Invoice'),
        ],
        string='Invoice Kind',
        default='labour',
        copy=True,
        help="Construction Invoice bills each line by its Work Done %. "
             "Labour Supply Invoice is a normal invoice.",
    )
    cpi_contract_total = fields.Monetary(
        string='Contract Value',
        compute='_compute_cpi_contract_total',
        currency_field='currency_id',
        help='Full contract value of the lines (quantity x unit price), before Work Done %.',
    )

    @api.depends('invoice_line_ids.quantity', 'invoice_line_ids.price_unit')
    def _compute_cpi_contract_total(self):
        for move in self:
            lines = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
            move.cpi_contract_total = sum(lines.mapped('cpi_contract_amount'))

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'cpi_invoice_kind' in fields and 'default_cpi_invoice_kind' not in self.env.context:
            move_type = res.get('move_type') or self.env.context.get('default_move_type')
            if move_type in CUSTOMER_MOVE_TYPES and not self.env.context.get('default_invoice_origin'):
                res['cpi_invoice_kind'] = 'construction'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'cpi_invoice_kind' in vals or 'default_cpi_invoice_kind' in self.env.context:
                continue
            move_type = vals.get('move_type') or self.env.context.get('default_move_type')
            # Invoices created from sales orders or other documents stay normal invoices.
            if move_type not in CUSTOMER_MOVE_TYPES or vals.get('invoice_origin'):
                vals['cpi_invoice_kind'] = 'labour'
        return super().create(vals_list)

    def write(self, vals):
        if 'cpi_invoice_kind' in vals:
            locked = self.filtered(lambda move: move.state != 'draft' and move.cpi_invoice_kind != vals['cpi_invoice_kind'])
            if locked:
                raise UserError(_('Reset the invoice to draft before changing between Labour Supply and Construction.'))
        return super().write(vals)

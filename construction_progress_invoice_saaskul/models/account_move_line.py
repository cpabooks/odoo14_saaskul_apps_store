# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    cpi_previous_pct = fields.Float(
        string='Previous %',
        digits=(16, 2),
        copy=True,
        help='Share of this line already billed on earlier progress invoices. For information only.',
    )
    cpi_work_done_pct = fields.Float(
        string='Work Done %',
        digits=(16, 2),
        compute='_compute_cpi_work_done_pct',
        inverse='_inverse_cpi_work_done_pct',
        help='Share of the line billed on this invoice. The line amount, tax and '
             'journal entry are calculated on this percentage.',
    )
    cpi_guaranteed = fields.Boolean(string='Gtee', copy=True, help='Mark lines covered by a guarantee.')
    cpi_contract_amount = fields.Monetary(
        string='Contract Amount',
        compute='_compute_cpi_contract_amount',
        currency_field='currency_id',
        help='Quantity x unit price, before Work Done %.',
    )

    def write(self, vals):
        if 'cpi_work_done_pct' in vals and any(line.move_id.state != 'draft' for line in self):
            raise UserError(_('Reset the invoice to draft before changing Work Done %.'))
        return super().write(vals)

    @api.depends('discount')
    def _compute_cpi_work_done_pct(self):
        # Work Done % is stored as the complement of the standard discount, so Odoo's own
        # subtotal, tax and journal entry logic bills exactly the work done.
        for line in self:
            line.cpi_work_done_pct = 100.0 - (line.discount or 0.0)

    @staticmethod
    def _cpi_discount_from_pct(pct):
        return 100.0 - min(max(pct or 0.0, 0.0), 100.0)

    def _inverse_cpi_work_done_pct(self):
        for line in self:
            discount = self._cpi_discount_from_pct(line.cpi_work_done_pct)
            if float_compare(line.discount or 0.0, discount, precision_digits=4) == 0:
                continue
            if line.move_id.state != 'draft':
                raise UserError(_('Reset the invoice to draft before changing Work Done %.'))
            line.move_id.write({'invoice_line_ids': [(1, line.id, {'discount': discount})]})

    @api.onchange('cpi_work_done_pct')
    def _onchange_cpi_work_done_pct(self):
        for line in self:
            line.discount = self._cpi_discount_from_pct(line.cpi_work_done_pct)
            line._onchange_price_subtotal()

    @api.depends('quantity', 'price_unit')
    def _compute_cpi_contract_amount(self):
        for line in self:
            line.cpi_contract_amount = (line.quantity or 0.0) * (line.price_unit or 0.0)

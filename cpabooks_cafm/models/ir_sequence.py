# -*- coding: utf-8 -*-

from odoo import fields, models


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    sequence_for = fields.Selection(
        selection_add=[('cafm_contract_order', 'CAFM Contract Order')],
        ondelete={'cafm_contract_order': 'set null'},
    )

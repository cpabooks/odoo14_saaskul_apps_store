# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CafmContractDocument(models.Model):
    _name = 'cpabooks.cafm.contract.document'
    _description = 'CAFM Contract Document'
    _order = 'contract_id, sequence, id'

    contract_id = fields.Many2one('cpabooks.cafm.contract', string='Contract', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Serial')
    name = fields.Char(string='Document Name', required=True)
    attachment = fields.Binary(string='Attach')
    attachment_filename = fields.Char(string='Filename')
    note = fields.Text()

    @api.model
    def create(self, vals):
        if not vals.get('sequence') and vals.get('contract_id'):
            last_line = self.search([('contract_id', '=', vals['contract_id'])], order='sequence desc, id desc', limit=1)
            vals['sequence'] = (last_line.sequence or 0) + 1
        return super().create(vals)

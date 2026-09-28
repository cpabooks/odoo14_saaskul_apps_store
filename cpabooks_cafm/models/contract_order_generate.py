# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class CafmContractOrderGenerate(models.TransientModel):
    _name = 'cpabooks.cafm.contract.order.generate'
    _description = 'Generate Contract Orders'

    generate_for = fields.Selection([
        ('all', 'All Contracts'),
        ('project', 'Specific Project'),
        ('customer', 'Specific Customer'),
        ('contract', 'Specific AMC Contract'),
    ], string='Generate For', default='all', required=True)
    project_id = fields.Many2one('project.project', string='Project')
    customer_id = fields.Many2one('res.partner', string='Customer')
    contract_id = fields.Many2one('cpabooks.cafm.contract', string='AMC Contract')

    def action_generate_contract_orders(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.generate_for == 'project':
            if not self.project_id:
                raise UserError(_('Please select a project.'))
            domain.append(('project_id', '=', self.project_id.id))
        elif self.generate_for == 'customer':
            if not self.customer_id:
                raise UserError(_('Please select a customer.'))
            domain.append(('client_id', '=', self.customer_id.id))
        elif self.generate_for == 'contract':
            if not self.contract_id:
                raise UserError(_('Please select an AMC contract.'))
            domain.append(('id', '=', self.contract_id.id))

        contracts = self.env['cpabooks.cafm.contract'].search(domain)
        if not contracts:
            raise UserError(_('No AMC contracts found for the selected filters.'))

        before_count = self.env['cpabooks.cafm.contract.order'].search_count([
            ('contract_id', 'in', contracts.ids),
        ])
        for contract in contracts:
            contract._create_contract_orders(invoice_date=contract.invoicing_date)
        after_count = self.env['cpabooks.cafm.contract.order'].search_count([
            ('contract_id', 'in', contracts.ids),
        ])
        created_count = after_count - before_count

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Generate Contract Orders'),
                'message': _('%s contract(s) processed, %s contract order(s) created.') % (
                    len(contracts),
                    created_count,
                ),
                'sticky': False,
                'type': 'success',
            }
        }

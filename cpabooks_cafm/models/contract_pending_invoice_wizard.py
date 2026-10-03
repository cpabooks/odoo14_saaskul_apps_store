# -*- coding: utf-8 -*-

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


class CafmPendingInvoiceWizard(models.TransientModel):
    _name = 'cpabooks.cafm.pending.invoice.wizard'
    _description = 'Create Pending Invoice'

    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        help='Leave empty to include all clients.',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        help='Leave empty to include all projects.',
    )
    customer_group_id = fields.Many2one(
        'cpabooks.cafm.customer.group',
        string='Client Group',
        help='Leave empty to include all client groups.',
    )
    date_from = fields.Date(
        string='Start Invoice Creation From',
        required=True,
        default=lambda self: self._default_date_from(),
        help='Invoice uninvoiced contract orders whose billing period overlaps this start date through Until. '
             'Default: 1 Jan current year.',
    )
    date_to = fields.Date(
        string='Create Invoices Until',
        required=True,
        default=lambda self: self._default_date_to(),
        help='Invoice uninvoiced contract orders through this date. Default: 31 Dec current year.',
    )

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = fields.Date.to_date(today)
        return date(today.year, 1, 1)

    @api.model
    def _default_date_to(self):
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = fields.Date.to_date(today)
        return date(today.year, 12, 31)

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    def _get_order_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.env.company.id),
            ('invoice_id', '=', False),
            ('state', 'not in', ('cancelled', 'invoiced')),
            ('contract_id.active', '=', True),
            ('contract_id.amc_contract_type', '=', 'amc'),
            ('contract_id.contract_status', 'not in', ('cancelled',)),
        ]
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))
        if self.customer_group_id:
            domain.append(('contract_id.customer_group_id', '=', self.customer_group_id.id))
        period_or = expression.OR([
            [('invoice_date', '>=', self.date_from), ('invoice_date', '<=', self.date_to)],
            [
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from),
            ],
        ])
        return expression.AND([domain, period_or])

    def _filter_orders_by_mode(self, orders, mode):
        """Split orders for New vs Missed buttons.

        - new: only contracts that have never been invoiced
        - missed / all: every uninvoiced order in the period (keep existing invoices)
        """
        self.ensure_one()
        orders = orders.filtered(lambda order: (order.amount or 0.0) > 0.0)
        if mode != 'new':
            return orders
        already_invoiced = self.env['cpabooks.cafm.contract.order'].search([
            ('contract_id', 'in', orders.mapped('contract_id').ids),
            '|',
            ('invoice_id', '!=', False),
            ('state', '=', 'invoiced'),
        ]).mapped('contract_id')
        return orders.filtered(lambda order: order.contract_id not in already_invoiced)

    def action_create_new_invoices(self):
        """Invoice orders only for contracts that have never been invoiced."""
        return self._run_create_invoices(mode='new')

    def action_create_missed_invoices(self):
        """All matching uninvoiced orders in the period; existing invoices stay."""
        return self._run_create_invoices(mode='missed')

    def _run_create_invoices(self, mode='missed'):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Please set both Start and Until dates for invoice creation.'))
        if self.date_to < self.date_from:
            raise UserError(_('Create Invoices Until must be on or after the Start date.'))

        orders = self.env['cpabooks.cafm.contract.order'].search(
            self._get_order_domain(),
            order='partner_id, contract_id, invoice_date, id',
        )
        orders = self._filter_orders_by_mode(orders, mode)
        mode_label = {
            'new': _('Create New Invoices'),
            'missed': _('Create Missed Invoices'),
        }.get(mode, _('Create Pending Invoice'))

        if not orders:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': mode_label,
                    'message': _(
                        'No matching uninvoiced contract orders for this action in %(date_from)s → %(date_to)s.\n'
                        'New = contracts with no invoices yet.\n'
                        'Missed = all uninvoiced orders in the period (keep existing invoices).'
                    ) % {
                        'date_from': fields.Date.to_string(self.date_from),
                        'date_to': fields.Date.to_string(self.date_to),
                    },
                    'sticky': False,
                    'type': 'warning',
                },
            }

        created_moves = self.env['account.move']
        skipped = 0
        errors = []
        for order in orders:
            try:
                order.action_create_invoice()
                if order.invoice_id:
                    created_moves |= order.invoice_id
                else:
                    skipped += 1
            except UserError as exc:
                skipped += 1
                errors.append('%s: %s' % (order.display_name, str(exc)))
            except Exception as exc:
                skipped += 1
                errors.append('%s: %s' % (order.display_name, str(exc)))

        message = _(
            '%(mode)s: %(orders)s order(s) processed, %(invoices)s invoice(s) created for '
            '%(date_from)s → %(date_to)s. Existing invoices were left unchanged.'
        ) % {
            'mode': mode_label,
            'orders': len(orders),
            'invoices': len(created_moves),
            'date_from': fields.Date.to_string(self.date_from),
            'date_to': fields.Date.to_string(self.date_to),
        }
        if skipped:
            message = _('%s Skipped %s order(s).') % (message, skipped)
            if errors:
                message = '%s\n%s' % (message, '\n'.join(errors[:8]))
                if len(errors) > 8:
                    message = _('%s\n… and %s more.') % (message, len(errors) - 8)

        if created_moves:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Pending Invoices'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', created_moves.ids)],
                'target': 'current',
                'context': {'default_move_type': 'out_invoice'},
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': mode_label,
                'message': message or _('No new invoices were created (already up to date).'),
                'sticky': bool(errors),
                'type': 'warning' if skipped and not created_moves else 'success',
            },
        }

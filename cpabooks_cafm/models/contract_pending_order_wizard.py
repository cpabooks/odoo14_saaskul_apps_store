# -*- coding: utf-8 -*-

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CafmPendingContOrderWizard(models.TransientModel):
    _name = 'cpabooks.cafm.pending.cont.order.wizard'
    _description = 'Create Pending Contract Orders'

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
        string='Start Cont. Order Creation From',
        required=True,
        default=lambda self: self._default_date_from(),
        help='Create orders for periods overlapping this start date through Until. '
             'For Live contracts valid today, orders continue to Until even if stored '
             'expiry is earlier (contract dates unchanged). Default: 1 Jan current year.',
    )
    date_to = fields.Date(
        string='Create Cont. Orders Until',
        required=True,
        default=lambda self: self._default_date_to(),
        help='Create orders through this date. Live+valid-today contracts are treated as '
             'valid for ordering until this date (Dec 2028 / 2050 OK). Contract start/expiry '
             'fields are not modified. Default: 31 Dec current year.',
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

    def _get_contract_domain(self):
        self.ensure_one()
        domain = [
            ('active', '=', True),
            ('amc_contract_type', '=', 'amc'),
            ('contract_status', 'not in', ['cancelled']),
            ('contract_date', '!=', False),
        ]
        if self.partner_id:
            domain.append(('client_id', '=', self.partner_id.id))
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))
        if self.customer_group_id:
            domain.append(('customer_group_id', '=', self.customer_group_id.id))
        return domain

    def _filter_contracts_by_mode(self, contracts, mode):
        """Split contracts for New vs Missed buttons.

        - new: contracts with no contract orders at all
        - missed / all: every matching contract — keep existing orders; create any
          missing overlapping periods through Until (includes zero-order contracts)
        """
        self.ensure_one()
        if mode == 'new':
            return contracts.filtered(lambda c: not c.contract_order_ids)
        # missed + all: cover all filtered contracts (valid till Sept, etc.)
        return contracts

    def action_create_new_orders(self):
        """Create orders only for contracts that have no orders yet."""
        return self._run_create_orders(mode='new')

    def action_create_missed_orders(self):
        """All contracts: keep existing; fill gaps + create through Until date."""
        return self._run_create_orders(mode='missed')

    def action_create_pending_orders(self):
        """Backward-compatible: same as Create Missed + New (all gaps in period)."""
        return self._run_create_orders(mode='all')

    def _run_create_orders(self, mode='all'):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Please set both Start and Until dates for Cont. Order creation.'))
        if self.date_to < self.date_from:
            raise UserError(_('Create Cont. Orders Until must be on or after the Start date.'))

        contracts = self.env['cpabooks.cafm.contract'].search(self._get_contract_domain())
        if not contracts:
            raise UserError(_('No AMC contracts found for the selected filters.'))

        contracts = self._filter_contracts_by_mode(contracts, mode)
        mode_label = {
            'new': _('Create New Orders'),
            'missed': _('Create Missed Orders'),
            'all': _('Create Pending Cont. Orders'),
        }.get(mode, _('Create Pending Cont. Orders'))

        if not contracts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': mode_label,
                    'message': _(
                        'No matching contracts for this action in %(date_from)s → %(date_to)s.\n'
                        'New = contracts with no orders yet.\n'
                        'Missed = all contracts in filters (keep existing; fill overlapping gaps to Until).'
                    ) % {
                        'date_from': fields.Date.to_string(self.date_from),
                        'date_to': fields.Date.to_string(self.date_to),
                    },
                    'sticky': False,
                    'type': 'warning',
                },
            }

        created = self.env['cpabooks.cafm.contract.order']
        skipped = 0
        renewed = 0
        errors = []
        for contract in contracts:
            try:
                # Auto-renew ONLY when already expired as of yesterday.
                if contract._auto_renew_live_if_expired():
                    renewed += 1
                # Existing orders kept; missing schedule periods in range are created
                # (gaps from deletes + periods after the last order) up to date_to.
                created |= contract._create_pending_contract_orders(
                    from_date=self.date_from,
                    to_date=self.date_to,
                    invoice_date=self.date_from,
                )
            except UserError as exc:
                skipped += 1
                errors.append('%s: %s' % (contract.display_name, str(exc)))
            except Exception as exc:
                skipped += 1
                errors.append('%s: %s' % (contract.display_name, str(exc)))

        message = _(
            '%(mode)s: %(contracts)s contract(s) processed, %(renewed)s auto-renewed '
            '(expired as of yesterday), %(orders)s order(s) created for '
            '%(date_from)s → %(date_to)s. Existing orders were left unchanged.'
        ) % {
            'mode': mode_label,
            'contracts': len(contracts),
            'renewed': renewed,
            'orders': len(created),
            'date_from': fields.Date.to_string(self.date_from),
            'date_to': fields.Date.to_string(self.date_to),
        }
        if skipped:
            message = _('%s Skipped %s contract(s).') % (message, skipped)
            if errors:
                message = '%s\n%s' % (message, '\n'.join(errors[:8]))
                if len(errors) > 8:
                    message = _('%s\n… and %s more.') % (message, len(errors) - 8)

        if created:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Pending Contract Orders'),
                'res_model': 'cpabooks.cafm.contract.order',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', created.ids)],
                'target': 'current',
                'context': {
                    'default_search': True,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': mode_label,
                'message': message or _('No new contract orders were created (already up to date).'),
                'sticky': bool(errors),
                'type': 'warning' if skipped and not created else 'success',
            },
        }

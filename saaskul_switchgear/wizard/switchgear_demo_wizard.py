# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SwitchgearDemoWizard(models.TransientModel):
    _name = 'switchgear.demo.wizard'
    _description = 'Switchgear demo data load / clean'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    profile = fields.Selection(
        selection=[
            ('switchgear', 'Switchgear'),
            ('furniture', 'Furniture'),
        ],
        default='switchgear',
        required=True,
    )
    voucher_count = fields.Integer(
        string='Number of demo stacks',
        default=25,
        required=True,
    )
    full_cycle = fields.Boolean(
        string='Full process cycle',
        default=True,
        help='Delivery, customer invoice, and payment samples.',
    )
    load_timesheets = fields.Boolean(string='Create timesheet samples', default=True)
    create_pr_when_no_stock = fields.Boolean(
        string='Create purchase requisitions',
        default=True,
    )
    create_job_orders = fields.Boolean(string='Create job orders', default=True)
    load_activities = fields.Boolean(
        string='Create scheduled activities',
        default=True,
        help='Schedule demo activities on CRM, estimates, sales, projects, MRP, purchase, and accounting documents.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'voucher_count' in fields_list and 'cpabooks.demo.config' in self.env:
            config = self.env['cpabooks.demo.config'].sudo().search([
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if config and config.default_voucher_count:
                res['voucher_count'] = config.default_voucher_count
        return res

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only Settings / Administrator users can manage switchgear demo data.'))

    def _loader_options(self):
        self.ensure_one()
        return {
            'profile': self.profile,
            'voucher_count': self.voucher_count,
            'company_id': self.company_id.id,
            'load_timesheets': self.load_timesheets,
            'create_pr_when_no_stock': self.create_pr_when_no_stock,
            'create_job_orders': self.create_job_orders,
            'full_cycle': self.full_cycle,
            'load_activities': self.load_activities,
        }

    def _notification(self, title, message, ntype='success', sticky=False, close=True):
        params = {
            'title': title,
            'message': message,
            'type': ntype,
            'sticky': sticky,
        }
        if close:
            params['next'] = {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': params,
        }

    def action_load_demo_data(self):
        self._check_admin()
        self.ensure_one()
        if self.voucher_count < 1 or self.voucher_count > 100:
            raise UserError(_('Number of demo stacks must be between 1 and 100.'))
        if 'switchgear.demo.loader' not in self.env:
            raise UserError(_('Upgrade module "Saaskul Switchgear".'))

        result = self.env['switchgear.demo.loader'].sudo().load_demo_batch(
            self._loader_options(),
        )
        stacks = len(result.get('estimates', []))
        failed = len(result.get('errors', []))
        parts = [
            _('%(stacks)s demo stack(s)') % {'stacks': stacks},
            _('%(leads)s CRM records') % {'leads': len(result.get('leads', []))},
            _('%(design)s design registers') % {'design': len(result.get('design_documents', []))},
            _('%(activities)s scheduled activities') % {
                'activities': result.get('activities', 0),
            },
        ]
        message = _(
            'Loaded for %(company)s: %(summary)s. Refresh the dashboard to update KPIs.'
        ) % {
            'company': self.company_id.name,
            'summary': ', '.join(parts),
        }
        if failed:
            message += ' ' + _('%s stack(s) failed (see server log).') % failed
        return self._notification(
            _('Switchgear demo data loaded'),
            message,
            ntype='success' if stacks else 'warning',
            sticky=bool(failed or not stacks),
        )

    def action_clean_demo_data(self):
        self._check_admin()
        self.ensure_one()
        if 'switchgear.demo.loader' not in self.env:
            raise UserError(_('Upgrade module "Saaskul Switchgear".'))

        stats = self.env['switchgear.demo.loader'].sudo().clean_demo_batch({
            'profile': self.profile,
            'company_id': self.company_id.id,
        })
        failed = len(stats.get('errors', []))
        message = _(
            'Cleaned demo data for %(company)s (%(profile)s): '
            '%(leads)s CRM stack(s), %(partners)s customer(s), %(products)s product(s) removed.'
        ) % {
            'company': self.company_id.name,
            'profile': dict(self._fields['profile'].selection).get(self.profile),
            'leads': stats.get('leads_removed', 0),
            'partners': stats.get('partners_removed', 0),
            'products': stats.get('products_removed', 0),
        }
        if failed:
            message += ' ' + _('%s item(s) could not be removed (see server log).') % failed
        return self._notification(
            _('Demo data cleaned'),
            message,
            ntype='success' if not failed else 'warning',
            sticky=bool(failed),
        )

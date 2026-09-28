# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class CafmContractOrderMonitor(models.TransientModel):
    _name = 'cpabooks.cafm.contract.order.monitor'
    _description = 'Contract Order to Invoice Monitoring'

    start_month = fields.Date(string='Start Month', default=lambda self: self._default_start_month())
    summary_line_ids = fields.One2many(
        'cpabooks.cafm.contract.order.monitor.line',
        'wizard_id',
        string='Summary',
        domain=[('line_type', '=', 'summary')],
    )
    all_line_ids = fields.One2many(
        'cpabooks.cafm.contract.order.monitor.line',
        'wizard_id',
        string='AMC Monthly Table',
        domain=[('line_type', '=', 'all')],
    )
    invoiced_line_ids = fields.One2many(
        'cpabooks.cafm.contract.order.monitor.line',
        'wizard_id',
        string='Invoiced',
        domain=[('line_type', '=', 'invoiced')],
    )
    pending_line_ids = fields.One2many(
        'cpabooks.cafm.contract.order.monitor.line',
        'wizard_id',
        string='Pending to Invoice',
        domain=[('line_type', '=', 'pending')],
    )

    @api.model
    def _default_start_month(self):
        today = fields.Date.context_today(self)
        year = today.year if today.month >= 4 else today.year - 1
        return today.replace(year=year, month=4, day=1)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        start_month = fields.Date.to_date(res.get('start_month') or self._default_start_month()).replace(day=1)
        res['start_month'] = fields.Date.to_string(start_month)
        lines = self._prepare_monitor_lines(start_month)
        res['summary_line_ids'] = [(0, 0, vals) for vals in lines if vals['line_type'] == 'summary']
        res['all_line_ids'] = [(0, 0, vals) for vals in lines if vals['line_type'] == 'all']
        res['invoiced_line_ids'] = [(0, 0, vals) for vals in lines if vals['line_type'] == 'invoiced']
        res['pending_line_ids'] = [(0, 0, vals) for vals in lines if vals['line_type'] == 'pending']
        return res

    def _month_starts(self):
        self.ensure_one()
        start = fields.Date.to_date(self.start_month or self._default_start_month()).replace(day=1)
        return [start + relativedelta(months=index) for index in range(12)]

    @api.model
    def _month_starts_from(self, start_month):
        start = fields.Date.to_date(start_month or self._default_start_month()).replace(day=1)
        return [start + relativedelta(months=index) for index in range(12)]

    def _cell_key(self, month_index):
        return 'm%02d' % (month_index + 1)

    def _sum_amount(self, orders):
        return sum(orders.mapped('amount'))

    def _line_values(self, line_type, name, orders, months, sequence=0, contract=False, partner=False, project=False):
        vals = {
            'line_type': line_type,
            'sequence': sequence,
            'name': name,
            'contract_number': contract.name if contract else '',
            'customer_name': partner.display_name if partner else '',
            'project_name': project.display_name if project else '',
            'order_ids': [(6, 0, orders.ids)],
        }
        date_from = months[0]
        date_to = months[-1] + relativedelta(months=1)
        vals['overdue'] = self._sum_amount(orders.filtered(
            lambda order: order.invoice_date and order.invoice_date < date_from
        ))
        for index, month_start in enumerate(months):
            month_end = month_start + relativedelta(months=1)
            amount = self._sum_amount(orders.filtered(
                lambda order: order.invoice_date and month_start <= order.invoice_date < month_end
            ))
            vals[self._cell_key(index)] = amount
        for index in range(3):
            year_start = date_to + relativedelta(years=index)
            year_end = date_to + relativedelta(years=index + 1)
            amount = self._sum_amount(orders.filtered(
                lambda order: order.invoice_date and year_start <= order.invoice_date < year_end
            ))
            vals['y%02d' % (index + 1)] = amount
        return vals

    def _balance_values(self, orders_vals, invoiced_vals, pending_vals):
        vals = {
            'line_type': 'summary',
            'name': _('Balance Difference'),
        }
        amount_fields = ['overdue'] + [self._cell_key(index) for index in range(12)] + ['y01', 'y02', 'y03']
        for field_name in amount_fields:
            vals[field_name] = (orders_vals.get(field_name) or 0.0) - (invoiced_vals.get(field_name) or 0.0) - (pending_vals.get(field_name) or 0.0)
        return vals

    def _prepare_monitor_lines(self, start_month):
        order_model = self.env['cpabooks.cafm.contract.order']
        months = self._month_starts_from(start_month)
        date_from = months[0]
        date_to = months[-1] + relativedelta(months=1, years=3)
        orders = order_model.search([
            ('invoice_date', '<', fields.Date.to_string(date_to)),
            ('state', '!=', 'cancelled'),
        ])
        invoiced = orders.filtered(lambda order: order.invoice_id or order.state == 'invoiced')
        pending = orders - invoiced

        order_summary = self._line_values('summary', _('Contract Orders'), orders, months)
        invoiced_summary = self._line_values('summary', _('Orders Invoiced'), invoiced, months)
        pending_summary = self._line_values('summary', _('Pending Orders Invoice Pending'), pending, months)
        values = [
            order_summary,
            invoiced_summary,
            pending_summary,
            self._balance_values(order_summary, invoiced_summary, pending_summary),
        ]

        groups = {}
        for order in orders:
            contract = order.contract_id
            key = (
                contract.id,
                order.partner_id.id,
                contract.project_id.id if contract.project_id else False,
                contract.name,
                order.partner_id.display_name,
                contract.project_id.display_name if contract.project_id else contract.display_name,
            )
            groups.setdefault(key, order_model.browse())
            groups[key] |= order

        sequence = 1
        for key, group_orders in sorted(groups.items(), key=lambda item: (item[0][4] or '', item[0][5] or '', item[0][3] or '')):
            contract = self.env['cpabooks.cafm.contract'].browse(key[0])
            partner = self.env['res.partner'].browse(key[1])
            project = self.env['project.project'].browse(key[2]) if key[2] else False
            values.append(self._line_values('all', '', group_orders, months, sequence, contract, partner, project))
            values.append(self._line_values('invoiced', '', group_orders & invoiced, months, sequence, contract, partner, project))
            values.append(self._line_values('pending', '', group_orders & pending, months, sequence, contract, partner, project))
            sequence += 1
        return values

    def action_reset_period(self):
        for wizard in self:
            wizard.start_month = wizard._default_start_month()
            wizard.action_refresh()
        return self._reload_action()

    def action_refresh(self):
        order_model = self.env['cpabooks.cafm.contract.order']
        line_model = self.env['cpabooks.cafm.contract.order.monitor.line']
        for wizard in self:
            line_model.search([('wizard_id', '=', wizard.id)]).unlink()
            for vals in wizard._prepare_monitor_lines(wizard.start_month):
                vals['wizard_id'] = wizard.id
                line_model.create(vals)
        return self._reload_action()

    def _reload_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Monitoring Cont. Order to Invoice'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class CafmContractOrderMonitorLine(models.TransientModel):
    _name = 'cpabooks.cafm.contract.order.monitor.line'
    _description = 'Contract Order to Invoice Monitoring Line'

    wizard_id = fields.Many2one('cpabooks.cafm.contract.order.monitor', required=True, ondelete='cascade')
    order_ids = fields.Many2many(
        'cpabooks.cafm.contract.order',
        'cafm_monitor_order_rel',
        'line_id',
        'order_id',
        string='Contract Orders',
    )
    line_type = fields.Selection([
        ('summary', 'Summary'),
        ('all', 'All Contract Orders'),
        ('invoiced', 'Invoiced'),
        ('pending', 'Pending to Invoice'),
    ], required=True)
    name = fields.Char(string='Customer / Project')
    sequence = fields.Integer(string='Sr No.')
    contract_number = fields.Char(string='Cont. Number')
    customer_name = fields.Char(string='Customer Name')
    project_name = fields.Char(string='Project Name')
    overdue = fields.Float(string='Over Dues')
    m01 = fields.Float(string='Apr')
    m02 = fields.Float(string='May')
    m03 = fields.Float(string='Jun')
    m04 = fields.Float(string='Jul')
    m05 = fields.Float(string='Aug')
    m06 = fields.Float(string='Sep')
    m07 = fields.Float(string='Oct')
    m08 = fields.Float(string='Nov')
    m09 = fields.Float(string='Dec')
    m10 = fields.Float(string='Jan')
    m11 = fields.Float(string='Feb')
    m12 = fields.Float(string='Mar')
    y01 = fields.Float(string='Year 2027')
    y02 = fields.Float(string='Year 2028')
    y03 = fields.Float(string='Year 2029')

    def action_open_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name or _('Contract Orders'),
            'res_model': 'cpabooks.cafm.contract.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.order_ids.ids)],
            'context': {
                'group_by': ['project_id', 'partner_id', 'contract_id'],
            },
            'target': 'current',
        }

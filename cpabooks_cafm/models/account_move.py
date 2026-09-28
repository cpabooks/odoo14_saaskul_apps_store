# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.osv import expression
from dateutil.relativedelta import relativedelta


class AccountMove(models.Model):
    _inherit = 'account.move'

    project_title = fields.Char(
        string='Title',
        help='The title of the customer project or work being invoiced.',
    )
    cafm_contract_order_ids = fields.One2many(
        'cpabooks.cafm.contract.order',
        'invoice_id',
        string='AMC Contract Orders',
    )
    cafm_amc_call_ids = fields.One2many(
        'maintenance.request',
        'invoice_id',
        string='AMC Calls',
        domain=[('call_type', '=', 'amc')],
    )

    @api.model
    def _cafm_default_amc_invoice_domain(self):
        return [
            '&',
            '|', ('cafm_contract_order_ids', '!=', False), ('cafm_amc_call_ids', '!=', False),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ]

    @api.model
    def action_cafm_open_status_view(self):
        domain = list(self._cafm_default_amc_invoice_domain())
        return {
            'type': 'ir.actions.client',
            'tag': 'cpabooks_cafm_amc_invoice_status',
            'name': _('AMC Invoice Status'),
            'target': 'current',
            'params': {'domain': domain},
            'context': dict(
                self.env.context,
                cafm_invoice_status_domain=domain,
                cafm_amc_invoice_list=1,
            ),
        }

    @api.model
    def action_cafm_toggle_yearly_invoice_view(self):
        ctx = dict(self.env.context or {})
        yearly_on = not ctx.get('cafm_yearly_view_on')
        ctx.update({
            'cafm_amc_invoice_list': 1,
            'cafm_yearly_view_on': yearly_on,
            'default_move_type': 'out_invoice',
        })
        if yearly_on:
            ctx['group_by'] = ['invoice_date:year']
        else:
            ctx.pop('group_by', None)
        action = self.env.ref('cpabooks_cafm.action_cpabooks_cafm_amc_invoices').read()[0]
        action['context'] = ctx
        action['domain'] = self._cafm_default_amc_invoice_domain()
        return action

    @api.model
    def action_cafm_back_to_invoice_list(self):
        ctx = dict(self.env.context or {})
        ctx.update({
            'cafm_amc_invoice_list': 1,
            'default_move_type': 'out_invoice',
        })
        if ctx.get('cafm_yearly_view_on'):
            ctx['group_by'] = ['invoice_date:year']
        action = self.env.ref('cpabooks_cafm.action_cpabooks_cafm_amc_invoices').read()[0]
        action['context'] = ctx
        action['domain'] = self._cafm_default_amc_invoice_domain()
        return action

    @api.model
    def action_cafm_open_invoice_list(self):
        today = fields.Date.context_today(self)
        last_end = today.replace(day=1) - relativedelta(days=1)
        last_start = last_end.replace(day=1)
        action = self.env.ref('cpabooks_cafm.action_cpabooks_cafm_amc_invoices').read()[0]
        tree_id = self.env.ref('cpabooks_cafm.view_cafm_amc_customer_invoice_tree').id
        action['view_mode'] = 'tree,form'
        action['views'] = [(tree_id, 'tree'), (False, 'form')]
        action['view_id'] = tree_id
        action['target'] = 'current'
        action['context'] = {
            'default_move_type': 'out_invoice',
            'cafm_amc_invoice_list': 1,
        }
        action['domain'] = expression.AND([
            self._cafm_default_amc_invoice_domain(),
            [('invoice_date', '>=', last_start), ('invoice_date', '<=', last_end)],
        ])
        return action

    @api.model
    def _cafm_status_fmt_short_date(self, value):
        value = fields.Date.to_date(value) if value else False
        if not value:
            return ''
        return value.strftime('%d/%m/%y')

    @api.model
    def _cafm_status_fmt_long_date(self, value):
        value = fields.Date.to_date(value) if value else False
        if not value:
            return ''
        return value.strftime('%d/%m/%Y')

    @api.model
    def _cafm_status_period_label(self, date_from, date_to, period_label=False):
        if date_from and date_to:
            return '%s to %s' % (
                date_from.strftime('%d-%m-%Y'),
                date_to.strftime('%d-%m-%Y'),
            )
        if period_label:
            return period_label
        if date_from:
            return date_from.strftime('%d-%m-%Y')
        return ''

    @api.model
    def _cafm_status_client_key(self, client_name):
        name = (client_name or '').strip().lower()
        if 'lulu' in name:
            return 'lulu'
        if 'prea' in name:
            return 'prea'
        if 'relaam' in name:
            return 'relaam'
        if name == 'pvt' or ' pvt' in name:
            return 'pvt'
        return 'default'

    @api.model
    def _cafm_status_tracking_date(self, record, field_name, expected_values):
        if not record or not field_name:
            return False
        expected = {str(v) for v in (expected_values or [])}
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', record._name),
            ('res_id', '=', record.id),
            ('message_type', '!=', 'notification'),
        ], order='date desc', limit=50)
        for message in messages:
            for tracking in message.tracking_value_ids:
                if tracking.field != field_name:
                    continue
                new_val = tracking.new_value_char or tracking.new_value_text or ''
                if new_val in expected or tracking.new_value_integer in expected_values:
                    return fields.Date.to_date(message.date)
        return False

    @api.model
    def _cafm_match_amc_invoice_reg(self, Reg, move, property_name=''):
        company_ids = [move.company_id.id, False]
        if move.name:
            reg = Reg.search([
                ('company_id', 'in', company_ids),
                ('ref_no', '=', move.name),
            ], limit=1)
            if reg:
                return reg
        if property_name and move.invoice_date:
            reg = Reg.search([
                ('company_id', 'in', company_ids),
                ('project_name', 'ilike', property_name),
                ('invoice_date', '=', move.invoice_date),
            ], limit=1)
            if reg:
                return reg
        if move.partner_id and move.invoice_date:
            return Reg.search([
                ('company_id', 'in', company_ids),
                ('partner_id', '=', move.partner_id.id),
                ('invoice_date', '=', move.invoice_date),
                ('invoice_amount', '=', move.amount_untaxed),
            ], limit=1)
        return Reg.browse()

    @api.model
    def _cafm_status_received_copy(self, move, reg):
        att_count = self.env['ir.attachment'].sudo().search_count([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', move.id),
        ])
        if att_count:
            return _('Uploaded'), 'ok'
        if reg and reg.attachment_ids:
            return _('Received'), 'ok'
        return '', ''

    @api.model
    def _cafm_status_row_from_order(self, order, move, serial_no, reg):
        property_name = order.property_name or move.project_title or ''
        client_name = order.partner_id.display_name if order.partner_id else (
            move.partner_id.display_name if move.partner_id else ''
        )
        amount = order.amount or move.amount_untaxed or 0.0
        month_label = order.billing_month_label or (
            move.invoice_date.strftime('%b %y') if move.invoice_date else ''
        )
        period_label = self._cafm_status_period_label(
            order.date_from, order.date_to, order.period_label,
        )
        period_class = 'ok' if order.date_from and order.date_to else ''

        if order.docs_status == 'received':
            docs_date = self._cafm_status_tracking_date(
                order, 'docs_status', ['received', 'Docs Received'],
            )
            docs_text = _('Docs Received')
            if docs_date:
                docs_text = '%s %s' % (docs_text, self._cafm_status_fmt_short_date(docs_date))
            docs_class = 'ok'
        else:
            docs_text = _('Waiting for Docs')
            docs_class = ''

        invoice_status_class = ''
        if reg and reg.status == 'not_submitted':
            invoice_status = _('Invoice not Submitted')
            invoice_status_class = 'danger'
        elif reg and reg.status == 'submitted':
            submitted_on = reg.write_date or move.invoice_date
            invoice_status = _('Submitted on %s') % self._cafm_status_fmt_long_date(submitted_on)
            invoice_status_class = 'ok'
        elif order.invoice_submission_status == 'submitted' and move.invoice_date:
            invoice_status = _('Submitted on %s') % self._cafm_status_fmt_long_date(move.invoice_date)
            invoice_status_class = 'ok'
        else:
            invoice_status = _('Invoice not Submitted')
            invoice_status_class = 'danger'

        submitted_by = ''
        if reg and reg.follow_up_user_id:
            submitted_by = reg.follow_up_user_id.name
        elif order.client_manager_id:
            submitted_by = order.client_manager_id.name

        received_copy, received_copy_class = self._cafm_status_received_copy(move, reg)
        remarks = (order.notes or '') or (reg.remarks if reg else '') or ''

        return {
            'sl': serial_no,
            'property_name': property_name,
            'invoice_period': period_label,
            'period_class': period_class,
            'client_name': client_name,
            'client_key': self._cafm_status_client_key(client_name),
            'month_label': month_label,
            'invoice_no': move.name or '',
            'invoice_id': move.id,
            'amount': amount,
            'docs_status': docs_text,
            'docs_class': docs_class,
            'invoice_status': invoice_status,
            'invoice_status_class': invoice_status_class,
            'submitted_by': submitted_by,
            'received_copy': received_copy,
            'received_copy_class': received_copy_class,
            'remarks': remarks,
        }

    @api.model
    def _cafm_status_row_from_move(self, move, serial_no, reg):
        property_name = move.project_title or ''
        client_name = move.partner_id.display_name if move.partner_id else ''
        amount = move.amount_untaxed or 0.0
        month_label = move.invoice_date.strftime('%b %y') if move.invoice_date else ''
        period_label = ''
        if reg and reg.invoice_date:
            period_label = self._cafm_status_fmt_long_date(reg.invoice_date)

        if reg and reg.status == 'not_submitted':
            invoice_status = _('Invoice not Submitted')
            invoice_status_class = 'danger'
        elif reg and reg.status == 'submitted':
            invoice_status = _('Submitted on %s') % self._cafm_status_fmt_long_date(
                reg.write_date or move.invoice_date,
            )
            invoice_status_class = 'ok'
        elif move.invoice_date:
            invoice_status = _('Submitted on %s') % self._cafm_status_fmt_long_date(move.invoice_date)
            invoice_status_class = 'ok'
        else:
            invoice_status = _('Invoice not Submitted')
            invoice_status_class = 'danger'

        submitted_by = reg.follow_up_user_id.name if reg and reg.follow_up_user_id else ''
        received_copy, received_copy_class = self._cafm_status_received_copy(move, reg)
        remarks = (reg.remarks if reg else '') or (move.narration or '')

        return {
            'sl': serial_no,
            'property_name': property_name,
            'invoice_period': period_label,
            'period_class': '',
            'client_name': client_name,
            'client_key': self._cafm_status_client_key(client_name),
            'month_label': month_label,
            'invoice_no': move.name or '',
            'invoice_id': move.id,
            'amount': amount,
            'docs_status': '',
            'docs_class': '',
            'invoice_status': invoice_status,
            'invoice_status_class': invoice_status_class,
            'submitted_by': submitted_by,
            'received_copy': received_copy,
            'received_copy_class': received_copy_class,
            'remarks': remarks,
        }

    @api.model
    def cafm_invoice_status_data(self, domain=None):
        """AMC Invoice Status grid for CAFM Invoice list STATUS button."""
        base_domain = [
            '&',
            '|', ('cafm_contract_order_ids', '!=', False), ('cafm_amc_call_ids', '!=', False),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ]
        search_domain = expression.AND([base_domain, domain or []])
        moves = self.search(search_domain, order='invoice_date desc, id desc')
        Reg = self.env['cpabooks.cafm.amc.invoice.reg'].sudo()
        rows = []
        total_amount = 0.0
        serial_no = 1
        for move in moves:
            reg = self._cafm_match_amc_invoice_reg(
                Reg, move, property_name=move.project_title or '',
            )
            orders = move.cafm_contract_order_ids.sorted('date_from')
            if orders:
                for order in orders:
                    row = self._cafm_status_row_from_order(order, move, serial_no, reg)
                    rows.append(row)
                    total_amount += row.get('amount') or 0.0
                    serial_no += 1
            else:
                row = self._cafm_status_row_from_move(move, serial_no, reg)
                rows.append(row)
                total_amount += row.get('amount') or 0.0
                serial_no += 1
        return {
            'title': _('AMC Invoice Status'),
            'rows': rows,
            'total_amount': total_amount,
        }

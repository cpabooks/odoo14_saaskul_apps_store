# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CafmContractOrder(models.Model):
    _name = 'cpabooks.cafm.contract.order'
    _description = 'CAFM Contract Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'invoice_date, name'
    _rec_name = 'name'

    name = fields.Char(string='Contract Order No.', required=True, readonly=True, copy=False, default=lambda self: _('Draft'))
    contract_id = fields.Many2one('cpabooks.cafm.contract', string='AMC Contract', required=True, ondelete='cascade')
    project_id = fields.Many2one('project.project', string='Project', related='contract_id.project_id', store=True)
    schedule_line_id = fields.Many2one('cpabooks.cafm.invoice.stagger', string='Invoice Stagger', ondelete='set null')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    date_order = fields.Date(string='Order Date', default=lambda self: fields.Date.context_today(self))
    invoice_date = fields.Date(string='Invoice Date')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    period_label = fields.Char(string='Period')
    amount = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    invoice_due_bucket = fields.Char(string='Invoice Due Bucket', compute='_compute_invoice_due_bucket')
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('order', 'Contract Order'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    notes = fields.Text()
    docs_status = fields.Selection(
        [
            ('waiting', 'Waiting for Docs'),
            ('received', 'Docs Received'),
        ],
        string='Docs Status',
        default='waiting',
        tracking=True,
    )
    invoice_submission_status = fields.Selection(
        [
            ('not_submitted', 'Invoice not Submitted'),
            ('submitted', 'Invoice Submitted'),
        ],
        string='Invoice Submission',
        compute='_compute_invoice_submission_status',
        store=True,
        readonly=True,
    )
    is_overdue_amc_pending = fields.Boolean(
        string='Overdue Pending',
        compute='_compute_is_overdue_amc_pending',
        store=True,
        help='Pending contract order with invoice date in a month before the current month.',
    )
    property_name = fields.Char(
        string='Property Name',
        compute='_compute_property_name',
        store=True,
    )
    amc_period_display = fields.Char(
        string='AMC Period',
        compute='_compute_amc_period_display',
        store=True,
    )
    billing_month_label = fields.Char(
        string='Billing Month',
        compute='_compute_billing_month_label',
        store=True,
    )
    invoice_display_ref = fields.Char(
        string='Invoice / Order Ref.',
        compute='_compute_invoice_display_ref',
        store=True,
    )
    project_location_id = fields.Many2one(
        'cpabooks.cafm.location',
        string='Project Location',
        related='contract_id.project_location_id',
        store=True,
        readonly=True,
    )
    location_area_text = fields.Char(
        string='Location (area)',
        related='contract_id.project_id.cafm_location',
        store=True,
        readonly=True,
    )
    client_manager_id = fields.Many2one(
        'res.users',
        string='Client Manager',
        related='contract_id.client_manager_id',
        store=True,
        readonly=True,
    )
    gfs_supervisor_id = fields.Many2one(
        'res.users',
        string='GFS Supervisor',
        related='contract_id.gfs_supervisor_id',
        store=True,
        readonly=True,
    )
    gfs_admin_id = fields.Many2one(
        'res.users',
        string='GFS Admin',
        related='contract_id.gfs_admin_id',
        store=True,
        readonly=True,
    )
    customer_trn = fields.Char(
        string='Customer TRN',
        related='contract_id.customer_trn',
        store=True,
        readonly=True,
    )
    contact_person_id = fields.Many2one(
        'cpabooks.cafm.contact.person',
        string='Client Contact Person',
        related='contract_id.contact_person_id',
        store=True,
        readonly=True,
    )
    contact_no = fields.Char(
        string='Client Contact Number',
        related='contract_id.contact_no',
        store=True,
        readonly=True,
    )
    customer_group_id = fields.Many2one(
        'cpabooks.cafm.customer.group',
        string='Customer Group',
        related='contract_id.customer_group_id',
        store=True,
        readonly=True,
    )
    unit_id = fields.Many2one(
        'cpabooks.cafm.unit',
        string='Villa / Flat',
        related='contract_id.unit_id',
        store=True,
        readonly=True,
    )
    amc_contract_type = fields.Selection(
        related='contract_id.amc_contract_type',
        store=True,
        readonly=True,
    )
    contract_date = fields.Date(
        string='AMC Start Date',
        related='contract_id.contract_date',
        store=True,
        readonly=True,
    )
    contract_expiry = fields.Date(
        string='AMC Expiry Date',
        related='contract_id.contract_expiry',
        store=True,
        readonly=True,
    )

    _sql_constraints = [
        ('schedule_unique', 'unique(schedule_line_id)', 'A contract order already exists for this invoice stagger.'),
    ]

    @api.depends('invoice_date', 'invoice_id', 'state')
    def _compute_invoice_due_bucket(self):
        today = fields.Date.context_today(self)
        current_month = today.replace(day=1)
        for order in self:
            if order.invoice_id or order.state == 'invoiced':
                order.invoice_due_bucket = _('Invoiced')
            elif order.state == 'cancelled':
                order.invoice_due_bucket = _('Cancelled')
            elif not order.invoice_date:
                order.invoice_due_bucket = _('No Invoice Date')
            else:
                invoice_month = order.invoice_date.replace(day=1)
                if invoice_month < current_month:
                    order.invoice_due_bucket = _('Overdue')
                elif invoice_month == current_month:
                    order.invoice_due_bucket = _('To Invoice This Month')
                elif invoice_month.year > today.year:
                    order.invoice_due_bucket = _('Future Year')
                else:
                    order.invoice_due_bucket = _('To Invoice %s') % order.invoice_date.strftime('%b %Y')

    @api.depends('invoice_id', 'state')
    def _compute_invoice_submission_status(self):
        for order in self:
            if order.invoice_id or order.state == 'invoiced':
                order.invoice_submission_status = 'submitted'
            else:
                order.invoice_submission_status = 'not_submitted'

    @api.depends('invoice_date', 'invoice_id', 'state')
    def _compute_is_overdue_amc_pending(self):
        today = fields.Date.context_today(self)
        current_month = today.replace(day=1)
        for order in self:
            if order.invoice_id or order.state in ('invoiced', 'cancelled'):
                order.is_overdue_amc_pending = False
            elif order.state not in ('draft', 'order'):
                order.is_overdue_amc_pending = False
            elif not order.invoice_date:
                order.is_overdue_amc_pending = False
            else:
                invoice_month = order.invoice_date.replace(day=1)
                order.is_overdue_amc_pending = invoice_month < current_month

    @api.depends(
        'contract_id',
        'contract_id.unit_id',
        'contract_id.unit_id.name',
        'contract_id.unit_id.code',
        'contract_id.project_id',
        'contract_id.project_id.name',
        'contract_id.name',
    )
    def _compute_property_name(self):
        for rec in self:
            c = rec.contract_id
            if not c:
                rec.property_name = False
                continue
            parts = []
            if c.project_id and c.project_id.name:
                parts.append(c.project_id.name.strip())
            if c.unit_id:
                label = (c.unit_id.name or c.unit_id.code or '').strip()
                if label:
                    parts.append(label)
            rec.property_name = ' - '.join(parts) if parts else (c.name or '')

    @api.depends('contract_id.contract_date', 'contract_id.contract_expiry')
    def _compute_amc_period_display(self):
        for rec in self:
            c = rec.contract_id
            if c and c.contract_date and c.contract_expiry:
                rec.amc_period_display = '%s to %s' % (
                    c.contract_date.strftime('%d-%m-%Y'),
                    c.contract_expiry.strftime('%d-%m-%Y'),
                )
            elif c and c.contract_date:
                rec.amc_period_display = c.contract_date.strftime('%d-%m-%Y')
            else:
                rec.amc_period_display = ''

    @api.depends('invoice_date')
    def _compute_billing_month_label(self):
        for rec in self:
            if rec.invoice_date:
                rec.billing_month_label = rec.invoice_date.strftime('%b-%y')
            else:
                rec.billing_month_label = ''

    @api.depends('invoice_id', 'invoice_id.name', 'name')
    def _compute_invoice_display_ref(self):
        for rec in self:
            if rec.invoice_id:
                rec.invoice_display_ref = rec.invoice_id.name or ''
            else:
                rec.invoice_display_ref = rec.name or ''

    @api.model
    def create(self, vals):
        if vals.get('name', _('Draft')) in (_('Draft'), _('New'), '/'):
            vals['name'] = self._next_contract_order_number(vals)
        return super().create(vals)

    def _next_contract_order_number(self, vals):
        sequence_date = vals.get('date_order') or vals.get('invoice_date') or fields.Date.context_today(self)
        sequence = False
        if hasattr(self.env['ir.sequence'], 'next_by_sequence_for'):
            sequence = self.env['ir.sequence'].next_by_sequence_for('cafm_contract_order', sequence_date=sequence_date)
        return sequence or self.env['ir.sequence'].next_by_code('cpabooks.cafm.contract.order', sequence_date=sequence_date) or _('Draft')

    def action_confirm(self):
        self.write({'state': 'order'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_set_draft(self):
        self.write({'state': 'draft'})

    def _get_income_account(self):
        revenue_type = self.env.ref('account.data_account_type_revenue', raise_if_not_found=False)
        domain = [
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
        ]
        if revenue_type:
            domain.append(('user_type_id', '=', revenue_type.id))
        account = self.env['account.account'].search(domain, limit=1)
        if not account:
            account = self.env['account.account'].search([
                ('company_id', '=', self.company_id.id),
                ('deprecated', '=', False),
            ], limit=1)
        if not account:
            raise UserError(_('Please configure an income account before creating invoices.'))
        return account

    def action_create_invoice(self):
        for order in self:
            if order.invoice_id:
                continue
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': order.partner_id.id,
                'invoice_date': order.invoice_date or fields.Date.context_today(order),
                'company_id': order.company_id.id,
                'currency_id': order.currency_id.id,
                'invoice_origin': order.name,
                'project_title': order.contract_id.project_id.name or order.contract_id.name,
                'invoice_line_ids': [(0, 0, {
                    'name': '%s - %s' % (order.contract_id.name, order.period_label or order.name),
                    'quantity': 1.0,
                    'price_unit': order.amount,
                    'account_id': order._get_income_account().id,
                })],
            })
            order.write({'invoice_id': invoice.id, 'state': 'invoiced'})
            if order.schedule_line_id:
                order.schedule_line_id.state = 'invoiced'
        return True

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

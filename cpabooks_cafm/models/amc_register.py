# -*- coding: utf-8 -*-

from calendar import monthrange
from datetime import date, datetime, timedelta
import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CafmContract(models.Model):
    _name = 'cpabooks.cafm.contract'
    _description = 'CAFM AMC Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'contract_expiry, contract_date, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Contract No.',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    active = fields.Boolean(default=True)
    amc_contract_type = fields.Selection([
        ('amc', 'AMC'),
        ('var', 'VAR'),
    ], string='Contract Type', default='amc', required=True)
    contract_date = fields.Date(string='Start Date', default=lambda self: fields.Date.context_today(self), tracking=True)
    contract_expiry = fields.Date(string='Expiry Date', tracking=True)
    renewal_date = fields.Date(string='Renewal Date')

    # Spreadsheet / import tracking columns (AMC Register Excel formats)
    serial_no = fields.Integer(string='SL')
    ubs_no = fields.Char(string='Client UBS Number', tracking=True, index=True)
    business_unit = fields.Char(string='Business Unit', index=True)
    last_invoiced_date = fields.Date(string='Last Invoiced')
    next_invoice_month = fields.Char(
        string='Next Invoice',
        help='Invoice month tags by frequency, e.g. Mar, Jun, Sep, Dec '
             '(end of each billing period). Expanded from frequency if one month given.',
    )
    invoice_update_status = fields.Selection([
        ('updated', 'Updated'),
        ('not_updated', 'Not updated'),
    ], string='Invoice Status', tracking=True)
    contract_check_status = fields.Selection([
        ('check_verified', 'check & verified'),
        ('auto_renewed_no_copy', 'Auto Renewed - No Cont. Copy'),
    ], string='Contract Check Status', tracking=True,
       help='Contract verification / renewal copy status.')
    verifying_date = fields.Date(string='Verifying Date')
    location = fields.Char(
        string='Location',
        help='Free-text location from AMC spreadsheet / register.',
        index=True,
    )

    client_id = fields.Many2one('res.partner', string='Client Name', required=True, tracking=True)
    customer_group_id = fields.Many2one('cpabooks.cafm.customer.group', string='Customer Group Name')
    customer_trn = fields.Char(string='Customer TRN', related='client_id.vat', readonly=False, store=True)
    contact_person_id = fields.Many2one('cpabooks.cafm.contact.person', string='Client Contact Person')
    contact_no = fields.Char(string='Client Contact Number')
    client_manager_id = fields.Many2one('res.users', string='Client Manager', tracking=True)
    gfs_supervisor_id = fields.Many2one(
        'res.users',
        string='GFS Supervisor',
        tracking=True,
        help='User responsible as GFS supervisor.',
    )
    gfs_admin_id = fields.Many2one(
        'res.users',
        string='GFS Admin',
        tracking=True,
        help='User responsible as GFS administrator.',
    )
    project_id = fields.Many2one('project.project', string='Project Name', tracking=True)
    unit_id = fields.Many2one('cpabooks.cafm.unit', string='Villa / Flat', domain="[('project_id', '=', project_id)]")
    project_location_id = fields.Many2one('cpabooks.cafm.location', string='Project Location')

    contract_status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    live_status = fields.Selection([
        ('live', 'Live'),
        ('non_live', 'Non Live'),
    ], string='Contract Status', default='live', tracking=True)
    contract_period_years = fields.Integer(string='Contract Period (Years)', default=1, required=True)
    invoice_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('half_yearly', 'Half Yearly'),
        ('annually', 'Annually'),
    ], string='Invoice Frequency', default='quarterly', required=True, tracking=True)
    total_contract_value = fields.Monetary(
        string='Contract Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        tracking=True,
    )
    number_of_flats = fields.Integer(string='No. of Flat / Villa')
    unit_contract_type = fields.Selection([
        ('villa', 'Villa'),
        ('flat', 'Flat'),
    ], string='Villa / Flat', default='villa', required=True)
    sqft_qty = fields.Float(string='SQFT Qty')
    yearly_contract_amount = fields.Monetary(
        string='Yearly Contract Amount',
        compute='_compute_contract_amounts',
        store=True,
        group_operator='sum',
        currency_field='currency_id',
    )
    quarterly_amount = fields.Monetary(
        string='Quarterly Amount',
        compute='_compute_contract_amounts',
        store=True,
        group_operator='sum',
        currency_field='currency_id',
    )
    monthly_revenue = fields.Monetary(
        string='Monthly Revenue',
        compute='_compute_contract_amounts',
        store=True,
        group_operator='sum',
        currency_field='currency_id',
    )
    invoicing_value = fields.Monetary(
        string='Invoicing Value',
        compute='_compute_contract_amounts',
        inverse='_inverse_invoicing_value',
        store=True,
        group_operator='sum',
        currency_field='currency_id',
    )
    rate_per_flat_yearly = fields.Monetary(
        string='Rate Per Flat (Yearly)',
        compute='_compute_contract_amounts',
        store=True,
        currency_field='currency_id',
    )
    rate_per_flat_monthly = fields.Monetary(
        string='Rate Per Flat (Monthly)',
        compute='_compute_contract_amounts',
        store=True,
        currency_field='currency_id',
    )
    sqft_rate = fields.Monetary(
        string='SQFT Rate',
        compute='_compute_contract_amounts',
        store=True,
        currency_field='currency_id',
    )
    days_to_expiry = fields.Integer(string='Days to Expiry', compute='_compute_days_to_expiry', store=True)
    schedule_line_ids = fields.One2many(
        'cpabooks.cafm.invoice.stagger',
        'contract_id',
        string='Invoice Schedule',
        copy=True,
    )
    contract_order_ids = fields.One2many(
        'cpabooks.cafm.contract.order',
        'contract_id',
        string='Contract Orders',
        copy=False,
    )
    contract_order_count = fields.Integer(compute='_compute_contract_order_count')
    invoicing_date = fields.Date(string='Invoicing Date', default=lambda self: fields.Date.context_today(self))
    flat_detail_ids = fields.One2many(
        'cpabooks.cafm.flat.detail',
        'contract_id',
        string='Flat Details',
        copy=True,
    )
    document_line_ids = fields.One2many(
        'cpabooks.cafm.contract.document',
        'contract_id',
        string='Contract Copy / Documents',
        copy=True,
    )
    schedule_total = fields.Monetary(
        string='Schedule Total',
        compute='_compute_schedule_total',
        store=True,
        currency_field='currency_id',
    )
    remarks = fields.Text(string='Remarks')
    notes = fields.Text()
    color = fields.Integer()
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Very High'),
    ], default='0')
    state_change_date = fields.Date(string='State Change Date', readonly=True, copy=False)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Contract number must be unique.'),
        ('period_positive', 'CHECK(contract_period_years > 0)', 'Contract period must be greater than zero.'),
        ('total_non_negative', 'CHECK(total_contract_value >= 0)', 'Total contract value cannot be negative.'),
        ('flats_non_negative', 'CHECK(number_of_flats >= 0)', 'Number of flats cannot be negative.'),
        ('sqft_non_negative', 'CHECK(sqft_qty >= 0)', 'SQFT quantity cannot be negative.'),
    ]

    @api.onchange('contract_date', 'contract_period_years')
    def _onchange_contract_dates(self):
        for rec in self:
            if rec.contract_date and rec.contract_period_years:
                expiry = rec.contract_date + timedelta(days=(rec.contract_period_years * 365) - 1)
                rec.contract_expiry = expiry
                rec.renewal_date = expiry

    def _inverse_invoicing_value(self):
        for rec in self:
            multiplier = {
                'monthly': 12,
                'quarterly': 4,
                'half_yearly': 2,
                'annually': 1,
            }.get(rec.invoice_frequency, 1)
            period = rec.contract_period_years or 1
            rec.total_contract_value = rec.invoicing_value * multiplier * period

    @api.depends('total_contract_value', 'contract_period_years', 'invoice_frequency', 'number_of_flats', 'sqft_qty')
    def _compute_contract_amounts(self):
        for rec in self:
            yearly_amount = rec.total_contract_value / rec.contract_period_years if rec.contract_period_years else 0.0
            quarterly_amount = yearly_amount / 4.0
            monthly_revenue = yearly_amount / 12.0
            invoicing_map = {
                'monthly': monthly_revenue,
                'quarterly': quarterly_amount,
                'half_yearly': yearly_amount / 2.0,
                'annually': yearly_amount,
            }
            rec.yearly_contract_amount = yearly_amount
            rec.quarterly_amount = quarterly_amount
            rec.monthly_revenue = monthly_revenue
            rec.invoicing_value = invoicing_map.get(rec.invoice_frequency, 0.0)
            rec.rate_per_flat_yearly = rec.total_contract_value / rec.number_of_flats if rec.number_of_flats else 0.0
            rec.rate_per_flat_monthly = rec.rate_per_flat_yearly / 12.0 if rec.number_of_flats else 0.0
            rec.sqft_rate = rec.total_contract_value / rec.sqft_qty if rec.sqft_qty else 0.0

    @api.depends('contract_expiry')
    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        for rec in self:
            exp = rec.contract_expiry
            if not exp:
                rec.days_to_expiry = 0
                continue
            if isinstance(exp, float) and not isinstance(exp, bool):
                try:
                    from openpyxl.utils.datetime import WINDOWS_EPOCH, from_excel
                    dt = from_excel(float(exp), WINDOWS_EPOCH)
                    exp = dt.date() if isinstance(dt, datetime) else None
                except Exception:
                    exp = None
            if not exp:
                rec.days_to_expiry = 0
                continue
            try:
                if isinstance(exp, datetime):
                    exp = exp.date()
                elif not isinstance(exp, date):
                    exp = fields.Date.to_date(exp)
                rec.days_to_expiry = (exp - today).days
            except Exception:
                rec.days_to_expiry = 0

    @api.depends('schedule_line_ids.amount')
    def _compute_schedule_total(self):
        for rec in self:
            rec.schedule_total = sum(rec.schedule_line_ids.mapped('amount'))

    def _compute_contract_order_count(self):
        for rec in self:
            rec.contract_order_count = len(rec.contract_order_ids)

    @api.onchange('contact_person_id')
    def _onchange_contact_person_id(self):
        if self.contact_person_id:
            self.contact_no = self.contact_person_id.mobile

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id:
            self.project_id = self.unit_id.project_id

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.cafm_location:
            location = self.env['cpabooks.cafm.location'].search([('name', '=', self.project_id.cafm_location)], limit=1)
            self.project_location_id = location
        elif self.project_id:
            self.project_location_id = False

    @api.constrains('contract_date', 'contract_expiry')
    def _check_contract_dates(self):
        for rec in self:
            if rec.contract_date and rec.contract_expiry and rec.contract_expiry < rec.contract_date:
                raise ValidationError(_('Contract expiry must be on or after the contract date.'))

    @api.model
    def create(self, vals):
        vals = self._prepare_import_vals(vals)
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('cpabooks.cafm.contract') or _('New')
        if vals.get('contract_date') and vals.get('contract_period_years') and not vals.get('contract_expiry'):
            start_date = fields.Date.to_date(vals['contract_date'])
            vals['contract_expiry'] = fields.Date.to_string(start_date + timedelta(days=(vals['contract_period_years'] * 365) - 1))
        if vals.get('contract_expiry') and not vals.get('renewal_date'):
            vals['renewal_date'] = vals['contract_expiry']
        if vals.get('contract_status') and vals['contract_status'] != 'draft':
            vals['state_change_date'] = fields.Date.context_today(self)
        return super().create(vals)

    def write(self, vals):
        vals = self._prepare_import_vals(vals)
        if 'contract_status' in vals:
            vals['state_change_date'] = fields.Date.context_today(self)
        return super().write(vals)

    def _prepare_import_vals(self, vals):
        vals = dict(vals)
        # Import wizard used to pass this as a scratch key; it is not a model field.
        vals.pop('invoice_amount_import', None)
        if vals.get('customer_trn') and vals.get('client_id'):
            self.env['res.partner'].browse(vals['client_id']).vat = vals['customer_trn']
        if 'invoicing_value' in vals and 'total_contract_value' not in vals:
            frequency = vals.get('invoice_frequency') or 'quarterly'
            multiplier = {
                'monthly': 12,
                'quarterly': 4,
                'half_yearly': 2,
                'annually': 1,
            }.get(frequency, 1)
            period = self._to_import_float(vals.get('contract_period_years') or 1)
            vals['total_contract_value'] = self._to_import_float(vals.get('invoicing_value')) * multiplier * int(period or 1)
        return vals

    def _to_import_float(self, value):
        if value in (False, None, ''):
            return 0.0
        if isinstance(value, str):
            value = value.replace(',', '').strip()
        return float(value or 0.0)

    def action_confirm(self):
        self.write({'contract_status': 'active'})

    def action_set_pending(self):
        self.write({'contract_status': 'pending'})

    def action_set_draft(self):
        self.write({'contract_status': 'draft'})

    def action_cancel(self):
        self.write({'contract_status': 'cancelled'})

    def action_mark_expired(self):
        self.write({'contract_status': 'expired'})

    def action_reset_schedule(self):
        self.mapped('schedule_line_ids').unlink()

    def action_generate_invoice_schedule(self):
        for contract in self:
            contract._generate_invoice_schedule()

    def action_create_contract_orders(self):
        for contract in self:
            contract._auto_renew_live_if_expired()
            contract._create_contract_orders(invoice_date=contract.invoicing_date)

    def action_create_contract_orders_by_invoice_date(self):
        for contract in self:
            contract._auto_renew_live_if_expired(as_of=contract.invoicing_date)
            contract._create_contract_orders(invoice_date=contract.invoicing_date)

    def action_clear_contract_orders(self):
        for contract in self:
            invoiced_orders = contract.contract_order_ids.filtered(lambda order: order.invoice_id)
            if invoiced_orders:
                raise UserError(_('You cannot clear contract orders that already have invoices.'))
            contract.contract_order_ids.unlink()
            contract.schedule_line_ids.unlink()

    def action_view_contract_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract Orders'),
            'res_model': 'cpabooks.cafm.contract.order',
            'view_mode': 'tree,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
            'target': 'current',
        }

    def action_generate_flat_villa_lines(self):
        for contract in self:
            if contract.number_of_flats < 0:
                raise UserError(_('No. of Flat / Villa cannot be negative.'))
            contract.flat_detail_ids.unlink()
            line_values = []
            for index in range(1, contract.number_of_flats + 1):
                number = 1000 + index
                label = 'Flat' if contract.unit_contract_type == 'flat' else 'Villa'
                code = '%s-%s' % (label, number)
                line_values.append((0, 0, {
                    'sequence': index,
                    'contract_type': contract.unit_contract_type,
                    'flat_code': code,
                    'flat_name': code,
                }))
            contract.write({'flat_detail_ids': line_values})

    def action_clear_flat_villa_lines(self):
        self.mapped('flat_detail_ids').unlink()

    def _get_schedule_interval(self):
        self.ensure_one()
        return {
            'monthly': (1, 12),
            'quarterly': (3, 4),
            'half_yearly': (6, 2),
            'annually': (12, 1),
        }.get(self.invoice_frequency, (3, 4))

    AUTO_RENEWED_CHECK_STATUS = 'auto_renewed_no_copy'
    CHECK_VERIFIED_STATUS = 'check_verified'

    @api.model
    def _normalize_check_status_text(self, value):
        text = (value or '').strip().lower()
        text = text.replace(' and ', ' & ')
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('.', '').strip()
        return text

    @api.model
    def _parse_contract_check_status(self, value):
        """Map Excel / free text → Selection key."""
        if value in (False, None, ''):
            return False
        # Already a selection key
        if value in ('check_verified', 'auto_renewed_no_copy'):
            return value
        text = self._normalize_check_status_text(value)
        if text in (
            'check & verified',
            'checked & verified',
            'check verified',
            'checked verified',
        ):
            return self.CHECK_VERIFIED_STATUS
        if 'auto renewed' in text or 'auto-renewed' in text or 'no cont copy' in text:
            return self.AUTO_RENEWED_CHECK_STATUS
        return False

    @api.model
    def _is_check_verified_status(self, value):
        if value == self.CHECK_VERIFIED_STATUS:
            return True
        return self._parse_contract_check_status(value) == self.CHECK_VERIFIED_STATUS

    def _auto_renew_live_if_expired(self, as_of=False):
        """For Live contracts expired as of yesterday: roll start/end and update status.

        - Non Live: do not change dates.
        - Live + still valid (expiry >= today when as_of is today): no date change;
          keep check & verified / Auto Renewed status as-is.
        - Live + expired till yesterday (expiry < as_of / today): renew dates and set
          status to Auto Renewed - No Cont. Copy.

        Do NOT pass a future wizard end date as as_of — pending-order creation must not
        renew contracts just to fill a future creation period.
        """
        as_of_date = fields.Date.to_date(as_of) if as_of else fields.Date.context_today(self)
        if isinstance(as_of_date, str):
            as_of_date = fields.Date.to_date(as_of_date)
        # "Expired till yesterday" → expiry must be strictly before as_of (usually today).
        renewed_contracts = self.browse()
        for contract in self:
            if contract.live_status != 'live':
                continue
            if not contract.contract_expiry:
                continue
            expiry = contract.contract_expiry
            if isinstance(expiry, str):
                expiry = fields.Date.to_date(expiry)
            if not expiry or expiry >= as_of_date:
                # Still valid through yesterday / today: keep original dates & status.
                continue

            period = max(1, min(int(contract.contract_period_years or 1), 5))
            new_start = expiry + timedelta(days=1)
            new_end = new_start + relativedelta(years=period, days=-1)
            # Keep rolling until the term covers as_of (multi-year gap already past).
            safety = 0
            while new_end < as_of_date and safety < 20:
                new_start = new_end + timedelta(days=1)
                new_end = new_start + relativedelta(years=period, days=-1)
                safety += 1

            vals = {
                'contract_date': new_start,
                'contract_expiry': new_end,
                'renewal_date': new_end,
                'contract_check_status': self.AUTO_RENEWED_CHECK_STATUS,
            }
            if contract.contract_status in ('expired', 'draft', 'pending'):
                vals['contract_status'] = 'active'
            contract.write(vals)
            renewed_contracts |= contract
        return renewed_contracts

    def _is_live_valid_today(self, as_of=False):
        """Live contract whose expiry is still on/after today (or no expiry set)."""
        self.ensure_one()
        if self.live_status != 'live':
            return False
        as_of_date = fields.Date.to_date(as_of) if as_of else fields.Date.context_today(self)
        if isinstance(as_of_date, str):
            as_of_date = fields.Date.to_date(as_of_date)
        if not self.contract_expiry:
            return True
        expiry = self.contract_expiry
        if isinstance(expiry, str):
            expiry = fields.Date.to_date(expiry)
        return bool(expiry and expiry >= as_of_date)

    def _get_contract_schedule_end(self, force_end_date=False):
        """End date for schedule generation.

        Default: contract expiry (or period years), capped at 5 years from start.
        When force_end_date is set (wizard Until) for a Live+valid-today contract,
        schedule may extend to that date without changing stored contract dates.
        """
        self.ensure_one()
        if not self.contract_date:
            return False
        force_end = fields.Date.to_date(force_end_date) if force_end_date else False
        if force_end and self._is_live_valid_today():
            # Live + still valid today → treat as valid through wizard Until for orders only
            return force_end

        max_end = self.contract_date + relativedelta(years=5, days=-1)
        if self.contract_expiry:
            end = self.contract_expiry
        else:
            years = max(1, min(int(self.contract_period_years or 1), 5))
            end = self.contract_date + relativedelta(years=years, days=-1)
        return min(end, max_end)

    def _iter_schedule_period_vals(self, invoice_day=False, force_end_date=False):
        """Build stagger vals from contract start through schedule end."""
        self.ensure_one()
        if not self.contract_date:
            return []
        interval_months, _periods = self._get_schedule_interval()
        expiry = self._get_contract_schedule_end(force_end_date=force_end_date)
        if not expiry:
            return []
        # Long wizard Until (e.g. 2050) needs more than 60 monthly slots
        max_periods = 600 if force_end_date else 60
        vals_list = []
        index = 0
        date_from = self.contract_date
        while date_from <= expiry and index < max_periods:
            date_to = date_from + relativedelta(months=interval_months, days=-1)
            if date_to > expiry:
                date_to = expiry
            sequence = index + 1
            vals_list.append({
                'sequence': sequence,
                'name': _('Stagger %s') % sequence,
                'period_label': self._get_period_label(sequence, date_from, date_to),
                'date_from': date_from,
                'date_to': date_to,
                'invoice_date': self._get_period_invoice_date(date_from, invoice_day),
                'amount': self.invoicing_value,
            })
            index += 1
            date_from = self.contract_date + relativedelta(months=index * interval_months)
            if date_from > expiry:
                break
        return vals_list

    def _ensure_full_invoice_schedule(self, invoice_day=False, force_end_date=False):
        """Ensure stagger lines cover the schedule end (add missing periods)."""
        self.ensure_one()
        if not self.contract_date:
            raise UserError(_('Set the contract start date before creating contract orders.'))
        planned = self._iter_schedule_period_vals(
            invoice_day=invoice_day,
            force_end_date=force_end_date,
        )
        if not planned:
            raise UserError(_('Could not build an invoice schedule for contract %s.') % self.display_name)
        if not self.schedule_line_ids:
            self.write({'schedule_line_ids': [(0, 0, vals) for vals in planned]})
            return self.schedule_line_ids

        existing_from = {
            fields.Date.to_date(d) if d else False
            for d in self.schedule_line_ids.mapped('date_from')
        }
        seq = max(self.schedule_line_ids.mapped('sequence') or [0])
        to_add = []
        for vals in planned:
            date_from = vals['date_from']
            if date_from in existing_from:
                continue
            seq += 1
            line_vals = dict(vals, sequence=seq, name=_('Stagger %s') % seq)
            to_add.append((0, 0, line_vals))
        if to_add:
            self.write({'schedule_line_ids': to_add})
        return self.schedule_line_ids

    def _generate_invoice_schedule(self, invoice_day=False):
        self.ensure_one()
        if self.schedule_line_ids:
            raise UserError(_('Reset the existing invoice schedule before generating a new one.'))
        if not self.contract_date:
            raise UserError(_('Set the contract date before generating the invoice schedule.'))
        planned = self._iter_schedule_period_vals(invoice_day=invoice_day)
        if not planned:
            raise UserError(_('Set a valid contract period / expiry before generating the invoice schedule.'))
        self.write({'schedule_line_ids': [(0, 0, vals) for vals in planned]})

    def _get_period_invoice_date(self, period_start, invoice_day=False):
        self.ensure_one()
        day = invoice_day or period_start.day
        last_day = monthrange(period_start.year, period_start.month)[1]
        return period_start.replace(day=min(day, last_day))

    def _get_period_label(self, sequence, date_from, date_to):
        self.ensure_one()
        label_prefix = {
            'monthly': _('M%s') % sequence,
            'quarterly': _('Q%s') % sequence,
            'half_yearly': _('H%s') % sequence,
            'annually': _('Y%s') % sequence,
        }.get(self.invoice_frequency, _('Period %s') % sequence)
        return '%s (%s to %s)' % (
            label_prefix,
            fields.Date.to_string(date_from),
            fields.Date.to_string(date_to),
        )

    def _create_contract_orders(self, invoice_date=False):
        """Create orders for all schedule lines (used by form Create Cont. Order)."""
        self.ensure_one()
        self._create_pending_contract_orders(from_date=False, invoice_date=invoice_date)

    def _create_pending_contract_orders(self, from_date=False, to_date=False, invoice_date=False):
        """Create missing contract orders within an optional period window.

        Wizard Start/Until filters by **period overlap**.
        If Live and still valid today, schedule/orders extend to wizard Until even when
        the stored contract expiry falls in the middle — contract dates are NOT changed.
        Non Live (or not valid today) still stop at contract expiry.
        """
        self.ensure_one()
        invoice_day = False
        if invoice_date:
            invoice_day = invoice_date.day if hasattr(invoice_date, 'day') else False
        elif from_date:
            invoice_day = from_date.day if hasattr(from_date, 'day') else False

        # Legacy behaviour: empty schedule + empty orders → rebuild schedule day from invoice_date
        if self.schedule_line_ids and not self.contract_order_ids and not from_date and not to_date:
            self.schedule_line_ids.unlink()

        force_end = False
        to_d = fields.Date.to_date(to_date) if to_date else False
        if to_d and self._is_live_valid_today():
            force_end = to_d

        self._ensure_full_invoice_schedule(invoice_day=invoice_day, force_end_date=force_end)
        schedule_lines = self.schedule_line_ids.sorted('date_from')
        if not schedule_lines:
            raise UserError(_('No invoice schedule lines for contract %s.') % self.display_name)

        from_d = fields.Date.to_date(from_date) if from_date else False
        order_model = self.env['cpabooks.cafm.contract.order']
        created = self.env['cpabooks.cafm.contract.order']
        for line in schedule_lines:
            line_start = fields.Date.to_date(line.date_from) if line.date_from else False
            line_end = fields.Date.to_date(line.date_to) if line.date_to else line_start
            # Overlap with [from_d, to_d]: period ends before window OR starts after → skip
            if from_d and line_end and line_end < from_d:
                continue
            if to_d and line_start and line_start > to_d:
                continue
            existing = order_model.search([
                ('contract_id', '=', self.id),
                '|',
                ('schedule_line_id', '=', line.id),
                '&',
                ('date_from', '=', line.date_from),
                ('date_to', '=', line.date_to),
            ], limit=1)
            if existing:
                continue
            created |= order_model.create({
                'contract_id': self.id,
                'schedule_line_id': line.id,
                'partner_id': self.client_id.id,
                'date_order': line.invoice_date or line.date_from,
                'invoice_date': line.invoice_date or line.date_from,
                'date_from': line.date_from,
                'date_to': line.date_to,
                'period_label': line.period_label,
                'amount': line.amount,
                'currency_id': self.currency_id.id,
                'company_id': self.company_id.id,
            })
        return created

    def action_open_project(self):
        self.ensure_one()
        if not self.project_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project'),
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_unit(self):
        self.ensure_one()
        if not self.unit_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Villa / Flat'),
            'res_model': 'cpabooks.cafm.unit',
            'res_id': self.unit_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

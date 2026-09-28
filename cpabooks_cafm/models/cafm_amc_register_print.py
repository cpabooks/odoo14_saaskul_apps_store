# -*- coding: utf-8 -*-

import calendar
import re
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Date as OdooDate


_MONTH_ALIASES = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}


def _rolling_start(today=None):
    """First day of last month (always top of the 12-month window)."""
    today = today or date.today()
    return (today.replace(day=1) - relativedelta(months=1))


def cafm_rolling_months(today=None, count=12):
    """Return list of (YYYY-MM, 'Mon YYYY') starting from last month."""
    start = _rolling_start(today)
    rows = []
    for index in range(count):
        cur = start + relativedelta(months=index)
        rows.append((cur.strftime('%Y-%m'), cur.strftime('%b %Y')))
    return rows


def cafm_parse_month_token(raw, ref_date=None):
    """Parse free-text next invoice month → date(year, month, 1) or False."""
    text = (raw or '').strip()
    if not text:
        return False
    ref_date = ref_date or date.today()
    # YYYY-MM
    m = re.match(r'^(\d{4})-(\d{1,2})$', text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return date(y, mo, 1)
    # Mon YYYY / Month YYYY / Mon-YY
    m = re.match(r'^([A-Za-z]+)\s*[-/ ]\s*(\d{2,4})$', text)
    if m:
        mo = _MONTH_ALIASES.get(m.group(1).lower())
        y = int(m.group(2))
        if y < 100:
            y += 2000
        if mo:
            return date(y, mo, 1)
    # Month name only → map into rolling 12-month window
    mo = _MONTH_ALIASES.get(text.lower())
    if mo:
        for key, _label in cafm_rolling_months(ref_date, 12):
            y, mth = map(int, key.split('-'))
            if mth == mo:
                return date(y, mth, 1)
        # fallback current/next occurrence
        y = ref_date.year
        candidate = date(y, mo, 1)
        if candidate < _rolling_start(ref_date):
            candidate = date(y + 1, mo, 1)
        return candidate
    return False


def cafm_split_month_tokens(raw):
    """Split tag-style Next Invoice text: 'Mar, Jun, Sep, Dec' / 'Jul|Oct'."""
    text = (raw or '').strip()
    if not text:
        return []
    parts = re.split(r'[,;/|]+', text)
    return [p.strip() for p in parts if p and p.strip()]


def cafm_month_nums_from_raw(raw, ref_date=None):
    """Unique calendar month numbers (1-12) parsed from tag / free text."""
    nums = []
    for token in cafm_split_month_tokens(raw):
        parsed = cafm_parse_month_token(token, ref_date)
        if parsed:
            nums.append(parsed.month)
        else:
            mo = _MONTH_ALIASES.get(token.lower().strip('.'))
            if mo:
                nums.append(mo)
    # keep first-seen order then unique
    seen = set()
    ordered = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def cafm_default_month_nums(frequency):
    """Calendar invoice-end months by frequency (when field empty)."""
    if frequency == 'monthly':
        return list(range(1, 13))
    if frequency == 'quarterly':
        return [3, 6, 9, 12]  # Mar, Jun, Sep, Dec
    if frequency == 'half_yearly':
        return [6, 12]  # Jun, Dec
    if frequency == 'annually':
        return [12]  # Dec
    return [3, 6, 9, 12]


def cafm_expand_month_nums(frequency, month_nums):
    """Expand a single anchor month by frequency step; keep multi tags as-is."""
    step = {
        'monthly': 1,
        'quarterly': 3,
        'half_yearly': 6,
        'annually': 12,
    }.get(frequency or 'quarterly', 3)

    if not month_nums:
        return cafm_default_month_nums(frequency)

    if frequency == 'monthly':
        return list(range(1, 13))

    if len(month_nums) >= 2:
        return sorted(set(month_nums))

    # One anchor → walk the year by step (invoice end of each period)
    start = month_nums[0]
    result = []
    m = start
    for _ in range(max(1, 12 // step)):
        result.append(((m - 1) % 12) + 1)
        m += step
    return sorted(set(result))


def cafm_frequency_schedule(frequency, raw_next, today=None):
    """
    Rolling 12-month schedule rows: (YYYY-MM, 'Mon YYYY', month_num).
    Uses invoice frequency + Next Invoice tag months (Mar, Jun, Sep, Dec…).
    """
    today = today or date.today()
    month_nums = cafm_expand_month_nums(
        frequency, cafm_month_nums_from_raw(raw_next, today),
    )
    rows = []
    for key, label in cafm_rolling_months(today, 12):
        _y, mo = map(int, key.split('-'))
        if mo in month_nums:
            rows.append((key, label, mo))
    return rows


def cafm_schedule_abbr_text(frequency, raw_next, today=None):
    """Tag-style Next Invoice text without year: 'Mar, Jun, Sep, Dec'."""
    today = today or date.today()
    month_nums = cafm_expand_month_nums(
        frequency, cafm_month_nums_from_raw(raw_next, today),
    )
    return ', '.join(calendar.month_abbr[m] for m in month_nums)


def cafm_month_match_labels(month_key):
    """All label variants that can match a YYYY-MM key in Char fields."""
    y, m = map(int, month_key.split('-'))
    d = date(y, m, 1)
    abbr = d.strftime('%b')
    full = d.strftime('%B')
    return [
        month_key,
        d.strftime('%b %Y'),
        d.strftime('%B %Y'),
        d.strftime('%b-%Y'),
        d.strftime('%B-%Y'),
        d.strftime('%b/%Y'),
        abbr,
        full,
        abbr.lower(),
        full.lower(),
        calendar.month_abbr[m],
        calendar.month_name[m],
    ]



class CafmAmcNextInvoicePrintWizard(models.TransientModel):
    _name = 'cpabooks.cafm.amc.next.invoice.print.wizard'
    _description = 'Print AMC Contracts To be Invoiced'

    month_key = fields.Selection(
        selection='_selection_month_key',
        string='Next Invoice Month',
        required=True,
    )
    client_id = fields.Many2one('res.partner', string='Client')
    customer_group_id = fields.Many2one(
        'cpabooks.cafm.customer.group', string='Client Group',
    )
    project_id = fields.Many2one('project.project', string='Project')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )

    @api.model
    def _selection_month_key(self):
        return cafm_rolling_months(fields.Date.context_today(self), 12)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        months = cafm_rolling_months(fields.Date.context_today(self), 12)
        # Default to current calendar month if in window, else first (= last month)
        today = fields.Date.context_today(self)
        current_key = today.replace(day=1).strftime('%Y-%m')
        keys = [k for k, _l in months]
        if 'month_key' in fields_list:
            res['month_key'] = current_key if current_key in keys else (keys[0] if keys else False)
        return res

    def _month_label(self):
        self.ensure_one()
        for key, label in cafm_rolling_months(fields.Date.context_today(self), 12):
            if key == self.month_key:
                return label
        return self.month_key or ''

    def _contracts_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
            ('invoice_month_tag_ids.key', '=', self.month_key),
        ]
        if self.client_id:
            domain.append(('client_id', '=', self.client_id.id))
        if self.customer_group_id:
            domain.append(('customer_group_id', '=', self.customer_group_id.id))
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))
        return domain

    def _get_contracts(self):
        self.ensure_one()
        return self.env['cpabooks.cafm.contract'].search(
            self._contracts_domain(),
            order='client_id, project_id, name, id',
        )

    def action_print(self):
        self.ensure_one()
        contracts = self._get_contracts()
        if not contracts:
            raise UserError(_(
                'No AMC contracts found to be invoiced for %(month)s'
                '%(extra)s.'
            ) % {
                'month': self._month_label(),
                'extra': self._filter_extra_label(),
            })
        return self.env.ref(
            'cpabooks_cafm.action_report_cafm_next_invoice_list'
        ).report_action(
            contracts,
            data={
                'month_key': self.month_key,
                'month_label': self._month_label(),
                'client_name': self.client_id.display_name if self.client_id else '',
                'customer_group_name': (
                    self.customer_group_id.display_name if self.customer_group_id else ''
                ),
                'project_name': self.project_id.display_name if self.project_id else '',
                'company_name': self.company_id.display_name,
            },
        )

    def _filter_extra_label(self):
        parts = []
        if self.client_id:
            parts.append(_('Client=%s') % self.client_id.display_name)
        if self.customer_group_id:
            parts.append(_('Client Group=%s') % self.customer_group_id.display_name)
        if self.project_id:
            parts.append(_('Project=%s') % self.project_id.display_name)
        return (', ' + ', '.join(parts)) if parts else ''


class CafmInvoiceMonthTag(models.Model):
    _name = 'cpabooks.cafm.invoice.month.tag'
    _description = 'AMC Invoice Month Tag'
    _order = 'sort_key, name'

    name = fields.Char(string='Month', required=True, index=True)
    key = fields.Char(string='Key', required=True, index=True)
    sort_key = fields.Integer(string='Sort', index=True)

    _sql_constraints = [
        ('key_uniq', 'unique(key)', 'Invoice month key must be unique.'),
    ]


class CafmContractMonthLine(models.Model):
    """One row per contract × invoice month so list groupby works (M2M cannot groupby)."""
    _name = 'cpabooks.cafm.contract.month.line'
    _description = 'AMC Register Invoice Month Line'
    _order = 'month_sort, client_id, name, id'
    _rec_name = 'display_name'

    contract_id = fields.Many2one(
        'cpabooks.cafm.contract', string='AMC Contract',
        required=True, ondelete='cascade', index=True,
    )
    month_key = fields.Char(string='Month Key', required=True, index=True)
    month_label = fields.Char(string='Next Invoice', required=True, index=True)
    month_sort = fields.Integer(string='Sort', index=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    name = fields.Char(related='contract_id.name', string='Contract', store=True, readonly=True)
    client_id = fields.Many2one(
        related='contract_id.client_id', string='Client Name', store=True, readonly=True,
    )
    project_id = fields.Many2one(
        related='contract_id.project_id', string='Project Name', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        related='contract_id.currency_id', string='Currency', store=True, readonly=True,
    )
    yearly_contract_amount = fields.Monetary(
        related='contract_id.yearly_contract_amount', string='Yearly Amount',
        store=True, readonly=True, currency_field='currency_id',
    )
    monthly_revenue = fields.Monetary(
        related='contract_id.monthly_revenue', string='Monthly Amount',
        store=True, readonly=True, currency_field='currency_id',
    )
    invoicing_value = fields.Monetary(
        related='contract_id.invoicing_value', string='Next Invoice Amount',
        store=True, readonly=True, currency_field='currency_id',
    )
    total_contract_value = fields.Monetary(
        related='contract_id.total_contract_value', string='Cont. Amount',
        store=True, readonly=True, currency_field='currency_id',
    )
    contract_status = fields.Selection(
        related='contract_id.contract_status', string='Status', store=True, readonly=True,
    )
    company_id = fields.Many2one(
        related='contract_id.company_id', string='Company', store=True, readonly=True, index=True,
    )
    active = fields.Boolean(related='contract_id.active', store=True, readonly=True)

    # Extra register fields for optional columns (3-dots) — not shown by default
    serial_no = fields.Integer(related='contract_id.serial_no', string='SL', readonly=True)
    ubs_no = fields.Char(related='contract_id.ubs_no', string='Client UBS Number', readonly=True)
    business_unit = fields.Char(related='contract_id.business_unit', string='Business Unit', readonly=True)
    customer_group_id = fields.Many2one(
        related='contract_id.customer_group_id', string='Customer Group Name',
        store=True, readonly=True,
    )
    customer_trn = fields.Char(related='contract_id.customer_trn', string='Customer TRN', readonly=True)
    contact_person_id = fields.Many2one(
        related='contract_id.contact_person_id', string='Client Contact Person', readonly=True,
    )
    contact_no = fields.Char(related='contract_id.contact_no', string='Client Contact Number', readonly=True)
    client_manager_id = fields.Many2one(
        related='contract_id.client_manager_id', string='Client Manager', readonly=True,
    )
    gfs_supervisor_id = fields.Many2one(
        related='contract_id.gfs_supervisor_id', string='GFS Supervisor', readonly=True,
    )
    gfs_admin_id = fields.Many2one(
        related='contract_id.gfs_admin_id', string='GFS Admin', readonly=True,
    )
    unit_id = fields.Many2one(related='contract_id.unit_id', string='Villa / Flat', readonly=True)
    project_location_id = fields.Many2one(
        related='contract_id.project_location_id', string='Project Location', readonly=True,
    )
    location = fields.Char(related='contract_id.location', string='Location', readonly=True)
    amc_contract_type = fields.Selection(
        related='contract_id.amc_contract_type', string='AMC Contract Type', readonly=True,
    )
    contract_date = fields.Date(related='contract_id.contract_date', string='Start Date', readonly=True)
    contract_expiry = fields.Date(related='contract_id.contract_expiry', string='Expiry Date', readonly=True)
    renewal_date = fields.Date(related='contract_id.renewal_date', string='Renewal Date', readonly=True)
    contract_period_years = fields.Integer(
        related='contract_id.contract_period_years', string='Contract Period (Years)', readonly=True,
    )
    invoice_frequency = fields.Selection(
        related='contract_id.invoice_frequency', string='Invoice Frequency', readonly=True,
    )
    next_invoice_month = fields.Char(
        related='contract_id.next_invoice_month', string='Next Invoice (raw)', readonly=True,
    )
    last_invoiced_date = fields.Date(
        related='contract_id.last_invoiced_date', string='Last Invoiced', readonly=True,
    )
    invoice_update_status = fields.Selection(
        related='contract_id.invoice_update_status', string='Inv. Status', readonly=True,
    )
    contract_check_status = fields.Selection(
        related='contract_id.contract_check_status', string='Contract Check', readonly=True,
    )
    live_status = fields.Selection(
        related='contract_id.live_status', string='Cont. Status', readonly=True,
    )
    verifying_date = fields.Date(related='contract_id.verifying_date', string='Verifying Date', readonly=True)
    quarterly_amount = fields.Monetary(
        related='contract_id.quarterly_amount', string='Quarterly Amount',
        readonly=True, currency_field='currency_id',
    )
    number_of_flats = fields.Integer(
        related='contract_id.number_of_flats', string='No. of Flat / Villa', readonly=True,
    )
    remarks = fields.Text(related='contract_id.remarks', string='Remarks', readonly=True)

    _sql_constraints = [
        (
            'contract_month_uniq',
            'unique(contract_id, month_key)',
            'Contract already linked to this invoice month.',
        ),
    ]

    @api.depends('name', 'month_label')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%s)' % (rec.name or '', rec.month_label or '')

    def unlink(self):
        """Deleting Register rows deletes the underlying AMC contract(s)."""
        contracts = self.mapped('contract_id')
        # Cascade from contract removes remaining month lines for those contracts.
        return contracts.unlink()

    def action_open_contract(self):
        self.ensure_one()
        if not self.contract_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.contract_id.display_name,
            'res_model': 'cpabooks.cafm.contract',
            'res_id': self.contract_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def cafm_register_month_filter_options(self):
        """12-month window for AMC Invoice Register toolbar (starts last month)."""
        today = OdooDate.context_today(self)
        return [
            {'key': key, 'label': label}
            for key, label in cafm_rolling_months(today, 12)
        ]

    @api.model
    def cafm_register_rolling_month_keys(self):
        today = OdooDate.context_today(self)
        return [key for key, _label in cafm_rolling_months(today, 12)]

    @api.model
    def cafm_register_amount_totals(self, domain=None):
        """Grand totals for Monthly Amount + Next Invoice Amount (footer row)."""
        domain = list(domain or [])
        if not any(term[0] == 'active' for term in domain if isinstance(term, (list, tuple)) and len(term) >= 3):
            domain = [('active', '=', True)] + domain
        rows = self.read_group(
            domain,
            ['monthly_revenue', 'invoicing_value'],
            [],
            lazy=False,
        )
        row = rows[0] if rows else {}
        return {
            'monthly_revenue': row.get('monthly_revenue') or 0.0,
            'invoicing_value': row.get('invoicing_value') or 0.0,
        }

    @api.model
    def cafm_register_x_view_data(self, domain=None, year=None):
        """Revenue schedule grid (X view): Jan–Dec with billed/unbilled markers + amounts."""
        today = OdooDate.context_today(self)
        year = int(year) if year else today.year
        domain = list(domain or [])
        if not any(
            term[0] == 'active'
            for term in domain
            if isinstance(term, (list, tuple)) and len(term) >= 3
        ):
            domain = [('active', '=', True)] + domain

        wizard = self.env['cafm.monthly.billing.wizard'].new({
            'period_start': date(year, 1, 1),
            'billing_scope': 'both',
            'view_mode': 'all',
        })
        months_slots = wizard._month_slots()
        month_keys = [month['start'].strftime('%Y-%m') for month in months_slots]
        key_index = {key: index for index, key in enumerate(month_keys)}

        month_lines = self.search(
            domain + [('contract_id.contract_status', '!=', 'cancelled')],
            order='serial_no, client_id, name, month_sort, id',
        )
        contracts = month_lines.mapped('contract_id')
        if not contracts:
            contracts = self.env['cpabooks.cafm.contract'].search([
                ('active', '=', True),
                ('contract_status', '!=', 'cancelled'),
                ('company_id', '=', self.env.company.id),
            ])

        line_keys = set()
        for contract in contracts:
            month_nums = cafm_expand_month_nums(
                contract.invoice_frequency,
                cafm_month_nums_from_raw(contract.next_invoice_month, today),
            )
            for month_num in month_nums:
                line_keys.add((contract.id, '%d-%02d' % (year, month_num)))
        assigned = wizard._assign_orders_to_month_keys(contracts, months_slots, line_keys)

        freq_abbr = {
            'monthly': 'M',
            'quarterly': 'Q',
            'half_yearly': 'H',
            'annually': 'Y',
        }
        amount_map = {
            'monthly': lambda c: c.monthly_revenue or c.invoicing_value or 0.0,
            'quarterly': lambda c: c.quarterly_amount or c.invoicing_value or 0.0,
            'half_yearly': lambda c: c.invoicing_value or 0.0,
            'annually': lambda c: c.invoicing_value or 0.0,
        }
        contract_rows = {}
        for contract in contracts:
            cid = contract.id
            month_nums = cafm_expand_month_nums(
                contract.invoice_frequency,
                cafm_month_nums_from_raw(contract.next_invoice_month, today),
            )
            ctype = (contract.amc_contract_type or 'amc').upper()
            description = (
                contract.project_id.display_name
                or (contract.unit_id.display_name if contract.unit_id else '')
                or contract.location
                or ''
            )
            row = {
                'contract_id': cid,
                'sl': contract.serial_no or 0,
                'type': ctype,
                'description': description,
                'client_number': contract.ubs_no or '',
                'client_name': contract.client_id.display_name if contract.client_id else '',
                'inv_type': freq_abbr.get(contract.invoice_frequency or '', ''),
                'months': [{'status': '', 'amount': 0.0} for _index in range(12)],
            }
            amount_fn = amount_map.get(contract.invoice_frequency, lambda c: c.invoicing_value or 0.0)
            amount = amount_fn(contract)
            for month_num in month_nums:
                month_key = '%d-%02d' % (year, month_num)
                month_index = key_index.get(month_key)
                if month_index is None:
                    continue
                order = assigned.get((cid, month_key))
                billed = bool(order and wizard._is_invoiced_order(order))
                row['months'][month_index] = {
                    'status': 'billed' if billed else 'unbilled',
                    'amount': amount,
                }
            if any(cell.get('status') for cell in row['months']):
                contract_rows[cid] = row

        rows = sorted(
            contract_rows.values(),
            key=lambda item: (item.get('sl') or 999999, item.get('client_name') or '', item.get('description') or ''),
        )
        monthly_totals = [0.0 for _index in range(12)]
        for row in rows:
            for index, cell in enumerate(row['months']):
                monthly_totals[index] += cell.get('amount') or 0.0

        return {
            'title': _('Revenue Schedule as of %s') % today.strftime('%d-%m-%y'),
            'year': year,
            'months': [month['label'] for month in months_slots],
            'rows': rows,
            'monthly_totals': monthly_totals,
        }

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        result = super().read_group(
            domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy,
        )
        if not groupby:
            return result
        gb = groupby[0].split(':')[0]
        if gb not in ('month_label', 'month_key'):
            return result
        today = OdooDate.context_today(self)
        rolling = cafm_rolling_months(today, 12)
        label_rank = {}
        for idx, (key, label) in enumerate(rolling):
            label_rank[key] = idx
            label_rank[label] = idx
            label_rank[label.lower()] = idx

        def _rank(row):
            val = row.get(gb)
            if not val:
                return 9999
            if isinstance(val, tuple):
                val = val[0]
            text = (val or '').strip()
            if text in label_rank:
                return label_rank[text]
            if text.lower() in label_rank:
                return label_rank[text.lower()]
            return 9000

        result.sort(key=_rank)
        return result


class CafmContractNextInvoicePrint(models.Model):
    _inherit = 'cpabooks.cafm.contract'

    invoice_month_tag_ids = fields.Many2many(
        'cpabooks.cafm.invoice.month.tag',
        'cpabooks_cafm_contract_invoice_month_rel',
        'contract_id',
        'tag_id',
        string='Invoice Months',
        help='Frequency-expanded invoice months (with year).',
    )
    next_invoice_period = fields.Char(string='Next Invoice Period', index=True)
    next_invoice_label = fields.Char(string='Next Invoice Label', index=True)
    next_invoice_sort = fields.Integer(string='Next Invoice Sort', index=True)
    invoice_month_line_ids = fields.One2many(
        'cpabooks.cafm.contract.month.line', 'contract_id', string='Invoice Month Lines',
    )

    def _rebuild_invoice_month_schedule(self):
        """Expand frequency → tag text + tags + month lines (groupby-safe)."""
        Tag = self.env['cpabooks.cafm.invoice.month.tag'].sudo()
        Line = self.env['cpabooks.cafm.contract.month.line'].sudo()
        today = fields.Date.context_today(self)
        tag_cache = {t.key: t for t in Tag.search([])}
        for rec in self:
            schedule = cafm_frequency_schedule(
                rec.invoice_frequency, rec.next_invoice_month, today,
            )
            abbr_text = cafm_schedule_abbr_text(
                rec.invoice_frequency, rec.next_invoice_month, today,
            )
            tags = Tag.browse()
            line_vals = []
            for key, label, _mo in schedule:
                tag = tag_cache.get(key)
                if not tag:
                    y, m = map(int, key.split('-'))
                    tag = Tag.create({
                        'name': label,
                        'key': key,
                        'sort_key': y * 12 + m,
                    })
                    tag_cache[key] = tag
                tags |= tag
                y, m = map(int, key.split('-'))
                line_vals.append({
                    'contract_id': rec.id,
                    'month_key': key,
                    'month_label': label,
                    'month_sort': y * 12 + m,
                })
            vals = {
                'invoice_month_tag_ids': [(6, 0, tags.ids)],
            }
            if abbr_text:
                vals['next_invoice_month'] = abbr_text
            if schedule:
                first_key, first_label, _mo = schedule[0]
                y, m = map(int, first_key.split('-'))
                vals.update({
                    'next_invoice_period': first_key,
                    'next_invoice_label': first_label,
                    'next_invoice_sort': y * 12 + m,
                })
            else:
                vals.update({
                    'next_invoice_period': False,
                    'next_invoice_label': False,
                    'next_invoice_sort': 0,
                })
            super(CafmContractNextInvoicePrint, rec).write(vals)
            Line.search([('contract_id', '=', rec.id)]).unlink()
            if line_vals:
                Line.create(line_vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('cafm_skip_invoice_month_sync'):
            records.with_context(cafm_skip_invoice_month_sync=True)._rebuild_invoice_month_schedule()
        return records

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get('cafm_skip_invoice_month_sync')
            and any(k in vals for k in ('invoice_frequency', 'next_invoice_month'))
        ):
            self.with_context(cafm_skip_invoice_month_sync=True)._rebuild_invoice_month_schedule()
        return res

    @api.model
    def action_open_next_invoice_print_wizard(self, domain=None):
        """Open month / filter popup for landscape print."""
        wizard = self.env['cpabooks.cafm.amc.next.invoice.print.wizard'].create({})
        for leaf in (domain or []):
            if not (isinstance(leaf, (list, tuple)) and len(leaf) >= 3):
                continue
            fname, op, value = leaf[0], leaf[1], leaf[2]
            if fname in ('month_key', 'month_label'):
                parsed = cafm_parse_month_token(value, fields.Date.context_today(self))
                if parsed:
                    wizard.month_key = parsed.strftime('%Y-%m')
                    break
            if fname == 'invoice_month_tag_ids' and op in ('in', '=', 'child_of'):
                tag = self.env['cpabooks.cafm.invoice.month.tag'].browse(
                    value[0] if isinstance(value, (list, tuple)) else value
                )
                if tag and tag.key:
                    wizard.month_key = tag.key
                    break
            if fname in ('next_invoice_month', 'next_invoice_label') and op in (
                '=', '=ilike', 'ilike',
            ):
                parsed = cafm_parse_month_token(value, fields.Date.context_today(self))
                if parsed:
                    wizard.month_key = parsed.strftime('%Y-%m')
                    break
            if fname == 'next_invoice_period' and op == '=':
                wizard.month_key = value
                break
        view = self.env.ref(
            'cpabooks_cafm.view_cafm_amc_next_invoice_print_wizard_form',
            raise_if_not_found=False,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Print AMC Contracts To be Invoiced'),
            'res_model': 'cpabooks.cafm.amc.next.invoice.print.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(view.id if view else False, 'form')],
            'view_id': view.id if view else False,
            'target': 'new',
            'context': dict(self.env.context),
        }

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """Keep Next Invoice Char groups in rolling order (not M2M — M2M cannot groupby)."""
        result = super().read_group(
            domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy,
        )
        if not groupby:
            return result
        gb = groupby[0].split(':')[0]
        if gb not in ('next_invoice_month', 'next_invoice_period', 'next_invoice_label'):
            return result

        today = OdooDate.context_today(self)
        rolling = cafm_rolling_months(today, 12)
        label_rank = {}
        for idx, (key, label) in enumerate(rolling):
            label_rank[key] = idx
            label_rank[label] = idx
            label_rank[label.lower()] = idx
            for alt in cafm_month_match_labels(key):
                label_rank[alt.lower()] = idx

        def _rank(row):
            val = row.get(gb)
            if not val:
                return 9999
            if isinstance(val, tuple):
                val = val[0]
            text = (val or '').strip()
            if text in label_rank:
                return label_rank[text]
            if text.lower() in label_rank:
                return label_rank[text.lower()]
            parsed = cafm_parse_month_token(text, today)
            if parsed:
                key = parsed.strftime('%Y-%m')
                return label_rank.get(key, 5000)
            return 9000

        result.sort(key=_rank)
        return result


class ReportCafmNextInvoiceList(models.AbstractModel):
    _name = 'report.cpabooks_cafm.report_cafm_next_invoice_list_template'
    _description = 'AMC Contracts To be Invoiced Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['cpabooks.cafm.contract'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'cpabooks.cafm.contract',
            'docs': docs,
            'data': data or {},
            'company': self.env.company,
            'res_company': self.env.company,
        }

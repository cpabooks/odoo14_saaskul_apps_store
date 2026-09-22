from odoo import api, fields, models, _
from odoo.addons.cpabooks_sequences.models.sequence_format import build_format_preview_html
from odoo.addons.cpabooks_sequences.models.cpabooks_module_checks import (
    MRP_SEQUENCE_FOR,
    mrp_installed,
)


CPABOOKS_SEQUENCE_DEFINITIONS = [
    ('reconcile', 'Account Full Reconcile', 'A', 0),
    ('sale', 'Sale Quotation', 'QT', 5),
    ('outgoing', 'Sale Delivery', 'DO', 5),
    ('sale_invoice', 'Sale Invoice', 'INV', 5),
    ('credit_note', 'Credit Note', 'RINV', 5),
    ('purchase', 'Purchase Order', 'LPO', 5),
    ('incoming', 'Purchase Receipt', 'GRN', 5),
    ('purchase_bill', 'Purchase Bill', 'BILL', 5),
    ('debit_note', 'Debit Note', 'RBILL', 5),
    ('internal', 'Internal Transfer', 'INT', 5),
    ('stock_adjustment', 'Stock Adjustment Journal', 'SAJ', 5),
    ('payment_voucher', 'Payment Voucher', 'PV', 5),
    ('receipt_voucher', 'Receipt Voucher', 'RV', 5),
    ('journal_voucher', 'Journal Voucher', 'JV', 5),
    ('crm', 'CRM', 'CRM', 5),
    ('job_estimation', 'Job Estimation', 'EST', 5),
    ('job_order', 'Job Order', 'JO', 5),
    ('project', 'Project', 'JOB', 5),
    ('bom', 'Bill of Material', 'BoM', 5),
    ('manufacturing', 'Manufacturing Orders', 'MO', 5),
    ('quality_chk', 'Quality Check', 'QC', 5),
    ('daily_site_report', 'Daily Site Report', 'DR', 5),
    ('weekly_site_report', 'Weekly Site Report', 'WR', 5),
    ('monthly_site_report', 'Monthly Site Report', 'MR', 5),
    ('supervisor_daily_report', 'Supervisor Daily Report', 'DSR', 5),
    ('supervisor_weekly_report', 'Supervisor Weekly Report', 'WSR', 5),
    ('supervisor_monthly_report', 'Supervisor Monthly Report', 'MSR', 5),
    ('client_report', 'Client Report', 'CR', 5),
    ('helpdesk_ticket', 'Helpdesk Ticket', 'HT', 5),
    ('pdc_payment', 'PDC Payment Voucher', 'PDP', 5),
    ('pdc_receipt', 'PDC Receipt Voucher', 'PDR', 5),
    ('fsm_crn', 'FSM CRN', 'CRN', 5),
    ('stock_issue_note', 'Material Issue Note', 'MIN', 5),
    ('stock_return_note', 'Material Return Note', 'MRN', 5),
    ('project_task', 'Project Task (TID)', 'TID', 5),
    ('transport_inquiry', 'Transport Inquiry', 'INQ', 5),
    ('transport_quotation', 'Transport Quotation', 'TQ', 5),
    ('transport_job', 'Transport Job', 'JOB', 5),
    ('transport_delivery', 'Transport Delivery Order', 'DO', 5),
    ('transport_tq_delivery', 'Transport TQ Delivery', 'TD', 5),
]

# Legacy default when company has no granularity set yet
MONTHLY_SEQUENCE_FOR = {'sale_invoice', 'purchase_bill', 'journal_voucher'}

# Main document sequences shown in Re-Sequences and company setup list
CPABOOKS_MAIN_SEQUENCE_FOR = (
    'sale',              # Sales (quotation)
    'outgoing',          # Delivery
    'sale_invoice',      # Invoice
    'payment_voucher',   # Payment
    'journal_voucher',   # Journal
)


class SetCompanyPrefix(models.Model):
    _name = 'set.company.prefix'
    _description = 'Set Company Prefix for all Sequences'

    name = fields.Char('Name', default='New')
    prefix = fields.Char('Prefix')
    sequence_granularity = fields.Selection(
        [
            ('yearly', 'Yearly (resets each year)'),
            ('monthly', 'Monthly (resets each month)'),
        ],
        string='Document Sequence Period',
        default='yearly',
    )
    sequence_year_digits = fields.Selection(
        [
            ('4', '4-digit year (2026)'),
            ('2', '2-digit year (26)'),
        ],
        string='Year Format',
        default='4',
    )
    sequence_number_digits = fields.Selection(
        [
            ('4', '4-digit number (0001)'),
            ('5', '5-digit number (00001)'),
        ],
        string='Sequence Number Length',
        default='5',
    )
    sequence_format_preview = fields.Html(
        string='Pattern Preview',
        compute='_compute_sequence_format_preview',
        sanitize=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if 'sequence_granularity' in fields_list and company:
            res.setdefault(
                'sequence_granularity',
                company.cpabooks_sequence_granularity or 'yearly',
            )
        if 'sequence_year_digits' in fields_list and company:
            res.setdefault(
                'sequence_year_digits',
                company.cpabooks_sequence_year_digits or '4',
            )
        if 'sequence_number_digits' in fields_list and company:
            res.setdefault(
                'sequence_number_digits',
                getattr(company, 'cpabooks_sequence_number_digits', None) or '5',
            )
        if 'prefix' in fields_list:
            ctx_prefix = self.env.context.get('default_prefix')
            if ctx_prefix:
                res.setdefault('prefix', ctx_prefix)
            elif getattr(company, 'cpabooks_sequence_prefix', None):
                res.setdefault('prefix', company.cpabooks_sequence_prefix)
        if 'sequence_granularity' in fields_list:
            res.setdefault(
                'sequence_granularity',
                self.env.context.get('default_sequence_granularity')
                or res.get('sequence_granularity'),
            )
        if 'sequence_year_digits' in fields_list:
            res.setdefault(
                'sequence_year_digits',
                self.env.context.get('default_sequence_year_digits')
                or res.get('sequence_year_digits'),
            )
        if 'sequence_number_digits' in fields_list:
            res.setdefault(
                'sequence_number_digits',
                self.env.context.get('default_sequence_number_digits')
                or res.get('sequence_number_digits'),
            )
        return res

    @api.depends(
        'prefix', 'sequence_granularity', 'sequence_year_digits', 'sequence_number_digits',
    )
    def _compute_sequence_format_preview(self):
        for rec in self:
            rec.sequence_format_preview = build_format_preview_html(
                rec.prefix,
                rec.sequence_granularity or 'yearly',
                rec.sequence_year_digits or '4',
                rec.sequence_number_digits or '5',
            )

    @api.onchange('sequence_granularity')
    def _onchange_sequence_granularity_defaults(self):
        for rec in self:
            if rec.sequence_granularity == 'monthly':
                rec.sequence_year_digits = '2'
                rec.sequence_number_digits = '4'
            else:
                rec.sequence_year_digits = '4'
                rec.sequence_number_digits = '5'

    @api.model
    def _resolve_granularity(self, company, sequence_for, granularity=None):
        if sequence_for == 'reconcile':
            return 'yearly'
        if granularity:
            return granularity
        if company and company.cpabooks_sequence_granularity:
            return company.cpabooks_sequence_granularity
        if sequence_for in MONTHLY_SEQUENCE_FOR:
            return 'monthly'
        return 'yearly'

    @api.model
    def _sequence_pattern_value(self, granularity, year_digits='4'):
        if granularity == 'monthly':
            return 'month_year_monthly'
        if year_digits == '2':
            return 'year'
        return 'year_yearly'

    @api.model
    def _format_prefix(self, document_code, company_prefix, sequence_for, company=None, granularity=None):
        company_prefix = (company_prefix or '').strip()
        if sequence_for == 'reconcile':
            return document_code
        gran = self._resolve_granularity(company, sequence_for, granularity)
        if gran == 'monthly':
            return '%s/%s/%%(year)s/%%(month)s/' % (document_code, company_prefix)
        return '%s/%s/%%(year)s/' % (document_code, company_prefix)

    @api.model
    def _cpabooks_document_code_from_sequence(self, seq):
        prefix = (seq.prefix or '').strip()
        if prefix:
            return prefix.split('/')[0].strip()
        if seq.sequence_for:
            for sequence_for, _name, code, _padding in CPABOOKS_SEQUENCE_DEFINITIONS:
                if sequence_for == seq.sequence_for:
                    return code
        return (seq.name or 'DOC').split()[0]

    @api.model
    def apply_prefix_for_company(
        self,
        company,
        prefix,
        create_missing=True,
        line_overrides=None,
        granularity=None,
        year_digits=None,
        number_digits=None,
        update_existing=False,
        update_company_settings=True,
    ):
        """Create/update CPABooks ir.sequence rows for one company.

        By default only missing sequence types are created; existing prefixes
        are left unchanged (e.g. on module upgrade). Pass update_existing=True
        when the user explicitly resets or applies sequence setup.
        """
        company = company.sudo()
        prefix = (prefix or '').strip()
        if not prefix:
            return False
        granularity = granularity or company.cpabooks_sequence_granularity or 'yearly'
        year_digits = year_digits or company.cpabooks_sequence_year_digits or '4'
        number_digits = number_digits or getattr(
            company, 'cpabooks_sequence_number_digits', None,
        ) or '5'
        if update_company_settings:
            company.write({
                'cpabooks_sequence_granularity': granularity,
                'cpabooks_sequence_year_digits': year_digits,
                'cpabooks_sequence_number_digits': number_digits,
            })
            if 'cpabooks_sequence_prefix' in company._fields:
                if (company.cpabooks_sequence_prefix or '') != prefix:
                    company.cpabooks_sequence_prefix = prefix

        Sequence = self.env['ir.sequence'].sudo()
        line_overrides = line_overrides or {}

        pad_digits = int(number_digits or 5)

        for sequence_for, name, code, padding in CPABOOKS_SEQUENCE_DEFINITIONS:
            if sequence_for in MRP_SEQUENCE_FOR and not mrp_installed(self.env):
                continue
            prefix_value = self._format_prefix(
                code, prefix, sequence_for, company=company, granularity=granularity,
            )
            override = line_overrides.get(sequence_for) or {}
            if override.get('prefix'):
                prefix_value = override['prefix']

            existing_seq = Sequence.search([
                ('sequence_for', '=', sequence_for),
                ('company_id', '=', company.id),
            ], limit=1)

            seq_granularity = self._resolve_granularity(company, sequence_for, granularity)
            effective_padding = 0 if padding == 0 else pad_digits
            seq_year_digits = '2' if seq_granularity == 'monthly' else year_digits
            pattern_value = self._sequence_pattern_value(seq_granularity, seq_year_digits)
            vals = {
                'name': name,
                'prefix': prefix_value,
                'sequence_pattern': pattern_value,
                'padding': effective_padding,
                'cpabooks_year_digits': seq_year_digits,
            }
            if override.get('number_next_actual'):
                vals['number_next_actual'] = int(override['number_next_actual'])

            if existing_seq:
                if update_existing:
                    existing_seq.with_context(cpabooks_sequence_force_write=True).write(vals)
                    if not existing_seq.cpabooks_sequence_locked:
                        existing_seq.write({'cpabooks_sequence_locked': True})
            elif create_missing:
                create_vals = {
                    'name': name,
                    'sequence_for': sequence_for,
                    'company_id': company.id,
                    'prefix': prefix_value,
                    'padding': effective_padding,
                    'number_increment': 1,
                    'number_next_actual': vals.get('number_next_actual', 1),
                    'sequence_pattern': pattern_value,
                    'cpabooks_year_digits': seq_year_digits,
                    'cpabooks_sequence_locked': True,
                }
                Sequence.create(create_vals)

        handled_fors = {row[0] for row in CPABOOKS_SEQUENCE_DEFINITIONS}
        if update_existing:
            extra_seqs = Sequence.search([
                ('sequence_for', '!=', False),
                ('company_id', '=', company.id),
                ('sequence_for', 'not in', list(handled_fors)),
            ])
            for seq in extra_seqs:
                doc_code = self._cpabooks_document_code_from_sequence(seq)
                seq_granularity = self._resolve_granularity(
                    company, seq.sequence_for, granularity,
                )
                effective_padding = pad_digits
                seq_year_digits = '2' if seq_granularity == 'monthly' else year_digits
                pattern_value = self._sequence_pattern_value(seq_granularity, seq_year_digits)
                prefix_value = self._format_prefix(
                    doc_code, prefix, seq.sequence_for,
                    company=company, granularity=granularity,
                )
                seq.with_context(cpabooks_sequence_force_write=True).write({
                    'prefix': prefix_value,
                    'sequence_pattern': pattern_value,
                    'padding': effective_padding,
                    'cpabooks_year_digits': seq_year_digits,
                })
        return True

    def set_prefix(self):
        self.ensure_one()
        if not self.prefix:
            return False
        return self.apply_prefix_for_company(
            self.env.company,
            self.prefix,
            create_missing=True,
            update_existing=True,
            granularity=self.sequence_granularity,
            year_digits=self.sequence_year_digits,
            number_digits=self.sequence_number_digits,
        )

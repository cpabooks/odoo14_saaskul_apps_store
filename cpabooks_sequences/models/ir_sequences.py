from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.sql import column_exists, create_column
import logging
from datetime import date, datetime

from .cpabooks_module_checks import mrp_installed

_logger = logging.getLogger(__name__)
class SequenceInheritance(models.Model):
    _inherit = 'ir.sequence'

    @staticmethod
    def _cpabooks_clamp_sequence_next(value, minimum=1):
        try:
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return minimum

    def _set_number_next_actual(self):
        """Never persist number_next below 1 (PostgreSQL RESTART rejects 0 or negative)."""
        for seq in self:
            seq.write({
                'number_next': self._cpabooks_clamp_sequence_next(seq.number_next_actual),
            })

    @api.model
    def _cpabooks_ensure_sequence_columns(self):
        """Create newer ir_sequence columns when code is ahead of the DB (skipped upgrade)."""
        cr = self.env.cr
        table = self._table
        if not column_exists(cr, table, 'cpabooks_year_digits'):
            create_column(cr, table, 'cpabooks_year_digits', 'varchar')
        if not column_exists(cr, table, 'cpabooks_sequence_locked'):
            create_column(cr, table, 'cpabooks_sequence_locked', 'bool')
            cr.execute(
                "UPDATE ir_sequence SET cpabooks_sequence_locked = true "
                "WHERE sequence_for IS NOT NULL"
            )
        if not column_exists(cr, table, 'cpabooks_start_new_sequence'):
            create_column(cr, table, 'cpabooks_start_new_sequence', 'bool')

    def _auto_init(self):
        result = super()._auto_init()
        self._cpabooks_ensure_sequence_columns()
        return result

    _CPABOOKS_LOCKED_PROTECTED_FIELDS = frozenset({
        'name', 'code', 'implementation', 'active', 'company_id',
        'prefix', 'suffix', 'use_date_range', 'sequence_pattern', 'padding',
        'cpabooks_year_digits', 'number_increment', 'sequence_for',
        'cpabooks_start_new_sequence',
    })
    # number_next / number_next_actual must stay writable while locked so documents
    # can consume the next number; the form view keeps those fields readonly.

    def write(self, vals):
        self._cpabooks_ensure_sequence_columns()
        vals = dict(vals)
        if 'number_next' in vals:
            vals['number_next'] = self._cpabooks_clamp_sequence_next(vals.get('number_next'))
        if 'number_next_actual' in vals:
            vals['number_next'] = self._cpabooks_clamp_sequence_next(vals.pop('number_next_actual'))
        if vals.get('cpabooks_start_new_sequence'):
            vals['number_next'] = 1
            vals['number_next_actual'] = 1
        if (
            'sequence_pattern' in vals
            and 'prefix' not in vals
            and len(self) == 1
            and self.sequence_for
        ):
            synced_prefix = self._cpabooks_prefix_for_pattern(
                vals['sequence_pattern'], self.prefix or '',
            )
            if synced_prefix and synced_prefix != (self.prefix or ''):
                vals['prefix'] = synced_prefix
        if (
            not self.env.context.get('cpabooks_sequence_force_write')
            and self._CPABOOKS_LOCKED_PROTECTED_FIELDS.intersection(vals)
        ):
            locked = self.filtered(
                lambda s: s.sequence_for and s.cpabooks_sequence_locked,
            )
            if locked:
                raise ValidationError(_(
                    'Sequence "%s" is locked. Uncheck Locked or use Lock / Unlock, '
                    'then edit prefix or pattern.',
                    locked[0].display_name,
                ))
        return super(SequenceInheritance, self).write(vals)

    def _cpabooks_resolve_selection(self):
        records = self.exists()
        if not records:
            active_ids = self.env.context.get('active_ids') or []
            if not active_ids and self.env.context.get('active_id'):
                active_ids = [self.env.context['active_id']]
            records = self.browse(active_ids).exists()
        return records.filtered('sequence_for')

    def action_cpabooks_toggle_lock(self):
        records = self._cpabooks_resolve_selection()
        if not records:
            raise ValidationError(_('Select at least one sequence row.'))
        if all(records.mapped('cpabooks_sequence_locked')):
            records.write({'cpabooks_sequence_locked': False})
        else:
            records.write({'cpabooks_sequence_locked': True})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def set_prefix(self):
        company = self.env.company
        sequences = self.env['ir.sequence'].search([
            ('sequence_for', '!=', False),
            ('company_id', '=', company.id),
        ])
        if sequences and all(sequences.mapped('cpabooks_sequence_locked')):
            raise ValidationError(_(
                'All document sequences are locked. Select rows and use Lock / Unlock '
                '(or uncheck Locked), then run Reset Company Prefix.',
            ))
        return self.env.ref('cpabooks_sequences.set_company_prefix_wizard').read()[0]

    # is_journals=fields.Boolean(string="IS Journal Entries Sequences")
    sequence_pattern=fields.Selection([
        ('year_yearly', 'Year (4 digits)'),
        ('year', 'Year (2 digits)'),
        ('month_year_monthly', 'Monthly'),
        ('month_year', 'Month With Year (legacy)'),
        ('no_month_year', 'Without Year / Month'),
    ], string="Sequence Contains", default="year_yearly")
    cpabooks_year_digits = fields.Selection(
        [
            ('4', '4-digit year (2026)'),
            ('2', '2-digit year (26)'),
        ],
        string='Year Format',
        help='Used in pattern example and document numbers for this sequence.',
    )
    cpabooks_sequence_locked = fields.Boolean(
        string='Locked',
        default=True,
        help='Locked sequences are not changed on module upgrade or Reset Company Prefix '
             'until you unlock them here.',
    )
    cpabooks_start_new_sequence = fields.Boolean(
        string='Start New Sequence',
        default=False,
        help='Yes: use the Next Number counter (usually 1), even if documents exist. '
             'No (default): continue after the highest number for the current prefix/pattern only.',
    )
    sequence_pattern_example = fields.Char(
        string="Pattern Example",
        compute="_compute_sequence_pattern_example",
    )
    sequence_for=fields.Selection([('sale','Sale Quotation'),
                                   ('outgoing', 'Sale Delivery'),
                                   ('sale_invoice', 'Sale Invoice'),
                                   ('credit_note', 'Credit Note'),

                                   ('purchase','Purchase Order'),
                                   ('incoming', 'Purchase Receipt'),
                                   ('purchase_bill','Purchase Bill'),
                                   ('debit_note', 'Debit Note'),

                                   ('internal', 'Internal Transfer'),
                                   ('stock_adjustment', 'Stock Adjustment Journal'),
                                   ('reconcile','Account Full Reconcile'),
                                   ('payment_voucher','Payment Voucher'),
                                   ('receipt_voucher','Receipt Voucher'),
                                   ('journal_voucher','Journal Voucher'),
                                   ('pdc_payment','PDC Payment Voucher'),
                                   ('pdc_receipt','PDC Receipt Voucher'),

                                   ('crm','CRM'),
                                   ('job_estimation','Job Estimation'),
                                   ('job_order', 'Job order'),

                                   ('bom','Bill of Material'),
                                   ('manufacturing','Manufacturing Orders'),
                                   ('project', 'Project'),
                                   ('fsm_crn', 'FSM CRN'),
                                   ('stock_issue_note', 'Material Issue Note'),
                                   ('stock_return_note', 'Material Return Note'),
                                   ('project_task', 'Project Task (TID)'),
                                   ('quality_chk', 'Quality Check'),

                                   ('daily_site_report', 'Daily Site Report'),
                                   ('weekly_site_report', 'Weekly Site Report'),
                                   ('monthly_site_report', 'Monthly Site Report'),

                                   ('supervisor_daily_report', 'Supervisor Daily Report'),
                                   ('supervisor_weekly_report', 'Supervisor Weekly Report'),
                                   ('supervisor_monthly_report', 'Supervisor Monthly Report'),

                                   ('client_report', 'Client Report'),
                                   ('helpdesk_ticket','Helpdesk Ticket'),

                                   ('transport_inquiry', 'Transport Inquiry'),
                                   ('transport_quotation', 'Transport Quotation'),
                                   ('transport_job', 'Transport Job'),
                                   ('transport_delivery', 'Transport Delivery Order'),
                                   ('transport_tq_delivery', 'Transport TQ Delivery'),
                                   ],string="Sequence For")
    sequence_for_journals=fields.Many2one('account.journal',domain=lambda self:[('id','in',self.env['account.journal'].search([('type','not in',('sale','purchase','bank','cash'))]).ids)],check_company=True, string="Sequence For Payment/Journals")

    _CPABOOKS_SEQUENCE_DOCUMENT_LOOKUP = {
        'sale_invoice': ('account.move', [('move_type', 'in', ('out_invoice', 'out_receipt'))], 'name'),
        'credit_note': ('account.move', [('move_type', '=', 'out_refund')], 'name'),
        'purchase_bill': ('account.move', [('move_type', 'in', ('in_invoice', 'in_receipt'))], 'name'),
        'debit_note': ('account.move', [('move_type', '=', 'in_refund')], 'name'),
        'journal_voucher': ('account.move', [('move_type', '=', 'entry')], 'name'),
        'sale': ('sale.order', [], 'name'),
        'purchase': ('purchase.order', [], 'name'),
        'outgoing': ('stock.picking', [('picking_type_id.code', '=', 'outgoing')], 'name'),
        'incoming': ('stock.picking', [('picking_type_id.code', '=', 'incoming')], 'name'),
        'internal': ('stock.picking', [('picking_type_id.code', '=', 'internal')], 'name'),
        'stock_issue_note': (
            'stock.picking', [('name', '=like', 'MIN/%')], 'name',
        ),
        'stock_return_note': (
            'stock.picking', [('name', '=like', 'MRN/%')], 'name',
        ),
        'stock_adjustment': ('stock.inventory', [], 'saj_number'),
        'payment_voucher': ('account.payment', [('payment_type', '=', 'outbound')], 'name'),
        'receipt_voucher': ('account.payment', [('payment_type', '=', 'inbound')], 'name'),
        'fsm_crn': ('project.task', [], 'task_seq'),
        'project_task': ('project.task', [], 'task_seq'),
    }

    def cpabooks_resolve_next_number(
        self, sequence_date=None, model=None, extra_domain=None, record_id=None,
        name_field=None,
    ):
        """Pick next counter: Start New Sequence = counter; else last number for this pattern + 1."""
        self.ensure_one()
        counter = self._cpabooks_clamp_sequence_next(self.number_next_actual or 1)
        if self.cpabooks_start_new_sequence or not model:
            return counter
        common = self.env['common.method']
        ref = common.parse_sequence_datetime(
            sequence_date or fields.Date.context_today(self),
        )
        highest = common.get_highest_seq_no_for_current_pattern(
            self, ref, model,
            name_field=name_field,
            record_id=record_id,
            extra_domain=extra_domain,
        )
        if not highest:
            return 1
        return highest + 1

    def _cpabooks_document_lookup(self, sequence_for):
        return self._CPABOOKS_SEQUENCE_DOCUMENT_LOOKUP.get(sequence_for)

    @api.model
    def _cpabooks_is_monthly_pattern(self, pattern):
        return pattern in ('month_year', 'month_year_monthly')

    @api.model
    def _cpabooks_prefix_for_pattern(self, pattern, prefix):
        """Align prefix placeholders with sequence_pattern (same rules as form onchange)."""
        prefix = prefix or ''
        if not prefix or not pattern:
            return prefix
        if pattern in ('year', 'year_yearly'):
            if '/%(year)s/%(month)s/' in prefix:
                return prefix.replace('/%(year)s/%(month)s/', '/%(year)s/')
            if '/%(year)s/%(month)s/' not in prefix and '/%(year)s/' not in prefix and '/%(month)s/' in prefix:
                return prefix.replace('/%(month)s/', '/%(year)s/')
            if '/%(year)s/' not in prefix and '/%(month)s/' not in prefix:
                return prefix + '%(year)s/'
        if pattern in ('month_year', 'month_year_monthly'):
            if '/%(year)s/%(month)s/' in prefix:
                return prefix
            if '/%(year)s/%(month)s/' not in prefix and '/%(year)s/' in prefix:
                return prefix.replace('/%(year)s/', '/%(year)s/%(month)s/')
            if '/%(year)s/%(month)s/' not in prefix and '/%(month)s/' in prefix:
                return prefix.replace('/%(month)s/', '/%(year)s/%(month)s/')
            if '/%(year)s/' not in prefix:
                return prefix + '%(year)s/%(month)s/'
        if pattern == 'no_month_year':
            if '/%(year)s/%(month)s/' in prefix:
                return prefix.replace('/%(year)s/%(month)s/', '/')
            if '/%(year)s/' in prefix:
                return prefix.replace('/%(year)s/', '/')
            if '/%(month)s/' in prefix:
                return prefix.replace('/%(month)s/', '/')
        return prefix

    def _cpabooks_year_digits(self):
        self.ensure_one()
        if self.cpabooks_year_digits:
            return self.cpabooks_year_digits
        if self.sequence_pattern == 'year':
            return '2'
        if self.sequence_pattern in ('year_yearly',):
            return '4'
        company = self.company_id or self.env.company
        return getattr(company, 'cpabooks_sequence_year_digits', None) or '4'

    @api.depends(
        'prefix', 'padding', 'sequence_for', 'sequence_pattern',
        'cpabooks_year_digits',
        'company_id', 'company_id.cpabooks_sequence_year_digits',
        'number_next_actual',
    )
    def _compute_sequence_pattern_example(self):
        from odoo.addons.cpabooks_sequences.models.sequence_format import build_sequence_number
        from odoo.addons.cpabooks_sequences.models.set_company_prefix import (
            CPABOOKS_SEQUENCE_DEFINITIONS,
        )
        code_by_for = {row[0]: row[2] for row in CPABOOKS_SEQUENCE_DEFINITIONS}
        for rec in self:
            if not rec.sequence_for or rec.sequence_for == 'reconcile':
                rec.sequence_pattern_example = rec.prefix or ''
                continue
            prefix = rec.prefix or ''
            parts = [p for p in prefix.split('/') if p and '%' not in p]
            doc_code = parts[0] if parts else code_by_for.get(rec.sequence_for, 'DOC')
            company_prefix = parts[1] if len(parts) > 1 else (
                (getattr(rec.company_id, 'cpabooks_sequence_prefix', None) or '')
                if rec.company_id else ''
            )
            granularity = (
                'monthly' if '/%(year)s/%(month)s/' in prefix
                else 'yearly'
            )
            rec.sequence_pattern_example = build_sequence_number(
                doc_code,
                company_prefix,
                granularity,
                rec._cpabooks_year_digits(),
                padding=rec.padding,
                next_number=rec.number_next_actual or 1,
            )

    def _interpolation_dict(self):
        res = super()._interpolation_dict()
        year_digits = self._cpabooks_year_digits()
        if year_digits == '2' and res.get('year'):
            year_val = res['year']
            try:
                res['year'] = str(int(year_val) % 100).zfill(2)
            except (TypeError, ValueError):
                res['year'] = str(year_val)[-2:].zfill(2)
        return res

    # ('journal_entry', 'Journal Entry')
    @api.onchange('sequence_pattern')
    def _set_sequence_pattern(self):
        for rec in self:
            if rec.sequence_pattern == 'year':
                rec.cpabooks_year_digits = '2'
            elif rec.sequence_pattern == 'year_yearly':
                rec.cpabooks_year_digits = '4'
            elif rec.sequence_pattern in ('month_year', 'month_year_monthly'):
                rec.cpabooks_year_digits = '2'
            if len(rec.ids) > 0:
                if rec.sequence_pattern=='year' or rec.sequence_pattern=='year_yearly':
                    if '/%(year)s/%(month)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(year)s/%(month)s/','/%(year)s/')
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(year)s/' in rec.prefix:
                        continue
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(month)s/' in rec.prefix:
                        rec.prefix = rec.prefix.replace('/%(month)s/', '/%(year)s/')
                    else:
                        rec.prefix+='%(year)s/'
                elif rec.sequence_pattern=='month_year' or rec.sequence_pattern=='month_year_monthly':
                    if '/%(year)s/%(month)s/' in rec.prefix:
                        continue
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(year)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(year)s/','/%(year)s/%(month)s/')
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(month)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(month)s/','/%(year)s/%(month)s/')
                    else:
                        rec.prefix+='%(year)s/%(month)s/'
                elif rec.sequence_pattern=='no_month_year':
                    if '/%(year)s/%(month)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(year)s/%(month)s/','/')
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(year)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(year)s/','/')
                    elif '/%(year)s/%(month)s/' not in rec.prefix and '/%(month)s/' in rec.prefix:
                        rec.prefix=rec.prefix.replace('/%(month)s/','/')
                    else:
                        continue

                else:
                    continue


    @api.model
    def action_create_sequence(self):

        get_all_company = self.env['res.company'].sudo().search([])
        for com in get_all_company:
            val_list = []
            # ************************DELETE BANK CASH JOURNAL SEQUENCE***************************
            get_all_null_company = self.env['ir.sequence'].search([('company_id','=',False)])
            if get_all_null_company:
                # Never rewrite locked CPABooks sequences (blocks module install
                # when leave/internal tasks call action_create_sequence).
                assignable = get_all_null_company.filtered(
                    lambda s: not s.cpabooks_sequence_locked
                )
                if assignable:
                    assignable.write({'company_id': com.id})
            get_null_code_sequences = self.env['ir.sequence'].search(
                [('sequence_for', '=', None), ('code', '=', None), ('company_id', '=', com.id)])
            if get_null_code_sequences:
                get_null_code_sequences.unlink()
            get_bank_cash_journals = self.env['account.journal'].search(
                [('type', 'in', ('bank', 'cash', 'general')), ('company_id', '=', com.id)])
            for bcj in get_bank_cash_journals:
                get_sequence_for_bank_cash = self.env['ir.sequence'].sudo().search([('sequence_for_journals', '=',
                                                                                     self.env['account.journal'].search(
                                                                                         [('name', '=', bcj.name), (
                                                                                         'company_id', '=',
                                                                                         com.id)]).id),
                                                                                    ('company_id', '=', com.id)])
                if get_sequence_for_bank_cash:
                    get_sequence_for_bank_cash.unlink()
            # ************************DELETE BANK CASH JOURNAL SEQUENCE***************************
            # get_journals=self.env['account.journal'].search([('type','not in',('sale','purchase','bank','cash')),('company_id','=',com.id)])
            # for journal in get_journals:
            #     get_journal_seq=self.env['ir.sequence'].sudo().search([('sequence_for_journals','=',
            #                             self.env['account.journal'].search([('name','=',journal.name),('company_id','=',com.id)]).id),('company_id','=',com.id)])
            #     if not get_journal_seq:
            #         vals = {
            #             'name': journal.name,
            #             'sequence_for_journals': self.env['account.journal'].search([('name','=',journal.name),('company_id','=',com.id)]).id,
            #             'company_id': com.id,
            #             'prefix': 'CO' + str(com.id) + '/'+journal.code+'/%(year)s/',
            #             'padding': 5,
            #             'number_increment': 1,
            #             'number_next_actual': 1
            #         }
            #         val_list.append(vals)
            get_acc_reconcile_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'reconcile'), ('company_id', '=', com.id)])

            if not get_acc_reconcile_seq:
                vals = {
                    'name': 'Account Full Reconcile',
                    'sequence_for': 'reconcile',
                    'company_id': com.id,
                    'prefix': 'A',
                    'padding': 0,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_sale_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'sale'), ('company_id', '=', com.id)])
            if not get_sale_seq:
                vals = {
                    'name': 'Sale Qutotation',
                    'sequence_for': 'sale',
                    'company_id': com.id,
                    'prefix': 'QT/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_do_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'outgoing'), ('company_id', '=', com.id)])
            if not get_do_seq:
                vals = {
                    'name': 'Sale Delivery',
                    'sequence_for': 'outgoing',
                    'company_id': com.id,
                    'prefix': 'DO/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_inv_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'sale_invoice'), ('company_id', '=', com.id)])
            if not get_inv_seq:
                vals = {
                    'name': 'Sale Invoice',
                    'sequence_for': 'sale_invoice',
                    'company_id': com.id,
                    'prefix': 'INV/' + 'CO' + str(com.id) + '/%(year)s/%(month)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'month_year_monthly'
                }
                val_list.append(vals)

            get_inv_return_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'credit_note'), ('company_id', '=', com.id)])
            if not get_inv_return_seq:
                vals = {
                    'name': 'Credit Note',
                    'sequence_for': 'credit_note',
                    'company_id': com.id,
                    'prefix': 'RINV/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_lpo_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'purchase'), ('company_id', '=', com.id)])
            if not get_lpo_seq:
                vals = {
                    'name': 'Purchase Order',
                    'sequence_for': 'purchase',
                    'company_id': com.id,
                    'prefix': 'LPO/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_grn_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'incoming'), ('company_id', '=', com.id)])
            if not get_grn_seq:
                vals = {
                    'name': 'Purchase Receipt',
                    'sequence_for': 'incoming',
                    'company_id': com.id,
                    'prefix': 'GRN/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_bill_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'purchase_bill'), ('company_id', '=', com.id)])
            if not get_bill_seq:
                vals = {
                    'name': 'Purchase Bill',
                    'sequence_for': 'purchase_bill',
                    'company_id': com.id,
                    'prefix': 'BILL/' + 'CO' + str(com.id) + '/%(year)s/%(month)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'month_year_monthly'
                }
                val_list.append(vals)

            get_bill_return_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'debit_note'), ('company_id', '=', com.id)])
            if not get_bill_return_seq:
                vals = {
                    'name': 'Debit Note',
                    'sequence_for': 'debit_note',
                    'company_id': com.id,
                    'prefix': 'RBILL/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_transfer_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'internal'), ('company_id', '=', com.id)])
            if not get_transfer_seq:
                vals = {
                    'name': 'Internal Transfer',
                    'sequence_for': 'internal',
                    'company_id': com.id,
                    'prefix': 'INT/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_payment_voucher_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'payment_voucher'), ('company_id', '=', com.id)])
            if not get_payment_voucher_seq:
                vals = {
                    'name': 'Payment Voucher',
                    'sequence_for': 'payment_voucher',
                    'company_id': com.id,
                    'prefix': 'PV/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_receipt_voucher_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'receipt_voucher'), ('company_id', '=', com.id)])
            if not get_receipt_voucher_seq:
                vals = {
                    'name': 'Receipt Voucher',
                    'sequence_for': 'receipt_voucher',
                    'company_id': com.id,
                    'prefix': 'RV/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_journal_voucher_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'journal_voucher'), ('company_id', '=', com.id)])
            if not get_journal_voucher_seq:
                vals = {
                    'name': 'Journal Voucher',
                    'sequence_for': 'journal_voucher',
                    'company_id': com.id,
                    'prefix': 'JV/' + 'CO' + str(com.id) + '/%(year)s/%(month)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'month_year_monthly'
                }
                val_list.append(vals)

            get_crm_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'crm'), ('company_id', '=', com.id)])
            if not get_crm_seq:
                vals = {
                    'name': 'CRM',
                    'sequence_for': 'crm',
                    'company_id': com.id,
                    'prefix': 'CRM/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_job_estimate_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'job_estimation'), ('company_id', '=', com.id)])
            if not get_job_estimate_seq:
                vals = {
                    'name': 'Job Estimation',
                    'sequence_for': 'job_estimation',
                    'company_id': com.id,
                    'prefix': 'EST/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_job_order_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'job_order'), ('company_id', '=', com.id)])
            if not get_job_order_seq:
                vals = {
                    'name': 'Job Order',
                    'sequence_for': 'job_order',
                    'company_id': com.id,
                    'prefix': 'JO/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_project_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'project'), ('company_id', '=', com.id)])
            if not get_project_seq:
                vals = {
                    'name': 'Project',
                    'sequence_for': 'project',
                    'company_id': com.id,
                    'prefix': 'JOB/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_fsm_crn_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'fsm_crn'), ('company_id', '=', com.id)])
            if not get_fsm_crn_seq:
                vals = {
                    'name': 'FSM CRN',
                    'sequence_for': 'fsm_crn',
                    'company_id': com.id,
                    'prefix': 'CRN/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'year_yearly',
                }
                val_list.append(vals)

            get_sin_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'stock_issue_note'), ('company_id', '=', com.id)])
            if not get_sin_seq:
                val_list.append({
                    'name': 'Material Issue Note',
                    'sequence_for': 'stock_issue_note',
                    'company_id': com.id,
                    'prefix': 'MIN/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'year_yearly',
                })

            get_srn_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'stock_return_note'), ('company_id', '=', com.id)])
            if not get_srn_seq:
                val_list.append({
                    'name': 'Material Return Note',
                    'sequence_for': 'stock_return_note',
                    'company_id': com.id,
                    'prefix': 'MRN/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'year_yearly',
                })

            get_project_task_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'project_task'), ('company_id', '=', com.id)])
            if not get_project_task_seq:
                vals = {
                    'name': 'Project Task TID',
                    'sequence_for': 'project_task',
                    'company_id': com.id,
                    'prefix': 'TID-%(year)s/%(month)s/',
                    'padding': 3,
                    'number_increment': 1,
                    'number_next_actual': 1,
                    'sequence_pattern': 'month_year_monthly',
                    'cpabooks_year_digits': '2',
                }
                val_list.append(vals)

            if mrp_installed(self.env):
                get_bom_seq = self.env['ir.sequence'].sudo().search(
                    [('sequence_for', '=', 'bom'), ('company_id', '=', com.id)])
                if not get_bom_seq:
                    val_list.append({
                        'name': 'Bill of Material',
                        'sequence_for': 'bom',
                        'company_id': com.id,
                        'prefix': 'BoM/' + 'CO' + str(com.id) + '/%(year)s/',
                        'padding': 5,
                        'number_increment': 1,
                        'number_next_actual': 1,
                    })

                get_manufacturing_seq = self.env['ir.sequence'].sudo().search(
                    [('sequence_for', '=', 'manufacturing'), ('company_id', '=', com.id)])
                if not get_manufacturing_seq:
                    val_list.append({
                        'name': 'Manufacturing Orders',
                        'sequence_for': 'manufacturing',
                        'company_id': com.id,
                        'prefix': 'MO/' + 'CO' + str(com.id) + '/%(year)s/',
                        'padding': 5,
                        'number_increment': 1,
                        'number_next_actual': 1,
                    })

            get_quality_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'quality_chk'), ('company_id', '=', com.id)])
            if not get_quality_seq:
                vals = {
                    'name': 'Quality Check',
                    'sequence_for': 'quality_chk',
                    'company_id': com.id,
                    'prefix': 'QC/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_daily_site_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'daily_site_report'), ('company_id', '=', com.id)])
            if not get_daily_site_report_seq:
                vals = {
                    'name': 'Daily Site Report',
                    'sequence_for': 'daily_site_report',
                    'company_id': com.id,
                    'prefix': 'DR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_weekly_site_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'weekly_site_report'), ('company_id', '=', com.id)])
            if not get_weekly_site_report_seq:
                vals = {
                    'name': 'Weekly Site Report',
                    'sequence_for': 'weekly_site_report',
                    'company_id': com.id,
                    'prefix': 'WR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_monthly_site_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'monthly_site_report'), ('company_id', '=', com.id)])
            if not get_monthly_site_report_seq:
                vals = {
                    'name': 'Monthly Site Report',
                    'sequence_for': 'monthly_site_report',
                    'company_id': com.id,
                    'prefix': 'MR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_supervisor_daily_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'supervisor_daily_report'), ('company_id', '=', com.id)])
            if not get_supervisor_daily_report_seq:
                vals = {
                    'name': 'Supervisor Daily Report',
                    'sequence_for': 'supervisor_daily_report',
                    'company_id': com.id,
                    'prefix': 'DSR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_supervisor_weekly_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'supervisor_weekly_report'), ('company_id', '=', com.id)])
            if not get_supervisor_weekly_report_seq:
                vals = {
                    'name': 'Supervisor Weekly Report',
                    'sequence_for': 'supervisor_weekly_report',
                    'company_id': com.id,
                    'prefix': 'WSR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_supervisor_monthly_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'supervisor_monthly_report'), ('company_id', '=', com.id)])
            if not get_supervisor_monthly_report_seq:
                vals = {
                    'name': 'Supervisor Monthly Report',
                    'sequence_for': 'supervisor_monthly_report',
                    'company_id': com.id,
                    'prefix': 'MSR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_client_report_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'client_report'), ('company_id', '=', com.id)])
            if not get_client_report_seq:
                vals = {
                    'name': 'Client Report',
                    'sequence_for': 'client_report',
                    'company_id': com.id,
                    'prefix': 'CR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_acc_reconcile_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'helpdesk_ticket'), ('company_id', '=', com.id)])

            if not get_acc_reconcile_seq:
                vals = {
                    'name': 'Helpdesk Ticket',
                    'sequence_for': 'helpdesk_ticket',
                    'company_id': com.id,
                    'prefix': 'HT/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_pdc_payment_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'pdc_payment'), ('company_id', '=', com.id)])
            if not get_pdc_payment_seq:
                vals = {
                    'name': 'PDC Payment Voucher',
                    'sequence_for': 'pdc_payment',
                    'company_id': com.id,
                    'prefix': 'PDP/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            get_pdc_receipt_seq = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'pdc_receipt'), ('company_id', '=', com.id)])
            if not get_pdc_receipt_seq:
                vals = {
                    'name': 'PDC Receipt Voucher',
                    'sequence_for': 'pdc_receipt',
                    'company_id': com.id,
                    'prefix': 'PDR/' + 'CO' + str(com.id) + '/%(year)s/',
                    'padding': 5,
                    'number_increment': 1,
                    'number_next_actual': 1
                }
                val_list.append(vals)

            self.create(val_list)

    @api.model
    def next_by_sequence_for(self, sequence_for,hint=None, sequence_date=None):
        """ Draw an interpolated string using a sequence with the requested code.
            If several sequences with the correct code are available to the user
            (multi-company cases), the one from the user's current company will
            be used.
        """
        self._cpabooks_ensure_sequence_columns()
        self.check_access_rights('read')
        company_id = self.env.company.id
        seq_ids = self.search([('sequence_for', '=', sequence_for), ('company_id', 'in', [company_id, False])],limit=1,
                              order='company_id')
        if not seq_ids:
            _logger.debug(
                "No ir.sequence has been found for code '%s'. Please make sure a sequence is set for current company." % sequence_for)
            return False
        seq_id = seq_ids[0]
        normalized_date = sequence_date
        if isinstance(normalized_date, str):
            normalized_date = fields.Date.to_date(normalized_date)
        elif isinstance(normalized_date, datetime):
            normalized_date = normalized_date.date()

        if not normalized_date:
            normalized_date = fields.Date.context_today(self)
        lookup = seq_id._cpabooks_document_lookup(sequence_for)
        if lookup:
            model, extra_domain, name_field = (
                lookup[0], lookup[1], lookup[2] if len(lookup) > 2 else None,
            )
            next_number = seq_id.cpabooks_resolve_next_number(
                normalized_date,
                model=model,
                extra_domain=extra_domain,
                name_field=name_field,
            )
        else:
            next_number = seq_id._cpabooks_clamp_sequence_next(seq_id.number_next_actual or 1)
        result = seq_id.next_by_custom_seq(
            sequence_for=sequence_for,
            field_date=normalized_date,
            next_number=next_number,
        )
        seq_id.sudo().write({
            'number_next_actual': self._cpabooks_clamp_sequence_next(
                next_number + seq_id.number_increment,
            ),
        })
        return result

    def get_next_char(self, number_next):
        return super(SequenceInheritance, self).get_next_char(number_next)

    def next_by_sequence_for_journal(self, sequence_for, sequence_date=None):
        """ Draw an interpolated string using a sequence with the requested code.
            If several sequences with the correct code are available to the user
            (multi-company cases), the one from the user's current company will
            be used.
        """
        self.check_access_rights('read')
        company_id = self.env.company.id
        seq_ids = self.search([('sequence_for_journals', '=', sequence_for), ('company_id', 'in', [company_id, False])],limit=1,
                              order='company_id')
        if not seq_ids:
            _logger.debug(
                "No ir.sequence has been found for code '%s'. Please make sure a sequence is set for current company." % sequence_for)
            return False
        seq_id = seq_ids[0]
        normalized_date = sequence_date
        if isinstance(normalized_date, str):
            normalized_date = fields.Date.to_date(normalized_date)
        elif isinstance(normalized_date, datetime):
            normalized_date = normalized_date.date()

        if normalized_date:
            next_number = seq_id.number_next_actual
            from odoo.addons.cpabooks_sequences.models.sequence_format import replace_prefix_placeholders
            seq_prefix = replace_prefix_placeholders(
                seq_id.prefix or "",
                normalized_date,
                seq_id._cpabooks_year_digits(),
            )
            result = f"{seq_prefix}{str(next_number).zfill(seq_id.padding)}"
            seq_id.sudo().write({
                'number_next_actual': self._cpabooks_clamp_sequence_next(
                    next_number + seq_id.number_increment,
                ),
            })
            return result
        return seq_id._next(sequence_date=sequence_date)

    @api.model
    def create(self, vals_list):
        self._cpabooks_ensure_sequence_columns()
        if isinstance(vals_list, dict):
            vals_to_check = [vals_list]
        else:
            vals_to_check = vals_list
        for vals in vals_to_check:
            if vals.get('sequence_for') and 'cpabooks_sequence_locked' not in vals:
                vals['cpabooks_sequence_locked'] = True
            if vals.get('sequence_for'):
                get_exists_one = self.env['ir.sequence'].sudo().search([
                    ('company_id', '=', vals.get('company_id')),
                    ('sequence_for', '=', vals['sequence_for'])
                ], limit=1)
                if get_exists_one:
                    raise ValidationError(_("Already sequence for '%s' is created for company '%s'" % (
                        get_exists_one.sequence_for, get_exists_one.company_id.name
                    )))
        res = super(SequenceInheritance, self).create(vals_list)
        return res

    @api.onchange('sequence_for')
    def existency_chk(self):
        if  self.sequence_for!=False:
            # self.sequence_for_journals=False
            get_exists_one = self.env['ir.sequence'].sudo().search(
                [('company_id', '=', self.company_id.id), ('sequence_for', '=', self.sequence_for)], limit=1)
            if get_exists_one:
                raise ValidationError(_("Already sequence for this type is created for company '%s'" % (
                 get_exists_one.company_id.name)))

    # @api.onchange('sequence_for_journals')
    # def existency_journals_chk(self):
    #     if self.sequence_for_journals:
    #         # self.sequence_for=False
    #         get_exists_one = self.env['ir.sequence'].sudo().search(
    #             [('company_id', '=', self.company_id.id), ('sequence_for_journals', '=', self.sequence_for_journals.id)], limit=1)
    #         if get_exists_one:
    #             raise ValidationError(_("Already sequence for this type is created for company '%s'" % (
    #                 get_exists_one.company_id.name)))

    def next_by_custom_seq(self, sequence_for=False, field_date=False, next_number=False):
        # Prefer the sequence record itself so payment/move company wins over navbar company.
        if len(self) == 1 and self.sequence_for == sequence_for:
            seq_id = self
        else:
            seq_id = self.search([
                ('sequence_for', '=', sequence_for),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

        # Handle prefix and next number
        seq_prefix = seq_id.prefix or ""
        if not next_number:
            next_number = seq_id.number_next_actual
        padding = seq_id.padding

        # Ensure field_date is set, default to today's date
        if not field_date:
            field_date = date.today()

        # If field_date is a string, ensure it is parsed correctly
        if isinstance(field_date, str):
            try:
                # Handle both formats: YYYY-MM-DD and DD/MM/YYYY
                if "-" in field_date:
                    date_obj = datetime.strptime(field_date, "%Y-%m-%d")
                else:
                    date_obj = datetime.strptime(field_date, "%d/%m/%Y")
            except ValueError:
                raise ValueError(f"Invalid date format: {field_date}. Expected formats: 'YYYY-MM-DD' or 'DD/MM/YYYY'.")
        else:
            # If already a `date` object, no need to parse
            date_obj = field_date

        from odoo.addons.cpabooks_sequences.models.sequence_format import replace_prefix_placeholders
        seq_prefix = replace_prefix_placeholders(
            seq_prefix, date_obj, seq_id._cpabooks_year_digits(),
        )

        seq = f'{seq_prefix}{str(next_number).zfill(padding)}'
        return seq


class ResUserInherit(models.Model):
    _inherit = 'res.users'

    def sequence_domain(self):
        return [('company_id','=',self.env.company.id)]

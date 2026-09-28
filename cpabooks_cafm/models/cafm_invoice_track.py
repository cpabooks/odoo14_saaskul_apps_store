# -*- coding: utf-8 -*-

from odoo import api, fields, models


TRACK_FIELD_KIND = (
    ('cafm_track_kp_id', 'kp'),
    ('cafm_track_ppm_id', 'ppm'),
    ('cafm_track_sr_id', 'sr'),
    ('cafm_track_invoice_status_id', 'invoice'),
)


class CafmInvoiceTrackStatus(models.Model):
    _name = 'cpabooks.cafm.invoice.track.status'
    _description = 'CAFM Invoice Track Status'
    _order = 'kind, sequence, name'

    name = fields.Char(required=True)
    kind = fields.Selection(
        [
            ('kp', 'KP'),
            ('ppm', 'PPM'),
            ('sr', 'SR'),
            ('invoice', 'Invoice Status'),
            ('received_copy', 'Received Copy Status'),
            ('final', 'Final Status'),
        ],
        required=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    is_pending = fields.Boolean(compute='_compute_flags')
    is_all_done = fields.Boolean(compute='_compute_flags')

    _sql_constraints = [
        ('cafm_track_status_kind_name_uniq', 'unique(kind, name)',
         'This status name already exists for this column.'),
    ]

    @api.depends('name', 'kind')
    def _compute_flags(self):
        for rec in self:
            key = (rec.name or '').strip().lower()
            rec.is_pending = key == 'pending'
            rec.is_all_done = rec.kind == 'final' and key in ('all done', 'alldone')

    @api.model
    def get_or_create_named(self, kind, name):
        rec = self.search([('kind', '=', kind), ('name', '=', name)], limit=1)
        if rec:
            return rec
        return self.create({'kind': kind, 'name': name})


class AccountMove(models.Model):
    _inherit = 'account.move'

    cafm_invoice_sr = fields.Integer(string='Sr', compute='_compute_cafm_invoice_sr')
    cafm_invoice_period = fields.Char(
        string='Invoice Period',
        compute='_compute_cafm_invoice_period',
    )
    cafm_track_month = fields.Char(
        string='Month',
        compute='_compute_cafm_track_month',
        store=True,
    )
    cafm_track_kp_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='KP',
        domain="[('kind', '=', 'kp')]",
        context="{'default_kind': 'kp'}",
        ondelete='restrict',
    )
    cafm_track_ppm_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='PPM',
        domain="[('kind', '=', 'ppm')]",
        context="{'default_kind': 'ppm'}",
        ondelete='restrict',
    )
    cafm_track_sr_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='SR',
        domain="[('kind', '=', 'sr')]",
        context="{'default_kind': 'sr'}",
        ondelete='restrict',
    )
    cafm_track_invoice_status_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='Invoice Status',
        domain="[('kind', '=', 'invoice')]",
        context="{'default_kind': 'invoice'}",
        ondelete='restrict',
    )
    cafm_inv_sub_date = fields.Date(string='Inv. Sub Date')
    cafm_invoice_submitted_by = fields.Many2one(
        'res.users',
        string='Invoice Submitted By',
        ondelete='set null',
    )
    cafm_received_copy_status_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='Received Copy Status',
        domain="[('kind', '=', 'received_copy')]",
        context="{'default_kind': 'received_copy'}",
        ondelete='restrict',
    )
    cafm_track_remarks = fields.Char(string='Remarks')
    cafm_final_status_id = fields.Many2one(
        'cpabooks.cafm.invoice.track.status',
        string='Final Status',
        domain="[('kind', '=', 'final')]",
        context="{'default_kind': 'final'}",
        ondelete='restrict',
    )

    @api.depends('invoice_date')
    def _compute_cafm_invoice_sr(self):
        ordered = self.sorted(
            key=lambda m: (m.invoice_date or fields.Date.from_string('1970-01-01'), m.id or 0)
        )
        for index, rec in enumerate(ordered, start=1):
            rec.cafm_invoice_sr = index

    @api.depends(
        'cafm_contract_order_ids.date_from',
        'cafm_contract_order_ids.date_to',
        'cafm_contract_order_ids.period_label',
        'cafm_contract_order_ids.amc_period_display',
    )
    def _compute_cafm_invoice_period(self):
        for rec in self:
            labels = []
            orders = rec.cafm_contract_order_ids.sorted(
                key=lambda o: (o.date_from or o.invoice_date or fields.Date.from_string('1970-01-01'), o.id or 0)
            )
            for order in orders:
                label = rec._cafm_status_period_label(
                    order.date_from, order.date_to, order.period_label,
                ) or (order.amc_period_display or '')
                label = (label or '').strip()
                if label and label not in labels:
                    labels.append(label)
            rec.cafm_invoice_period = ', '.join(labels) if labels else False

    @api.depends('invoice_date')
    def _compute_cafm_track_month(self):
        for rec in self:
            rec.cafm_track_month = rec.invoice_date.strftime("%b'%y") if rec.invoice_date else False

    def _cafm_enforce_final_all_done(self):
        if self.env.context.get('cafm_skip_final_sync'):
            return
        Status = self.env['cpabooks.cafm.invoice.track.status']
        for rec in self:
            if not rec.cafm_final_status_id or not rec.cafm_final_status_id.is_all_done:
                continue
            vals = {}
            for fname, kind in TRACK_FIELD_KIND:
                current = rec[fname]
                if not current or current.is_pending:
                    vals[fname] = Status.get_or_create_named(kind, 'Submitted').id
            if vals:
                rec.with_context(cafm_skip_final_sync=True).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._cafm_enforce_final_all_done()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._cafm_enforce_final_all_done()
        return res

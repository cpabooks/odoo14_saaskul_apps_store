# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


# Excel upload column order (left → right). Tally columns used on upload;
# QT.No / Call No. (without Tally) are for records created in Odoo.
EXCEL_HEADERS = (
    'SLNo',
    'QT.No (Tally)',
    'QT.Date',
    'Call No. (Tally)',
    'Call Dt.',
    'Work Appr.By.',
    'Work Appr.Dt.',
    'Work App. Amt',
    'LPO No.',
    'LPO Dt.',
    'LPO Amount',
    'Work Comp.Dt.',
    'Report Date',
    'Inv. No.',
    'Inv. Dt.',
    'Inv. Amt',
    'Open By',
    'L2 Level (Client Group)',
    'L3 Level (Project)',
    'Flat / Villa',
    'Problem Description',
    'Status',
)


class CafmVarWork(models.Model):
    _name = 'cpabooks.cafm.var.work'
    _description = 'CAFM VAR Work'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'work_date desc, id desc'
    _rec_name = 'qt_no'

    call_id = fields.Many2one(
        'maintenance.request', string='Call', ondelete='set null', index=True,
        help='Optional link to AMC call. Creating here usually fills Call No. from this call.',
    )
    # Created in Odoo (sequence / linked call) — not from Tally Excel
    call_no = fields.Char(string='Call No.', copy=False, index=True)
    # Uploaded from Tally Excel
    call_no_tally = fields.Char(string='Call No. (Tally)', copy=False, index=True, tracking=True)
    call_date = fields.Datetime(
        related='call_id.call_date', string='Call DateTime', store=True, readonly=True,
    )
    call_dt = fields.Date(string='Call Dt.', tracking=True)
    # Invoice-to partner; defaults from L3 Level (Project) name, user may change
    partner_id = fields.Many2one(
        'res.partner', string='Client Name', tracking=True,
        help='Partner the invoice will be billed to. Defaults from L3 Level (Project) name.',
    )
    cafm_unit_id = fields.Many2one('cpabooks.cafm.unit', string='Unit')
    flat_villa = fields.Char(string='Flat / Villa', tracking=True)
    l2_level_id = fields.Many2one(
        'cpabooks.cafm.customer.group', string='L2 Level (Client Group)', tracking=True,
    )
    l3_level_id = fields.Many2one(
        'project.project', string='L3 Level (Project)', tracking=True,
    )
    work_type_id = fields.Many2one('cpabooks.cafm.work.type', string='Type of Work', tracking=True)
    problem_description = fields.Text(string='Problem Description', tracking=True)

    work_date = fields.Date(string='Date', default=fields.Date.context_today, tracking=True)
    # Created in Odoo (ir.sequence)
    qt_no = fields.Char(string='QT.No', copy=False, index=True, tracking=True)
    # Uploaded from Tally Excel
    qt_no_tally = fields.Char(string='QT.No (Tally)', copy=False, index=True, tracking=True)
    qt_date = fields.Date(string='QT.Date', tracking=True)
    qt_amount = fields.Monetary(string='Qt. Amount', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id)

    work_approved_by = fields.Char(string='Work Appr.By.', tracking=True)
    work_approval_date = fields.Date(string='Work Appr.Dt.', tracking=True)
    work_approved_amount = fields.Monetary(string='Work App. Amt', currency_field='currency_id', tracking=True)

    lpo_no = fields.Char(string='LPO No.', tracking=True)
    lpo_date = fields.Date(string='LPO Dt.', tracking=True)
    lpo_amount = fields.Monetary(string='LPO Amount', currency_field='currency_id', tracking=True)

    work_completion_date = fields.Date(string='Work Comp.Dt.', tracking=True)
    report_date = fields.Date(string='Report Date', tracking=True)
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]",
    )
    invoice_no = fields.Char(string='Inv. No.')
    invoice_date = fields.Date(string='Inv. Dt.')
    invoice_amount = fields.Monetary(string='Inv. Amt', currency_field='currency_id')

    opened_by = fields.Char(string='Open By', default=lambda self: self.env.user.name)
    technician_id = fields.Many2one('cpabooks.cafm.technician', string='Technician')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    status = fields.Selection([
        ('waiting_approval', 'VAR Work Approval'),
        ('work_ongoing', 'Work Ongoing'),
        ('waiting_lpo', 'Waiting for LPO'),
        ('waiting_report', 'Waiting for Report Completion'),
        ('invoiced', 'VAR work - Invoiced'),
        ('no_status', 'No Status Found'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='no_status', tracking=True)

    remark_ids = fields.One2many(
        'cpabooks.cafm.var.work.remark', 'var_work_id', string='Remarks History',
    )
    # Normal form field — user types here each update; history goes to notebook
    remarks_last_update = fields.Text(
        string='Remarks (last update)', tracking=True,
    )

    sl_no = fields.Integer(string='SLNo', store=False)

    def _renumber_remarks(self):
        """Keep Sr. 1 = latest after delete."""
        for work in self:
            lines = work.remark_ids.sorted(
                key=lambda r: (r.remark_date or fields.Datetime.from_string('1970-01-01'), r.id),
                reverse=True,
            )
            for idx, line in enumerate(lines, start=1):
                if line.sr != idx:
                    line.sr = idx

    def _append_remark_history(self, text, source='form'):
        """Add notebook history line (Sr. 1 = newest). Skip duplicate of current top."""
        text = (text or '').strip()
        if not text:
            return
        Remark = self.env['cpabooks.cafm.var.work.remark']
        for rec in self:
            latest = rec.remark_ids.filtered(lambda r: r.sr == 1)[:1]
            if latest and (latest.name or '').strip() == text:
                continue
            Remark.create({
                'var_work_id': rec.id,
                'name': text,
                'source': source,
                'user_id': self.env.uid,
            })

    @api.model
    def create(self, vals):
        vals = dict(vals or {})
        vals.pop('sl_no', None)
        vals = self._link_call_from_numbers(vals)
        if not vals.get('qt_no'):
            seq = self.env['ir.sequence'].next_by_code('cpabooks.cafm.var.qt') or '0000'
            year_suffix = fields.Date.today().strftime('%y')
            vals['qt_no'] = '%sG%sQ' % (year_suffix, seq)
        if vals.get('call_id') and not vals.get('call_no'):
            call = self.env['maintenance.request'].browse(vals['call_id'])
            if call.call_no:
                vals['call_no'] = call.call_no
        vals = self._default_client_from_l3(vals)
        remark_text = vals.get('remarks_last_update')
        rec = super(CafmVarWork, self).create(vals)
        if remark_text:
            rec._append_remark_history(remark_text, source='form')
        return rec

    def write(self, vals):
        vals = dict(vals or {})
        vals.pop('sl_no', None)
        vals = self._link_call_from_numbers(vals)
        # L3 project changed → default Client Name from project (unless user set partner)
        if vals.get('l3_level_id') and 'partner_id' not in vals:
            vals = self._default_client_from_l3(vals, force=True)
        old_remarks = {}
        if 'remarks_last_update' in vals and not self.env.context.get('skip_remark_history'):
            old_remarks = {rec.id: (rec.remarks_last_update or '').strip() for rec in self}
        res = super(CafmVarWork, self).write(vals)
        if 'remarks_last_update' in vals and not self.env.context.get('skip_remark_history'):
            new_text = (vals.get('remarks_last_update') or '').strip()
            for rec in self:
                if new_text and new_text != old_remarks.get(rec.id, ''):
                    rec._append_remark_history(new_text, source='form')
        return res

    def _default_client_from_l3(self, vals, force=False):
        """Set Client Name (partner_id) from L3 Level (Project) name when missing / forced."""
        if not vals.get('l3_level_id'):
            return vals
        if vals.get('partner_id') and not force:
            return vals
        project = self.env['project.project'].browse(vals['l3_level_id'])
        partner = self._get_or_create_partner_from_name(project.name)
        if partner:
            vals['partner_id'] = partner.id
        return vals

    def message_post(self, **kwargs):
        """Chatter comments → Remarks field + notebook history."""
        msg = super(CafmVarWork, self).message_post(**kwargs)
        if self.env.context.get('skip_remark_history'):
            return msg
        message_type = kwargs.get('message_type') or 'notification'
        if message_type != 'comment':
            return msg
        body = kwargs.get('body') or ''
        if not body:
            return msg
        from odoo.tools import html2plaintext
        text = html2plaintext(body).strip()
        if not text:
            return msg
        # Avoid tracking / system noise
        if text.startswith('Remark (Sr.') or '→' in text[:80]:
            return msg
        self.with_context(skip_remark_history=True).write({
            'remarks_last_update': text,
        })
        self._append_remark_history(text, source='chatter')
        return msg

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        aliases = {
            'sl_no': ['SLNo', 'Sl No', 'Sl.No', 'SL No', 'Sr', 'Sr.'],
            'qt_no': ['QT.No', 'QT No', 'QT No.'],
            'qt_no_tally': ['QT.No (Tally)', 'QT No (Tally)', 'QT.No(Tally)', 'QT No. (Tally)'],
            'qt_date': ['QT.Date', 'QT Date'],
            'call_no': ['Call No.', 'Call No'],
            'call_no_tally': ['Call No. (Tally)', 'Call No (Tally)', 'Call No.(Tally)'],
            'call_dt': ['Call Dt.', 'Call Dt', 'Call Date'],
            'work_approved_by': ['Work Appr.By.', 'Work Appr By', 'Work Appr.By'],
            'work_approval_date': ['Work Appr.Dt.', 'Work Appr Dt', 'Work Appr.Dt'],
            'work_approved_amount': [
                'Work App. Amt', 'Work Appr. Amt', 'Work App Amt', 'Work Appr Amt',
                'Work App.',  # multiline Excel header "Work App." / "Amt"
            ],
            'work_completion_date': ['Work Comp.Dt.', 'Work Comp Dt', 'Work Comp.Dt'],
            'opened_by': ['Open By', 'Open by'],
            'partner_id': ['Client Name', 'Party Name (client)', 'Party Name'],
            'l2_level_id': ['L2 Level (Client Group)', 'L2 Level', 'L2 Level (Project Group)'],
            'l3_level_id': ['L3 Level (Project)', 'L3 Level'],
        }
        for fname, labels in aliases.items():
            if fname in res:
                res[fname]['string'] = labels[0]
                res[fname]['exportable'] = fname != 'sl_no'
        return res

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id:
            self.invoice_no = self.invoice_id.name
            self.invoice_date = self.invoice_id.invoice_date
            self.invoice_amount = self.invoice_id.amount_total

    @api.onchange('call_id')
    def _onchange_call_id(self):
        call = self.call_id
        if not call:
            return
        self.cafm_unit_id = call.cafm_unit_id
        self.flat_villa = call.flat or (call.cafm_unit_id.name if call.cafm_unit_id else False)
        self.l2_level_id = call.l2_level_id
        self.l3_level_id = call.l1_level_id or call.cafm_project_id
        self.work_type_id = call.work_type_id
        self.problem_description = call.problem_description or call.problem
        self.technician_id = call.technician_id
        # Odoo Call No. from linked call; keep Tally separate
        if call.call_no:
            self.call_no = call.call_no
        if call.call_no_tally:
            self.call_no_tally = call.call_no_tally
        if call.call_date:
            self.call_dt = fields.Datetime.to_datetime(call.call_date).date()
        # Client Name: prefer call customer, else L3 project name, else contract client
        if call.partner_id:
            self.partner_id = call.partner_id
        elif self.l3_level_id:
            self.partner_id = self._get_or_create_partner_from_name(self.l3_level_id.name)
        elif call.contract_id and call.contract_id.client_id:
            self.partner_id = call.contract_id.client_id

    @api.model
    def _get_or_create_partner_from_name(self, name):
        name = (name or '').strip()
        if not name:
            return self.env['res.partner']
        Partner = self.env['res.partner']
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({'name': name})
        return partner

    @api.onchange('l3_level_id')
    def _onchange_l3_level_id(self):
        """Dropping L3 Level (Project) → default Client Name from project name (user may change)."""
        if self.l3_level_id:
            self.partner_id = self._get_or_create_partner_from_name(self.l3_level_id.name)
        else:
            self.partner_id = False

    def _link_call_from_numbers(self, vals):
        """Match AMC call from Call No. (Tally) or Call No. when call_id empty."""
        if vals.get('call_id'):
            return vals
        Call = self.env['maintenance.request']
        for key in ('call_no_tally', 'call_no'):
            raw = vals.get(key)
            if not raw:
                continue
            number = str(raw).strip()
            if not number:
                continue
            call = Call.search([('call_no', '=', number)], limit=1)
            if not call:
                call = Call.search([('call_no_tally', '=', number)], limit=1)
            if call:
                vals['call_id'] = call.id
                if not vals.get('call_no') and call.call_no:
                    vals['call_no'] = call.call_no
                break
        return vals

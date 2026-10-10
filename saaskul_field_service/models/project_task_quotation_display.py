# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

_FSM_STAGE7_JOB_DONE_KEYS = frozenset({
    'waiting_for_invoice',
    'job_completed',
    'job_completed_invoiced',
    'approved',
})

_FSM_INVOICE_STAGE_KEYS = frozenset({
    'waiting_for_invoice',
    'job_completed',
    'job_completed_invoiced',
})


class ProjectTaskFsmQuotationDisplay(models.Model):
    """FSM stage 3/4 quotation labels (separate file for safe module upgrades)."""

    _inherit = 'project.task'

    fsm_stage7_job_complete = fields.Boolean(
        string='FSM Job Complete',
        compute='_compute_fsm_stage7_approval_display',
    )
    fsm_stage7_approval_status = fields.Char(
        string='Approval Status',
        compute='_compute_fsm_stage7_approval_display',
    )
    # Legacy aliases — kept so older form views / cached assets do not break on read().
    fsm_stage7_approval_waiting = fields.Char(
        compute='_compute_fsm_stage7_approval_display',
    )
    fsm_stage7_approval_approved = fields.Char(
        compute='_compute_fsm_stage7_approval_display',
    )
    fsm_stage7_approval_rejected = fields.Char(
        compute='_compute_fsm_stage7_approval_display',
    )
    fsm_stage7_approval_tone = fields.Selection(
        selection=[
            ('waiting', 'Waiting'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('none', 'None'),
        ],
        compute='_compute_fsm_stage7_approval_display',
    )

    fsm_quotation_id = fields.Many2one(
        'sale.order',
        string='Quotation',
        compute='_compute_fsm_quotation_stage_info',
    )
    fsm_quotation_status = fields.Char(
        string='Quotation Progress',
        compute='_compute_fsm_quotation_stage_info',
    )
    fsm_quotation_approval_status = fields.Char(
        string='Quotation Approval',
        compute='_compute_fsm_quotation_stage_info',
    )
    fsm_invoice_progress_status = fields.Char(
        string='Invoice Progress',
        compute='_compute_fsm_invoice_display',
    )
    fsm_invoice_number_display = fields.Char(
        string='Invoice Number',
        compute='_compute_fsm_invoice_display',
    )
    fsm_invoice_progress_tone = fields.Selection(
        selection=[
            ('in_progress', 'In Progress'),
            ('draft', 'Draft'),
            ('issued', 'Issued'),
            ('none', 'None'),
        ],
        compute='_compute_fsm_invoice_display',
    )

    def _get_fsm_crn_quotation_invoices(self):
        """Customer invoices created from this CRN's linked quotation(s)."""
        self.ensure_one()
        move_model = self.env['account.move'] if self.env.registry.get('account.move') else False
        if move_model is False:
            return move_model
        sale_order_model = self.env['sale.order'] if self.env.registry.get('sale.order') else False
        orders = sale_order_model.browse() if sale_order_model is not False else False
        if sale_order_model is not False:
            task_id = self.id if isinstance(self.id, int) else False
            if not task_id:
                origin = getattr(self, '_origin', None)
                task_id = origin.id if origin and origin.id else False
            if task_id:
                orders |= sale_order_model.search([('task_id', '=', task_id), ('state', '!=', 'cancel')])
        if orders is not False and self.qt_no:
            orders |= self.qt_no

        invoices = move_model
        if orders:
            invoices |= orders.mapped('invoice_ids')
            origins = [name for name in orders.mapped('name') if name]
            if self.task_seq:
                origins.append(self.task_seq)
            for origin in origins:
                invoices |= move_model.search([
                    ('move_type', '=', 'out_invoice'),
                    ('state', '!=', 'cancel'),
                    ('invoice_origin', 'ilike', origin),
                ], limit=50)
        # Do NOT include invoice_id (Stage 1 Reference Invoice Number).
        # That old invoice is only a registration reference; Stage 6 must use
        # invoices created from this CRN's quotation / workflow.

        return invoices.filtered(
            lambda move: move.move_type == 'out_invoice' and move.state != 'cancel'
        ).sorted('id', reverse=True)

    def _fsm_invoice_panel_active(self):
        self.ensure_one()
        # Reference Invoice (invoice_id) must not open / fill Stage 6.
        if self.next_action in ('closed', 'foc'):
            return bool(self._get_fsm_crn_quotation_invoices())
        stage_key = (
            self._get_fsm_stage_value()
            if hasattr(self, '_get_fsm_stage_value')
            else (self.stage or self.state or 'registered')
        )
        if stage_key in _FSM_INVOICE_STAGE_KEYS:
            return True
        if self._get_fsm_related_orders_active():
            return bool(self.date_end)
        return False

    @api.depends(
        'stage',
        'state',
        'date_end',
        'next_action',
        'fsm_all_invoice_count',
        'qt_no',
        'qt_no.invoice_ids',
        'qt_no.invoice_ids.state',
        'qt_no.invoice_ids.name',
        'qt_no.invoice_ids.invoice_origin',
    )
    def _compute_fsm_invoice_display(self):
        for task in self:
            task.select_invoice = False
            task.fsm_invoice_progress_status = ''
            task.fsm_invoice_number_display = ''
            task.fsm_invoice_progress_tone = 'none'
            if not task._fsm_invoice_panel_active():
                continue
            invoices = task._get_fsm_crn_quotation_invoices()
            numbered = invoices.filtered(lambda move: move.name and move.name != '/')
            posted = invoices.filtered(lambda move: move.state == 'posted')
            draft = invoices.filtered(lambda move: move.state == 'draft')
            if numbered:
                invoice = numbered[0]
                task.select_invoice = invoice.id
                task.fsm_invoice_progress_status = _('Done')
                task.fsm_invoice_number_display = invoice.name
                task.fsm_invoice_progress_tone = 'issued'
            elif posted:
                invoice = posted[0]
                task.select_invoice = invoice.id
                task.fsm_invoice_progress_status = _('Done')
                task.fsm_invoice_number_display = invoice.name if invoice.name != '/' else ''
                task.fsm_invoice_progress_tone = 'issued'
            elif draft:
                task.fsm_invoice_progress_status = _('Pending')
                task.fsm_invoice_progress_tone = 'draft'
            else:
                task.fsm_invoice_progress_status = _('Pending')
                task.fsm_invoice_progress_tone = 'in_progress'

    @api.depends('fsm_all_quotation_count', 'qt_no', 'qt_no.state')
    def _compute_fsm_quotation_stage_info(self):
        for task in self:
            orders = task._get_fsm_related_orders_active().sorted('id', reverse=True)
            order = orders[:1]
            task.fsm_quotation_id = order.id if order else False
            if not order:
                task.fsm_quotation_status = ''
                task.fsm_quotation_approval_status = ''
                continue
            if order.state in ('sale', 'done'):
                task.fsm_quotation_status = ''
                task.fsm_quotation_approval_status = _('Done')
            elif order.state in ('draft', 'sent'):
                task.fsm_quotation_status = _('Done')
                task.fsm_quotation_approval_status = ''
            else:
                task.fsm_quotation_status = _('Done')
                task.fsm_quotation_approval_status = ''

    def _cpabooks_refresh_fsm_quotation_display(self):
        """Re-read quotation stage labels after linked sale.order changes."""
        cache = getattr(self.env, '_cpabooks_fsm_perf_cache', None)
        if cache:
            cache.get('orders', {}).clear()
            cache.get('checks_map', {}).clear()
        fnames = [
            'fsm_all_quotation_count',
            'fsm_quotation_id',
            'fsm_quotation_status',
            'fsm_quotation_approval_status',
            'fsm_stage7_job_complete',
            'fsm_stage7_approval_status',
            'fsm_stage7_approval_waiting',
            'fsm_stage7_approval_approved',
            'fsm_stage7_approval_rejected',
            'fsm_stage7_approval_tone',
            'select_invoice',
            'fsm_invoice_progress_status',
            'fsm_invoice_number_display',
            'fsm_invoice_progress_tone',
        ]
        fnames = [name for name in fnames if name in self._fields]
        if fnames:
            self.invalidate_cache(fnames)

    @api.depends(
        'stage',
        'state',
        'date_end',
        'select_invoice',
        'approved_by',
    )
    def _compute_fsm_stage7_approval_display(self):
        for task in self:
            stage_key = task._get_fsm_stage_value() if hasattr(task, '_get_fsm_stage_value') else (
                task.stage or task.state or 'registered'
            )
            job_complete = stage_key in _FSM_STAGE7_JOB_DONE_KEYS
            task.fsm_stage7_job_complete = job_complete
            task.fsm_stage7_approval_status = ''
            task.fsm_stage7_approval_waiting = ''
            task.fsm_stage7_approval_approved = ''
            task.fsm_stage7_approval_rejected = ''
            task.fsm_stage7_approval_tone = 'none'
            if not job_complete:
                continue
            approval_state = getattr(task, 'approval_state', None) or 'pending'
            if approval_state == 'approved' or task.approved_by:
                label = _('Done')
                task.fsm_stage7_approval_status = label
                task.fsm_stage7_approval_approved = label
                task.fsm_stage7_approval_tone = 'approved'
            else:
                label = _('Waiting for Approval')
                task.fsm_stage7_approval_status = label
                task.fsm_stage7_approval_waiting = label
                task.fsm_stage7_approval_tone = 'waiting'

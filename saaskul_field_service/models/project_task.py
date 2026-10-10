from datetime import date, datetime
import json
import re

import pytz
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression

CPABOOKS_FSM_CRN_MUTATION_CTX = 'cpabooks_fsm_crn_mutation'


STAGE_SELECTION = [
    ('registered', '1. Registered'),
    ('site_visited', '2. Site Visited (i)'),
    ('qty_issued', '3. Qtn Issued and waiting for Approval'),
    ('qty_approved', '4. QTN Approved'),
    ('in_progress', '5. Work in Progress'),
    ('waiting_for_invoice', '6. Job Complete Waiting for Invoice'),
    ('job_completed', '7. Job Completed-FOC'),
    ('job_completed_invoiced', '8. Job Completed & Invoiced'),
    ('approved', '9. Approved'),
]

COMPLAINT_TYPE_SELECTION = [
    ('amc', 'AMC'),
    ('others', 'Others'),
    ('warranty', 'Warranty'),
    ('service', 'Service'),
    ('new_installation', 'New Installation'),
    ('new_inquiry', 'New Inquiry'),
    ('site_visit', 'Site Visit'),
]

STATE = [
    ('registered', '1. Reg.'),
    ('site_visited', '2. Site Visit'),
    ('qty_issued', '3. QTN Issue'),
    ('qty_approved', '4. QTN Appvd'),
    ('in_progress', '5. WIP'),
    ('waiting_for_invoice', '6. Wait Inv'),
    ('job_completed', '7. FOC Done'),
    ('job_completed_invoiced', '8. Invoiced'),
    ('approved', '9. Approved'),
]

_FSM_STATE_KEYS = frozenset(dict(STATE).keys())
_FSM_STAGE_KEYS = frozenset(dict(STAGE_SELECTION).keys())
_FSM_STAGE_PROGRESS_WEIGHTS = {
    key: round(index * 100.0 / (len(STAGE_SELECTION) - 1), 2)
    for index, (key, _label) in enumerate(STAGE_SELECTION)
}

_FSM_NAV_STEPS = [
    ('site_visit', '1. Site Visit'),
    ('closed', '2. Closed'),
    ('issue', '3. Issue Quotation'),
    ('foc', '4. FOC / Work in Progress'),
    ('complete', '5. Job Complete'),
    ('invoice', '6. Invoiced'),
    ('approval', '7. Approved'),
]

# Top progress bar + right sidebar (7 stages, mockup-aligned labels)
_FSM_WORKFLOW_STAGE_ORDER = [
    'registered',
    'site_visited',
    'qty_issued',
    'qty_approved',
    'in_progress',
    'waiting_for_invoice',
    'approved',
]
_FSM_WORKFLOW_PROGRESS_LABELS = [
    ('registered', _('CRN Number Created'), 'cpabooks_fsm_chev_orange'),
    ('site_visited', _('SITE VISIT'), 'cpabooks_fsm_chev_green'),
    ('qty_issued', _('QUOTATION ISSUED'), 'cpabooks_fsm_chev_blue'),
    ('qty_approved', _('QUOTATION APPROVED'), 'cpabooks_fsm_chev_purple'),
    ('in_progress', _('WIP'), 'cpabooks_fsm_chev_teal'),
    ('waiting_for_invoice', _('INVOICE'), 'cpabooks_fsm_chev_yellow'),
    ('approved', _('CLOSE'), 'cpabooks_fsm_chev_pink'),
]
# Sidebar checklist items → form field serial (1–38)
_FSM_WORKFLOW_OPTION_KEYS = frozenset({
    's2_close',
    's2_issue_qtn',
    's4_client_approved',
    's4_client_rejected',
    's4_need_revision',
    's5_route_invoice',
    's5_route_foc',
})

_FSM_WORKFLOW_ITEM_SERIALS = {
    's1_crn': '1',
    's1_create_date': '2',
    's1_created_by': '3',
    's1_customer': '4',
    's1_site': '5',
    's1_contact': '6',
    's1_phone': '7',
    's1_email': '8',
    's1_complaint_type': '9',
    's1_old_invoice': '10',
    's1_qtn': '11',
    's1_invoice_line': '12',
    's1_invoice_type': '13',
    's1_repeated': '14',
    's1_project': '15',
    's1_no_ref': '15',
    's1_title': '16',
    's1_details': '17',
    's1_deadline': '18',
    's1_priority': '19',
    's1_print_rows': '20',
    's2_visited_by': '21',
    's2_visit_date': '22',
    's2_remarks': '23',
    's2_next_action': '24',
    's3_assign_tech': '27',
    's3_assign_date': '28',
    's3_job_complete': '29',
    's3_invoice_created': '30',
    's5_assign_to': '27',
    's5_assign_date': '28',
    's5_end_date': '29',
    's6_link_invoice': '30',
    's3_material_cost': '32',
    's5_timesheet': '33',
    's5_transport': '34',
    's5_other': '35',
    's5_total_cost': '36',
    's5_completion_remarks': '37',
    's7_closing_remarks': '37',
}

_FSM_WORKFLOW_BANNER = {
    'registered': (_('STAGE 1 (CRN NUMBER CREATED)'), 'cpabooks_fsm_banner_orange'),
    'site_visited': (_('STAGE 2 (SITE VISIT)'), 'cpabooks_fsm_banner_green'),
    'qty_issued': (_('STAGE 3 (QUOTATION ISSUED)'), 'cpabooks_fsm_banner_blue'),
    'qty_approved': (_('STAGE 4 (QUOTATION APPROVED)'), 'cpabooks_fsm_banner_purple'),
    'in_progress': (_('STAGE 5 (WORK IN PROGRESS)'), 'cpabooks_fsm_banner_teal'),
    'waiting_for_invoice': (_('STAGE 6 (WAITING INVOICE / INVOICE)'), 'cpabooks_fsm_banner_yellow'),
    'job_completed': (_('STAGE 6 (WAITING INVOICE / INVOICE)'), 'cpabooks_fsm_banner_yellow'),
    'job_completed_invoiced': (_('STAGE 6 (WAITING INVOICE / INVOICE)'), 'cpabooks_fsm_banner_yellow'),
    'approved': (_('STAGE 7 (APPROVAL / CLOSE)'), 'cpabooks_fsm_banner_pink'),
}


class ProjectTask(models.Model):
    _inherit = 'project.task'
    _rec_name = 'task_seq'
    _order = 'write_date desc, create_date desc, id desc'

    project_id = fields.Many2one(required=False)

    state = fields.Selection(
        STATE,
        string='State',
        compute='_compute_state_from_stage',
        inverse='_inverse_state_from_fsm_selection',
        search='_search_state',
        tracking=True,
    )
    remarks = fields.Text('Remarks', tracking=True)
    date_start = fields.Date('Start Date', default=fields.Date.today)
    date_end = fields.Date('End Date')
    task_seq = fields.Char('CRN Number', copy=False, readonly=True, index=True, default='/')
    fsm_creator_uid = fields.Many2one(
        'res.users',
        string='CRN Created By',
        copy=False,
        readonly=True,
        index=True,
        help='User who registered this CRN. Used for My CRNs list visibility (independent of assignee).',
    )
    sample = fields.Char('Sample')
    close_remarks = fields.Text('Closing Remarks')
    complaint_title = fields.Many2one('complaint.detail', 'Complaint Title')
    complaint_details = fields.Text('Complaint Details')
    complaint_details_short = fields.Char(
        string='Complaint Details',
        compute='_compute_complaint_details_short',
    )
    client_person = fields.Many2one('contact.person', 'Contact Person')
    client_contact = fields.Char('Contact Number')
    site_location = fields.Many2one('site.location', 'Site Location')
    client_email = fields.Char('Email ID')
    qt_no = fields.Many2one('sale.order', string='Ref Quotation No.')
    qt_no_text = fields.Char(
        string='Ref Quotation No. (Text)',
        help='Manual quotation reference when no linked quotation is available on the invoice.',
    )
    check_fsm = fields.Boolean('Check FSM', default=False)
    fsm_crn_form = fields.Boolean(
        string='CRN Complaint Registration Form',
        compute='_compute_fsm_crn_form',
        store=True,
        index=True,
        help='True for call-center CRN records (not standard project tasks).',
    )
    source_task_id = fields.Many2one(
        'project.task',
        string='Source Project Task',
        copy=False,
        readonly=True,
        help='Project task (not a CRN) from which this call-center CRN was created.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='CRN Analytic Account',
        copy=False,
        readonly=True,
    )
    complaint_type = fields.Selection(COMPLAINT_TYPE_SELECTION, 'Complaint Type')
    total_print_row = fields.Integer(default=10, string='Total Print Row')
    invoice_id = fields.Many2one(
        'account.move',
        'Ref. Invoice No.',
        domain=[('move_type', '=', 'out_invoice'), ('invoice_type', '!=', False)],
    )
    available_invoice_ids = fields.Many2many(
        'account.move',
        compute='_compute_available_invoice_ids',
    )
    invoice_type = fields.Char(compute='_compute_invoice_type', string='Invoice Type', readonly=True)
    show_invoice_line = fields.Boolean(compute='_compute_show_invoice_line')
    available_invoice_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_available_invoice_line_ids',
    )
    available_quotation_ids = fields.Many2many(
        'sale.order',
        compute='_compute_available_quotation_ids',
        string='Available Quotations',
    )
    invoice_line_notice = fields.Char(compute='_compute_invoice_line_notice')
    invoice_project_ids = fields.Many2many(
        'project.project',
        compute='_compute_invoice_project_ids',
    )
    item_des = fields.Many2one(
        'account.move.line',
        string='Invoice Line',
        domain="""
                [
                    ('move_id', '=', invoice_id),
                    ('display_type', '=', False)
                ]
            """
    )
    stage = fields.Selection(
        STAGE_SELECTION,
        string='Stage',
        default='registered',
        tracking=True,
        compute='_compute_stage_logic',
        compute_sudo=True,
        inverse='_inverse_stage_from_fsm_selection',
        search='_search_stage',
    )
    fsm_stage_progress = fields.Float(
        string='Progress %',
        compute='_compute_fsm_stage_progress',
        store=True,
        search='_search_fsm_stage_progress',
    )
    fsm_stage_group = fields.Selection(
        STAGE_SELECTION,
        string='Stage',
        compute='_compute_stage_logic',
        compute_sudo=True,
        store=True,
        index=True,
    )
    site_visit = fields.Text('Site Visit Remarks')
    visited_by = fields.Many2one('hr.employee', 'Visited By')
    visited_date = fields.Date('Visited Date')
    fsm_assigned_employee_id = fields.Many2one(
        'hr.employee',
        string='Assigned To',
        index=True,
        help='Technician assigned for FOC / Issue QT (synced to task assignee user).',
    )
    material_line_ids = fields.One2many('material.request.line', 'task_id')
    customer_part_line_ids = fields.One2many(
        'project.task.customer.part.line',
        'task_id',
        string='Customer Material Details',
    )
    customer_labour_line_ids = fields.One2many(
        'project.task.customer.labour.line',
        'task_id',
        string='Customer Labour Cost',
    )
    material_return_picking_ids = fields.One2many(
        'stock.picking',
        'issue_project_task_id',
        string='Material Returns',
        domain=[('is_material_return', '=', True)],
    )
    material_return_move_ids = fields.Many2many(
        'stock.move',
        string='Material Return Moves',
        compute='_compute_material_return_move_ids',
    )
    material_amount_done_total = fields.Float(
        string='Total Amount Done',
        compute='_compute_material_amount_done_total',
    )
    material_cost_total = fields.Monetary(
        string='Material Cost',
        currency_field='currency_id',
        compute='_compute_material_amount_done_total',
    )
    timesheet_cost_total = fields.Monetary(
        string='Timesheet Cost',
        currency_field='currency_id',
        compute='_compute_timesheet_cost_total',
        compute_sudo=True,
        store=True,
        prefetch=False,
    )
    fsm_transport_cost = fields.Monetary(
        string='Transport Cost',
        currency_field='currency_id',
        default=0.0,
    )
    fsm_other_cost = fields.Monetary(
        string='Other Cost',
        currency_field='currency_id',
        default=0.0,
    )
    total_service_cost = fields.Monetary(
        string='Total Service Cost',
        currency_field='currency_id',
        compute='_compute_total_service_cost',
        compute_sudo=True,
    )
    work_completion = fields.Selection([('invoiced', 'Invoiced'), ('foc', 'FOC Done')], string='iv. Work Completion:')
    closing_remarks = fields.Text('Closing Remarks')
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        ondelete='set null',
        readonly=True,
    )
    select_invoice = fields.Many2one(
        'account.move',
        string='Select Invoice',
        compute='_compute_fsm_invoice_display',
    )
    next_action = fields.Selection([
        ('closed', '1. Closed'),
        ('issue', '2. Issue QT'),
        ('foc', '3. FOC'),
    ], string='Next Action', tracking=True)
    fsm_nav_completed = fields.Text(
        string='FSM Navigation Completed Steps',
        copy=False,
        help='JSON list of workflow step keys the user has already completed.',
    )
    fsm_action_nav_html = fields.Html(
        string='Workflow Guide',
        compute='_compute_fsm_workflow_ui',
        sanitize=False,
    )
    fsm_workflow_progress_html = fields.Html(
        string='Workflow Progress',
        compute='_compute_fsm_workflow_ui',
        sanitize=False,
    )
    fsm_stage_banner_html = fields.Html(
        string='Current Stage Banner',
        compute='_compute_fsm_workflow_ui',
        sanitize=False,
    )
    fsm_nav_suggested_label = fields.Char(
        string='Suggested Next Step',
        compute='_compute_fsm_workflow_ui',
    )
    fsm_workflow_pending_serials_display = fields.Char(
        string='Pending Checklist Items',
        compute='_compute_fsm_workflow_pending_serials_display',
    )
    fsm_workflow_pending_ribbon_text = fields.Char(
        string='Pending Ribbon Text',
        compute='_compute_fsm_workflow_pending_ribbon_text',
    )
    fsm_workflow_ribbon_status = fields.Char(
        string='CRN Workflow Ribbon Status',
        compute='_compute_fsm_workflow_ribbon_status',
    )
    fsm_ui_active_stage = fields.Integer(
        string='FSM UI Active Stage',
        default=0,
        copy=False,
        help='0=Registration … 6=Close. Controls which form block is editable until Edit is used.',
    )
    fsm_workflow_edit_mode = fields.Boolean(
        string='FSM Workflow Edit Mode',
        default=False,
        copy=False,
        help='When enabled, all workflow stages are editable again.',
    )
    fsm_stage_0_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_1_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_2_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_3_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_4_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_5_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    fsm_stage_6_readonly = fields.Boolean(compute='_compute_fsm_ui_readonly_flags')
    assign_date = fields.Date(string='Assign Date')
    crn_done_before = fields.Char(
        'CRN Done Before',
        compute='_compute_crn_done_before',
        readonly=True,
    )
    age_days = fields.Integer('Age Days', compute='_compute_age_days')
    deadline = fields.Date('Date Deadline')
    importance = fields.Selection([
        ('urgent', 'Urgent'),
        ('normal', 'Normal'),
        ('emergency', 'Emergency'),
    ], string='Priority')
    issue_note_done = fields.Boolean(
        'Issue Note Done',
        compute='_compute_issue_note_done',
        search='_search_issue_note_done',
    )
    fsm_all_quotation_count = fields.Integer(compute='_compute_fsm_related_document_counts')
    fsm_all_invoice_count = fields.Integer(compute='_compute_fsm_related_document_counts')
    fsm_all_delivery_count = fields.Integer(compute='_compute_fsm_related_document_counts')
    fsm_show_pending_banner = fields.Boolean(default=False, copy=False)
    fsm_stage0_force_complete = fields.Boolean(
        string='Registration Stage Force Closed',
        default=False,
        copy=False,
        help='When set, stage 1 registration is treated as 100% complete even if some fields are empty.',
    )
    fsm_pending_banner_html = fields.Html(compute='_compute_fsm_pending_banner_html', sanitize=False)

    def init(self):
        cr = self.env.cr
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'project_task' AND column_name = 'complaint_type'
        """)
        if not cr.fetchone():
            return
        cr.execute("""
            UPDATE project_task
               SET complaint_type = 'warranty'
             WHERE complaint_type = 'warranty_service'
        """)

    @api.model
    def _fsm_default_planned_datetimes(self):
        """Match industry_fsm: today 09:00–17:00 in user TZ so planning filters do not hide new CRNs."""
        user_tz = pytz.timezone(self.env.context.get('tz') or 'UTC')
        now_utc = pytz.utc.localize(datetime.utcnow())
        local_now = now_utc.astimezone(user_tz)
        begin = local_now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = local_now.replace(hour=17, minute=0, second=0, microsecond=0)
        return (
            begin.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _cpabooks_should_leave_project_empty(self):
        """New CRN forms should not auto-pick Field Service unless caller sets default_project_id."""
        if self.env.context.get('default_project_id'):
            return False
        return bool(
            self.env.context.get('fsm_mode')
            or self.env.context.get('create_crn')
            or self.env.context.get('default_is_fsm')
            or self.env.context.get('default_check_fsm')
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if (
            self.env.context.get('fsm_mode')
            or self.env.context.get('create_crn')
            or self.env.context.get('default_is_fsm')
            or self.env.context.get('default_check_fsm')
        ):
            res['check_fsm'] = True
            res['is_fsm'] = True
            if 'fsm_creator_uid' in fields_list and not res.get('fsm_creator_uid'):
                res['fsm_creator_uid'] = self.env.uid
            if 'planned_date_begin' in fields_list and not res.get('planned_date_begin'):
                begin, end = self._fsm_default_planned_datetimes()
                res['planned_date_begin'] = begin
                if 'planned_date_end' in fields_list and not res.get('planned_date_end'):
                    res['planned_date_end'] = end
            res['partner_id'] = False
            res.pop('user_id', None)
            res.pop('visited_by', None)
            res.pop('fsm_assigned_employee_id', None)
        if self._cpabooks_should_leave_project_empty():
            res.pop('project_id', None)
        if not res.get('name'):
            res['name'] = self._default_task_name_from_vals(res)
        # Other project apps may default state to 'todo'; our state uses FSM keys only
        st = res.get('state')
        if st is not None and st is not False and st not in _FSM_STATE_KEYS:
            res.pop('state', None)
        return res

    @api.model
    def _get_default_fsm_project(self, company_id=False):
        project_model = self.env['project.project'].sudo()
        if hasattr(company_id, 'id'):
            company_id = company_id.id

        fsm_project = self.env.ref('industry_fsm.fsm_project', raise_if_not_found=False)
        if fsm_project:
            fsm_project = fsm_project.sudo()
            if company_id and fsm_project.company_id and fsm_project.company_id.id != company_id:
                fsm_project = project_model

        if not fsm_project:
            domain = [('is_fsm', '=', True), ('name', '=', 'Field Service')]
            if company_id:
                domain.append(('company_id', 'in', [False, company_id]))
            fsm_project = project_model.with_context(active_test=False).search(domain, order='company_id desc, sequence, id', limit=1)

        if not fsm_project:
            vals = {
                'name': _('Field Service'),
                'is_fsm': True,
                'allow_timesheets': True,
            }
            if company_id:
                vals['company_id'] = company_id
            fsm_project = project_model.create(vals)
        return self.env['project.project'].browse(fsm_project.id)

    @api.model
    def _get_project_not_available_fsm_project(self, company_id=False):
        project_model = self.env['project.project'].sudo()
        if hasattr(company_id, 'id'):
            company_id = company_id.id

        domain = [('is_fsm', '=', True), ('name', '=', 'Project Not Available')]
        if company_id:
            domain.append(('company_id', 'in', [False, company_id]))
        fsm_project = project_model.with_context(active_test=False).search(
            domain,
            order='company_id desc, sequence, id',
            limit=1,
        )
        if not fsm_project:
            vals = {
                'name': _('Project Not Available'),
                'is_fsm': True,
                'allow_timesheets': True,
            }
            if company_id:
                vals['company_id'] = company_id
            fsm_project = project_model.create(vals)
        return self.env['project.project'].browse(fsm_project.id)

    @api.depends('is_fsm', 'check_fsm')
    def _compute_fsm_crn_form(self):
        for task in self:
            task.fsm_crn_form = bool(task.is_fsm or task.check_fsm)

    @api.depends('complaint_details')
    def _compute_complaint_details_short(self):
        word_limit = 20
        for task in self:
            text = (task.complaint_details or '').strip()
            if not text:
                task.complaint_details_short = ''
                continue
            words = text.split()
            if len(words) <= word_limit:
                task.complaint_details_short = text
            else:
                task.complaint_details_short = '%s...' % ' '.join(words[:word_limit])

    @api.depends('parent_id.partner_id', 'project_id.partner_id', 'is_fsm')
    def _compute_partner_id(self):
        non_fsm_tasks = self.filtered(lambda task: not task.is_fsm)
        if non_fsm_tasks:
            super(ProjectTask, non_fsm_tasks)._compute_partner_id()

        for task in self - non_fsm_tasks:
            if not task.partner_id and task.parent_id.partner_id:
                task.partner_id = task.parent_id.partner_id

    def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None):
        """Avoid duplicate followers when the same partner is subscribed twice (e.g. duplicate form widgets)."""
        if partner_ids and self.ids:
            existing_partner_ids = set(self.env['mail.followers'].sudo().search([
                ('res_model', '=', self._name),
                ('res_id', 'in', self.ids),
                ('partner_id', 'in', partner_ids),
            ]).mapped('partner_id').ids)
            partner_ids = [pid for pid in partner_ids if pid not in existing_partner_ids]
            if not partner_ids and not channel_ids:
                return True
        return super().message_subscribe(
            partner_ids=partner_ids,
            channel_ids=channel_ids,
            subtype_ids=subtype_ids,
        )

    @api.model
    def _crn_sequence_year(self, sequence_date=None):
        if sequence_date:
            if isinstance(sequence_date, str):
                sequence_date = fields.Date.to_date(sequence_date)
            elif isinstance(sequence_date, datetime):
                sequence_date = sequence_date.date()
            return sequence_date.year
        return fields.Date.context_today(self).year

    @api.model
    def _crn_number_from_task_seq(self, task_seq):
        if not task_seq:
            return 0
        match = re.search(r'/(\d+)\s*$', str(task_seq).strip())
        return int(match.group(1)) if match else 0

    @api.model
    def _get_fsm_crn_sequence(self, company_id):
        """Per-company CRN sequence, numbered per calendar year."""
        sequence_model = self.env['ir.sequence'].sudo()
        sequence = sequence_model.search([
            ('code', '=', 'fsm.crn'),
            ('company_id', '=', company_id),
        ], limit=1)
        if not sequence:
            company = self.env['res.company'].sudo().browse(company_id)
            sequence = sequence_model.create({
                'name': _('CRN Number (%s)') % company.name,
                'code': 'fsm.crn',
                'company_id': company_id,
                'prefix': 'CRN/CO%s/%%(range_year)s/' % company_id,
                'padding': 5,
                'number_increment': 1,
                'use_date_range': True,
            })
        return sequence

    @api.model
    def _get_fsm_crn_prefix(self, sequence, year):
        year_start = '%04d-01-01' % year
        prefix, _suffix = sequence._get_prefix_suffix(date=year_start, date_range=year_start)
        return prefix

    @api.model
    def _get_max_existing_crn_number(self, company_id, year):
        """Highest CRN suffix already used (duplicates kept; used to avoid new duplicates)."""
        company_id = company_id.id if hasattr(company_id, 'id') else (company_id or self.env.company.id)
        year = year or self._crn_sequence_year()
        prefix = self._get_fsm_crn_prefix(self._get_fsm_crn_sequence(company_id), year)
        tasks = self.with_context(active_test=False).sudo().search([
            ('task_seq', '=like', prefix + '%'),
        ])
        max_number = 0
        for task in tasks:
            max_number = max(max_number, self._crn_number_from_task_seq(task.task_seq))
        return max_number

    @api.model
    def _sync_fsm_crn_sequence_counter(self, company_id, year, next_number):
        sequence = self._get_fsm_crn_sequence(company_id)
        date_range = sequence._get_current_sequence(sequence_date=date(year, 1, 1))
        if date_range.number_next_actual < next_number:
            date_range.number_next_actual = next_number

    @api.model
    def _next_task_seq(self, sequence_date=False):
        company_id = self.env.company.id
        year = self._crn_sequence_year(sequence_date)
        sequence_date = sequence_date or fields.Date.context_today(self)
        sequence = self._get_fsm_crn_sequence(company_id)
        max_existing = self._get_max_existing_crn_number(company_id, year)
        self._sync_fsm_crn_sequence_counter(company_id, year, max_existing + 1)
        for _attempt in range(50):
            number = sequence._next(sequence_date=sequence_date)
            if not self.with_context(active_test=False).sudo().search_count([('task_seq', '=', number)]):
                return number
            max_existing = max(max_existing, self._crn_number_from_task_seq(number))
            self._sync_fsm_crn_sequence_counter(company_id, year, max_existing + 1)
        prefix = self._get_fsm_crn_prefix(sequence, year)
        return '%s%s' % (prefix, str(max_existing + 1).zfill(sequence.padding))

    @api.model
    def _strip_tid_prefix_from_crn(self, sequence):
        if not sequence:
            return sequence
        sequence = str(sequence).strip()
        if sequence.startswith('TID-CRN'):
            return sequence[len('TID-'):]
        return sequence

    @api.model
    def _normalize_task_seq(self, sequence):
        sequence = self._strip_tid_prefix_from_crn(sequence)
        if sequence and str(sequence).startswith('CRN'):
            return sequence
        parent = super(ProjectTask, self)
        if hasattr(parent, '_normalize_task_seq'):
            return parent._normalize_task_seq(sequence)
        return sequence

    def _normalize_crn_task_seq_values(self):
        for task in self:
            task_seq = task._strip_tid_prefix_from_crn(task.task_seq)
            if task_seq != task.task_seq:
                task.write({'task_seq': task_seq})

    @api.model
    def action_normalize_fsm_crn_numbers(self):
        tasks = self.sudo().search([('task_seq', 'ilike', 'TID-CRN')])
        tasks.filtered(lambda task: task.task_seq and task.task_seq.startswith('TID-CRN'))._normalize_crn_task_seq_values()
        return True

    @api.model
    def action_assign_default_project_to_unlinked_fsm_crns(self):
        unlinked_tasks = self.with_context(active_test=False).sudo().search([
            ('project_id', '=', False),
            ('task_seq', '=like', 'CRN%'),
        ])
        blank_invoice_project_tasks = self.with_context(active_test=False).sudo().search([
            ('invoice_id', '!=', False),
            ('invoice_id.project_id', '=', False),
            ('task_seq', '=like', 'CRN%'),
        ])
        tasks_by_project = {}
        for task in unlinked_tasks - blank_invoice_project_tasks:
            company_id = task.company_id.id if task.company_id else False
            fsm_project = self._get_default_fsm_project(company_id)
            if fsm_project:
                tasks_by_project.setdefault(fsm_project.id, self.browse())
                tasks_by_project[fsm_project.id] |= task
        for task in blank_invoice_project_tasks:
            company_id = task.company_id.id if task.company_id else False
            fsm_project = self._get_project_not_available_fsm_project(company_id)
            if fsm_project:
                tasks_by_project.setdefault(fsm_project.id, self.browse())
                tasks_by_project[fsm_project.id] |= task
        for project_id, project_tasks in tasks_by_project.items():
            project_tasks.write({'project_id': project_id})
        return True

    @api.model
    def action_backfill_fsm_crn_creators(self):
        """Backfill permanent CRN creator for list visibility (assignee may stay empty)."""
        tasks = self.with_context(active_test=False).sudo().search([
            ('is_fsm', '=', True),
            ('fsm_creator_uid', '=', False),
            ('create_uid', '!=', False),
        ])
        for task in tasks:
            task.fsm_creator_uid = task.create_uid
        legacy_crn = self.with_context(active_test=False).sudo().search([
            ('fsm_creator_uid', '=', False),
            ('task_seq', '=like', 'CRN%'),
            ('create_uid', '!=', False),
        ])
        for task in legacy_crn - tasks:
            task.fsm_creator_uid = task.create_uid
        return True

    @api.model
    def _default_task_name_from_vals(self, vals):
        return _('CRN')

    @api.model
    def _is_crn_create_vals(self, vals):
        """True when the record should be created as a Field Service CRN (not a project task)."""
        if self.env.context.get('create_crn') or self.env.context.get('fsm_mode'):
            return True
        if vals.get('is_fsm'):
            return True
        if vals.get('check_fsm'):
            return True
        task_seq = vals.get('task_seq')
        if task_seq and task_seq != '/' and str(task_seq).startswith('CRN'):
            return True
        return False

    @api.model
    def _prepare_fsm_task_vals(self, vals):
        vals = dict(vals)
        is_crn_create = self._is_crn_create_vals(vals)
        if is_crn_create:
            vals['is_fsm'] = True
            vals['check_fsm'] = True
            sequence_date = vals.get('date_start') or fields.Date.context_today(self)
            if not vals.get('task_seq') or vals.get('task_seq') == '/':
                vals['task_seq'] = self._next_task_seq(sequence_date=sequence_date)
            if not vals.get('project_id') and self._cpabooks_should_leave_project_empty():
                vals['project_id'] = False
            vals.setdefault('fsm_creator_uid', self.env.uid)
            vals.pop('user_id', None)
            vals.pop('fsm_assigned_employee_id', None)
            if not vals.get('planned_date_begin'):
                begin, end = self._fsm_default_planned_datetimes()
                vals['planned_date_begin'] = begin
                vals.setdefault('planned_date_end', end)
        if vals.get('complaint_title') and not vals.get('name'):
            complaint_title = self.env['complaint.detail'].browse(vals['complaint_title'])
            vals['name'] = complaint_title.display_name
        if not vals.get('name'):
            vals['name'] = self._default_task_name_from_vals(vals)
        return self._sanitize_fsm_compute_fields_in_vals(vals)

    @api.model
    def _sanitize_fsm_compute_fields_in_vals(self, vals):
        """Drop non-FSM project.task.state values (todo/done/hold) set by other project apps."""
        vals = dict(vals)
        st = vals.get('state')
        if st is not None and st is not False and st not in _FSM_STATE_KEYS:
            vals.pop('state', None)
        sg = vals.get('stage')
        if sg is not None and sg is not False and sg not in _FSM_STAGE_KEYS:
            vals.pop('stage', None)
        return vals

    @api.model
    def _add_missing_default_values(self, values):
        """Strip non-FSM state/stage and bad defaults before create cache."""
        res = super()._add_missing_default_values(values)
        res = self._sanitize_fsm_compute_fields_in_vals(res)
        if self._is_crn_create_vals(values) and self._cpabooks_should_leave_project_empty():
            res['project_id'] = False
        return res

    def _register_hook(self):
        """Drop a default 'todo' state if the registry state selection is FSM-only."""
        super()._register_hook()
        field = self._fields.get('state')
        if not field or not field.default:
            return
        try:
            valid = set(field.get_values(self.env))
        except Exception:
            return
        if valid and 'todo' not in valid:
            field.default = False

    def _search_fsm_stage_progress(self, operator, value):
        def _as_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        def _match(progress):
            progress = _as_float(progress)
            if operator == '=':
                return abs(progress - target) < 0.0001
            if operator == '!=':
                return abs(progress - target) >= 0.0001
            if operator == '>':
                return progress > target
            if operator == '>=':
                return progress >= target
            if operator == '<':
                return progress < target
            if operator == '<=':
                return progress <= target
            if operator == 'in':
                return any(abs(progress - _as_float(item)) < 0.0001 for item in values)
            if operator == 'not in':
                return all(abs(progress - _as_float(item)) >= 0.0001 for item in values)
            return False

        if operator in ('in', 'not in'):
            values = value if isinstance(value, (list, tuple, set)) else [value]
            target = 0.0
        else:
            values = []
            target = _as_float(value)

        if operator not in ('=', '!=', '>', '>=', '<', '<=', 'in', 'not in'):
            return [('id', '=', 0)]

        candidates = self.search(['|', ('is_fsm', '=', True), ('check_fsm', '=', True)])
        matched_ids = candidates.filtered(lambda task: _match(task.fsm_stage_progress)).ids
        return [('id', 'in', matched_ids)]

    @api.depends(
        'parent_id.project_id.subtask_project_id',
        'invoice_id',
        'invoice_id.project_id',
        'qt_no',
        'qt_no.project_id',
        'complaint_type',
    )
    def _compute_project_id(self):
        super()._compute_project_id()
        for task in self:
            if task.invoice_id and 'project_id' in task.invoice_id._fields:
                task.project_id = task.invoice_id.project_id or task._get_project_not_available_fsm_project(task.company_id)
            elif (
                task.complaint_type == 'new_installation'
                and task.qt_no
                and 'project_id' in task.qt_no._fields
                and task.qt_no.project_id
            ):
                task.project_id = task.qt_no.project_id

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            if self._is_crn_create_vals(vals):
                prepared_vals_list.append(self._prepare_fsm_task_vals(vals))
            else:
                vals.setdefault('check_fsm', False)
                vals = self._sanitize_fsm_compute_fields_in_vals(vals)
                if vals.get('complaint_title') and not vals.get('name'):
                    complaint_title = self.env['complaint.detail'].browse(vals['complaint_title'])
                    vals['name'] = complaint_title.display_name
                if not vals.get('name'):
                    vals['name'] = self._default_task_name_from_vals(vals)
                prepared_vals_list.append(vals)
        tasks = super().create(prepared_vals_list)
        for task in tasks:
            if task._is_fsm_crn_task() and not task.fsm_creator_uid:
                task.fsm_creator_uid = task.create_uid or self.env.user
        tasks._normalize_crn_task_seq_values()
        tasks.filtered(lambda t: t._is_fsm_crn_task())._ensure_crn_analytic_account()
        tasks._enable_quotations_for_issue_qt()
        for task in tasks.filtered(lambda t: t.is_fsm):
            payload = json.dumps(sorted(task._fsm_nav_collect_completed_keys()))
            if task.fsm_nav_completed != payload:
                super(ProjectTask, task.with_context(skip_fsm_nav_sync=True)).write({
                    'fsm_nav_completed': payload,
                })
        return tasks

    @api.model
    def _register_hook(self):
        """Related fields overwrite search= with _search_related; restore CRN-aware search."""
        super()._register_hook()
        field = self._fields.get('is_fsm')
        if field is not None:
            field.search = '_search_is_fsm'

    @api.model
    def _cpabooks_all_crn_domain(self):
        """All CRNs list domain: include empty-project CRNs; exclude internal projects.

        Use explicit markers (not only related is_fsm) so lists work even when
        related-field setup overwrote custom search=.
        """
        return [
            '|', '|',
            ('project_id.is_fsm', '=', True),
            ('check_fsm', '=', True),
            ('task_seq', '=like', 'CRN%'),
            '|',
            ('project_id', '=', False),
            ('project_id.is_internal_project', '!=', True),
        ]

    @api.model
    def _cpabooks_non_crn_domain(self):
        """Project → Tasks: hide Field Service CRNs."""
        return [
            '&', '&',
            '|', ('project_id', '=', False), ('project_id.is_fsm', '=', False),
            ('check_fsm', '=', False),
            '!', ('task_seq', '=like', 'CRN%'),
        ]

    @api.model
    def _search_is_fsm(self, operator, value):
        """CRN membership: FSM project OR check_fsm OR CRN% seq (project may be empty).

        Do not call industry_fsm inselect here — related setup normally ignores
        search=, and wrapping inselect in expression.OR breaks domain parsing.
        """
        if operator not in ('=', '!='):
            return [('id', '=', False)]
        positive = (operator == '=' and value) or (operator == '!=' and not value)
        if positive:
            return [
                '|', '|',
                ('project_id.is_fsm', '=', True),
                ('check_fsm', '=', True),
                ('task_seq', '=like', 'CRN%'),
            ]
        return expression.AND([
            ['|', ('project_id', '=', False), ('project_id.is_fsm', '=', False)],
            [('check_fsm', '=', False)],
            ['!', ('task_seq', '=like', 'CRN%')],
        ])

    def _is_fsm_crn_task(self):
        self.ensure_one()
        return bool(
            self.is_fsm
            or self.check_fsm
            or (self.task_seq and str(self.task_seq).startswith('CRN'))
        )

    def action_create_crn_from_task(self):
        """Open a new CRN form linked to this project task (regular task stays unchanged)."""
        self.ensure_one()
        if self._is_fsm_crn_task():
            raise UserError(_('This record is already a CRN. Open it from My CRNs.'))
        fsm_project = self._get_default_fsm_project(self.company_id.id if self.company_id else False)
        ctx = {
            'fsm_mode': True,
            'create_crn': True,
            'default_is_fsm': True,
            'default_check_fsm': True,
            'default_source_task_id': self.id,
            'default_project_id': fsm_project.id if fsm_project else self.project_id.id,
            'default_partner_id': self.partner_id.id if self.partner_id else False,
            'default_name': _('CRN for %s') % (self.task_seq or self.name),
            'show_task_seq': True,
            'show_crn_number': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create CRN'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    @api.model
    def action_create_crn_from_activity(self, activity_id):
        """Create CRN from a scheduled activity linked to a project task."""
        activity = self.env['mail.activity'].browse(activity_id)
        if not activity.exists():
            raise UserError(_('Activity not found.'))
        task = self.browse()
        project = self.env['project.project']
        if activity.res_model == 'project.task' and activity.res_id:
            task = self.browse(activity.res_id).exists()
        elif activity.res_model == 'project.project' and activity.res_id:
            project = project.browse(activity.res_id).exists()
        if task:
            return task.action_create_crn_from_task()
        company = project.company_id or self.env.company
        fsm_project = self._get_default_fsm_project(company.id)
        ctx = {
            'fsm_mode': True,
            'create_crn': True,
            'default_is_fsm': True,
            'default_check_fsm': True,
            'default_project_id': project.id or (fsm_project.id if fsm_project else False),
            'default_name': activity.summary or _('CRN'),
            'show_task_seq': True,
            'show_crn_number': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create CRN'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def write(self, vals):
        vals = self._sanitize_fsm_compute_fields_in_vals(vals)
        if vals.get('complaint_title') and not vals.get('name'):
            complaint_title = self.env['complaint.detail'].browse(vals['complaint_title'])
            vals['name'] = complaint_title.display_name
        # Duplicate / hidden next_action widgets can send False on save while the header state stays
        # in_progress (FOC → WIP). Restore FOC so stage 4 (QTN approved) can move to 5 (WIP).
        if vals.get('next_action') is False and vals.get('state') == 'in_progress':
            if all(task.visited_by and task.visited_date for task in self):
                vals['next_action'] = 'foc'
        old_next_actions = {task.id: task.next_action for task in self.filtered('is_fsm')}
        result = super().write(vals)
        if any(key in vals for key in ('task_seq', 'complaint_title', 'name', 'is_fsm', 'check_fsm')):
            self.filtered(lambda t: t._is_fsm_crn_task())._ensure_crn_analytic_account()
        if 'fsm_assigned_employee_id' in vals:
            self.filtered('is_fsm')._sync_fsm_assignee_user_from_employee()
        if 'next_action' in vals or 'project_id' in vals:
            self._enable_quotations_for_issue_qt()
        if not self.env.context.get('skip_fsm_nav_sync'):
            for task in self.filtered(lambda t: t.is_fsm):
                completed = task._fsm_nav_collect_completed_keys()
                if old_next_actions.get(task.id):
                    completed.add(old_next_actions[task.id])
                payload = json.dumps(sorted(completed))
                if task.fsm_nav_completed != payload:
                    super(ProjectTask, task.with_context(skip_fsm_nav_sync=True)).write({
                        'fsm_nav_completed': payload,
                    })
        return result

    def _fsm_nav_parse_completed(self):
        self.ensure_one()
        if not self.fsm_nav_completed:
            return set()
        try:
            data = json.loads(self.fsm_nav_completed)
            return set(data) if isinstance(data, list) else set()
        except (TypeError, ValueError):
            return set()

    def _fsm_nav_collect_completed_keys(self, vals=None):
        """Build the set of workflow steps already done (flexible order)."""
        self.ensure_one()
        vals = vals or {}
        completed = self._fsm_nav_parse_completed()
        if (vals.get('visited_by') or self.visited_by) and (vals.get('visited_date') or self.visited_date):
            completed.add('site_visit')
        next_action = vals.get('next_action', self.next_action)
        if next_action:
            completed.add(next_action)
        if vals.get('date_end') or self.date_end:
            completed.add('complete')
        if vals.get('select_invoice') or self.select_invoice:
            completed.add('invoice')
        approval_state = vals.get('approval_state', getattr(self, 'approval_state', False))
        if vals.get('approved_by') or self.approved_by or approval_state == 'approved':
            completed.add('approval')
        return completed

    def _get_fsm_workflow_stage_key(self):
        self.ensure_one()
        stage = self.stage or self._get_fsm_stage_value()
        if stage in ('job_completed', 'job_completed_invoiced'):
            return 'waiting_for_invoice'
        return stage if stage in _FSM_WORKFLOW_STAGE_ORDER else 'registered'

    def _get_fsm_workflow_stage_index(self):
        self.ensure_one()
        try:
            return _FSM_WORKFLOW_STAGE_ORDER.index(self._get_fsm_workflow_stage_key())
        except ValueError:
            return 0

    def _fsm_has_created_crn_number(self):
        self.ensure_one()
        return bool(self.task_seq and self.task_seq != '/' and str(self.task_seq).startswith('CRN'))

    def _fsm_has_completed_site_visit(self):
        self.ensure_one()
        return bool(self.visited_by and self.visited_date and self.site_visit)

    def _fsm_has_generated_quotation(self):
        self.ensure_one()
        return bool(self._get_fsm_related_orders_active())

    def _fsm_has_approved_quotation(self):
        self.ensure_one()
        return any(order.state in ('sale', 'done') for order in self._get_fsm_related_orders_active())

    def _fsm_has_completed_invoice(self):
        self.ensure_one()
        if hasattr(self, '_get_fsm_crn_quotation_invoices'):
            invoices = self._get_fsm_crn_quotation_invoices()
        else:
            invoices = self._get_fsm_related_invoices().filtered(
                lambda move: move.move_type == 'out_invoice' and move.state != 'cancel'
            )
        return any(invoice.name and invoice.name != '/' for invoice in invoices)

    def _fsm_has_final_approval(self):
        self.ensure_one()
        return bool(getattr(self, 'approval_state', False) == 'approved' or self.approved_by)

    def _fsm_workflow_stage_is_applicable(self, stage_key):
        self.ensure_one()
        if self.next_action in ('closed', 'foc') and stage_key in (
            'qty_issued',
            'qty_approved',
            'waiting_for_invoice',
        ):
            return False
        if self.next_action == 'closed' and stage_key == 'in_progress':
            return False
        return True

    def _fsm_workflow_stage_is_done(self, stage_key):
        self.ensure_one()
        if not self._fsm_workflow_stage_is_applicable(stage_key):
            return True
        if stage_key == 'registered':
            return self._fsm_has_created_crn_number()
        if stage_key == 'site_visited':
            return self._fsm_has_completed_site_visit()
        if stage_key == 'qty_issued':
            return self._fsm_has_generated_quotation()
        if stage_key == 'qty_approved':
            return self._fsm_has_approved_quotation()
        if stage_key == 'in_progress':
            return bool(self.date_end) or self._fsm_has_completed_invoice()
        if stage_key == 'waiting_for_invoice':
            return self._fsm_has_completed_invoice()
        if stage_key == 'approved':
            return self._fsm_has_final_approval()
        return False

    @api.depends('is_fsm', 'check_fsm', 'fsm_workflow_edit_mode', 'fsm_ui_active_stage', 'complaint_type')
    def _compute_fsm_ui_readonly_flags(self):
        for task in self:
            is_crn = bool(task.is_fsm or task.check_fsm)
            if not is_crn or task.fsm_workflow_edit_mode:
                for index in range(7):
                    task['fsm_stage_%s_readonly' % index] = False
                continue
            active = task.fsm_ui_active_stage or 0
            for index in range(7):
                # Site visit fields are available as soon as complaint type is chosen.
                if index == 1 and task.complaint_type:
                    task['fsm_stage_%s_readonly' % index] = False
                else:
                    task['fsm_stage_%s_readonly' % index] = index != active

    def _fsm_get_ui_active_stage_index(self):
        self.ensure_one()
        active = self.fsm_ui_active_stage or 0
        return max(0, min(active, len(_FSM_WORKFLOW_STAGE_ORDER) - 1))

    def _fsm_stage0_pending_checklist_labels(self):
        """Pending registration checklist rows (before force-close)."""
        self.ensure_one()
        labels = []
        for section in self._fsm_workflow_sidebar_sections():
            if section.get('stage_key') != 'registered':
                continue
            for _block_title, items in section['blocks']:
                for item_key, item_label in items:
                    if not self._fsm_workflow_item_is_applicable(item_key):
                        continue
                    if self._fsm_workflow_item_is_done(item_key):
                        continue
                    serial = _FSM_WORKFLOW_ITEM_SERIALS.get(item_key)
                    if serial:
                        labels.append('%s. %s' % (serial, item_label))
                    else:
                        labels.append(item_label)
        return labels

    def action_fsm_stage0_close_wizard(self):
        """Open confirm dialog listing pending registration items."""
        self.ensure_one()
        if not self.is_fsm and not self.check_fsm:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Close Stage 1 — Registration'),
            'res_model': 'cpabooks.fsm.stage0.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
            },
        }

    def action_fsm_stage0_confirm_close(self):
        """Mark registration 100% complete and advance to site visit."""
        self.ensure_one()
        if not self.is_fsm and not self.check_fsm:
            return False
        next_stage = min(1, len(_FSM_WORKFLOW_STAGE_ORDER) - 1)
        self.write({
            'fsm_stage0_force_complete': True,
            'fsm_ui_active_stage': next_stage,
            'fsm_workflow_edit_mode': False,
            'fsm_show_pending_banner': True,
        })
        if hasattr(self.env, '_cpabooks_fsm_perf_cache'):
            self.env._cpabooks_fsm_perf_cache = {'orders': {}, 'checks_map': {}}
        return self._fsm_workflow_reload_form_action()

    def _fsm_workflow_stage_missing_items(self, stage_index):
        self.ensure_one()
        if stage_index == 0 and self.fsm_stage0_force_complete:
            return []
        ctype = self.complaint_type
        missing = []
        if stage_index == 0:
            checks = [
                (self.partner_id, _('Customer')),
                (self.site_location, _('Site Location')),
                (self.client_person, _('Contact Person')),
                (self.client_contact, _('Contact Number')),
                (self.client_email, _('Email ID')),
                (ctype, _('Complaint Type')),
                (self.complaint_title, _('Complaint Title')),
                (self.deadline, _('Date Deadline')),
                (self.importance, _('Priority')),
                (self.total_print_row, _('Total Print Row')),
            ]
            if ctype in ('amc', 'others', 'warranty', 'service'):
                checks.extend([
                    (self.invoice_id, _('Reference Invoice Number')),
                    (self.item_des, _('Invoice Line')),
                ])
            elif ctype == 'new_installation':
                checks.append((
                    self.qt_no or (self.qt_no_text or '').strip(),
                    _('Reference Quotation Number'),
                ))
        elif stage_index == 1:
            checks = [
                (self.visited_by, _('Visited By')),
                (self.visited_date, _('Visited Date')),
                (self.site_visit, _('Site Visit Remarks')),
            ]
        elif stage_index == 2:
            checks = []
            if self.next_action in ('issue', 'foc'):
                checks.extend([
                    (self.fsm_assigned_employee_id, _('Assigned to')),
                    (self.assign_date, _('Assign Date')),
                ])
        elif stage_index == 3:
            checks = [(self.date_end, _('End Date'))]
        elif stage_index == 4:
            checks = []
            if self.next_action == 'issue':
                checks.append((self.select_invoice, _('Invoice Issued')))
        elif stage_index == 5:
            checks = [(self.closing_remarks, _('Closing Remarks'))]
        else:
            checks = []
        for value, label in checks:
            if not value:
                missing.append(label)
        return missing

    def _fsm_workflow_first_incomplete_stage(self):
        self.ensure_one()
        for index in range(len(_FSM_WORKFLOW_STAGE_ORDER)):
            if self._fsm_workflow_stage_missing_items(index):
                return index
        return len(_FSM_WORKFLOW_STAGE_ORDER) - 1

    def action_fsm_workflow_edit_step(self):
        """Legacy hook — standard Edit no longer calls this."""
        self.ensure_one()
        return False

    def action_fsm_workflow_edit(self):
        """Unlock every workflow stage for editing (FULL EDIT)."""
        self.filtered(lambda task: task.is_fsm or task.check_fsm).write({
            'fsm_workflow_edit_mode': True,
        })
        return False

    def action_fsm_workflow_full_edit(self):
        """Header/control-panel alias for full-stage edit."""
        return self.action_fsm_workflow_edit()

    def action_fsm_workflow_next(self):
        """Handled client-side: scroll/highlight next pending checklist field."""
        self.ensure_one()
        return False

    def action_fsm_workflow_what_to_do(self):
        """Alias kept for API clarity; WHAT TO DO dialog is handled client-side."""
        self.ensure_one()
        return False

    def action_fsm_dismiss_pending_banner(self):
        """Handled client-side: open WHAT TO DO pending checklist dialog."""
        self.ensure_one()
        return False

    def _fsm_workflow_reload_form_action(self):
        self.ensure_one()
        action = self.env.ref('industry_fsm.project_task_action_fsm').read()[0]
        action['views'] = [(False, 'form')]
        action['res_id'] = self.id
        action['target'] = 'current'
        ctx = dict(self.env.context)
        ctx.update({
            'fsm_mode': True,
            'cpabooks_fsm_focus_stage': self.fsm_ui_active_stage,
        })
        action['context'] = ctx
        return action

    def _get_fsm_related_orders_active(self):
        self.ensure_one()
        return self._get_fsm_related_orders().filtered(lambda o: o.state != 'cancel')

    def _fsm_workflow_has_attachments(self):
        self.ensure_one()
        messages = self.message_ids.filtered(lambda m: m.attachment_ids)
        return bool(messages)

    def _fsm_workflow_item_checks_map(self):
        self.ensure_one()
        orders = self._get_fsm_related_orders_active()
        has_qtn_draft = any(o.state in ('draft', 'sent') for o in orders)
        has_qtn_confirmed = any(o.state in ('sale', 'done') for o in orders)
        invoices = self._get_fsm_related_invoices().filtered(
            lambda m: m.state != 'cancel' and m.move_type == 'out_invoice',
        )
        posted_invoice = any(inv.state == 'posted' for inv in invoices)
        visit_done = bool(self.visited_by and self.visited_date)
        site_visit_done = self._fsm_has_completed_site_visit()
        ctype = self.complaint_type
        invoice_types = ('amc', 'others', 'warranty', 'service')
        approval_state = getattr(self, 'approval_state', False)

        return {
            's1_crn': bool(self.task_seq and self.task_seq != '/'),
            's1_create_date': bool(self.create_date),
            's1_created_by': bool(self.fsm_creator_uid or self.create_uid),
            's1_customer': bool(self.partner_id),
            's1_site': bool(self.site_location),
            's1_contact': bool(self.client_person),
            's1_phone': bool(self.client_contact),
            's1_email': bool(self.client_email),
            's1_complaint_type': bool(ctype),
            's1_invoice_type': bool(self.invoice_type) if ctype in invoice_types else None,
            's1_project': bool(self.project_id),
            's1_repeated': bool(self._get_prior_crn_task_seqs()),
            's1_title': bool(self.complaint_title),
            's1_details': None,
            's1_deadline': bool(self.deadline),
            's1_priority': bool(self.importance),
            's1_print_rows': bool(self.total_print_row),
            's1_old_invoice': bool(self.invoice_id) if ctype in invoice_types else None,
            's1_invoice_line': bool(self.item_des) if ctype in invoice_types else None,
            's1_qtn': bool(self.qt_no or (self.qt_no_text or '').strip()) if ctype == 'new_installation' else None,
            's1_no_ref': ctype in ('new_inquiry', 'site_visit') if ctype else False,
            's2_visited_by': bool(self.visited_by),
            's2_visit_date': bool(self.visited_date),
            's2_remarks': bool(self.site_visit),
            's2_next_action': site_visit_done or bool(self.next_action),
            's2_close': self.next_action == 'closed',
            's2_issue_qtn': self.next_action in ('issue', 'foc'),
            's3_create_qtn': has_qtn_draft or has_qtn_confirmed,
            's3_add_products': any(o.order_line for o in orders),
            's3_material_cost': bool(self.material_cost_total) or bool(self.material_line_ids),
            's3_terms': any((o.note or '').strip() for o in orders),
            's3_send_qtn': has_qtn_draft and any(o.state == 'sent' for o in orders),
            's3_email_print': has_qtn_draft,
            's3_client_confirms': has_qtn_confirmed,
            's3_sales_order': has_qtn_confirmed,
            's3_assign_tech': bool(self.fsm_assigned_employee_id),
            's3_assign_date': bool(self.assign_date),
            's3_wip': self._get_fsm_workflow_stage_key() in ('in_progress', 'waiting_for_invoice', 'approved') or bool(self.date_end),
            's3_job_complete': bool(self.date_end),
            's3_invoice_created': bool(self.select_invoice) or bool(invoices),
            's3_admin_approval': approval_state in ('approved', 'pending') or bool(self.approved_by),
            's4_client_approved': has_qtn_confirmed,
            's4_client_rejected': approval_state == 'rejected',
            's4_need_revision': has_qtn_draft and not has_qtn_confirmed and visit_done,
            's4_approval_date': bool(getattr(self, 'approval_request_id', False)),
            's4_approval_remarks': bool(
                getattr(self, 'approval_request_id', False)
                and self.approval_request_id.approval_note
            ),
            's4_documents': bool(getattr(self, 'approval_request_id', False)),
            's4_to_wip': self._get_fsm_workflow_stage_index() >= 4,
            's4_notify_staff': bool(self.fsm_assigned_employee_id) and self._get_fsm_workflow_stage_index() >= 4,
            's5_assign_to': bool(self.fsm_assigned_employee_id),
            's5_assign_date': bool(self.assign_date),
            's5_wip': self._get_fsm_workflow_stage_key() in ('in_progress', 'waiting_for_invoice', 'approved'),
            's5_timesheet': bool(self.timesheet_ids),
            's5_material': bool(self.material_line_ids),
            's5_end_date': bool(self.date_end),
            's5_completion_remarks': bool(self.closing_remarks),
            's5_photos': self._fsm_workflow_has_attachments(),
            's5_service_details': bool(self.complaint_details or self.site_visit),
            's5_route_invoice': bool(self.select_invoice) or self.next_action == 'issue',
            's5_route_foc': self.next_action == 'foc' or self.work_completion == 'foc',
            's6_generate_invoice': bool(invoices),
            's6_add_items': bool(invoices) and any(inv.invoice_line_ids for inv in invoices),
            's6_verify_amount': bool(invoices),
            's6_post_invoice': posted_invoice,
            's6_email_print_inv': posted_invoice,
            's6_link_invoice': bool(self.select_invoice),
            's6_final_approval_route': self._get_fsm_workflow_stage_index() >= 6,
            's7_approval_status': approval_state == 'approved' or bool(self.approved_by),
            's7_approved_by': bool(self.approved_by),
            's7_approval_date': bool(self.approved_by),
            's7_closing_remarks': bool(self.closing_remarks),
            's7_resolution': bool(self.closing_remarks or self.complaint_details),
            's7_feedback': bool(self.remarks),
            's7_final_status': self._get_fsm_workflow_stage_key() == 'approved',
            's7_process_done': self._get_fsm_workflow_stage_key() == 'approved',
        }

    def _cpabooks_fsm_record_cache_key(self):
        """Stable cache key for this task during one ORM request/compute cycle."""
        self.ensure_one()
        record_id = self.id
        if isinstance(record_id, int):
            return ('id', record_id)
        origin = getattr(self, '_origin', None)
        if origin and origin.id:
            return ('id', origin.id)
        return ('new', id(self))

    def _cpabooks_fsm_env_cache(self):
        cache = getattr(self.env, '_cpabooks_fsm_perf_cache', None)
        if cache is None:
            cache = {'orders': {}, 'checks_map': {}}
            self.env._cpabooks_fsm_perf_cache = cache
        return cache

    def _fsm_workflow_get_checks_map(self):
        self.ensure_one()
        cache_key = self._cpabooks_fsm_record_cache_key()
        checks_cache = self._cpabooks_fsm_env_cache()['checks_map']
        if cache_key not in checks_cache:
            checks_cache[cache_key] = self._fsm_workflow_item_checks_map()
        return checks_cache[cache_key]

    def _fsm_workflow_item_check_value(self, item_key):
        self.ensure_one()
        return self._fsm_workflow_get_checks_map().get(item_key)

    def _fsm_workflow_item_is_applicable(self, item_key):
        self.ensure_one()
        return self._fsm_workflow_item_check_value(item_key) is not None

    def _fsm_workflow_item_is_done(self, item_key):
        self.ensure_one()
        result = self._fsm_workflow_item_check_value(item_key)
        if result is None:
            return False
        return bool(result)

    def _fsm_workflow_checklist_item_keys(self):
        self.ensure_one()
        keys = []
        for section in self._fsm_workflow_sidebar_sections():
            for _block_title, items in section['blocks']:
                for item_key, _label in items:
                    keys.append(item_key)
        return keys

    def _fsm_workflow_collect_pending_serials(self):
        """Pending checklist serial numbers in workflow order (form field numbers)."""
        self.ensure_one()
        checks = self._fsm_workflow_get_checks_map()
        serials = []
        seen = set()
        for item_key in self._fsm_workflow_checklist_item_keys():
            check_value = checks.get(item_key)
            if check_value is None or check_value:
                continue
            serial = _FSM_WORKFLOW_ITEM_SERIALS.get(item_key)
            if not serial:
                continue
            serial_text = str(serial)
            if serial_text in seen:
                continue
            seen.add(serial_text)
            serials.append(serial_text)
        return serials

    def _fsm_workflow_pending_serials(self, limit=5):
        """Next pending checklist serial numbers in workflow order."""
        self.ensure_one()
        serials = self._fsm_workflow_collect_pending_serials()
        if limit:
            return serials[:limit]
        return serials

    def _fsm_workflow_pending_serials_compact_text(self, preview_limit=5):
        """e.g. '12, 14, 15, 16' or '12, 14, 15, 16, ...' when more pending items exist."""
        self.ensure_one()
        serials = self._fsm_workflow_collect_pending_serials()
        if not serials:
            return ''
        preview = serials[:preview_limit]
        suffix = ', ...' if len(serials) > preview_limit else ''
        return '%s%s' % (', '.join(preview), suffix)

    def _fsm_workflow_next_hint_text(self, limit=5):
        self.ensure_one()
        serials = self._fsm_workflow_pending_serials(limit=limit)
        if not serials:
            return _('All checklist items complete.')
        return _('Next go to sr %s') % ', '.join(serials)

    def _fsm_workflow_pending_items_by_stage(self):
        """Return pending checklist rows grouped by stage title."""
        self.ensure_one()
        checks = self._fsm_workflow_get_checks_map()
        grouped = []
        for section in self._fsm_workflow_sidebar_sections():
            pending_labels = []
            for _block_title, items in section['blocks']:
                for item_key, item_label in items:
                    check_value = checks.get(item_key)
                    if check_value is None or check_value:
                        continue
                    serial = _FSM_WORKFLOW_ITEM_SERIALS.get(item_key)
                    label = '%s. %s' % (serial, item_label) if serial else item_label
                    pending_labels.append(label)
            if pending_labels:
                grouped.append((section['title'], pending_labels))
        return grouped

    def _fsm_workflow_immediate_action_text(self, grouped=None):
        """Lead line for the NEXT banner — same first pending item as the sidebar list."""
        self.ensure_one()
        if grouped is None:
            grouped = self._fsm_workflow_pending_items_by_stage()
        if grouped:
            return _('Next: %s') % grouped[0][1][0]
        suggested = self.fsm_nav_suggested_label or ''
        if suggested:
            return _('Suggested: %s') % suggested
        return _('All checklist items are complete.')

    def _fsm_workflow_render_pending_stages_html(self, grouped=None):
        """Shared pending checklist HTML for banner and sidebar accordion."""
        self.ensure_one()
        if grouped is None:
            grouped = self._fsm_workflow_pending_items_by_stage()
        if not grouped:
            return Markup(
                '<p class="cpabooks_fsm_pending_empty">%s</p>'
                % _('All checklist items are complete.')
            )
        parts = []
        for stage_title, labels in grouped:
            parts.append(
                '<div class="cpabooks_fsm_pending_stage"><strong>%s</strong><ul>' % stage_title
            )
            for label in labels:
                parts.append('<li>%s</li>' % label)
            parts.append('</ul></div>')
        return Markup(''.join(parts))

    def _fsm_workflow_render_pending_banner_html(self):
        self.ensure_one()
        grouped = self._fsm_workflow_pending_items_by_stage()
        immediate = self._fsm_workflow_immediate_action_text(grouped)
        parts = [
            '<div class="cpabooks_fsm_pending_banner">',
            '<div class="cpabooks_fsm_pending_banner_title">', _('What to do now'), '</div>',
            '<div class="cpabooks_fsm_pending_banner_lead">', immediate, '</div>',
            '<div class="cpabooks_fsm_pending_banner_body">',
        ]
        parts.append(self._fsm_workflow_render_pending_stages_html(grouped))
        parts.append('</div></div>')
        return Markup(''.join(parts))

    def _fsm_workflow_render_pending_activities_html(self):
        self.ensure_one()
        grouped = self._fsm_workflow_pending_items_by_stage()
        parts = [
            '<details class="cpabooks_fsm_pending_accordion">',
            '<summary class="cpabooks_fsm_pending_accordion_title">', _('PENDING Activities'), '</summary>',
            '<div class="cpabooks_fsm_pending_accordion_body">',
        ]
        parts.append(self._fsm_workflow_render_pending_stages_html(grouped))
        parts.append('</div></details>')
        return Markup(''.join(parts))

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'partner_id',
        'complaint_type',
        'complaint_title',
        'visited_by',
        'visited_date',
        'next_action',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'fsm_ui_active_stage',
        'invoice_id',
        'qt_no',
        'item_des',
        'is_fsm',
        'check_fsm',
    )
    def _compute_fsm_pending_banner_html(self):
        for task in self:
            if task.is_fsm or task.check_fsm:
                task.fsm_pending_banner_html = task._fsm_workflow_render_pending_stages_html()
            else:
                task.fsm_pending_banner_html = False

    @api.depends(
        'fsm_nav_completed',
        'fsm_stage_progress',
        'task_seq',
        'partner_id',
        'complaint_type',
        'complaint_title',
        'visited_by',
        'visited_date',
        'next_action',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'fsm_ui_active_stage',
        'invoice_id',
        'qt_no',
        'item_des',
        'is_fsm',
        'check_fsm',
    )
    def _compute_fsm_workflow_ribbon_status(self):
        for task in self:
            if not (task.is_fsm or task.check_fsm):
                task.fsm_workflow_ribbon_status = False
                continue
            compact = task._fsm_workflow_pending_serials_compact_text(preview_limit=5)
            pending_part = compact or _('none')
            pct = int(round(task.fsm_stage_progress or 0.0))
            task.fsm_workflow_ribbon_status = _('Pending: %s | %s%%') % (pending_part, pct)

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'partner_id',
        'complaint_type',
        'complaint_title',
        'visited_by',
        'visited_date',
        'next_action',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'fsm_ui_active_stage',
        'invoice_id',
        'qt_no',
        'item_des',
    )
    def _compute_fsm_workflow_pending_serials_display(self):
        for task in self:
            if not (task.is_fsm or task.check_fsm):
                task.fsm_workflow_pending_serials_display = False
                continue
            compact = task._fsm_workflow_pending_serials_compact_text(preview_limit=5)
            task.fsm_workflow_pending_serials_display = compact or ''

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'partner_id',
        'complaint_type',
        'complaint_title',
        'visited_by',
        'visited_date',
        'next_action',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'fsm_ui_active_stage',
        'invoice_id',
        'qt_no',
        'item_des',
        'is_fsm',
        'check_fsm',
    )
    def _compute_fsm_workflow_pending_ribbon_text(self):
        for task in self:
            if not (task.is_fsm or task.check_fsm):
                task.fsm_workflow_pending_ribbon_text = ''
                continue
            serials = task._fsm_workflow_pending_serials(limit=5)
            task.fsm_workflow_pending_ribbon_text = (
                'pending %s' % ', '.join(serials) if serials else ''
            )

    def _get_fsm_workflow_checklist_progress(self):
        """Progress is based on Stage 1-6 completion; approval does not reduce 100%."""
        self.ensure_one()
        stage_keys = [
            stage_key for stage_key in _FSM_WORKFLOW_STAGE_ORDER[:6]
            if self._fsm_workflow_stage_is_applicable(stage_key)
        ]
        total = len(stage_keys)
        done = sum(1 for stage_key in stage_keys if self._fsm_workflow_stage_is_done(stage_key))
        if not total:
            return 0.0
        return round(100.0 * done / total, 2)

    def _get_crn_analytic_account_name(self):
        self.ensure_one()
        crn = self.task_seq if self.task_seq and self.task_seq != '/' else _('New CRN')
        title = ''
        if self.complaint_title:
            title = self.complaint_title.display_name
        elif self.name and self.name != self._default_task_name_from_vals({}):
            title = self.name
        return '%s - %s' % (crn, title) if title else crn

    def _ensure_crn_analytic_account(self):
        analytic_model = self.env['account.analytic.account'].sudo()
        for task in self.filtered(lambda rec: rec._is_fsm_crn_task()):
            account_name = task._get_crn_analytic_account_name()
            company = task.company_id or self.env.company
            if task.analytic_account_id:
                if task.analytic_account_id.name != account_name:
                    task.analytic_account_id.sudo().write({'name': account_name})
                continue
            task.sudo().write({
                'analytic_account_id': analytic_model.create({
                    'name': account_name,
                    'company_id': company.id,
                }).id,
            })

    def _fsm_workflow_sidebar_sections(self):
        """Checklist sections per stage (right panel)."""
        self.ensure_one()
        return [
            {
                'stage_key': 'registered',
                'title': _('STAGE 1 — CRN NUMBER CREATED'),
                'css': 'cpabooks_fsm_side_orange',
                'blocks': [
                    (_('i. Basic Details (Auto)'), [
                        ('s1_crn', _('CRN (Auto Generated)')),
                        ('s1_create_date', _('CRN Creation Date (Auto)')),
                        ('s1_created_by', _('Created By (Auto)')),
                    ]),
                    (_('ii. Enter Customer Details'), [
                        ('s1_customer', _('Customer Name')),
                        ('s1_site', _('Site Location')),
                        ('s1_contact', _('Contact Person')),
                        ('s1_phone', _('Contact Number')),
                        ('s1_email', _('Email ID')),
                    ]),
                    (_('iii. Select Complaint Type'), [
                        ('s1_complaint_type', _('Complaint Type Selected')),
                    ]),
                    (_('iv. Additional Complaint Information'), [
                        ('s1_repeated', _('CRN Repeated Complaint / Service (Auto)')),
                        ('s1_title', _('Complaint Title')),
                        ('s1_deadline', _('Deadline')),
                        ('s1_priority', _('Priority')),
                        ('s1_print_rows', _('Total Print Rows')),
                    ]),
                    (_('v. Action Based on Selection'), [
                        ('s1_old_invoice', _('Select Old Invoice')),
                        ('s1_invoice_line', _('Select Line Item from Invoice')),
                        ('s1_qtn', _('Select QTN')),
                        ('s1_no_ref', _('No Reference Required')),
                    ]),
                ],
            },
            {
                'stage_key': 'site_visited',
                'title': _('STAGE 2 — SITE VISIT'),
                'css': 'cpabooks_fsm_side_green',
                'blocks': [
                    (_('i. Site Visit Details'), [
                        ('s2_visited_by', _('Visited By')),
                        ('s2_visit_date', _('Visit Date')),
                        ('s2_remarks', _('Site Visit Remarks')),
                    ]),
                    (_('ii. Next Action After Site Visit'), [
                        ('s2_next_action', _('Next Action Selected')),
                        ('s2_close', _('Close Complaint')),
                        ('s2_issue_qtn', _('Issue QTN / F.O.C')),
                    ]),
                ],
            },
            {
                'stage_key': 'qty_issued',
                'title': _('STAGE 3 — QUOTATION ISSUED'),
                'css': 'cpabooks_fsm_side_blue',
                'blocks': [
                    (_('i. Create QTN'), [
                        ('s3_create_qtn', _('Create New Quotation')),
                        ('s3_add_products', _('Add Products / Services')),
                        ('s3_material_cost', _('Add Material Cost')),
                        ('s3_terms', _('Add Terms & Conditions')),
                    ]),
                    (_('ii. QTN Issued'), [
                        ('s3_send_qtn', _('Send Quotation to Client')),
                        ('s3_email_print', _('Email / Print QTN')),
                    ]),
                    (_('iii. Client Approval'), [
                        ('s3_client_confirms', _('Customer Confirms Quotation')),
                        ('s3_sales_order', _('Sales Order Created')),
                    ]),
                    (_('iv. Assign Staff'), [
                        ('s3_assign_tech', _('Assign Technician')),
                        ('s3_assign_date', _('Assign Date')),
                    ]),
                    (_('v. Work In Progress'), [
                        ('s3_wip', _('Job Work In Progress')),
                    ]),
                    (_('vi. Job Completion'), [
                        ('s3_job_complete', _('End Date')),
                    ]),
                    (_('vii. Invoice Generated'), [
                        ('s3_invoice_created', _('Invoice Created After Job')),
                    ]),
                    (_('viii. Admin Approval'), [
                        ('s3_admin_approval', _('Final Admin Approval')),
                    ]),
                ],
            },
            {
                'stage_key': 'qty_approved',
                'title': _('STAGE 4 — QUOTATION APPROVED'),
                'css': 'cpabooks_fsm_side_purple',
                'blocks': [
                    (_('i. Client Approval Status'), [
                        ('s4_client_approved', _('Approved')),
                        ('s4_client_rejected', _('Rejected')),
                        ('s4_need_revision', _('Need Revision')),
                    ]),
                    (_('ii. Approval Details'), [
                        ('s4_approval_date', _('Approval Date')),
                        ('s4_approval_remarks', _('Approval Remarks')),
                        ('s4_documents', _('Supporting Documents')),
                    ]),
                    (_('iii. System Action'), [
                        ('s4_to_wip', _('Change Stage → WIP')),
                        ('s4_notify_staff', _('Notify Assigned Staff')),
                    ]),
                ],
            },
            {
                'stage_key': 'in_progress',
                'title': _('STAGE 5 — WORK IN PROGRESS'),
                'css': 'cpabooks_fsm_side_teal',
                'blocks': [
                    (_('i. Assign Staff'), [
                        ('s5_assign_to', _('Assign To')),
                        ('s5_assign_date', _('Assign Date')),
                    ]),
                    (_('ii. Work In Progress'), [
                        ('s5_wip', _('Job Work In Progress')),
                        ('s5_timesheet', _('Add Timesheet')),
                        ('s5_material', _('Material Consumption')),
                    ]),
                    (_('iii. Job Completion'), [
                        ('s5_end_date', _('End Date')),
                        ('s5_completion_remarks', _('Completion Remarks')),
                    ]),
                    (_('iv. Update Work Details'), [
                        ('s5_photos', _('Photos / Attachments')),
                        ('s5_service_details', _('Service Details')),
                    ]),
                    (_('v. Next Route'), [
                        ('s5_route_invoice', _('Invoice Required → Invoice Stage')),
                        ('s5_route_foc', _('F.O.C → F.O.C Completed')),
                    ]),
                ],
            },
            {
                'stage_key': 'waiting_for_invoice',
                'title': _('STAGE 6 — INVOICE'),
                'css': 'cpabooks_fsm_side_yellow',
                'blocks': [
                    (_('i. Create Invoice'), [
                        ('s6_generate_invoice', _('Generate Invoice')),
                        ('s6_add_items', _('Add Items')),
                        ('s6_verify_amount', _('Verify Amount')),
                    ]),
                    (_('ii. Invoice Issued'), [
                        ('s6_post_invoice', _('Post Invoice')),
                        ('s6_email_print_inv', _('Email / Print Invoice')),
                    ]),
                    (_('iii. Invoice Linked'), [
                        ('s6_link_invoice', _('Link Invoice Reference to CRN')),
                    ]),
                    (_('iv. Approval Route'), [
                        ('s6_final_approval_route', _('Move to Final Approval')),
                    ]),
                ],
            },
            {
                'stage_key': 'approved',
                'title': _('STAGE 7 — APPROVAL / CLOSE'),
                'css': 'cpabooks_fsm_side_pink',
                'blocks': [
                    (_('i. Final Approval'), [
                        ('s7_approval_status', _('Approval Status')),
                        ('s7_approved_by', _('Approved By')),
                        ('s7_approval_date', _('Approval Date')),
                    ]),
                    (_('ii. Close Complaint'), [
                        ('s7_closing_remarks', _('Closing Remarks')),
                        ('s7_resolution', _('Resolution Details')),
                        ('s7_feedback', _('Customer Feedback')),
                    ]),
                    (_('iii. Final Status'), [
                        ('s7_final_status', _('Approved / Closed')),
                    ]),
                    (_('iv. Process Completed'), [
                        ('s7_process_done', _('End of Workflow')),
                    ]),
                ],
            },
        ]

    def _fsm_workflow_render_check_item(self, item_key, label):
        done = self._fsm_workflow_item_is_done(item_key)
        icon = 'fa-check-circle' if done else 'fa-circle-o'
        state = 'done' if done else 'pending'
        serial = _FSM_WORKFLOW_ITEM_SERIALS.get(item_key)
        if serial:
            label = '%s. %s' % (serial, label)
            item_css = 'cpabooks_fsm_check_numbered'
        elif item_key in _FSM_WORKFLOW_OPTION_KEYS:
            item_css = 'cpabooks_fsm_check_option'
        else:
            item_css = 'cpabooks_fsm_check_workflow'
        return (
            '<li class="cpabooks_fsm_check_item cpabooks_fsm_check_%s %s">'
            '<i class="fa %s" aria-hidden="true"></i>'
            '<span>%s</span></li>'
        ) % (state, item_css, icon, label)

    def _fsm_workflow_render_sidebar_html(self):
        self.ensure_one()
        ui_index = self._fsm_get_ui_active_stage_index()
        parts = [
            '<div class="cpabooks_fsm_sidebar_inner">',
            '<div class="cpabooks_fsm_sidebar_title">CRM / COMPLAINT WORKFLOW</div>',
            '<div class="cpabooks_fsm_sidebar_sub">', _('Follow the stages to complete this CRN.'), '</div>',
        ]
        for section in self._fsm_workflow_sidebar_sections():
            try:
                stage_index = _FSM_WORKFLOW_STAGE_ORDER.index(section['stage_key'])
            except ValueError:
                stage_index = 0
            if self._fsm_workflow_stage_is_done(section['stage_key']):
                stage_status = _('Done')
                stage_status_css = 'cpabooks_fsm_stage_done'
            elif stage_index == ui_index:
                stage_status = _('Pending')
                stage_status_css = 'cpabooks_fsm_stage_current'
            else:
                stage_status = _('Pending')
                stage_status_css = 'cpabooks_fsm_stage_pending'
            open_attr = ' open' if stage_index == ui_index else ''
            parts.append(
                '<details class="cpabooks_fsm_stage_accordion %s %s"%s>'
                '<summary class="cpabooks_fsm_stage_head %s">'
                '<span class="cpabooks_fsm_stage_head_title">%s</span>'
                '<span class="cpabooks_fsm_stage_head_status %s">%s</span>'
                '</summary><div class="cpabooks_fsm_stage_body">'
                % (
                    section['css'],
                    stage_status_css,
                    open_attr,
                    section['css'],
                    section['title'],
                    stage_status_css,
                    stage_status,
                )
            )
            for block_title, items in section['blocks']:
                block_css = section['css'].replace('cpabooks_fsm_side_', 'cpabooks_fsm_block_')
                parts.append(
                    '<div class="cpabooks_fsm_block_title cpabooks_fsm_block_roman %s">%s</div>'
                    '<ul class="cpabooks_fsm_check_list">' % (block_css, block_title)
                )
                for item_key, item_label in items:
                    parts.append(self._fsm_workflow_render_check_item(item_key, item_label))
                parts.append('</ul>')
            parts.append('</div></details>')
        parts.append(self._fsm_workflow_render_pending_activities_html())
        parts.append('</div>')
        return Markup(''.join(parts))

    def _fsm_workflow_progress_status_text(self, stage_key, stage_index, current_index):
        self.ensure_one()
        return _('Done') if self._fsm_workflow_stage_is_done(stage_key) else _('Pending')

    def _fsm_workflow_render_progress_html(self):
        self.ensure_one()
        ui_index = self._fsm_get_ui_active_stage_index()
        business_index = self._get_fsm_workflow_stage_index()
        parts = ['<div class="cpabooks_fsm_chevron_track" data-active-stage="%s">' % ui_index]
        total = len(_FSM_WORKFLOW_PROGRESS_LABELS)
        for index, (stage_key, label, css) in enumerate(_FSM_WORKFLOW_PROGRESS_LABELS):
            if index < ui_index:
                step_css = css + ' cpabooks_fsm_chev_done'
            elif index == ui_index:
                step_css = css + ' cpabooks_fsm_chev_current'
            else:
                step_css = css + ' cpabooks_fsm_chev_pending'
            if index < business_index:
                step_css += ' cpabooks_fsm_chev_business_done'
            status = self._fsm_workflow_progress_status_text(stage_key, index, ui_index)
            chev_class = 'cpabooks_fsm_chevron'
            if index:
                chev_class += ' cpabooks_fsm_chevron_not_first'
            if index == total - 1:
                chev_class += ' cpabooks_fsm_chevron_last'
            parts.append(
                '<div class="%s" data-stage-index="%s">'
                '<div class="%s">'
                '<span class="cpabooks_fsm_chev_label">%s</span>'
                '<span class="cpabooks_fsm_chev_status">%s</span>'
                '</div></div>'
                % (chev_class, index, step_css, label, status)
            )
        parts.append('</div>')
        return Markup(''.join(parts))

    def _fsm_workflow_render_banner_html(self):
        self.ensure_one()
        ui_index = self._fsm_get_ui_active_stage_index()
        stage_key = _FSM_WORKFLOW_STAGE_ORDER[ui_index]
        title, css = _FSM_WORKFLOW_BANNER.get(stage_key, _FSM_WORKFLOW_BANNER['registered'])
        return Markup(
            '<div class="cpabooks_fsm_stage_banner cpabooks_fsm_stage_banner_text_only %s">'
            '<span>%s</span></div>' % (css, title)
        )

    def _fsm_workflow_suggested_nav_key(self):
        self.ensure_one()
        completed = self._fsm_nav_collect_completed_keys()
        for key, _label in _FSM_NAV_STEPS:
            if key not in completed:
                return key
        return None

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'create_date',
        'fsm_creator_uid',
        'partner_id',
        'site_location',
        'client_person',
        'client_contact',
        'client_email',
        'complaint_type',
        'crn_done_before',
        'complaint_title',
        'complaint_details',
        'deadline',
        'importance',
        'total_print_row',
        'invoice_id',
        'item_des',
        'qt_no',
        'visited_by',
        'visited_date',
        'site_visit',
        'next_action',
        'fsm_assigned_employee_id',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'remarks',
        'work_completion',
        'material_line_ids',
        'timesheet_ids',
        'material_cost_total',
        'stage',
        'state',
        'is_fsm',
        'check_fsm',
        'message_ids',
        'fsm_ui_active_stage',
        'fsm_workflow_edit_mode',
    )
    def _compute_fsm_workflow_ui(self):
        for task in self:
            if not task.is_fsm and not task.check_fsm:
                task.fsm_action_nav_html = False
                task.fsm_workflow_progress_html = False
                task.fsm_stage_banner_html = False
                task.fsm_nav_suggested_label = False
                continue
            task.fsm_workflow_progress_html = False
            task.fsm_stage_banner_html = task._fsm_workflow_render_banner_html()
            task.fsm_action_nav_html = task._fsm_workflow_render_sidebar_html()
            task.fsm_nav_suggested_label = False

    def _enable_quotations_for_issue_qt(self):
        projects = self.filtered(lambda task: task.next_action == 'issue').mapped('project_id')
        projects.filtered(lambda project: project and not project.allow_quotations).sudo().write({
            'allow_quotations': True,
        })

    def _sync_fsm_assignee_user_from_employee(self):
        for task in self:
            if task.fsm_assigned_employee_id:
                task.user_id = task.fsm_assigned_employee_id.user_id
            elif task._is_fsm_crn_task():
                task.user_id = False

    @api.onchange('fsm_assigned_employee_id')
    def _onchange_fsm_assigned_employee_id(self):
        for rec in self:
            if rec.fsm_assigned_employee_id:
                rec.user_id = rec.fsm_assigned_employee_id.user_id
            else:
                rec.user_id = False

    @api.onchange('next_action')
    def _onchange_next_action_clear_assignee(self):
        for rec in self:
            if (
                rec.next_action
                and (rec.user_id or rec.fsm_assigned_employee_id)
                and rec._origin
                and rec._origin.id
                and rec.next_action != rec._origin.next_action
            ):
                rec.user_id = False
                rec.fsm_assigned_employee_id = False

    @api.onchange('next_action', 'project_id')
    def _onchange_issue_qt_enable_quotations(self):
        for rec in self:
            if rec.next_action == 'issue' and rec.project_id:
                rec.project_id.allow_quotations = True

    def _update_name(self):
        return True

    def name_get(self):
        show_crn_number = (
            self.env.context.get('show_task_seq')
            or self.env.context.get('show_crn_number')
        )
        result = []
        fallback_names = {}
        fallback_tasks = self.browse()

        for task in self:
            seq = task.task_seq if task.task_seq and task.task_seq != '/' else False
            seq_display = seq[len('TID-'):] if seq and seq.startswith('TID-') else seq
            # Real CRN numbers must never fall back to complaint title (name),
            # even when related is_fsm is False (empty project) or context is missing.
            is_crn_number = bool(seq and str(seq).startswith('CRN'))
            if show_crn_number or is_crn_number or (task.is_fsm and seq):
                result.append((task.id, seq_display or _('CRN')))
            else:
                fallback_tasks |= task

        if fallback_tasks:
            fallback_names = dict(super(ProjectTask, fallback_tasks).name_get())

        if fallback_names:
            ordered_result = []
            custom_names = dict(result)
            for task in self:
                ordered_result.append((task.id, custom_names.get(task.id) or fallback_names.get(task.id)))
            return ordered_result
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = list(args or [])
        show_crn_number = (
            self.env.context.get('show_task_seq')
            or self.env.context.get('show_crn_number')
        )
        # Quotation CRN picker (and any CRN-scoped domain): search/display numbers only.
        crn_scoped = show_crn_number or any(
            isinstance(term, (list, tuple)) and len(term) >= 3
            and term[0] == 'task_seq' and term[1] in ('=like', '=ilike', 'like', 'ilike')
            and str(term[2]).upper().startswith('CRN')
            for term in args
        )
        if not crn_scoped:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        args = [('task_seq', '=like', 'CRN%')] + args
        if name:
            args = [('task_seq', operator, name)] + args
        tasks = self.search(args, limit=limit)
        return tasks.with_context(show_task_seq=True, show_crn_number=True).name_get()

    @api.onchange('complaint_title')
    def _onchange_complaint_title_set_name(self):
        for rec in self:
            if rec.complaint_title:
                rec.name = rec.complaint_title.display_name

    @api.depends('stage')
    def _compute_state_from_stage(self):
        for rec in self:
            rec.state = rec.stage or 'registered'

    def _prepare_fsm_inverse_vals_for_fsm_key(self, key):
        """Map a statusbar / stage choice onto stored FSM fields so computed stage survives save."""
        self.ensure_one()
        if key != 'in_progress':
            return {}
        visit_done = bool(self.visited_by and self.visited_date)
        if not visit_done:
            raise UserError(_('Fill Visited By and Visited Date before moving to WIP (5. WIP).'))
        vals = {'next_action': 'foc'}
        if self.date_end:
            vals['date_end'] = False
        return vals

    def _inverse_state_from_fsm_selection(self):
        for rec in self:
            vals = rec._prepare_fsm_inverse_vals_for_fsm_key(rec.state)
            if vals:
                rec.write(vals)

    def _inverse_stage_from_fsm_selection(self):
        for rec in self:
            vals = rec._prepare_fsm_inverse_vals_for_fsm_key(rec.stage)
            if vals:
                rec.write(vals)

    def _get_prior_crn_task_seqs(self):
        """Comma-separated CRN numbers for the same invoice line on other tasks."""
        self.ensure_one()
        if not self.item_des:
            return ''
        domain = [('item_des', '=', self.item_des.id)]
        task_id = self.id or (self._origin.id if self._origin else False)
        if task_id:
            domain.append(('id', '!=', task_id))
        similar_tasks = self.env['project.task'].search(domain, limit=50)
        return ', '.join(filter(None, similar_tasks.mapped('task_seq')))

    @api.depends('item_des')
    def _compute_crn_done_before(self):
        for rec in self:
            seqs = rec._get_prior_crn_task_seqs()
            rec.crn_done_before = seqs or _('Not yet done')

    @api.depends(
        'visited_by',
        'visited_date',
        'next_action',
        'assign_date',
        'date_end',
        'select_invoice',
        'fsm_assigned_employee_id',
        'user_id',
        'approved_by',
    )
    def _compute_stage_logic(self):
        for rec in self:
            stage_val = rec._get_fsm_stage_value()
            rec.stage = stage_val
            rec.fsm_stage_group = stage_val

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'create_date',
        'fsm_creator_uid',
        'partner_id',
        'site_location',
        'client_person',
        'client_contact',
        'client_email',
        'complaint_type',
        'crn_done_before',
        'complaint_title',
        'complaint_details',
        'deadline',
        'importance',
        'total_print_row',
        'invoice_id',
        'item_des',
        'qt_no',
        'project_id',
        'visited_by',
        'visited_date',
        'site_visit',
        'next_action',
        'fsm_assigned_employee_id',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'closing_remarks',
        'remarks',
        'work_completion',
        'material_line_ids',
        'timesheet_ids',
        'material_cost_total',
        'stage',
        'state',
        'is_fsm',
        'check_fsm',
        'message_ids',
    )
    def _compute_fsm_stage_progress(self):
        for rec in self:
            if rec.is_fsm or rec.check_fsm:
                rec.fsm_stage_progress = rec._get_fsm_workflow_checklist_progress()
            else:
                rec.fsm_stage_progress = rec._get_fsm_stage_progress(rec.stage or rec.fsm_stage_group)

    def _recompute_fsm_stage_progress(self):
        """Explicitly recompute and store fsm_stage_progress (used by migration backfill)."""
        self._compute_fsm_stage_progress()

    @api.depends(
        'fsm_nav_completed',
        'task_seq',
        'partner_id',
        'complaint_type',
        'complaint_title',
        'complaint_details',
        'visited_by',
        'visited_date',
        'site_visit',
        'next_action',
        'user_id',
        'assign_date',
        'date_end',
        'select_invoice',
        'approved_by',
        'material_line_ids',
        'timesheet_ids',
        'stage',
        'state',
        'is_fsm',
        'check_fsm',
        'planned_hours',
        'effective_hours',
        'subtask_effective_hours',
    )
    def _compute_progress_hours(self):
        fsm_tasks = self.filtered(lambda task: task.is_fsm or task.check_fsm)
        non_fsm_tasks = self - fsm_tasks
        if non_fsm_tasks:
            super(ProjectTask, non_fsm_tasks)._compute_progress_hours()
        for task in fsm_tasks:
            progress = task._get_fsm_workflow_checklist_progress()
            task.progress = progress
            if 'overtime' in task._fields:
                task.overtime = 0.0

    @api.model
    def _get_fsm_stage_progress(self, stage_value):
        return _FSM_STAGE_PROGRESS_WEIGHTS.get(stage_value or 'registered', 0.0)

    def _get_fsm_stage_value(self):
        self.ensure_one()
        related_orders = self._get_fsm_related_orders().filtered(
            lambda o: o.state != 'cancel',
        )
        has_confirmed_quotation = any(order.state in ('sale', 'done') for order in related_orders)
        has_created_quotation = any(order.state in ('draft', 'sent') for order in related_orders)
        visit_done = bool(self.visited_by and self.visited_date)
        assigned_for_work = bool(
            visit_done
            and self.next_action
            and self.fsm_assigned_employee_id
            and self.assign_date
        )

        if self.approved_by:
            return 'approved'
        if self.select_invoice:
            return 'job_completed_invoiced'
        if self.next_action == 'closed':
            return 'job_completed'
        if self.date_end and assigned_for_work and self.next_action == 'foc':
            return 'job_completed'
        if self.date_end:
            return 'waiting_for_invoice'
        if assigned_for_work:
            return 'in_progress'
        if has_confirmed_quotation:
            return 'qty_approved'
        if has_created_quotation:
            return 'qty_issued'
        if visit_done:
            return 'site_visited'
        # Assigned but site visit not recorded yet → stay at 1. REG
        if self.fsm_assigned_employee_id or self.user_id or self.assign_date:
            return 'registered'
        return 'registered'

    def _update_fsm_stage_group(self):
        for task in self:
            task.fsm_stage_group = task._get_fsm_stage_value()

    @api.model
    def update_fsm_reporting_fields(self):
        tasks = self.with_context(active_test=False).sudo().search([('is_fsm', '=', True)])
        tasks._update_fsm_stage_group()
        return True

    def _search_stage(self, operator, value):
        tasks = self.env['project.task'].with_context(prefetch_fields=False).search([])
        if operator == '=':
            matching_ids = tasks.filtered(lambda task: task.stage == value).ids
        elif operator == '!=':
            matching_ids = tasks.filtered(lambda task: task.stage != value).ids
        elif operator == 'in':
            matching_ids = tasks.filtered(lambda task: task.stage in value).ids
        elif operator == 'not in':
            matching_ids = tasks.filtered(lambda task: task.stage not in value).ids
        else:
            matching_ids = []
        return [('id', 'in', matching_ids)]

    def _search_state(self, operator, value):
        return self._search_stage(operator, value)

    def _get_fsm_related_orders(self):
        self.ensure_one()
        cache_key = self._cpabooks_fsm_record_cache_key()
        orders_cache = self._cpabooks_fsm_env_cache()['orders']
        if cache_key in orders_cache:
            return orders_cache[cache_key]
        sale_order_model = self.env['sale.order'] if self.env.registry.get('sale.order') else False
        if sale_order_model is False:
            orders = self.env['sale.order']
        else:
            task_id = self.id if isinstance(self.id, int) else False
            if not task_id:
                origin = getattr(self, '_origin', None)
                task_id = origin.id if origin and origin.id else False
            if not task_id:
                orders = self.env['sale.order']
            else:
                orders = sale_order_model.search([('task_id', '=', task_id)])
        orders_cache[cache_key] = orders
        return orders

    def _get_fsm_related_invoices(self):
        self.ensure_one()
        return self._get_fsm_related_orders().mapped('invoice_ids')

    def _get_fsm_related_pickings(self):
        self.ensure_one()
        orders = self._get_fsm_related_orders()
        if 'picking_ids' in orders._fields:
            return orders.mapped('picking_ids')
        return self.env['stock.picking'].search([('origin', 'in', orders.mapped('name'))])

    def _compute_fsm_related_document_counts(self):
        for rec in self:
            orders = rec._get_fsm_related_orders()
            rec.fsm_all_quotation_count = len(orders)
            rec.fsm_all_invoice_count = len(rec._get_fsm_related_invoices())
            rec.fsm_all_delivery_count = len(rec._get_fsm_related_pickings())

    def _cpabooks_fsm_list_first_action(self, action):
        views = list(action.get('views') or [])
        if not views and action.get('view_mode'):
            views = [
                (False, mode.strip())
                for mode in str(action.get('view_mode')).split(',')
                if mode.strip()
            ]
        if len(views) == 1 and self._cpabooks_fsm_action_view_mode(views[0]) == 'form':
            return action
        list_views = [
            view for view in views
            if self._cpabooks_fsm_action_view_mode(view) in ('tree', 'list')
        ]
        form_views = [
            view for view in views
            if self._cpabooks_fsm_action_view_mode(view) == 'form'
        ]
        other_views = [
            view for view in views
            if self._cpabooks_fsm_action_view_mode(view) not in ('tree', 'list', 'form')
        ]
        if list_views:
            action['views'] = list_views + other_views + form_views
        else:
            action['views'] = [(False, 'tree')] + other_views + (form_views or [(False, 'form')])
        action['views'] = [
            (
                self._cpabooks_fsm_action_view_id(view),
                'tree' if self._cpabooks_fsm_action_view_mode(view) == 'list'
                else self._cpabooks_fsm_action_view_mode(view),
            )
            for view in action['views']
            if self._cpabooks_fsm_action_view_mode(view)
        ]
        action['view_mode'] = ','.join(view[1] for view in action['views'])
        action.pop('res_id', None)
        return action

    def _cpabooks_fsm_action_view_mode(self, view):
        if isinstance(view, (list, tuple)) and len(view) > 1:
            return view[1]
        if isinstance(view, dict):
            return view.get('type')
        return False

    def _cpabooks_fsm_action_view_id(self, view):
        if isinstance(view, (list, tuple)) and view:
            return view[0] or False
        if isinstance(view, dict):
            return view.get('viewID') or view.get('view_id') or False
        return False

    def action_fsm_view_all_related_quotations(self):
        self.ensure_one()
        orders = self._get_fsm_related_orders()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations")
        action.update({
            'name': _('Quotations / Orders'),
            'domain': [('id', 'in', orders.ids)],
            'context': {
                'default_task_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
                'search_default_my_quotation': 0,
            },
        })
        return self._cpabooks_fsm_list_first_action(action)

    def action_fsm_view_all_related_invoices(self):
        self.ensure_one()
        invoices = self._get_fsm_related_invoices()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action.update({
            'name': _('Invoices'),
            'domain': [('id', 'in', invoices.ids)],
            'context': {
                'default_move_type': 'out_invoice',
                'default_partner_id': self.partner_id.id,
                'default_invoice_origin': self.task_seq,
            },
        })
        return self._cpabooks_fsm_list_first_action(action)

    def action_fsm_view_all_related_deliveries(self):
        self.ensure_one()
        pickings = self._get_fsm_related_pickings()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action.update({
            'name': _('Deliveries'),
            'domain': [('id', 'in', pickings.ids)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_origin': self.task_seq,
            },
        })
        return self._cpabooks_fsm_list_first_action(action)

    def action_view_material_returns(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "saaskul_field_service.action_material_return"
        )
        action.update({
            'domain': [('issue_project_task_id', '=', self.id), ('is_material_return', '=', True)],
            'context': {
                'default_issue_project_task_id': self.id,
                'show_task_seq': True,
                'show_crn_number': True,
            },
        })
        return self._cpabooks_fsm_list_first_action(action)

    def action_load_customer_material_lines(self):
        for task in self:
            lines = []
            for line in task.material_line_ids:
                done_qty = line.quantity_done or line.quantity or 0.0
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'description': line.description or line.product_id.display_name,
                    'serial_no': line.product_id.default_code,
                    'quantity': line.quantity or 0.0,
                    'quantity_done': done_qty,
                    'amount_done': line.amount_done or 0.0,
                }))
            task.customer_part_line_ids.unlink()
            task.customer_part_line_ids = lines
        return True

    def action_load_customer_labour_lines(self):
        for task in self:
            lines = []
            for line in task.timesheet_ids:
                rate = 0.0
                if 'fsm_employee_timesheet_cost' in line._fields:
                    rate = line.fsm_employee_timesheet_cost or 0.0
                if not rate and line.employee_id and 'timesheet_cost' in line.employee_id._fields:
                    rate = line.employee_id.timesheet_cost or 0.0
                hours = line.unit_amount or 0.0
                lines.append((0, 0, {
                    'date': line.date,
                    'employee_id': line.employee_id.id,
                    'description': line.name,
                    'hours': hours,
                    'rate': rate,
                    'amount': hours * rate,
                }))
            task.customer_labour_line_ids.unlink()
            task.customer_labour_line_ids = lines
        return True

    @api.depends('invoice_id', 'invoice_id.invoice_type')
    def _compute_invoice_type(self):
        for rec in self:
            invoice_type = rec.invoice_id.invoice_type if rec.invoice_id and 'invoice_type' in rec.invoice_id._fields else False
            rec.invoice_type = invoice_type.name if invoice_type else False

    @api.depends('invoice_id', 'invoice_id.invoice_type', 'invoice_id.invoice_line_ids', 'invoice_id.invoice_line_ids.guaranteed')
    def _compute_show_invoice_line(self):
        for rec in self:
            rec.show_invoice_line = bool(rec.available_invoice_line_ids)

    @api.depends('invoice_id', 'invoice_id.invoice_type', 'invoice_id.invoice_line_ids', 'invoice_id.invoice_line_ids.guaranteed')
    def _compute_available_invoice_line_ids(self):
        for rec in self:
            rec.available_invoice_line_ids = rec._get_available_invoice_lines()

    @api.depends('show_invoice_line')
    def _compute_invoice_line_notice(self):
        for rec in self:
            rec.invoice_line_notice = False if rec.show_invoice_line else _('No invoice line available')

    @api.depends(
        'invoice_id',
        'invoice_id.project_id',
        'qt_no',
        'qt_no.project_id',
        'complaint_type',
    )
    def _compute_invoice_project_ids(self):
        Project = self.env['project.project']
        for rec in self:
            projects = Project
            if rec.invoice_id and 'project_id' in rec.invoice_id._fields:
                projects |= rec.invoice_id.project_id or rec._get_project_not_available_fsm_project(rec.company_id)
            if (
                rec.complaint_type == 'new_installation'
                and rec.qt_no
                and not rec.invoice_id
                and 'project_id' in rec.qt_no._fields
                and rec.qt_no.project_id
            ):
                projects |= rec.qt_no.project_id
            rec.invoice_project_ids = projects

    @api.depends('partner_id', 'complaint_type')
    def _compute_available_invoice_ids(self):
        invoice_model = self.env['account.move']
        for rec in self:
            base_domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_type', '!=', False),
            ]
            if rec.partner_id:
                commercial_partner = rec.partner_id.commercial_partner_id
                partner_domain = [
                    '|',
                    ('commercial_partner_id', '=', commercial_partner.id),
                    ('partner_id', 'child_of', commercial_partner.id),
                ]
                invoices = invoice_model.search(
                    base_domain + partner_domain,
                    order='invoice_date desc, id desc',
                    limit=200,
                )
            else:
                invoices = invoice_model.search(
                    base_domain,
                    order='invoice_date desc, id desc',
                    limit=200,
                )
            if rec.complaint_type:
                invoices = invoices.filtered(lambda invoice: rec._invoice_type_matches_complaint_type(invoice))
            rec.available_invoice_ids = invoices

    def _is_amc_invoice(self, invoice):
        self.ensure_one()
        invoice_type = invoice.invoice_type if invoice and 'invoice_type' in invoice._fields else False
        return bool(invoice_type and self._normalized_selection_value(invoice_type.name) == 'amc')

    def _get_auto_invoice_candidate(self):
        self.ensure_one()
        invoices = self.available_invoice_ids
        if not self.partner_id or not invoices:
            return self.env['account.move']
        amc_invoices = invoices.filtered(lambda invoice: self._is_amc_invoice(invoice))
        return amc_invoices[:1]

    def _get_invoice_related_sale_orders(self, invoice=None):
        """Sale orders linked to a customer invoice (quotation source)."""
        self.ensure_one()
        invoice = invoice or self.invoice_id
        sale_order_model = self.env['sale.order'] if self.env.registry.get('sale.order') else False
        if not invoice or sale_order_model is False:
            return sale_order_model
        orders = sale_order_model.browse()
        if 'invoice_ids' in sale_order_model._fields:
            orders |= sale_order_model.search([('invoice_ids', 'in', invoice.ids)])
        if 'sale_line_ids' in self.env['account.move.line']._fields:
            orders |= invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
        if invoice.invoice_origin:
            order_names = [name.strip() for name in invoice.invoice_origin.split(',') if name.strip()]
            if order_names:
                orders |= sale_order_model.search([('name', 'in', order_names)])
        return orders.filtered(lambda order: order.state != 'cancel')

    @api.depends(
        'invoice_id',
        'invoice_id.invoice_origin',
        'invoice_id.invoice_line_ids',
        'invoice_id.invoice_line_ids.sale_line_ids',
        'partner_id',
        'complaint_type',
    )
    def _compute_available_quotation_ids(self):
        sale_order_model = self.env['sale.order'] if self.env.registry.get('sale.order') else False
        for rec in self:
            if not sale_order_model:
                rec.available_quotation_ids = sale_order_model
                continue
            if rec.invoice_id:
                rec.available_quotation_ids = rec._get_invoice_related_sale_orders()
                continue
            if rec.complaint_type == 'new_installation' and rec.partner_id:
                rec.available_quotation_ids = sale_order_model.search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', 'in', ('draft', 'sent', 'sale')),
                ], order='id desc', limit=200)
            else:
                rec.available_quotation_ids = sale_order_model.browse()

    def _get_qt_no_form_domain(self):
        self.ensure_one()
        if self.available_quotation_ids:
            return [('id', 'in', self.available_quotation_ids.ids)]
        if self.invoice_id:
            return [('id', '=', False)]
        if self.complaint_type == 'new_installation' and self.partner_id:
            return [
                ('partner_id', '=', self.partner_id.id),
                ('state', 'in', ('draft', 'sent', 'sale')),
            ]
        return [('id', '=', False)]

    def _get_or_create_fsm_named_record(self, model_name, name):
        name = (name or '').strip()
        if not name:
            return self.env[model_name]
        record = self.env[model_name].search([('name', '=', name)], limit=1)
        return record or self.env[model_name].create({'name': name})

    def _get_invoice_sale_order(self, invoice):
        return self._get_invoice_related_sale_orders(invoice)[:1]

    def _clear_auto_invoice_details(self):
        for rec in self:
            rec.invoice_id = False
            rec.project_id = False
            rec.item_des = False
            rec.qt_no = False
            rec.qt_no_text = False
            rec.complaint_type = False
            rec.site_location = False
            rec.client_person = False
            rec.client_contact = False
            rec.client_email = False

    def _apply_invoice_details_to_fsm_task(self):
        for rec in self:
            invoice = rec.invoice_id
            if not invoice:
                continue

            partner = invoice.partner_id or rec.partner_id
            if partner:
                rec.partner_id = partner
                rec.client_contact = partner.phone or partner.mobile or rec.client_contact
                rec.client_email = partner.email or rec.client_email

            delivery_person = (
                invoice.delivery_person
                if 'delivery_person' in invoice._fields and invoice.delivery_person
                else False
            )
            if delivery_person:
                rec.client_person = rec._get_or_create_fsm_named_record(
                    'contact.person',
                    delivery_person.display_name or delivery_person.name,
                )
                rec.client_contact = delivery_person.phone or delivery_person.mobile or rec.client_contact
                rec.client_email = delivery_person.email or rec.client_email

            site_name = False
            delivery_address = (
                invoice.delivery_address
                if 'delivery_address' in invoice._fields and invoice.delivery_address
                else False
            )
            shipping_partner = (
                invoice.partner_shipping_id
                if 'partner_shipping_id' in invoice._fields and invoice.partner_shipping_id
                else False
            )
            if delivery_address:
                site_name = delivery_address.display_name or delivery_address.name
            elif shipping_partner:
                site_name = shipping_partner.display_name or shipping_partner.name
            elif 'delivery_detail' in invoice._fields and invoice.delivery_detail:
                site_name = invoice.delivery_detail
            if site_name:
                rec.site_location = rec._get_or_create_fsm_named_record('site.location', site_name)

            sale_order = rec._get_invoice_sale_order(invoice)
            if sale_order:
                rec.qt_no = sale_order
                rec.qt_no_text = False
                if (
                    'project_id' in sale_order._fields
                    and sale_order.project_id
                    and 'project_id' in invoice._fields
                    and invoice.project_id
                ):
                    rec.project_id = sale_order.project_id
                if not rec.client_person and 'attention' in sale_order._fields and sale_order.attention:
                    rec.client_person = rec._get_or_create_fsm_named_record('contact.person', sale_order.attention)
                if not rec.site_location and 'delivery_detail' in sale_order._fields and sale_order.delivery_detail:
                    rec.site_location = rec._get_or_create_fsm_named_record('site.location', sale_order.delivery_detail)

            if 'project_id' in invoice._fields:
                rec.project_id = invoice.project_id or rec._get_project_not_available_fsm_project(rec.company_id)
            if not rec.item_des and rec.available_invoice_line_ids:
                rec.item_des = rec.available_invoice_line_ids[:1]

    def _get_available_invoice_lines(self):
        self.ensure_one()
        invoice = self.invoice_id
        if not invoice or 'invoice_type' not in invoice._fields or not invoice.invoice_type:
            return self.env['account.move.line']
        if 'guaranteed' not in self.env['account.move.line']._fields:
            return self.env['account.move.line']
        return invoice.invoice_line_ids.filtered(lambda line: not line.display_type and line.guaranteed)

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id:
            self._apply_invoice_details_to_fsm_task()
        elif self.complaint_type != 'new_installation':
            self.qt_no = False
            self.qt_no_text = False
        if self.qt_no and self.qt_no not in self.available_quotation_ids:
            self.qt_no = False
        if self.invoice_id and 'project_id' in self.invoice_id._fields:
            self.project_id = self.invoice_id.project_id or self._get_project_not_available_fsm_project(self.company_id)
        complaint_type = self._invoice_type_to_complaint_type()
        if complaint_type:
            self.complaint_type = complaint_type
        if self.item_des not in self.available_invoice_line_ids:
            self.item_des = False
        return {
            'domain': {
                'invoice_id': [('id', 'in', self.available_invoice_ids.ids)],
                'project_id': [('id', 'in', (self.invoice_project_ids | self.project_id).ids)],
                'item_des': [('id', 'in', self.available_invoice_line_ids.ids)],
                'qt_no': self._get_qt_no_form_domain(),
            },
        }

    @api.onchange('partner_id')
    def _onchange_partner_id_auto_invoice(self):
        return {
            'domain': {
                'invoice_id': [('id', 'in', self.available_invoice_ids.ids)],
                'qt_no': self._get_qt_no_form_domain(),
            },
        }

    @api.onchange('complaint_type')
    def _onchange_complaint_type(self):
        if self.complaint_type == 'new_installation':
            self.invoice_id = False
            self.item_des = False
        else:
            if self.qt_no and self.qt_no not in self.available_quotation_ids:
                self.qt_no = False
        return {
            'domain': {
                'invoice_id': [('id', 'in', self.available_invoice_ids.ids)],
                'qt_no': self._get_qt_no_form_domain(),
            },
        }

    def _normalized_selection_value(self, value):
        return (value or '').strip().lower().replace(' ', '_').replace('/', '_')

    def _partner_allows_fsm_auto_invoice(self):
        """Commercial partner must have Invoice Type = AMC on the contact form."""
        self.ensure_one()
        if not self.partner_id:
            return False
        commercial = self.partner_id.commercial_partner_id
        if 'customer_invoice_type_id' not in commercial._fields:
            return False
        invoice_type_rec = commercial.customer_invoice_type_id
        if not invoice_type_rec or not invoice_type_rec.name:
            return False
        return self._normalized_selection_value(invoice_type_rec.name) == 'amc'

    def _invoice_type_matches_complaint_type(self, invoice):
        self.ensure_one()
        invoice_type = invoice.invoice_type if invoice and 'invoice_type' in invoice._fields else False
        if not self.complaint_type or not invoice_type:
            return True
        return self._invoice_type_name_to_complaint_type(invoice_type.name) == self.complaint_type

    def _invoice_type_name_to_complaint_type(self, name):
        normalized_name = self._normalized_selection_value(name)
        aliases = {
            'amc': 'amc',
            'others': 'others',
            'other': 'others',
            'warranty': 'warranty',
            'waranty': 'warranty',
            'warranty_service': 'warranty',
            'warranty_and_service': 'warranty',
            'waranty_and_service': 'warranty',
            'service': 'service',
            'new_installation': 'new_installation',
            'new_inquiry': 'new_inquiry',
            'site_visit': 'site_visit',
        }
        return aliases.get(normalized_name)

    def _invoice_type_to_complaint_type(self):
        self.ensure_one()
        invoice_type = self.invoice_id.invoice_type if self.invoice_id and 'invoice_type' in self.invoice_id._fields else False
        return self._invoice_type_name_to_complaint_type(invoice_type.name) if invoice_type else False

    def _sync_complaint_type_from_invoice_type(self):
        for rec in self:
            complaint_type = rec._invoice_type_to_complaint_type()
            if complaint_type:
                rec.complaint_type = complaint_type

    @api.onchange('qt_no')
    def _onchange_qt_no(self):
        for rec in self:
            if not rec.qt_no:
                continue
            rec.qt_no_text = False
            rec.partner_id = rec.qt_no.partner_id
            rec.project_id = rec.qt_no.project_id
            rec.client_email = rec.qt_no.partner_id.email
            rec.client_contact = rec.qt_no.partner_id.phone or rec.qt_no.partner_id.mobile
        return {
            'domain': {
                'qt_no': self._get_qt_no_form_domain(),
            },
        }

    @api.onchange('qt_no_text')
    def _onchange_qt_no_text(self):
        for rec in self:
            if (rec.qt_no_text or '').strip():
                rec.qt_no = False

    def _sync_issue_note_material_lines(self):
        done_pickings = self.env['stock.picking'].sudo().search([
            ('issue_project_task_id', 'in', self.ids),
            ('state', '=', 'done'),
        ])
        if done_pickings and hasattr(done_pickings, '_sync_issue_material_request_lines'):
            done_pickings._sync_issue_material_request_lines()

    @api.depends('material_line_ids', 'material_line_ids.amount_done')
    def _compute_material_amount_done_total(self):
        self._sync_issue_note_material_lines()
        for rec in self:
            total_amount = sum(rec.material_line_ids.mapped('amount_done'))
            rec.material_amount_done_total = total_amount
            rec.material_cost_total = total_amount

    @api.depends(
        'material_return_picking_ids',
        'material_return_picking_ids.state',
        'material_return_picking_ids.move_ids_without_package',
        'material_return_picking_ids.move_ids_without_package.state',
        'material_return_picking_ids.move_ids_without_package.product_uom_qty',
        'material_return_picking_ids.move_ids_without_package.quantity_done',
    )
    def _compute_material_return_move_ids(self):
        for task in self:
            moves = task.material_return_picking_ids.mapped('move_ids_without_package').filtered(
                lambda mv: mv.state != 'cancel'
            )
            task.material_return_move_ids = moves

    def _is_material_fully_issued(self):
        self.ensure_one()
        material_lines = self.material_line_ids
        if not material_lines:
            return False
        picking_model = self.env['stock.picking']
        pickings = picking_model.search([
            ('issue_project_task_id', '=', self.id),
            ('state', '=', 'done'),
        ])
        for line in material_lines:
            if 'issue_move_id' in line._fields and line.issue_move_id:
                move = line.issue_move_id
                issued_qty = move.quantity_done if move.state != 'cancel' else 0.0
            else:
                moves = pickings.move_ids_without_package.filtered(
                    lambda move: move.product_id.id == line.product_id.id and move.state != 'cancel'
                )
                issued_qty = sum(moves.mapped('quantity_done'))
            if issued_qty < line.quantity:
                return False
        return True

    def _compute_issue_note_done(self):
        self._sync_issue_note_material_lines()
        for task in self:
            task.issue_note_done = task._is_material_fully_issued()

    def _search_issue_note_done(self, operator, value):
        tasks = self.env['material.request.line'].search([]).mapped('task_id')
        done_tasks = tasks.filtered(lambda task: task._is_material_fully_issued())
        if (operator in ('=', '==') and value) or (operator == '!=' and not value):
            return [('id', 'in', done_tasks.ids)]
        return [('id', 'not in', done_tasks.ids)]

    def _update_issue_note_done(self):
        self.invalidate_cache(['issue_note_done'])

    def _fsm_cancel_tasks(self, include_related=False):
        tasks = self.sudo().with_context(active_test=False)
        if not tasks:
            return True

        if include_related:
            tasks._fsm_cancel_related_documents()

        vals = {
            'date_end': fields.Date.context_today(self),
            'closing_remarks': _('Cancelled'),
        }
        if 'active' in tasks._fields:
            vals['active'] = False
        if 'next_action' in tasks._fields:
            vals['next_action'] = 'closed'
        tasks.with_context(**{CPABOOKS_FSM_CRN_MUTATION_CTX: True}).write(vals)
        return True

    def _fsm_cancel_related_documents(self):
        tasks = self.sudo().with_context(active_test=False)
        if self.env.registry.get('planning.slot'):
            self.env['planning.slot'].sudo().search([('task_id', 'in', tasks.ids)]).unlink()

        pickings = self.env['stock.picking'].sudo().search([('issue_project_task_id', 'in', tasks.ids)])
        for picking in pickings:
            try:
                if picking.state not in ('done', 'cancel'):
                    picking.action_cancel()
                elif picking.state == 'done':
                    picking.move_ids_without_package.write({'state': 'cancel'})
                    picking.write({'state': 'cancel'})
            except Exception:
                pass

        orders = self.env['sale.order'].sudo().search([('task_id', 'in', tasks.ids)])
        for order in orders:
            try:
                if order.state not in ('cancel',):
                    order.action_cancel()
            except Exception:
                pass

        invoices = tasks.mapped('invoice_id') | orders.mapped('invoice_ids')
        for invoice in invoices.sudo():
            try:
                if invoice.state == 'posted':
                    invoice.button_draft()
                if hasattr(invoice, 'button_cancel') and invoice.state != 'cancel':
                    invoice.button_cancel()
            except Exception:
                pass
        return True

    def _is_internal_project_system_task(self):
        """Training/Meeting rows on an internal timesheet project."""
        self.ensure_one()
        if not self.project_id or not getattr(self.project_id, 'is_internal_project', False):
            return False
        if self.task_seq and str(self.task_seq).startswith('CRN'):
            return False
        name = (self.name or '').strip().lower()
        if name in ('training', 'meeting'):
            return True
        return not bool(self.task_seq and self.task_seq not in ('/', False))

    def _cpabooks_fsm_mutable_crns(self):
        return self.filtered(
            lambda task: (task.is_fsm or task.check_fsm)
            and not task._is_internal_project_system_task()
            and not task.project_id.is_internal_project,
        )

    def _cpabooks_fsm_deletable(self):
        return self._cpabooks_fsm_mutable_crns()

    def _cpabooks_fsm_archivable(self):
        return self._cpabooks_fsm_mutable_crns()

    def action_fsm_delete_crn(self):
        """Delete a single CRN (not internal Training/Meeting tasks)."""
        self.ensure_one()
        if not (self.is_fsm or self.check_fsm):
            raise UserError(_('This record is not a CRN.'))
        if self.project_id.is_internal_project or self._is_internal_project_system_task():
            raise UserError(_(
                'Training/Meeting tasks on an internal project cannot be deleted.',
            ))
        name = self.task_seq or self.display_name
        self.with_context(**{CPABOOKS_FSM_CRN_MUTATION_CTX: True}).unlink()
        action = self.env.ref('industry_fsm.project_task_action_all_fsm', raise_if_not_found=False)
        if action:
            result = action.read()[0]
            result.setdefault('params', {})
            result['params']['message'] = _('%(name)s was deleted.') % {'name': name}
            return result
        return {'type': 'ir.actions.act_window_close'}

    def action_fsm_delete_selected(self):
        """List Action: delete selected CRNs; skip internal Training/Meeting rows."""
        deletable = self._cpabooks_fsm_deletable()
        skipped = len(self) - len(deletable)
        if not deletable:
            raise UserError(_(
                'No deletable CRNs in the selection. '
                'Training/Meeting system tasks cannot be deleted. '
                'Deselect them and use Action → Delete CRN(s) for real CRNs.',
            ))
        count = len(deletable)
        deletable.with_context(**{CPABOOKS_FSM_CRN_MUTATION_CTX: True}).unlink()
        message = _('Deleted %s CRN(s).') % count
        sticky = False
        msg_type = 'success'
        if skipped:
            message += ' ' + _(
                '%s record(s) were skipped (internal project).',
            ) % skipped
            sticky = True
            msg_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Delete CRN'),
                'message': message,
                'type': msg_type,
                'sticky': sticky,
            },
        }

    def action_fsm_archive_selected(self):
        """List Action: archive selected CRNs; skip internal Training/Meeting rows."""
        archivable = self._cpabooks_fsm_archivable()
        skipped = len(self) - len(archivable)
        if not archivable:
            raise UserError(_(
                'No archivable CRNs in the selection. '
                'Training/Meeting system tasks cannot be archived. '
                'Deselect them and use Action → Archive CRN(s) for real CRNs.',
            ))
        count = len(archivable)
        archivable.with_context(**{CPABOOKS_FSM_CRN_MUTATION_CTX: True}).write({'active': False})
        message = _('Archived %s CRN(s).') % count
        sticky = False
        msg_type = 'success'
        if skipped:
            message += ' ' + _(
                '%s record(s) were skipped (Training/Meeting system tasks).',
            ) % skipped
            sticky = True
            msg_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Archive CRN'),
                'message': message,
                'type': msg_type,
                'sticky': sticky,
            },
        }

    def action_fsm_cancel_selected(self):
        cancellable = self._cpabooks_fsm_mutable_crns()
        skipped = len(self) - len(cancellable)
        if not cancellable:
            raise UserError(_(
                'No cancellable CRNs in the selection. '
                'Training/Meeting system tasks cannot be cancelled.',
            ))
        cancellable._fsm_cancel_tasks(include_related=False)
        if skipped:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cancel CRN'),
                    'message': _(
                        'Cancelled %(count)s CRN(s). %(skipped)s system task(s) were skipped.',
                    ) % {'count': len(cancellable), 'skipped': skipped},
                    'type': 'warning',
                    'sticky': True,
                },
            }
        return True

    @api.model
    def action_fsm_cancel_all_tasks(self):
        tasks = self.with_context(active_test=False).search(self._cpabooks_all_crn_domain())
        return tasks._fsm_cancel_tasks(include_related=False)

    @api.model
    def action_fsm_cancel_all_tasks_with_related(self):
        tasks = self.with_context(active_test=False).search(self._cpabooks_all_crn_domain())
        return tasks._fsm_cancel_tasks(include_related=True)

    @api.depends(
        'timesheet_ids.amount',
        'timesheet_ids.fsm_cost_amount',
        'timesheet_ids.fsm_employee_timesheet_cost',
        'timesheet_ids.unit_amount',
        'timesheet_ids.employee_id',
        'timesheet_ids.employee_id.timesheet_cost',
    )
    def _compute_timesheet_cost_total(self):
        for rec in self:
            if 'fsm_cost_amount' in self.env['account.analytic.line']._fields:
                rec.timesheet_cost_total = sum(rec.timesheet_ids.mapped('fsm_cost_amount'))
            else:
                rec.timesheet_cost_total = abs(sum(rec.timesheet_ids.mapped('amount')))

    @api.depends(
        'material_cost_total',
        'timesheet_cost_total',
        'fsm_transport_cost',
        'fsm_other_cost',
    )
    def _compute_total_service_cost(self):
        for rec in self:
            rec.total_service_cost = (
                rec.material_cost_total
                + rec.timesheet_cost_total
                + (rec.fsm_transport_cost or 0.0)
                + (rec.fsm_other_cost or 0.0)
            )

    @api.depends('create_date', 'date_end')
    def _compute_age_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.create_date:
                rec.age_days = 0
                continue
            start_date = fields.Date.to_date(rec.create_date)
            end_date = fields.Date.to_date(rec.date_end) if rec.date_end else today
            rec.age_days = (end_date - start_date).days

    def _jcr_print_row_count(self):
        self.ensure_one()
        try:
            count = int(self.total_print_row or 10)
        except (TypeError, ValueError):
            count = 10
        return max(1, min(50, count))

    def _jcr_print_is_approved(self):
        self.ensure_one()
        if self.approved_by:
            return True
        if getattr(self, 'approval_state', None) == 'approved':
            return True
        stage_val = self._get_fsm_stage_value() if hasattr(self, '_get_fsm_stage_value') else getattr(self, 'stage', False)
        if stage_val == 'approved':
            return True
        state_val = getattr(self, 'state', False)
        if state_val == 'approved':
            return True
        return False

    def _jcr_empty_part_row(self, sr_no):
        return {
            'sr': sr_no,
            'particulars': '',
            'serial': '',
            'qty': '',
        }

    def _jcr_part_row_from_line(self, line, sr_no):
        if line._name == 'project.task.customer.part.line':
            qty = line.quantity_done or line.quantity or 0.0
            return {
                'sr': sr_no,
                'particulars': line.description or line.product_id.display_name or '',
                'serial': line.serial_no or (line.product_id.default_code if line.product_id else '') or '',
                'qty': '%.2f' % qty,
            }
        qty = line.quantity or line.quantity_done or 0.0
        return {
            'sr': sr_no,
            'particulars': line.description or line.product_id.display_name or '',
            'serial': line.product_id.default_code if line.product_id else '',
            'qty': '%.2f' % qty,
        }

    def _jcr_print_parts_rows(self, customer_copy=False):
        self.ensure_one()
        count = self._jcr_print_row_count()
        rows = []
        if self._jcr_print_is_approved():
            if customer_copy:
                lines = self.customer_part_line_ids
            else:
                lines = self.material_line_ids
            for index in range(count):
                if index < len(lines):
                    rows.append(self._jcr_part_row_from_line(lines[index], index + 1))
                else:
                    rows.append(self._jcr_empty_part_row(index + 1))
        else:
            for index in range(count):
                rows.append(self._jcr_empty_part_row(index + 1))
        return rows

    def _jcr_empty_labour_row(self):
        return {
            'date': '',
            'technician': '',
            'time_in': '',
            'time_out': '',
            'hours': '',
        }

    def _jcr_labour_row_from_line(self, line):
        if line._name == 'project.task.customer.labour.line':
            technician = line.employee_id.name or ''
            if line.description:
                technician = '%s - %s' % (technician, line.description) if technician else line.description
            return {
                'date': line.date.strftime('%d/%m/%Y') if line.date else '',
                'technician': technician,
                'time_in': '',
                'time_out': '',
                'hours': '%.2f' % (line.hours or 0.0),
            }
        technician = line.employee_id.name or ''
        if line.name:
            technician = '%s - %s' % (technician, line.name) if technician else line.name
        hours = line.unit_amount or 0.0
        hours_str = ''
        if hours:
            hours_str = '%.2f' % hours
        return {
            'date': line.date.strftime('%d/%m/%Y') if line.date else '',
            'technician': technician,
            'time_in': '',
            'time_out': '',
            'hours': hours_str,
        }

    def _jcr_print_labour_rows(self, customer_copy=False):
        self.ensure_one()
        count = self._jcr_print_row_count()
        rows = []
        if self._jcr_print_is_approved():
            if customer_copy:
                lines = self.customer_labour_line_ids
            else:
                lines = self.timesheet_ids
            for index in range(count):
                if index < len(lines):
                    rows.append(self._jcr_labour_row_from_line(lines[index]))
                else:
                    rows.append(self._jcr_empty_labour_row())
        else:
            for index in range(count):
                rows.append(self._jcr_empty_labour_row())
        return rows


class ProjectTaskCustomerPartLine(models.Model):
    _name = 'project.task.customer.part.line'
    _description = 'Customer Material Detail'

    task_id = fields.Many2one(
        'project.task',
        string='CRN',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Char(string='Particulars')
    serial_no = fields.Char(string='Serial No.')
    quantity = fields.Float(string='Quantity', default=1.0)
    quantity_done = fields.Float(string='Done Quantity')
    amount_done = fields.Float(string='Amount Done')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                if not line.description:
                    line.description = line.product_id.display_name
                if not line.serial_no:
                    line.serial_no = line.product_id.default_code


class ProjectTaskCustomerLabourLine(models.Model):
    _name = 'project.task.customer.labour.line'
    _description = 'Customer Labour Cost'

    task_id = fields.Many2one(
        'project.task',
        string='CRN',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='task_id.currency_id',
        readonly=True,
    )
    date = fields.Date()
    employee_id = fields.Many2one('hr.employee', string='Service Eng / Technician')
    description = fields.Char(string='Description')
    hours = fields.Float(string='Hrs. Worked')
    rate = fields.Monetary(string='Labour Cost', currency_field='currency_id')
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        compute='_compute_amount',
        store=True,
        readonly=False,
    )

    @api.depends('hours', 'rate')
    def _compute_amount(self):
        for line in self:
            line.amount = (line.hours or 0.0) * (line.rate or 0.0)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for line in self:
            if line.employee_id and not line.description:
                line.description = line.employee_id.name
            if line.employee_id and 'timesheet_cost' in line.employee_id._fields:
                line.rate = line.employee_id.timesheet_cost or 0.0

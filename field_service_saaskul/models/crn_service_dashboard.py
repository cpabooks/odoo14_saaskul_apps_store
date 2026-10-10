# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.tools.safe_eval import safe_eval

_TERMINAL_STAGES = ('job_completed', 'job_completed_invoiced', 'approved')
_OPEN_STAGE_DOMAIN = [('fsm_stage_group', 'not in', list(_TERMINAL_STAGES))]
_TASK_ACTION = 'industry_fsm.project_task_action_all_fsm'
_ANALYSIS_ACTION = 'field_service_saaskul.action_fsm_task_analysis_monitor'
_DASHBOARD_ACTION_XMLIDS = (
    _TASK_ACTION,
    _ANALYSIS_ACTION,
    'industry_fsm.project_task_action_fsm',
    'field_service_saaskul.action_fsm_project_task_to_invoice',
    'field_service_saaskul.action_fsm_project_task_to_quotation_issue',
    'field_service_saaskul.action_fsm_store_material_request_pending',
    'field_service_saaskul.action_fsm_store_do_pending',
    'field_service_saaskul.action_fsm_store_do_issued',
    'field_service_saaskul.action_fsm_timesheet_analysis_monitor',
)
_WORKFLOW_NEXT_STAGE = {
    'registered': 'site_visited',
    'site_visited': 'qty_issued',
    'qty_issued': 'qty_approved',
    'qty_approved': 'in_progress',
    'in_progress': 'waiting_for_invoice',
}
# Status bar labels on the CRN form (project.task.state).
_CRN_STATE_KPIS = (
    ('registered', '1. Reg.'),
    ('site_visited', '2. Site Visit'),
    ('qty_issued', '3. QTN Issue'),
    ('qty_approved', '4. QTN Appvd'),
    ('in_progress', '5. WIP'),
    ('waiting_for_invoice', '6. Wait Inv'),
    ('job_completed', '7. FOC Done'),
    ('job_completed_invoiced', '8. Invoiced'),
    ('approved', '9. Approved'),
)


class CrnServiceDashboard(models.AbstractModel):
    _name = 'crn.service.dashboard'
    _description = 'Complaint Registration Management Dashboard'

    @api.model
    def get_dashboard_data(self):
        company = self.env.company
        return {
            'title': 'Complaint Registration Management',
            'subtitle': company.name,
            'kpis': self._dashboard_kpis(),
            'workflow': self._workflow_sections(),
            'action_templates': self._dashboard_action_templates(),
        }

    @api.model
    def _get_dashboard_action_template(self, xmlid):
        action = dict(self.env['ir.actions.actions']._for_xml_id(xmlid))
        domain = action.get('domain')
        if isinstance(domain, str):
            action['domain'] = safe_eval(domain)
        elif not domain:
            action['domain'] = []
        action.pop('res_id', None)
        return self._ensure_list_view_first(action)

    @api.model
    def _normalize_view_mode_for_web(self, mode):
        # Match web/controllers/main.py fix_view_modes: Odoo 14 web uses 'list', not 'tree'.
        return 'list' if mode in ('tree', 'list') else mode

    @api.model
    def _ensure_list_view_first(self, action):
        views = list(action.get('views') or [])
        if not views and action.get('view_mode'):
            views = [
                [False, mode.strip()]
                for mode in str(action.get('view_mode')).split(',')
                if mode.strip()
            ]
        if len(views) == 1 and self._action_view_mode(views[0]) == 'form':
            return action
        list_views = [view for view in views if self._action_view_mode(view) in ('tree', 'list')]
        form_views = [view for view in views if self._action_view_mode(view) == 'form']
        other_views = [
            view for view in views
            if self._action_view_mode(view) not in ('tree', 'list', 'form')
        ]
        if list_views:
            action['views'] = list_views + other_views + form_views
        else:
            action['views'] = [[False, 'list']] + other_views + (form_views or [[False, 'form']])
        action['views'] = [
            [
                self._action_view_id(view),
                self._normalize_view_mode_for_web(self._action_view_mode(view)),
            ]
            for view in action['views']
            if self._action_view_mode(view)
        ]
        action['view_mode'] = ','.join(view[1] for view in action['views'])
        return action

    @api.model
    def _action_view_mode(self, view):
        if isinstance(view, (list, tuple)) and len(view) > 1:
            return view[1]
        if isinstance(view, dict):
            return view.get('type')
        return False

    @api.model
    def _action_view_id(self, view):
        if isinstance(view, (list, tuple)) and view:
            return view[0] or False
        if isinstance(view, dict):
            return view.get('viewID') or view.get('view_id') or False
        return False

    @api.model
    def _dashboard_action_templates(self):
        templates = {}
        for xmlid in _DASHBOARD_ACTION_XMLIDS:
            try:
                templates[xmlid] = self._get_dashboard_action_template(xmlid)
            except ValueError:
                continue
        return templates

    @api.model
    def _fsm_base_domain(self):
        # Match All CRNs action; include empty-project CRNs (check_fsm / CRN%).
        return self.env['project.task']._cpabooks_all_crn_domain()

    @api.model
    def _open_crn_domain(self):
        return self._fsm_base_domain() + list(_OPEN_STAGE_DOMAIN)

    @api.model
    def _stage_domain(self, stage_key):
        return self._fsm_base_domain() + [('fsm_stage_group', '=', stage_key)]

    @api.model
    def _state_tasks(self, tasks, stage_key):
        return tasks.filtered(lambda task: task.fsm_stage_group == stage_key)

    @api.model
    def _tasks(self):
        return self.env['project.task'].sudo().search(self._fsm_base_domain())

    @api.model
    def _stage_tasks(self, tasks, stage_key):
        return tasks.filtered(lambda task: task.fsm_stage_group == stage_key)

    @api.model
    def _id_domain(self, records):
        return [('id', 'in', records.ids)] if records else [('id', '=', 0)]

    @api.model
    def _progress_done_tasks(self, tasks):
        return tasks.filtered(lambda task: (task.fsm_stage_progress or 0.0) >= 100.0)

    @api.model
    def _waiting_approval_tasks(self, tasks):
        Task = self.env['project.task']
        if 'approval_state' not in Task._fields:
            return tasks.browse()
        return tasks.filtered(lambda task: task.approval_state == 'pending' and not task.approved_by)

    @api.model
    def _count_overdue_open_tasks(self, open_tasks):
        """age_days is computed; filter in memory for dashboard counts and click domains."""
        return open_tasks.filtered(lambda task: (task.age_days or 0) >= 7)

    @api.model
    def _my_crn_domain(self, open_domain):
        user = self.env.user
        if 'user_id' in self.env['project.task']._fields:
            return open_domain + [('user_id', '=', user.id)]
        return open_domain

    @api.model
    def _dashboard_kpis(self):
        Task = self.env['project.task'].sudo()
        base_domain = self._fsm_base_domain()
        total = Task.search_count(base_domain)
        kpis = [
            self._kpi('All CRNs', total, 'fa-clipboard', _TASK_ACTION, []),
        ]
        for stage_key, label in _CRN_STATE_KPIS:
            kpis.append(
                self._kpi(
                    label,
                    Task.search_count(base_domain + [('fsm_stage_group', '=', stage_key)]),
                    'fa-circle-o',
                    _TASK_ACTION,
                    self._stage_domain(stage_key),
                ),
            )
        return kpis

    @api.model
    def _workflow_sections(self):
        Task = self.env['project.task'].sudo()
        tasks = self._tasks()
        open_domain = self._open_crn_domain()
        open_tasks = tasks.filtered(lambda task: task.stage not in _TERMINAL_STAGES)
        overdue_tasks = self._count_overdue_open_tasks(open_tasks)
        registered_tasks = self._stage_tasks(tasks, 'registered')
        site_visited_tasks = self._stage_tasks(tasks, 'site_visited')
        quotation_issued_tasks = self._stage_tasks(tasks, 'qty_issued')
        quotation_approved_tasks = self._stage_tasks(tasks, 'qty_approved')
        work_in_progress_tasks = self._stage_tasks(tasks, 'in_progress')
        waiting_invoice_tasks = tasks.filtered(lambda task: task.stage == 'waiting_for_invoice')
        foc_tasks = tasks.filtered(lambda task: task.stage == 'job_completed')
        invoiced_tasks = tasks.filtered(lambda task: task.stage == 'job_completed_invoiced')
        progress_done_tasks = self._progress_done_tasks(tasks)
        waiting_approval_tasks = self._waiting_approval_tasks(progress_done_tasks)
        sections = []

        sections.append({
            'id': 'registration',
            'title': 'Registration & Intake',
            'theme': 'intake',
            'items': [
                self._item('CRNs - registered', len(registered_tasks), _TASK_ACTION, 'pending',
                           self._stage_domain('registered')),
                self._item('CRNs - open (all stages)', len(open_tasks), _TASK_ACTION, 'progress', open_domain),
                self._item('My CRNs', Task.search_count(self._my_crn_domain(open_domain)),
                           'industry_fsm.project_task_action_fsm', 'progress', self._my_crn_domain(open_domain)),
            ],
        })

        sections.append({
            'id': 'site_quotation',
            'title': 'Site Visit & Quotation',
            'theme': 'quotation',
            'items': [
                self._item('Site visited', len(site_visited_tasks), _TASK_ACTION, 'progress',
                           self._stage_domain('site_visited')),
                self._item('Quotation issued', len(quotation_issued_tasks),
                           'field_service_saaskul.action_fsm_project_task_to_quotation_issue', 'pending',
                           self._stage_domain('qty_issued')),
                self._item('Quotation approved', len(quotation_approved_tasks), _TASK_ACTION, 'progress',
                           self._stage_domain('qty_approved')),
            ],
        })

        sections.append({
            'id': 'execution',
            'title': 'Execution & Materials',
            'theme': 'execution',
            'items': [
                self._item('Work in progress', len(work_in_progress_tasks), _TASK_ACTION, 'progress',
                           self._stage_domain('in_progress')),
                self._item('Overdue open CRNs', len(overdue_tasks), _ANALYSIS_ACTION, 'pending',
                           self._id_domain(overdue_tasks)),
            ],
        })

        if 'material.request.line' in self.env:
            Line = self.env['material.request.line'].sudo()
            sections[-1]['items'].append(
                self._item(
                    'Material request lines',
                    Line.search_count([('task_id', '!=', False)]),
                    'field_service_saaskul.action_fsm_store_material_request_pending',
                    'pending',
                ),
            )

        sections.append({
            'id': 'completion',
            'title': 'Completion & Billing',
            'theme': 'billing',
            'items': [
                self._item('Waiting for invoice', len(waiting_invoice_tasks),
                           'field_service_saaskul.action_fsm_project_task_to_invoice', 'pending',
                           self._fsm_base_domain() + [('fsm_stage_group', '=', 'waiting_for_invoice')]),
                self._item('Job completed (FOC)', len(foc_tasks), _TASK_ACTION, 'progress',
                           self._fsm_base_domain() + [('fsm_stage_group', '=', 'job_completed')]),
                self._item('Job completed & invoiced', len(invoiced_tasks), _TASK_ACTION, 'progress',
                           self._fsm_base_domain() + [('fsm_stage_group', '=', 'job_completed_invoiced')]),
                self._item('Approved / closed', len(progress_done_tasks), _ANALYSIS_ACTION, 'progress',
                           self._id_domain(progress_done_tasks)),
                self._item('Waiting for approval', len(waiting_approval_tasks), _TASK_ACTION, 'pending',
                           self._id_domain(waiting_approval_tasks)),
            ],
        })

        Picking = self.env['stock.picking'].sudo()
        cd = [('company_id', 'in', [False, self.env.company.id])]
        sections.append({
            'id': 'store',
            'title': 'Store & Delivery',
            'theme': 'store',
            'items': [
                self._item('Delivery - pending', Picking.search_count(cd + [
                    ('picking_type_code', '=', 'outgoing'),
                    ('state', 'not in', ('done', 'cancel')),
                ]), 'field_service_saaskul.action_fsm_store_do_pending', 'pending'),
                self._item('Delivery - done', Picking.search_count(cd + [
                    ('picking_type_code', '=', 'outgoing'),
                    ('state', '=', 'done'),
                ]), 'field_service_saaskul.action_fsm_store_do_issued', 'progress'),
            ],
        })

        sections.append({
            'id': 'timesheets',
            'title': 'Timesheets & Analysis',
            'theme': 'analysis',
            'items': [
                self._item('Timesheet lines (FSM)', self.env['account.analytic.line'].sudo().search_count([
                    ('task_id.is_fsm', '=', True),
                    ('company_id', 'in', [False, self.env.company.id]),
                ]), 'field_service_saaskul.action_fsm_timesheet_analysis_monitor', 'progress'),
                self._item('CRN task analysis', len(tasks), _ANALYSIS_ACTION, 'progress', []),
            ],
        })

        return sections

    @api.model
    def _kpi(self, label, value, icon, action_xmlid, domain=None):
        return {
            'label': label,
            'value': value,
            'action_xmlid': action_xmlid,
            'icon': icon,
            'domain': domain or [],
        }

    @api.model
    def _item(self, label, count, action_xmlid, status, domain=None):
        return {
            'label': label,
            'count': count,
            'action_xmlid': action_xmlid,
            'status': status,
            'domain': domain or [],
        }

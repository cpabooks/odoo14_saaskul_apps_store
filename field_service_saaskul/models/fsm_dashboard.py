# -*- coding: utf-8 -*-

from collections import OrderedDict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

_WORKFLOW_NEXT_STAGE = {
    'registered': 'site_visited',
    'site_visited': 'qty_issued',
    'qty_issued': 'qty_approved',
    'qty_approved': 'in_progress',
    'in_progress': 'waiting_for_invoice',
}


class ProjectTaskDashboard(models.Model):
    _inherit = 'project.task'

    @api.model
    def get_fsm_dashboard_data(self, filters=None):
        filters = self._normalize_fsm_dashboard_filters(filters or {})
        companies = self.env.user.company_ids or self.env.company
        company_ids = companies.ids
        if int(filters['company_id'] or 0):
            company_ids = [int(filters['company_id'])]

        today = fields.Date.context_today(self)
        start_date = False
        if filters['period'] != 'all':
            start_date = today - timedelta(days=int(filters['period']) - 1)

        task_domain = [('is_fsm', '=', True), ('company_id', 'in', company_ids)]
        if start_date:
            task_domain.append(('create_date', '>=', fields.Datetime.to_string(start_date)))
        tasks = self.search(task_domain)
        terminal_stages = ['job_completed', 'job_completed_invoiced', 'approved']
        active_tasks = tasks.filtered(lambda task: task.stage not in terminal_stages)
        overdue_tasks = tasks.filtered(lambda task: task.stage not in terminal_stages and task.age_days >= 7)
        waiting_invoice_tasks = tasks.filtered(lambda task: task.stage == 'waiting_for_invoice')
        registered_tasks = self._fsm_dashboard_stage_tasks(tasks, 'registered')
        site_visited_tasks = self._fsm_dashboard_stage_tasks(tasks, 'site_visited')
        quotation_issued_tasks = self._fsm_dashboard_stage_tasks(tasks, 'qty_issued')
        work_in_progress_tasks = self._fsm_dashboard_stage_tasks(tasks, 'in_progress')
        progress_done_tasks = tasks.filtered(lambda task: (task.fsm_stage_progress or 0.0) >= 100.0)
        waiting_approval_tasks = self._fsm_dashboard_waiting_approval_tasks(progress_done_tasks)

        timesheet_domain = [('task_id.is_fsm', '=', True), ('company_id', 'in', company_ids)]
        if start_date:
            timesheet_domain.append(('date', '>=', start_date))
        timesheet_groups = self.env['account.analytic.line'].read_group(
            timesheet_domain,
            ['fsm_cost_amount:sum', 'unit_amount:sum', 'employee_id'],
            ['employee_id'],
            lazy=False,
        )

        task_action = self._get_fsm_dashboard_action_template(
            'field_service_saaskul.action_fsm_task_analysis_monitor'
        )
        timesheet_action = self._get_fsm_dashboard_action_template(
            'field_service_saaskul.action_fsm_timesheet_analysis_monitor'
        )
        task_action['domain'] = list(task_domain)
        timesheet_action['domain'] = list(timesheet_domain)

        kpis = [
            {
                'label': 'Open CRN',
                'value': len(tasks),
                'subtitle': 'All CRNs',
                'tone': 'sand',
                'action_type': 'task',
                'domain': [],
            },
            {
                'label': 'Registered',
                'value': len(registered_tasks),
                'subtitle': 'Stage 1 done',
                'tone': 'ink',
                'action_type': 'task',
                'domain': self._fsm_dashboard_id_domain(registered_tasks),
            },
            {
                'label': 'Site Visited',
                'value': len(site_visited_tasks),
                'subtitle': 'Stage 2 done',
                'tone': 'teal',
                'action_type': 'task',
                'domain': self._fsm_dashboard_id_domain(site_visited_tasks),
            },
            {
                'label': 'Quotation Issued',
                'value': len(quotation_issued_tasks),
                'subtitle': 'Stage 3 done',
                'tone': 'amber',
                'action_type': 'task',
                'domain': self._fsm_dashboard_id_domain(quotation_issued_tasks),
            },
            {
                'label': 'Work In Progress',
                'value': len(work_in_progress_tasks),
                'subtitle': 'Stage 5 active',
                'tone': 'teal',
                'action_type': 'task',
                'domain': self._fsm_dashboard_id_domain(work_in_progress_tasks),
            },
            {
                'label': 'Waiting Invoice',
                'value': len(waiting_invoice_tasks),
                'subtitle': 'Completed pending invoice',
                'tone': 'amber',
                'action_type': 'task',
                'domain': [('fsm_stage_group', '=', 'waiting_for_invoice')],
            },
            {
                'label': 'Overdue',
                'value': len(overdue_tasks),
                'subtitle': 'Open for 7+ days',
                'tone': 'rose',
                'action_type': 'task',
                'domain': [('fsm_stage_group', 'not in', terminal_stages), ('age_days', '>=', 7)],
            },
            {
                'label': 'Approved',
                'value': len(progress_done_tasks),
                'subtitle': '100% progress CRNs',
                'tone': 'sage',
                'action_type': 'task',
                'domain': [('fsm_stage_progress', '>=', 100)],
            },
            {
                'label': 'Waiting for Approvals',
                'value': len(waiting_approval_tasks),
                'subtitle': '100% and pending approval',
                'tone': 'rose',
                'action_type': 'task',
                'domain': self._fsm_dashboard_id_domain(waiting_approval_tasks),
            },
            {
                'label': 'Material Cost',
                'value': sum(tasks.mapped('material_cost_total')),
                'subtitle': 'Issued material value',
                'tone': 'teal',
                'is_monetary': True,
                'action_type': 'task',
                'domain': [],
            },
            {
                'label': 'Timesheet Cost',
                'value': sum(tasks.mapped('timesheet_cost_total')),
                'subtitle': 'Engineer effort cost',
                'tone': 'ink',
                'is_monetary': True,
                'action_type': 'task',
                'domain': [],
            },
        ]

        stage_selection = OrderedDict(self._fields['stage'].selection)
        stage_chart = self._build_grouped_task_chart(
            tasks,
            'fsm_stage_group',
            stage_selection,
            task_domain_prefix=list(task_domain),
        )
        complaint_selection = OrderedDict(self._fields['complaint_type'].selection)
        complaint_chart = self._build_grouped_task_chart(
            tasks,
            'complaint_type',
            complaint_selection,
            task_domain_prefix=list(task_domain),
        )
        trend_chart = self._build_fsm_trend_chart(company_ids, today)
        team_chart = self._build_fsm_team_chart(timesheet_groups)
        spotlight_tasks = active_tasks.sorted(
            key=lambda task: (task.age_days or 0, task.timesheet_cost_total or 0.0), reverse=True
        )[:6]

        return {
            'filters': filters,
            'companies': [{'id': '0', 'name': 'All Companies'}] + [
                {'id': str(company.id), 'name': company.name} for company in companies
            ],
            'currency': {
                'symbol': self.env.company.currency_id.symbol,
                'position': self.env.company.currency_id.position,
            },
            'kpis': kpis,
            'stage_chart': stage_chart,
            'complaint_chart': complaint_chart,
            'trend_chart': trend_chart,
            'team_chart': team_chart,
            'spotlights': [
                {
                    'id': task.id,
                    'crn': task.task_seq,
                    'title': task.display_name,
                    'customer': task.partner_id.display_name or '-',
                    'stage': stage_selection.get(task.stage, task.stage),
                    'age_days': task.age_days,
                    'material_cost_total': task.material_cost_total,
                    'timesheet_cost_total': task.timesheet_cost_total,
                }
                for task in spotlight_tasks
            ],
            'task_action': task_action,
            'timesheet_action': timesheet_action,
        }

    def _normalize_fsm_dashboard_filters(self, filters):
        return {
            'period': str(filters.get('period') or '90'),
            'company_id': str(filters.get('company_id') or '0'),
        }

    def _get_fsm_dashboard_action_template(self, xmlid):
        action = dict(self.env['ir.actions.actions']._for_xml_id(xmlid))
        if isinstance(action.get('domain'), str):
            action['domain'] = safe_eval(action['domain'])
        return action

    def _fsm_dashboard_stage_tasks(self, tasks, stage_key):
        return tasks.filtered(lambda task: self._fsm_dashboard_is_stage_bucket(task, stage_key))

    def _fsm_dashboard_is_stage_done(self, task, stage_key):
        return (
            task._fsm_workflow_stage_is_applicable(stage_key)
            and task._fsm_workflow_stage_is_done(stage_key)
        )

    def _fsm_dashboard_is_stage_bucket(self, task, stage_key):
        if not self._fsm_dashboard_is_stage_done(task, stage_key):
            return False
        next_stage = _WORKFLOW_NEXT_STAGE.get(stage_key)
        return not next_stage or not self._fsm_dashboard_is_stage_done(task, next_stage)

    def _fsm_dashboard_waiting_approval_tasks(self, tasks):
        if 'approval_state' not in self._fields:
            return tasks.browse()
        return tasks.filtered(
            lambda task: task.approval_state == 'pending' and not task.approved_by
        )

    def _fsm_dashboard_id_domain(self, tasks):
        return [('id', 'in', tasks.ids)] if tasks else [('id', '=', 0)]

    def _build_grouped_task_chart(self, tasks, field_name, selection_map, task_domain_prefix=None):
        rows = []
        for key, label in selection_map.items():
            bucket = tasks.filtered(lambda task, field_name=field_name, key=key: task[field_name] == key)
            if not bucket:
                continue
            rows.append({
                'label': label,
                'value': len(bucket),
                'domain': (task_domain_prefix or []) + [(field_name, '=', key)],
            })
        return rows

    def _build_fsm_trend_chart(self, company_ids, today):
        created = []
        closed = []
        domains = []
        labels = []
        for offset in range(5, -1, -1):
            month_start = today.replace(day=1) - relativedelta(months=offset)
            month_end = month_start + relativedelta(months=1)
            labels.append(month_start.strftime('%b %Y'))
            created_domain = [
                ('is_fsm', '=', True),
                ('company_id', 'in', company_ids),
                ('create_date', '>=', fields.Datetime.to_string(month_start)),
                ('create_date', '<', fields.Datetime.to_string(month_end)),
            ]
            closed_domain = [
                ('is_fsm', '=', True),
                ('company_id', 'in', company_ids),
                ('date_end', '>=', month_start),
                ('date_end', '<', month_end),
            ]
            created.append(self.search_count(created_domain))
            closed.append(self.search_count(closed_domain))
            domains.append({
                'created': created_domain,
                'closed': closed_domain,
            })
        return {
            'labels': labels,
            'created': created,
            'closed': closed,
            'domains': domains,
        }

    def _build_fsm_team_chart(self, timesheet_groups):
        rows = []
        for group in timesheet_groups:
            if not group.get('employee_id'):
                continue
            rows.append({
                'label': group['employee_id'][1],
                'value': abs(group.get('fsm_cost_amount', 0.0)),
                'hours': group.get('unit_amount', 0.0),
                'domain': [('employee_id', '=', group['employee_id'][0])],
            })
        rows = sorted(rows, key=lambda row: row['value'], reverse=True)[:8]
        return rows

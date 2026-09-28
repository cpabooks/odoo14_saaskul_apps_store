# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval

# Progress weights aligned to CRN-style stages until invoicing (0–100).
_CAFM_STAGE_WEIGHTS = {
    'call_pending': 17.0,
    'quotation': 33.0,
    'work_ongoing': 50.0,
    'waiting_lpo': 67.0,
    'waiting_report': 83.0,
    'waiting_invoice': 90.0,
    'invoiced': 100.0,
}

_PIPELINE_STAGE_META = [
    ('call_pending', 'Call Registered', '#14532d'),
    ('quotation', 'Quotation / VAR Approval', '#166534'),
    ('work_ongoing', 'Work in Progress', '#15803d'),
    ('waiting_lpo', 'Waiting LPO', '#16a34a'),
    ('waiting_report', 'Waiting Report / Delivery', '#22c55e'),
    ('waiting_invoice', 'Waiting Invoice', '#4ade80'),
    ('invoiced', 'Invoiced & Closed', '#86efac'),
]

# Dashboard call KPI/workflow drill opens the Call Register list (table), not form.
_CALL_LIST_ACTION = 'cpabooks_cafm.action_cafm_call_register'


class CafmDashboard(models.AbstractModel):
    _name = 'cafm.dashboard'
    _description = 'CAFM Operations Dashboard'

    @api.model
    def get_dashboard_data(self):
        company = self.env.company
        return {
            'title': 'CAFM Operations Dashboard',
            'eyebrow': company.name or 'Green City FM',
            'subtitle': 'Facility management — AMC, calls, VAR, materials & billing',
            'completion': self._completion_kpi(),
            'charts': self._performance_charts(),
            'kpis': self._dashboard_kpis(),
            'workflow': self._workflow_sections(),
        }

    def _today(self):
        return fields.Date.context_today(self)

    def _amc_call_date_domain(self, date_from, date_to, extra=None):
        domain = [
            ('call_type', '=', 'amc'),
            ('call_date', '>=', date_from),
            ('call_date', '<=', date_to),
        ]
        if extra:
            domain += extra
        return domain

    def _count_amc_calls(self, date_from, date_to, extra=None):
        return self._search_count(
            'maintenance.request',
            self._amc_call_date_domain(date_from, date_to, extra=extra),
            action_xmlid=_CALL_LIST_ACTION,
        )

    def _call_metric_bundle(self, date_from, date_to):
        return {
            'calls': self._count_amc_calls(date_from, date_to),
            'completed': self._count_amc_calls(
                date_from, date_to, extra=[('work_status', '=', 'closed')],
            ),
            'in_progress': self._count_amc_calls(
                date_from,
                date_to,
                extra=[('work_status', 'in', ['work_ongoing', 'waiting_lpo', 'waiting_report'])],
            ),
            'invoiced': self._count_amc_calls(
                date_from, date_to, extra=[('invoice_id', '!=', False)],
            ),
            'pending': self._count_amc_calls(
                date_from, date_to, extra=[('work_status', '=', 'pending')],
            ),
        }

    def _chart_series_from_bundle(self, bundle):
        order = ('calls', 'completed', 'in_progress', 'invoiced')
        return [bundle[key] for key in order]

    @api.model
    def _performance_charts(self):
        today = self._today()
        cm_start = today.replace(day=1)
        lm_end = cm_start - relativedelta(days=1)
        lm_start = lm_end.replace(day=1)

        cy_start = today.replace(month=1, day=1)
        ly_start = cy_start - relativedelta(years=1)
        ly_end = today - relativedelta(years=1)

        labels = ['Calls', 'Completed', 'In Progress', 'Invoiced']
        lm_bundle = self._call_metric_bundle(lm_start, lm_end)
        cm_bundle = self._call_metric_bundle(cm_start, today)
        ly_bundle = self._call_metric_bundle(ly_start, ly_end)
        cy_bundle = self._call_metric_bundle(cy_start, today)

        return {
            'labels': labels,
            'month': {
                'title': 'Last Month vs Current Month',
                'subtitle': '%s – %s  vs  %s – %s' % (
                    lm_start.strftime('%b %Y'),
                    lm_end.strftime('%d %b'),
                    cm_start.strftime('%b %Y'),
                    today.strftime('%d %b'),
                ),
                'series': [
                    {
                        'label': 'Last Month',
                        'values': self._chart_series_from_bundle(lm_bundle),
                        'color': '#166534',
                    },
                    {
                        'label': 'Current Month',
                        'values': self._chart_series_from_bundle(cm_bundle),
                        'color': '#4ade80',
                    },
                ],
            },
            'year': {
                'title': 'Last Year (LY) vs Current Year (CY)',
                'subtitle': 'YTD %s – %s  vs  %s – %s' % (
                    ly_start.strftime('%b %Y'),
                    ly_end.strftime('%d %b %Y'),
                    cy_start.strftime('%b %Y'),
                    today.strftime('%d %b %Y'),
                ),
                'series': [
                    {
                        'label': 'Last Year (LY)',
                        'values': self._chart_series_from_bundle(ly_bundle),
                        'color': '#14532d',
                    },
                    {
                        'label': 'Current Year (CY)',
                        'values': self._chart_series_from_bundle(cy_bundle),
                        'color': '#86efac',
                    },
                ],
            },
        }

    @api.model
    def _completion_kpi(self):
        completed = self._search_count(
            'maintenance.request',
            [('call_type', '=', 'amc'), ('work_status', '=', 'closed')],
            action_xmlid=_CALL_LIST_ACTION,
        )
        pending = self._search_count(
            'maintenance.request',
            [('call_type', '=', 'amc'), ('work_status', '=', 'pending')],
            action_xmlid=_CALL_LIST_ACTION,
        )
        backlog = completed + pending
        rate = round((completed / backlog) * 100.0, 1) if backlog else 0.0
        return {
            'rate': rate,
            'completed': completed,
            'pending': pending,
            'label': 'Call completion rate',
            'hint': 'Closed AMC jobs vs pending call issues (open backlog)',
            'tiles': [
                {
                    'label': 'Completion rate',
                    'value': rate,
                    'suffix': '%',
                    'icon': 'fa-pie-chart',
                    'drill': self._list_action(
                        'Completed AMC calls',
                        'maintenance.request',
                        [('call_type', '=', 'amc'), ('work_status', '=', 'closed')],
                        action_xmlid=_CALL_LIST_ACTION,
                    ),
                },
                {
                    'label': 'Jobs completed',
                    'value': completed,
                    'suffix': '',
                    'icon': 'fa-check-circle',
                    'drill': self._list_action(
                        'Completed AMC calls',
                        'maintenance.request',
                        [('call_type', '=', 'amc'), ('work_status', '=', 'closed')],
                        action_xmlid=_CALL_LIST_ACTION,
                    ),
                },
                {
                    'label': 'Pending issues',
                    'value': pending,
                    'suffix': '',
                    'icon': 'fa-exclamation-circle',
                    'drill': self._list_action(
                        'Pending AMC calls',
                        'maintenance.request',
                        [('call_type', '=', 'amc'), ('work_status', '=', 'pending')],
                        action_xmlid=_CALL_LIST_ACTION,
                    ),
                },
            ],
        }

    def _cd(self, model_name):
        if model_name in self.env and 'company_id' in self.env[model_name]._fields:
            return [('company_id', 'in', [False, self.env.company.id])]
        return []

    def _merged_domain(self, res_model, domain, action_xmlid=None):
        merged = list(domain or [])
        if action_xmlid:
            action = self.env.ref(action_xmlid).sudo()
            base = action.domain or []
            if isinstance(base, str):
                base = safe_eval(base) if base else []
            if base:
                merged = base + merged
        return merged + self._cd(res_model)

    def _search_count(self, res_model, domain, action_xmlid=None):
        return self.env[res_model].search_count(
            self._merged_domain(res_model, domain, action_xmlid=action_xmlid)
        )

    def _tree_first_views(self, action):
        views = action.get('views') or []
        if not views and action.get('view_mode'):
            views = [[False, mode.strip()] for mode in action['view_mode'].split(',')]
        # Keep both legacy 'tree' and web-client 'list' as multi-record first.
        list_modes = ('tree', 'list')
        list_views = [view for view in views if view[1] in list_modes]
        other_views = [view for view in views if view[1] not in list_modes]
        ordered = list_views + other_views
        return ordered or [[False, 'list'], [False, 'form']]

    def _fix_view_modes_for_web(self, action):
        """Mirror web.fix_view_modes: frontend registry uses 'list', not 'tree'."""
        action = dict(action or {})
        action.pop('view_type', None)
        if action.get('view_mode'):
            action['view_mode'] = ','.join(
                mode if mode != 'tree' else 'list'
                for mode in action['view_mode'].split(',')
            )
        views = action.get('views') or []
        action['views'] = [
            [view_id, mode if mode != 'tree' else 'list']
            for view_id, mode in views
        ] or [[False, 'list'], [False, 'form']]
        # Never drop into create-form when opening dashboard drills.
        action.pop('res_id', None)
        return action

    def _clean_action_context(self, ctx):
        cleaned = dict(ctx or {})
        for key in list(cleaned.keys()):
            if cleaned[key] is None:
                cleaned.pop(key, None)
                continue
            if key.startswith('search_default_') or key == 'form_view_initial_mode' or key.startswith('default_'):
                cleaned.pop(key, None)
        return cleaned

    def _serialize_search_view_id(self, search_view_id):
        normalized = self._normalize_search_view_id(search_view_id)
        if not normalized:
            return False
        return [normalized, 'search']

    def _normalize_search_view_id(self, search_view_id):
        if isinstance(search_view_id, (list, tuple)):
            return search_view_id[0]
        return search_view_id or False

    def _list_action(self, name, res_model, domain, action_xmlid=None):
        result = {
            'name': name,
            'res_model': res_model,
            'domain': list(domain or []),
        }
        if action_xmlid:
            result['action_xmlid'] = action_xmlid
        return result

    def _call_register_drill_action(self, name, domain):
        """Hard-coded Call Register list action — avoids stale view_id / form-first menu actions."""
        tree_view = self.env.ref('cpabooks_cafm.view_cafm_call_register_tree')
        form_view = self.env.ref('cpabooks_cafm.view_cafm_amc_call_form')
        search_view = self.env.ref('cpabooks_cafm.view_cafm_amc_call_search')
        merged_domain = self._merged_domain(
            'maintenance.request',
            domain,
            action_xmlid=_CALL_LIST_ACTION,
        )
        return self._fix_view_modes_for_web({
            'type': 'ir.actions.act_window',
            'name': name or _('Call Register'),
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form',
            'views': [[tree_view.id, 'tree'], [form_view.id, 'form']],
            'search_view_id': [search_view.id, 'search'],
            'domain': merged_domain,
            'context': {},
            'target': 'current',
        })

    @api.model
    def get_drill_action(self, drill):
        """Build a web-client act_window that always opens the tree/list view first."""
        drill = drill or {}
        name = drill.get('name')
        res_model = drill.get('res_model')
        domain = drill.get('domain') or []
        action_xmlid = drill.get('action_xmlid')

        if action_xmlid == _CALL_LIST_ACTION:
            return self._call_register_drill_action(name, domain)

        ctx = {}
        if action_xmlid:
            action = self.env.ref(action_xmlid).sudo().read()[0]
            res_model = res_model or action.get('res_model')
            domain = self._merged_domain(res_model, domain, action_xmlid=action_xmlid)
            ctx = action.get('context') or {}
            if isinstance(ctx, str):
                ctx = safe_eval(ctx) if ctx else {}
            views = self._tree_first_views(action)
            search_view_id = self._serialize_search_view_id(action.get('search_view_id'))
            action_name = name or action.get('name')
        else:
            domain = self._merged_domain(res_model, domain)
            views = [[False, 'list'], [False, 'form']]
            search_view_id = False
            action_name = name or _('Records')

        result = {
            'type': 'ir.actions.act_window',
            'name': action_name,
            'res_model': res_model,
            'view_mode': 'list,form',
            'views': views,
            'domain': domain,
            'context': self._clean_action_context(ctx),
            'target': 'current',
        }
        if search_view_id:
            result['search_view_id'] = search_view_id
        return self._fix_view_modes_for_web(result)

    def _kpi(self, label, res_model, domain, icon, action_xmlid=None):
        return {
            'label': label,
            'value': self._search_count(res_model, domain, action_xmlid=action_xmlid),
            'icon': icon,
            'drill': self._list_action(label, res_model, domain, action_xmlid=action_xmlid),
        }

    def _item(self, label, res_model, domain, status='pending', action_xmlid=None):
        return {
            'label': label,
            'count': self._search_count(res_model, domain, action_xmlid=action_xmlid),
            'status': status,
            'drill': self._list_action(label, res_model, domain, action_xmlid=action_xmlid),
        }

    def _expiring_90_domain(self):
        return [
            ('contract_status', '=', 'active'),
            ('days_to_expiry', '>=', 0),
            ('days_to_expiry', '<=', 90),
        ]

    def _open_amc_call_domain(self):
        return [
            ('call_type', '=', 'amc'),
            ('work_status', 'not in', ['closed', 'cancelled']),
        ]

    def _call_bucket(self, call):
        status = call.work_status or 'pending'
        if status == 'cancelled':
            return None
        if status == 'pending':
            return 'call_pending'
        if status == 'work_ongoing':
            return 'work_ongoing'
        if status == 'waiting_lpo':
            return 'waiting_lpo'
        if status == 'waiting_report':
            return 'waiting_report'
        if status == 'closed':
            return 'invoiced' if call.invoice_id else 'waiting_invoice'
        return 'call_pending'

    def _var_bucket(self, var):
        status = var.status or 'waiting_approval'
        if status == 'cancelled':
            return None
        if status == 'waiting_approval':
            return 'quotation'
        if status == 'work_ongoing':
            return 'work_ongoing'
        if status == 'waiting_lpo':
            return 'waiting_lpo'
        if status == 'waiting_report':
            return 'waiting_report'
        if status == 'invoiced':
            return 'invoiced'
        if status == 'closed':
            return 'invoiced' if var.invoice_id else 'waiting_invoice'
        return 'quotation'

    def _call_domain_for_bucket(self, bucket):
        mapping = {
            'call_pending': [('call_type', '=', 'amc'), ('work_status', '=', 'pending')],
            'work_ongoing': [('call_type', '=', 'amc'), ('work_status', '=', 'work_ongoing')],
            'waiting_lpo': [('call_type', '=', 'amc'), ('work_status', '=', 'waiting_lpo')],
            'waiting_report': [('call_type', '=', 'amc'), ('work_status', '=', 'waiting_report')],
            'waiting_invoice': [
                ('call_type', '=', 'amc'), ('work_status', '=', 'closed'), ('invoice_id', '=', False),
            ],
            'invoiced': [
                ('call_type', '=', 'amc'), ('work_status', '=', 'closed'), ('invoice_id', '!=', False),
            ],
        }
        return mapping.get(bucket, [('call_type', '=', 'amc'), ('work_status', '=', 'pending')])

    def _var_domain_for_bucket(self, bucket):
        mapping = {
            'quotation': [('status', '=', 'waiting_approval')],
            'work_ongoing': [('status', '=', 'work_ongoing')],
            'waiting_lpo': [('status', '=', 'waiting_lpo')],
            'waiting_report': [('status', '=', 'waiting_report')],
            'waiting_invoice': [('status', '=', 'closed'), ('invoice_id', '=', False)],
            'invoiced': [
                '|',
                ('status', '=', 'invoiced'),
                '&',
                ('status', '=', 'closed'),
                ('invoice_id', '!=', False),
            ],
        }
        return mapping.get(bucket, [('status', '=', 'waiting_approval')])

    @api.model
    def _pipeline_summary(self):
        Call = self.env['maintenance.request'].sudo()
        VarWork = self.env['cpabooks.cafm.var.work'].sudo()
        amc_calls = Call.search(self._merged_domain('maintenance.request', [('call_type', '=', 'amc')]))
        var_works = VarWork.search(self._merged_domain('cpabooks.cafm.var.work', []))

        bucket_counts = {key: {'amc': 0, 'var': 0} for key, _label, _color in _PIPELINE_STAGE_META}
        progress_values = []

        for call in amc_calls:
            bucket = self._call_bucket(call)
            if not bucket:
                continue
            bucket_counts[bucket]['amc'] += 1
            progress_values.append(_CAFM_STAGE_WEIGHTS[bucket])

        for var in var_works:
            bucket = self._var_bucket(var)
            if not bucket:
                continue
            bucket_counts[bucket]['var'] += 1
            progress_values.append(_CAFM_STAGE_WEIGHTS[bucket])

        weighted_avg = round(sum(progress_values) / len(progress_values), 1) if progress_values else 0.0
        total_records = len(progress_values)

        stages = []
        for key, label, color in _PIPELINE_STAGE_META:
            counts = bucket_counts[key]
            total = counts['amc'] + counts['var']
            segments = []
            if counts['amc']:
                segments.append({
                    'label': 'AMC Calls',
                    'count': counts['amc'],
                    'drill': self._list_action(
                        label, 'maintenance.request', self._call_domain_for_bucket(key),
                        action_xmlid=_CALL_LIST_ACTION,
                    ),
                })
            if counts['var']:
                segments.append({
                    'label': 'VAR Works',
                    'count': counts['var'],
                    'drill': self._list_action(
                        label, 'cpabooks.cafm.var.work', self._var_domain_for_bucket(key),
                        action_xmlid='cpabooks_cafm.action_cafm_var_work_report',
                    ),
                })
            stages.append({
                'key': key,
                'label': label,
                'color': color,
                'weight': _CAFM_STAGE_WEIGHTS[key],
                'count': total,
                'segments': segments,
            })

        return {
            'weighted_avg': weighted_avg,
            'total_records': total_records,
            'stages': stages,
        }

    @api.model
    def _dashboard_kpis(self):
        Call = 'maintenance.request'
        VarWork = 'cpabooks.cafm.var.work'
        Stock = 'cpabooks.cafm.stock.issue'
        Contract = 'cpabooks.cafm.contract'

        return [
            self._kpi('Open Work Items', Call, self._open_amc_call_domain(), 'fa-clipboard',
                      action_xmlid=_CALL_LIST_ACTION),
            self._kpi('Call Pending', Call, [
                ('call_type', '=', 'amc'), ('work_status', '=', 'pending'),
            ], 'fa-pencil-square-o', action_xmlid=_CALL_LIST_ACTION),
            self._kpi('Quotation / VAR', VarWork, [('status', '=', 'waiting_approval')], 'fa-file-text-o',
                      action_xmlid='cpabooks_cafm.action_cafm_var_work_approval'),
            self._kpi('Work in Progress', Call, [
                ('call_type', '=', 'amc'), ('work_status', '=', 'work_ongoing'),
            ], 'fa-wrench', action_xmlid=_CALL_LIST_ACTION),
            self._kpi('Waiting LPO', Call, [
                ('call_type', '=', 'amc'), ('work_status', '=', 'waiting_lpo'),
            ], 'fa-hourglass-half', action_xmlid=_CALL_LIST_ACTION),
            self._kpi('Waiting Invoice', Call, [
                ('call_type', '=', 'amc'), ('work_status', '=', 'waiting_report'),
            ], 'fa-money', action_xmlid=_CALL_LIST_ACTION),
            self._kpi('Material Draft', Stock, [('state', '=', 'draft')], 'fa-cubes'),
            self._kpi('Active AMC', Contract, [('contract_status', '=', 'active')], 'fa-file-text-o',
                      action_xmlid='cpabooks_cafm.action_cpabooks_cafm_amc'),
        ]

    @api.model
    def _workflow_sections(self):
        Call = 'maintenance.request'
        VarWork = 'cpabooks.cafm.var.work'
        Stock = 'cpabooks.cafm.stock.issue'
        Contract = 'cpabooks.cafm.contract'
        Order = 'cpabooks.cafm.contract.order'

        sections = [
            {
                'id': 'intake',
                'title': 'Registration & Calls',
                'theme': 'intake',
                'items': [
                    self._item('AMC calls — pending', Call, [
                        ('call_type', '=', 'amc'), ('work_status', '=', 'pending'),
                    ], 'pending', action_xmlid=_CALL_LIST_ACTION),
                    self._item('AMC calls — open', Call, self._open_amc_call_domain(), 'progress',
                               action_xmlid=_CALL_LIST_ACTION),
                    self._item('All AMC calls', Call, [('call_type', '=', 'amc')], 'progress',
                               action_xmlid=_CALL_LIST_ACTION),
                    self._item('Active AMC contracts', Contract, [('contract_status', '=', 'active')], 'progress',
                               action_xmlid='cpabooks_cafm.action_cpabooks_cafm_amc'),
                ],
            },
            {
                'id': 'quotation',
                'title': 'Quotation & VAR',
                'theme': 'quotation',
                'items': [
                    self._item('VAR — waiting approval', VarWork, [('status', '=', 'waiting_approval')], 'pending',
                               action_xmlid='cpabooks_cafm.action_cafm_var_work_approval'),
                    self._item('VAR — work ongoing', VarWork, [('status', '=', 'work_ongoing')], 'progress',
                               action_xmlid='cpabooks_cafm.action_cafm_var_work_ongoing'),
                    self._item('VAR — waiting LPO', VarWork, [('status', '=', 'waiting_lpo')], 'pending',
                               action_xmlid='cpabooks_cafm.action_cafm_var_waiting_lpo'),
                    self._item('All VAR works', VarWork, [], 'progress',
                               action_xmlid='cpabooks_cafm.action_cafm_var_work_report'),
                ],
            },
            {
                'id': 'execution',
                'title': 'Execution & Materials',
                'theme': 'execution',
                'items': [
                    self._item('Calls — work ongoing', Call, [
                        ('call_type', '=', 'amc'), ('work_status', '=', 'work_ongoing'),
                    ], 'progress', action_xmlid=_CALL_LIST_ACTION),
                    self._item('VAR — work ongoing', VarWork, [('status', '=', 'work_ongoing')], 'progress',
                               action_xmlid='cpabooks_cafm.action_cafm_var_work_ongoing'),
                    self._item('Draft material issues', Stock, [('state', '=', 'draft')], 'pending'),
                ],
            },
            {
                'id': 'store',
                'title': 'Store & Material',
                'theme': 'store',
                'items': [
                    self._item('AMC stock issue', Stock, [
                        ('issue_type', '=', 'amc'), ('state', '!=', 'cancel'),
                    ], 'progress', action_xmlid='cpabooks_cafm.action_cafm_stock_issue_amc'),
                    self._item('VAR stock issue', Stock, [
                        ('issue_type', '=', 'var'), ('state', '!=', 'cancel'),
                    ], 'progress', action_xmlid='cpabooks_cafm.action_cafm_stock_issue_var'),
                    self._item('Stock transfer', Stock, [
                        ('issue_type', '=', 'transfer'), ('state', '!=', 'cancel'),
                    ], 'pending', action_xmlid='cpabooks_cafm.action_cafm_stock_transfer'),
                    self._item('Receipt notes', Stock, [
                        ('issue_type', '=', 'receipt'), ('state', '!=', 'cancel'),
                    ], 'pending', action_xmlid='cpabooks_cafm.action_cafm_stock_receipt_report'),
                ],
            },
            {
                'id': 'billing',
                'title': 'Completion & Billing',
                'theme': 'billing',
                'items': [
                    self._item('Calls — waiting report', Call, [
                        ('call_type', '=', 'amc'), ('work_status', '=', 'waiting_report'),
                    ], 'pending', action_xmlid=_CALL_LIST_ACTION),
                    self._item('Calls — closed no invoice', Call, [
                        ('call_type', '=', 'amc'), ('work_status', '=', 'closed'), ('invoice_id', '=', False),
                    ], 'pending', action_xmlid=_CALL_LIST_ACTION),
                    self._item('VAR — closed no invoice', VarWork, [
                        ('status', '=', 'closed'), ('invoice_id', '=', False),
                    ], 'pending', action_xmlid='cpabooks_cafm.action_cafm_var_work_report'),
                    self._item('VAR — invoiced / closed', VarWork, [
                        ('status', '=', 'closed'), ('invoice_id', '!=', False),
                    ], 'progress', action_xmlid='cpabooks_cafm.action_cafm_var_work_report'),
                ],
            },
        ]

        if Order in self.env:
            sections[3]['items'].append(
                self._item('Contract orders — pending invoice', Order, [
                    ('invoice_id', '=', False),
                    ('state', 'in', ['draft', 'order']),
                ], 'pending', action_xmlid='cpabooks_cafm.action_cpabooks_cafm_pending_orders_to_invoice'),
            )

        sections.append({
            'id': 'portfolio',
            'title': 'Portfolio & PPM',
            'theme': 'portfolio',
            'items': [
                self._item('Projects', 'project.project', [], 'progress',
                           action_xmlid='cpabooks_cafm.action_cpabooks_cafm_projects'),
                self._item('Units', 'cpabooks.cafm.unit', [], 'progress',
                           action_xmlid='cpabooks_cafm.action_cpabooks_cafm_units'),
                self._item('Active PPM', 'cpabooks.cafm.ppm', [('state', '=', 'active')], 'progress',
                           action_xmlid='cpabooks_cafm.action_cpabooks_cafm_ppm'),
                self._item('Expiring AMC (90d)', Contract, self._expiring_90_domain(), 'pending',
                           action_xmlid='cpabooks_cafm.action_cpabooks_cafm_amc'),
            ],
        })

        return sections

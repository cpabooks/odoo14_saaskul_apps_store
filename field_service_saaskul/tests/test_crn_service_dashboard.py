# -*- coding: utf-8 -*-

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCrnServiceDashboard(TransactionCase):

    def test_dashboard_action_templates_use_list_view_mode(self):
        Dashboard = self.env['crn.service.dashboard']
        data = Dashboard.get_dashboard_data()
        task_action = data['action_templates'].get('industry_fsm.project_task_action_all_fsm')
        self.assertTrue(task_action, 'FSM task action template missing from dashboard data')
        self.assertTrue(task_action.get('views'), 'dashboard action must include views')
        self.assertEqual(task_action['views'][0][1], 'list')
        self.assertNotIn('tree', task_action.get('view_mode', '').split(','))
        self.assertFalse(task_action.get('res_id'))

    def test_all_crns_kpi_matches_all_crns_list_domain(self):
        Dashboard = self.env['crn.service.dashboard']
        Task = self.env['project.task'].sudo()
        data = Dashboard.get_dashboard_data()
        all_kpi = next(kpi for kpi in data['kpis'] if kpi['label'] == 'All CRNs')
        list_domain = Task._cpabooks_all_crn_domain()
        self.assertEqual(all_kpi['value'], Task.search_count(list_domain))
        self.assertEqual(all_kpi['domain'], [])
        action_domain = data['action_templates']['industry_fsm.project_task_action_all_fsm']['domain']
        self.assertEqual(action_domain, list_domain)

    def test_stage_kpis_match_stage_counts(self):
        Dashboard = self.env['crn.service.dashboard']
        Task = self.env['project.task'].sudo()
        data = Dashboard.get_dashboard_data()
        base_domain = Dashboard._fsm_base_domain()
        for kpi in data['kpis'][1:]:
            stage_key = kpi['domain'][-1][2]
            expected = Task.search_count(base_domain + [('fsm_stage_group', '=', stage_key)])
            self.assertEqual(kpi['value'], expected, kpi['label'])

    def test_stage_kpis_use_status_bar_labels(self):
        Dashboard = self.env['crn.service.dashboard']
        data = Dashboard.get_dashboard_data()
        labels = [kpi['label'] for kpi in data['kpis']]
        self.assertEqual(labels[0], 'All CRNs')
        self.assertEqual(labels[1:], [
            '1. Reg.',
            '2. Site Visit',
            '3. QTN Issue',
            '4. QTN Appvd',
            '5. WIP',
            '6. Wait Inv',
            '7. FOC Done',
            '8. Invoiced',
            '9. Approved',
        ])
        reg_kpi = data['kpis'][1]
        self.assertEqual(reg_kpi['domain'][-1], ('fsm_stage_group', '=', 'registered'))

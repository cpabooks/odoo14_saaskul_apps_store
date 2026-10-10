# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests.common import TransactionCase


class TestProjectTask(TransactionCase):

    def test_fsm_task_default_order_shows_recent_updates_first(self):
        self.assertEqual(
            self.env['project.task']._order,
            'write_date desc, create_date desc, id desc',
        )

    def test_fsm_default_get_keeps_creator_without_default_project(self):
        defaults = self.env['project.task'].with_context(fsm_mode=True).default_get([
            'fsm_creator_uid', 'user_id', 'project_id',
        ])

        self.assertEqual(
            defaults.get('fsm_creator_uid'),
            self.env.user.id,
            "FSM task defaults should stamp the CRN creator.",
        )
        self.assertFalse(
            defaults.get('project_id'),
            "New CRN forms should not auto-select a default project.",
        )

    def test_fsm_create_does_not_assign_default_project(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM no default project regression',
        })

        self.assertFalse(task.project_id, "New CRN create should leave project empty until user selects one.")
        self.assertTrue(task.check_fsm, "FSM task creation should keep the CRN visible in FSM lists.")

    def test_crn_stays_in_all_crns_not_project_tasks(self):
        """CRNs belong in Field Service All CRNs, not Project → Tasks."""
        crn = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'CRN bifurcate list regression',
        })
        project = self.env['project.project'].create({
            'name': 'Regular Project bifurcate',
            'is_fsm': False,
        })
        regular = self.env['project.task'].create({
            'name': 'Regular task bifurcate',
            'project_id': project.id,
        })

        in_all_crns = self.env['project.task'].search(
            self.env['project.task']._cpabooks_all_crn_domain() + [('id', '=', crn.id)]
        )
        in_project_tasks = self.env['project.task'].search(
            self.env['project.task']._cpabooks_non_crn_domain() + [('id', 'in', [crn.id, regular.id])]
        )

        self.assertFalse(crn.project_id, 'Regression CRN must keep empty project.')
        self.assertEqual(in_all_crns, crn)
        self.assertEqual(in_project_tasks, regular)
        self.assertNotIn(crn, in_project_tasks)

    def test_fsm_create_preserves_entered_visited_by(self):
        employee = self.env['hr.employee'].create({'name': 'FSM create visit tech'})

        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM create visited by regression',
            'visited_by': employee.id,
        })

        self.assertEqual(task.visited_by, employee)

    def test_fsm_create_with_customer_without_project_stays_visible(self):
        partner = self.env['res.partner'].create({'name': 'FSM customer without project'})

        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM customer no project regression',
            'partner_id': partner.id,
        })

        self.assertFalse(task.project_id, "FSM customer tasks should not auto-fill a default project.")
        self.assertTrue(task.check_fsm, "FSM customer tasks should stay visible in FSM lists.")

    def test_fsm_create_does_not_auto_pick_field_service_project(self):
        self.env['project.project'].create({
            'name': 'Totalenergies Marketing UAE LLC',
            'is_fsm': True,
            'sequence': 0,
        })

        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM no auto project priority regression',
        })

        self.assertFalse(task.project_id)
        self.assertTrue(task.check_fsm)

    def test_regular_project_task_gets_tid_not_crn(self):
        project = self.env['project.project'].create({
            'name': 'Regular Project TID regression',
            'is_fsm': False,
        })
        task = self.env['project.task'].create({
            'name': 'Regular task TID regression',
            'project_id': project.id,
        })
        self.assertFalse(task.is_fsm)
        self.assertTrue(task.task_seq and task.task_seq != '/')
        self.assertFalse(
            str(task.task_seq).startswith('CRN'),
            'Regular tasks must not receive CRN numbering.',
        )

    def test_create_crn_from_task_opens_fsm_form(self):
        project = self.env['project.project'].create({
            'name': 'Source Project',
            'is_fsm': False,
        })
        task = self.env['project.task'].create({
            'name': 'Source task for CRN',
            'project_id': project.id,
        })
        action = task.action_create_crn_from_task()
        self.assertEqual(action['res_model'], 'project.task')
        self.assertTrue(action['context'].get('fsm_mode'))
        self.assertTrue(action['context'].get('create_crn'))
        self.assertEqual(action['context']['default_source_task_id'], task.id)

    def test_unlinked_crn_backfill_assigns_default_fsm_project(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM unlinked CRN backfill regression',
            'project_id': False,
            'task_seq': 'CRN/BACKFILL/2026/0001',
        })
        task.project_id = False

        self.env['project.task'].action_assign_default_project_to_unlinked_fsm_crns()

        self.assertTrue(task.project_id, "Unlinked CRNs should be attached to the default FSM project.")
        self.assertTrue(task.is_fsm, "Backfilled CRNs should be visible in FSM lists.")

    def test_fsm_create_drops_non_fsm_state(self):
        """A non-FSM state such as 'todo' must not crash FSM create."""
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM legacy state regression',
            'state': 'todo',
        })
        self.assertEqual(task.state, 'registered')

    def test_fsm_create_stamps_creator_without_forcing_assignee(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM creator stamp regression',
        })
        self.assertEqual(task.fsm_creator_uid, self.env.user)
        self.assertFalse(task.user_id)
        self.assertTrue(task.planned_date_begin)

    def test_fsm_crn_visible_to_creator_after_clearing_assignee(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM visibility regression',
            'user_id': self.env.user.id,
        })
        task.user_id = False
        found = self.env['project.task'].search([
            '|', '|',
            ('project_id.is_fsm', '=', True),
            ('check_fsm', '=', True),
            ('task_seq', '=like', 'CRN%'),
            ('fsm_creator_uid', '=', self.env.user.id),
            ('id', '=', task.id),
        ])
        self.assertEqual(found, task)

    def test_backfill_stamps_fsm_creator_uid(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM backfill creator regression',
        })
        task.fsm_creator_uid = False
        self.env['project.task'].action_backfill_fsm_crn_creators()
        self.assertEqual(task.fsm_creator_uid, task.create_uid)

    def test_fsm_complaint_type_options_match_invoice_types(self):
        self.assertEqual(
            self.env['project.task']._fields['complaint_type'].selection,
            [
                ('amc', 'AMC'),
                ('others', 'Others'),
                ('warranty', 'Warranty'),
                ('service', 'Service'),
                ('new_installation', 'New Installation'),
                ('new_inquiry', 'New Inquiry'),
                ('site_visit', 'Site Visit'),
            ],
        )
        task_model = self.env['project.task']
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('Warranty'), 'warranty')
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('Waranty'), 'warranty')
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('Service'), 'service')
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('New Installation'), 'new_installation')
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('New Inquiry'), 'new_inquiry')
        self.assertEqual(task_model._invoice_type_name_to_complaint_type('Site Visit'), 'site_visit')

    def test_new_crn_numbers_are_unique(self):
        task_a = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'CRN uniqueness A',
        })
        task_b = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'CRN uniqueness B',
        })
        self.assertTrue(task_a.task_seq.startswith('CRN'))
        self.assertTrue(task_b.task_seq.startswith('CRN'))
        self.assertNotEqual(task_a.task_seq, task_b.task_seq)

    def test_fsm_crn_number_keeps_crn_prefix(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM CRN prefix regression',
            'task_seq': 'CRN/CO1/2026/0001',
        })

        self.assertEqual(task.task_seq, 'CRN/CO1/2026/0001')

        task.write({'task_seq': 'TID-CRN/CO1/2026/0002'})

        self.assertEqual(task.task_seq, 'CRN/CO1/2026/0002')

    def test_fsm_task_counts_related_quotation(self):
        partner = self.env['res.partner'].create({'name': 'FSM Counter Customer'})
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM quotation counter regression',
            'partner_id': partner.id,
        })

        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'task_id': task.id,
        })

        self.assertEqual(task.qt_no, order, "The latest quotation should be linked back to the task.")
        self.assertEqual(task._get_fsm_related_orders(), order, "The task should find its related quotation.")
        self.assertEqual(task.fsm_all_quotation_count, 1, "The task should count its related quotation.")

    def test_fsm_task_ignores_old_reference_quotation_in_smart_counts(self):
        partner = self.env['res.partner'].create({'name': 'FSM old QT customer'})
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM old QT counter',
            'partner_id': partner.id,
        })
        old_order = self.env['sale.order'].create({
            'partner_id': partner.id,
        })
        task.write({'qt_no': old_order.id})

        self.assertEqual(task.fsm_all_quotation_count, 0)
        self.assertFalse(task._get_fsm_related_orders())

    def test_fsm_partner_onchange_keeps_project_manual(self):
        partner = self.env['res.partner'].create({'name': 'FSM manual project customer'})
        manual_project = self.env.ref('industry_fsm.fsm_project', raise_if_not_found=False)
        if not manual_project:
            manual_project = self.env['project.project'].create({
                'name': 'FSM manual project',
                'is_fsm': True,
            })
        task = self.env['project.task'].with_context(fsm_mode=True).new({
            'name': 'FSM customer keeps manual project',
            'project_id': manual_project.id,
        })

        task.partner_id = partner
        task._onchange_partner_id_auto_invoice()

        self.assertEqual(
            task.project_id,
            manual_project,
            "Selecting a customer should not auto-change the manually selected project.",
        )

    def test_fsm_partner_onchange_amc_customer_keeps_fields_manual(self):
        invoice_type = self.env['invoice.type'].search([('name', '=', 'AMC')], limit=1)
        if not invoice_type:
            invoice_type = self.env['invoice.type'].create({'name': 'AMC'})
        partner = self.env['res.partner'].create({
            'name': 'FSM AMC manual customer',
            'customer_invoice_type_id': invoice_type.id,
        })
        site = self.env['site.location'].create({'name': 'Manual Site'})
        contact = self.env['contact.person'].create({'name': 'Manual Contact'})
        task = self.env['project.task'].with_context(fsm_mode=True).new({
            'name': 'FSM AMC customer manual fields',
            'complaint_type': 'others',
            'site_location': site.id,
            'client_person': contact.id,
            'client_contact': '12345',
            'client_email': 'manual@example.com',
        })

        task.partner_id = partner
        task._onchange_partner_id_auto_invoice()

        self.assertFalse(task.invoice_id, "Selecting an AMC customer should not auto-select an invoice.")
        self.assertEqual(task.complaint_type, 'others')
        self.assertEqual(task.site_location, site)
        self.assertEqual(task.client_person, contact)
        self.assertEqual(task.client_contact, '12345')
        self.assertEqual(task.client_email, 'manual@example.com')

    def test_fsm_invoice_onchange_sets_invoice_project(self):
        if 'project_id' not in self.env['account.move']._fields:
            self.skipTest('account.move has no project_id field')
        invoice_type = self.env['invoice.type'].search([('name', '=', 'AMC')], limit=1)
        if not invoice_type:
            invoice_type = self.env['invoice.type'].create({'name': 'AMC'})
        partner = self.env['res.partner'].create({'name': 'FSM selectable invoice customer'})
        project = self.env.ref('industry_fsm.fsm_project', raise_if_not_found=False)
        if not project:
            project = self.env['project.project'].create({
                'name': 'FSM selectable invoice project',
                'is_fsm': True,
            })
        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_type': invoice_type.id,
            'project_id': project.id,
        })
        task = self.env['project.task'].with_context(fsm_mode=True).new({
            'name': 'FSM selectable manual invoice',
            'partner_id': partner.id,
            'complaint_type': 'amc',
            'invoice_id': invoice.id,
        })

        task._onchange_invoice_id()

        self.assertEqual(task.invoice_id, invoice, "Manual invoice selection should stay selected.")
        self.assertEqual(task.project_id, project, "Selecting an invoice should show its project.")
        self.assertEqual(task.complaint_type, 'amc', "Selecting an invoice should show its invoice type.")

    def test_reference_invoice_does_not_fill_stage6_or_jump_stage(self):
        """Stage 1 Reference Invoice must not load Stage 6 or mark WIP/Invoice done."""
        if 'invoice.type' not in self.env:
            self.skipTest('invoice.type model missing')
        invoice_type = self.env['invoice.type'].search([('name', '=', 'Warranty')], limit=1)
        if not invoice_type:
            invoice_type = self.env['invoice.type'].create({'name': 'Warranty'})
        partner = self.env['res.partner'].create({'name': 'FSM ref invoice stage isolation'})
        product = self.env['product.product'].create({
            'name': 'FSM Ref Inv Product',
            'type': 'service',
            'list_price': 100.0,
            'invoice_policy': 'order',
        })
        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_type': invoice_type.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        invoice.action_post()
        self.assertTrue(invoice.name and invoice.name != '/')

        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM ref invoice keeps stage 1',
            'partner_id': partner.id,
            'complaint_type': 'warranty',
            'invoice_id': invoice.id,
            'is_fsm': True,
            'check_fsm': True,
        })

        self.assertFalse(
            task.select_invoice,
            "Reference Invoice must not set Stage 6 select_invoice.",
        )
        self.assertFalse(
            task.fsm_invoice_number_display,
            "Reference Invoice must not fill Stage 6 Invoice No.",
        )
        self.assertFalse(
            (task.fsm_invoice_progress_status or '').strip(),
            "Reference Invoice must not set Stage 6 Invoice Status.",
        )
        self.assertFalse(
            task._fsm_has_completed_invoice(),
            "Reference Invoice must not count as Stage 6 completed invoice.",
        )
        self.assertEqual(
            task._get_fsm_stage_value(),
            'registered',
            "Selecting Reference Invoice must stay on Stage 1 (registered).",
        )
        self.assertFalse(
            task._fsm_workflow_stage_is_done('in_progress'),
            "Stage 5 WIP must stay pending after Reference Invoice only.",
        )
        self.assertFalse(
            task._fsm_workflow_stage_is_done('waiting_for_invoice'),
            "Stage 6 Invoice must stay pending after Reference Invoice only.",
        )

    def test_fsm_invoice_without_project_uses_project_not_available(self):
        if 'project_id' not in self.env['account.move']._fields:
            self.skipTest('account.move has no project_id field')
        invoice_type = self.env['invoice.type'].search([('name', '=', 'AMC')], limit=1)
        if not invoice_type:
            invoice_type = self.env['invoice.type'].create({'name': 'AMC'})
        partner = self.env['res.partner'].create({'name': 'FSM blank invoice project customer'})
        customer_project = self.env['project.project'].create({
            'name': 'Totalenergies Marketing UAE LLC',
            'is_fsm': True,
        })
        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_type': invoice_type.id,
            'project_id': False,
        })
        task = self.env['project.task'].with_context(fsm_mode=True).new({
            'name': 'FSM blank invoice project regression',
            'partner_id': partner.id,
            'project_id': customer_project.id,
            'invoice_id': invoice.id,
        })

        task._onchange_invoice_id()

        self.assertEqual(task.project_id, task._get_project_not_available_fsm_project(task.company_id))
        self.assertEqual(task.project_id.name, 'Project Not Available')
        self.assertTrue(task.is_fsm)

    def test_blank_invoice_project_backfill_overrides_customer_project(self):
        if 'project_id' not in self.env['account.move']._fields:
            self.skipTest('account.move has no project_id field')
        invoice_type = self.env['invoice.type'].search([('name', '=', 'AMC')], limit=1)
        if not invoice_type:
            invoice_type = self.env['invoice.type'].create({'name': 'AMC'})
        partner = self.env['res.partner'].create({'name': 'FSM blank invoice project backfill customer'})
        customer_project = self.env['project.project'].create({
            'name': 'Totalenergies Marketing UAE LLC',
            'is_fsm': True,
        })
        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_type': invoice_type.id,
            'project_id': False,
        })
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM blank invoice project backfill regression',
            'partner_id': partner.id,
            'invoice_id': invoice.id,
        })
        task.project_id = customer_project

        self.env['project.task'].action_assign_default_project_to_unlinked_fsm_crns()

        self.assertEqual(task.project_id, task._get_project_not_available_fsm_project(task.company_id))
        self.assertEqual(task.project_id.name, 'Project Not Available')
        self.assertTrue(task.is_fsm)

    def test_fsm_stage_new_task_stays_registered_with_default_assignee(self):
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM stage default REG',
        })
        self.assertEqual(
            task.stage,
            'registered',
            "New FSM tasks should show 1. REG until site visit is recorded.",
        )

    def test_fsm_stage_site_visit_requires_visited_by_and_date(self):
        employee = self.env['hr.employee'].create({'name': 'FSM visit tech'})
        partner = self.env['res.partner'].create({'name': 'FSM visit customer'})
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM site visit stage',
            'partner_id': partner.id,
        })
        self.assertEqual(task.stage, 'registered')
        task.write({'visited_by': employee.id})
        self.assertEqual(task.stage, 'registered')
        task.write({'visited_date': fields.Date.context_today(task)})
        self.assertEqual(task.stage, 'site_visited')

    def test_fsm_stage_next_action_issue_qt_stays_site_visited(self):
        employee = self.env['hr.employee'].create({'name': 'FSM QT tech'})
        partner = self.env['res.partner'].create({'name': 'FSM QT customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM issue QT stage',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
        })
        self.assertEqual(task.stage, 'site_visited')
        task.write({'next_action': 'issue'})
        self.assertEqual(task.stage, 'site_visited')

        self.env['sale.order'].create({
            'partner_id': partner.id,
            'task_id': task.id,
        })
        task.invalidate_cache()
        self.assertEqual(task.stage, 'qty_issued')

    def test_fsm_stage_next_action_foc_stays_site_visited(self):
        employee = self.env['hr.employee'].create({'name': 'FSM FOC to WIP tech'})
        partner = self.env['res.partner'].create({'name': 'FSM FOC customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM FOC WIP stage',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
        })
        self.assertEqual(task.stage, 'site_visited')
        task.write({'next_action': 'foc'})
        self.assertEqual(task.stage, 'site_visited')

    def test_fsm_stage_assigned_employee_and_date_sets_wip(self):
        employee = self.env['hr.employee'].create({'name': 'FSM assigned WIP tech'})
        partner = self.env['res.partner'].create({'name': 'FSM assigned WIP customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM assigned WIP',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
            'next_action': 'issue',
            'user_id': False,
        })
        self.assertEqual(task.stage, 'site_visited')
        task.write({'assign_date': today})
        self.assertEqual(task.stage, 'site_visited')
        task.write({'fsm_assigned_employee_id': employee.id})
        self.assertEqual(task.stage, 'in_progress')
        self.assertFalse(
            task.user_id,
            'A CRN assigned to an employee without a linked user should still be WIP.',
        )

    def test_fsm_stage_issue_end_date_sets_waiting_for_invoice(self):
        employee = self.env['hr.employee'].create({'name': 'FSM end date tech'})
        partner = self.env['res.partner'].create({'name': 'FSM end date customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM end date wait invoice',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
            'next_action': 'issue',
            'fsm_assigned_employee_id': employee.id,
            'assign_date': today,
        })
        self.assertEqual(task.stage, 'in_progress')
        task.write({'date_end': today})
        self.assertEqual(task.stage, 'waiting_for_invoice')

    def test_fsm_stage_foc_assigned_end_date_sets_foc_done(self):
        employee = self.env['hr.employee'].create({'name': 'FSM FOC done tech'})
        partner = self.env['res.partner'].create({'name': 'FSM FOC done customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM FOC done',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
            'next_action': 'foc',
            'fsm_assigned_employee_id': employee.id,
            'assign_date': today,
        })
        self.assertEqual(task.stage, 'in_progress')
        task.write({'date_end': today})
        self.assertEqual(task.stage, 'job_completed')

    def test_fsm_next_action_onchange_clears_assignee(self):
        task = self.env['project.task'].with_context(fsm_mode=True).new({
            'name': 'FSM clear assignee on next action',
            'user_id': self.env.user.id,
            'next_action': 'issue',
        })
        task._onchange_next_action_clear_assignee()
        self.assertFalse(task.user_id)

    def test_fsm_statusbar_wip_inverse_sets_next_action_foc_without_stage_change(self):
        employee = self.env['hr.employee'].create({'name': 'FSM WIP inverse tech'})
        partner = self.env['res.partner'].create({'name': 'FSM WIP inverse customer'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FSM WIP inverse',
            'partner_id': partner.id,
        })
        task.write({
            'visited_by': employee.id,
            'visited_date': today,
        })
        task.write({'state': 'in_progress'})
        task.invalidate_cache()
        self.assertEqual(task.next_action, 'foc')
        self.assertEqual(task.stage, 'site_visited')
        self.assertEqual(task.state, 'site_visited')

    def test_fsm_foc_after_qtn_approved_and_save_payload_fix(self):
        partner = self.env['res.partner'].create({'name': 'FOC after QTN approved'})
        employee = self.env['hr.employee'].create({'name': 'FOC after QTN tech'})
        today = fields.Date.context_today(self.env['project.task'])
        task = self.env['project.task'].with_context(fsm_mode=True).create({
            'name': 'FOC after QTN approved',
            'partner_id': partner.id,
            'visited_by': employee.id,
            'visited_date': today,
        })
        product = self.env['product.product'].search([('sale_ok', '=', True)], limit=1)
        if not product:
            self.skipTest('No sale_ok product in database')
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'task_id': task.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1,
                'price_unit': 1.0,
            })],
        })
        order.action_confirm()
        task.invalidate_cache()
        self.assertEqual(task.stage, 'qty_approved')
        task.write({'next_action': 'foc'})
        self.assertEqual(task.stage, 'qty_approved')

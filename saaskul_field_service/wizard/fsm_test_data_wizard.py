from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, fields, models


class FsmTestDataWizard(models.TransientModel):
    _name = 'cpabooks.fsm.test.data.wizard'
    _description = 'FSM Test Data Wizard'

    name = fields.Char(default='Field Service Test Data')
    last_result = fields.Text(readonly=True)

    def action_generate_test_data(self):
        self.ensure_one()
        self.action_clean_test_data()

        today = fields.Date.context_today(self)
        company = self.env.company
        project = self._create_project(company)
        invoice_types = self._create_invoice_types()
        products = self._create_products()
        employees = self._create_employees()
        complaints = self._create_complaints()
        sites = self._create_sites()
        contacts = self._create_contacts()
        partners = self._create_partners()

        scenarios = [
            ('Downtown Tower lobby AC no cooling', 'amc', 'registered', 0, 2.0, 0),
            ('Marina Heights pump room pressure drop', 'amc', 'site_visited', 1, 3.5, 1),
            ('Jumeirah villa water heater leak', 'warranty_service', 'in_progress', 1, 5.0, 2),
            ('Business Bay office CCTV outage', 'new_installation', 'qty_issued', 2, 4.0, 1),
            ('Al Quoz warehouse roller shutter fault', 'warranty_service', 'qty_approved', 2, 6.5, 2),
            ('Dubai Silicon Oasis server room AC alarm', 'amc', 'waiting_for_invoice', 3, 7.0, 3),
            ('Mirdif apartment electrical tripping', 'site_visit', 'job_completed', 3, 2.5, 1),
            ('Deira retail shop signage power issue', 'new_inquiry', 'approved', 4, 4.5, 2),
            ('Sharjah office pantry drain blockage', 'amc', 'in_progress', 4, 3.0, 1),
            ('Ajman warehouse emergency lighting test', 'site_visit', 'site_visited', 5, 2.0, 0),
            ('DIP factory compressor service request', 'new_inquiry', 'waiting_for_invoice', 5, 8.0, 3),
            ('Dubai Mall kiosk network rack overheating', 'warranty_service', 'approved', 6, 5.5, 2),
            ('Palm Jumeirah villa irrigation controller fault', 'amc', 'job_completed', 6, 3.5, 1),
            ('Ras Al Khaimah staff camp booster pump vibration', 'site_visit', 'in_progress', 7, 6.0, 2),
            ('Abu Dhabi branch access control reader failure', 'new_installation', 'qty_approved', 7, 7.5, 3),
        ]

        tasks = self.env['project.task']
        for index, scenario in enumerate(scenarios):
            task = self._create_task(
                index,
                scenario,
                today,
                project,
                partners[index % len(partners)],
                contacts[index % len(contacts)],
                sites[index % len(sites)],
                complaints[index % len(complaints)],
                employees[index % len(employees)],
                products,
                invoice_types,
            )
            tasks |= task

        self.last_result = _(
            'Created %s field service tasks with customers, sites, complaints, material requests, '
            'timesheets, quotations, and reference invoices where accounting setup allowed it.'
        ) % len(tasks)
        return self._reload_wizard()

    def action_clean_test_data(self):
        self.ensure_one()
        logs = self.env['cpabooks.fsm.test.data.record'].sudo().search([])
        removed = 0
        failed = 0
        for log in logs:
            if log.model_name in ('account.move.line', 'sale.order.line', 'stock.move'):
                log.unlink()
                continue
            try:
                model = self.env[log.model_name]
            except KeyError:
                log.unlink()
                continue
            record = model.sudo().browse(log.res_id).exists()
            if record:
                try:
                    self._prepare_record_for_unlink(record)
                    record.unlink()
                    removed += 1
                except Exception:
                    failed += 1
                    continue
            log.unlink()
        if failed:
            self.last_result = _('Removed %s test data records. %s records could not be removed and are still tracked.') % (
                removed, failed)
        else:
            self.last_result = _('Removed %s test data records.') % removed
        return self._reload_wizard()

    def _prepare_record_for_unlink(self, record):
        if record._name == 'project.task':
            self._unlink_task_plannings(record)
        if record._name == 'project.project' and self.env.registry.get('planning.slot'):
            self.env['planning.slot'].sudo().search([('project_id', '=', record.id)]).unlink()
        if record._name == 'account.move' and record.state == 'posted':
            try:
                record.button_draft()
            except Exception:
                pass
        if record._name == 'sale.order' and record.state not in ('draft', 'sent', 'cancel'):
            try:
                record.action_cancel()
            except Exception:
                pass

    def _unlink_task_plannings(self, task):
        if not self.env.registry.get('planning.slot'):
            return
        task_ids = task.ids
        if hasattr(task, '_get_all_subtasks'):
            task_ids += task._get_all_subtasks().ids
        self.env['planning.slot'].sudo().search([('task_id', 'in', task_ids)]).unlink()

    def _reload_wizard(self):
        return {
            'name': _('Run Test Data'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _track(self, record):
        if record:
            tracker = self.env['cpabooks.fsm.test.data.record'].sudo()
            existing = tracker.search([('model_name', '=', record._name), ('res_id', '=', record.id)], limit=1)
            if existing:
                return record
            tracker.create({
                'model_name': record._name,
                'res_id': record.id,
                'display_name': record.display_name,
            })
        return record

    def _get_or_create(self, model_name, domain, vals):
        model = self.env[model_name].sudo()
        record = model.search(domain, limit=1)
        if record:
            return self._track(record)
        return self._track(model.create(vals))

    def _create_project(self, company):
        analytic_name = 'FSM Test Data - Service Operations'
        analytic = self._get_or_create('account.analytic.account', [
            ('name', '=', analytic_name),
            ('company_id', 'in', [company.id, False]),
        ], {
            'name': analytic_name,
            'company_id': company.id,
        })
        return self._get_or_create('project.project', [
            ('name', '=', analytic_name),
            ('company_id', 'in', [company.id, False]),
        ], {
            'name': analytic_name,
            'is_fsm': True,
            'allow_timesheets': True,
            'allow_quotations': True,
            'allow_worksheets': True,
            'analytic_account_id': analytic.id,
            'company_id': company.id,
        })

    def _create_invoice_types(self):
        records = self.env['invoice.type']
        for name in ['AMC', 'Warranty/Service', 'New Installation', 'New Inquiry', 'Site Visit']:
            records |= self._get_or_create('invoice.type', [('name', '=', name)], {'name': name})
        return records

    def _create_products(self):
        product_model = self.env['product.product'].sudo()
        specs = [
            ('FSM Test Data - HVAC capacitor 45uF', 'product', 95.0, 160.0),
            ('FSM Test Data - Water pressure switch', 'product', 135.0, 240.0),
            ('FSM Test Data - CCTV power adaptor', 'product', 65.0, 120.0),
            ('FSM Test Data - LED emergency driver', 'product', 80.0, 150.0),
            ('FSM Test Data - Service labour hour', 'service', 0.0, 180.0),
        ]
        products = product_model
        for name, product_type, cost, price in specs:
            products |= self._get_or_create('product.product', [('name', '=', name)], {
                'name': name,
                'type': product_type,
                'standard_price': cost,
                'list_price': price,
            })
        return products

    def _create_employees(self):
        employees = self.env['hr.employee'].sudo()
        for name in ['Arun Mathew', 'Bilal Khan', 'Naveen George', 'Rashid Ali']:
            vals = {'name': 'FSM Test Data - %s' % name, 'company_id': self.env.company.id}
            if 'timesheet_cost' in self.env['hr.employee']._fields:
                vals['timesheet_cost'] = 85.0
            employees |= self._get_or_create('hr.employee', [
                ('name', '=', vals['name']),
                ('company_id', 'in', [self.env.company.id, False]),
            ], vals)
        return employees

    def _create_complaints(self):
        complaints = self.env['complaint.detail']
        for name in ['No cooling', 'Water leakage', 'Power tripping', 'Preventive maintenance', 'New installation request']:
            display_name = 'FSM Test Data - %s' % name
            complaints |= self._get_or_create('complaint.detail', [('name', '=', display_name)], {'name': display_name})
        return complaints

    def _create_sites(self):
        sites = self.env['site.location']
        for name in ['Dubai Marina', 'Business Bay', 'Al Quoz', 'Jumeirah', 'DIP']:
            display_name = 'FSM Test Data - %s' % name
            sites |= self._get_or_create('site.location', [('name', '=', display_name)], {'name': display_name})
        return sites

    def _create_contacts(self):
        contacts = self.env['contact.person']
        for name in ['Mohammed Faris', 'Sarah Thomas', 'Khalid Mansoor', 'Priya Nair', 'Omar Saeed']:
            display_name = 'FSM Test Data - %s' % name
            contacts |= self._get_or_create('contact.person', [('name', '=', display_name)], {'name': display_name})
        return contacts

    def _create_partners(self):
        partners = self.env['res.partner'].sudo()
        data = [
            ('Aster Facilities LLC', '04 555 1201', 'fm@asterfacilities.example'),
            ('Blue Line Properties', '04 555 1202', 'maintenance@blueline.example'),
            ('Crescent Retail Group', '04 555 1203', 'ops@crescentretail.example'),
            ('Delta Warehouse Services', '04 555 1204', 'admin@deltawarehouse.example'),
            ('Emirates Smart Homes', '04 555 1205', 'support@emiratessmarthomes.example'),
        ]
        for name, phone, email in data:
            display_name = 'FSM Test Data - %s' % name
            partners |= self._get_or_create('res.partner', [('name', '=', display_name)], {
                'name': display_name,
                'phone': phone,
                'email': email,
                'customer_rank': 1,
                'company_type': 'company',
                'company_id': self.env.company.id,
            })
        return partners

    def _create_task(self, index, scenario, today, project, partner, contact, site, complaint, employee, products,
                     invoice_types):
        title, complaint_type, stage_target, month_offset, hours, material_index = scenario
        start_date = today - relativedelta(months=month_offset) - timedelta(days=index % 5)
        task = self._track(self.env['project.task'].sudo().with_context(mail_create_nolog=True).create({
            'name': title,
            'project_id': project.id,
            'partner_id': partner.id,
            'client_person': contact.id,
            'client_contact': partner.phone,
            'client_email': partner.email,
            'site_location': site.id,
            'complaint_title': complaint.id,
            'complaint_details': '%s reported by site team. Test data for dashboards and service workflow.' % title,
            'complaint_type': complaint_type,
            'date_start': start_date,
            'is_fsm': True,
            'visited_by': employee.id if stage_target != 'registered' else False,
            'visited_date': start_date,
            'site_visit': 'Checked site condition, confirmed materials and work scope.',
            'user_id': self.env.user.id if stage_target in ('in_progress', 'waiting_for_invoice') else False,
            'assign_date': start_date if stage_target in ('in_progress', 'waiting_for_invoice') else False,
            'next_action': self._next_action_for_stage(stage_target),
            'date_end': start_date + timedelta(days=2) if stage_target in (
                'waiting_for_invoice', 'job_completed', 'approved') else False,
            'approved_by': self.env.user.id if stage_target == 'approved' else False,
        }))
        self._create_materials_and_issue(task, products, material_index)
        self._create_timesheet(task, employee, start_date, hours)
        self._create_sales_flow(task, products[-1], stage_target, start_date)
        self._create_reference_invoice(task, products[-1], invoice_types, start_date)
        return task

    def _next_action_for_stage(self, stage):
        if stage in ('waiting_for_invoice', 'qty_issued', 'qty_approved'):
            return 'issue'
        if stage in ('job_completed', 'approved'):
            return 'closed'
        return 'foc' if stage == 'in_progress' else False

    def _create_materials_and_issue(self, task, products, material_index):
        material_products = products.filtered(lambda product: product.type == 'product')
        selected = material_products[material_index % len(material_products)]
        quantity = 1.0 + (material_index % 3)
        issued_quantity = quantity if material_index % 4 else max(quantity - 1.0, 0.0)
        vals = {
            'task_id': task.id,
            'product_id': selected.id,
            'description': selected.display_name,
            'quantity': quantity,
        }
        if self._has_column('material_request_line', 'test_quantity_issued'):
            vals['test_quantity_issued'] = issued_quantity
        self._track(self.env['material.request.line'].sudo().create(vals))

    def _has_column(self, table_name, column_name):
        self.env.cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = %s
             LIMIT 1
        """, (table_name, column_name))
        return bool(self.env.cr.fetchone())

    def _create_timesheet(self, task, employee, date, hours):
        vals = {
            'name': 'FSM Test Data - Work completed for %s' % (task.task_seq or task.name),
            'date': date,
            'employee_id': employee.id,
            'project_id': task.project_id.id,
            'task_id': task.id,
            'unit_amount': hours,
            'amount': -(hours * 85.0),
            'company_id': task.company_id.id,
        }
        if 'account_id' in self.env['account.analytic.line']._fields and task.project_id.analytic_account_id:
            vals['account_id'] = task.project_id.analytic_account_id.id
        self._track(self.env['account.analytic.line'].sudo().create(vals))

    def _create_sales_flow(self, task, service_product, stage_target, date):
        if stage_target not in ('qty_issued', 'qty_approved'):
            return
        date_order = fields.Datetime.to_string(fields.Datetime.to_datetime(date))
        try:
            order = self._track(self.env['sale.order'].sudo().create({
                'partner_id': task.partner_id.id,
                'task_id': task.id,
                'client_order_ref': task.task_seq,
                'date_order': date_order,
                'order_line': [(0, 0, {
                    'product_id': service_product.id,
                    'name': 'Field service work for %s' % task.task_seq,
                    'product_uom_qty': 1.0,
                    'product_uom': service_product.uom_id.id,
                    'price_unit': 650.0,
                })],
            }))
        except Exception:
            return
        for line in order.order_line:
            self._track(line)
        if stage_target == 'qty_approved':
            try:
                order.action_confirm()
            except Exception:
                pass

    def _create_reference_invoice(self, task, service_product, invoice_types, date):
        invoice_type = invoice_types.filtered(
            lambda inv_type: task._normalized_selection_value(inv_type.name) in (
                task._normalized_selection_value(task.complaint_type),
                task._normalized_selection_value(dict(task._fields['complaint_type'].selection).get(task.complaint_type)),
            )
        )[:1]
        if not invoice_type:
            return
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': task.partner_id.id,
            'invoice_date': date,
            'invoice_type': invoice_type.id,
            'project_id': task.project_id.id,
            'invoice_origin': task.task_seq,
            'invoice_line_ids': [(0, 0, {
                'product_id': service_product.id,
                'name': 'Reference service invoice for %s' % task.task_seq,
                'quantity': 1.0,
                'price_unit': 950.0,
                'guaranteed': True,
            })],
        }
        try:
            invoice = self._track(self.env['account.move'].sudo().create(invoice_vals))
            for line in invoice.invoice_line_ids:
                self._track(line)
            invoice.action_post()
            task.sudo().write({'invoice_id': invoice.id})
        except Exception:
            invoice = self.env['account.move'].sudo().search([('invoice_origin', '=', task.task_seq)], limit=1)
            if invoice:
                invoice.unlink()

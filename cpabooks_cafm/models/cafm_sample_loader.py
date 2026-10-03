# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

DEMO_TAG = '[CAFM-DEMO]'
DEMO_COUNT = 18

# Facilities-management realistic PPM cadence (service_type, frequency, days_until_due)
PPM_DEMO_PROFILES = [
    ('hvac', 'monthly', 7),
    ('electrical', 'quarterly', 14),
    ('plumbing', 'quarterly', 21),
    ('fire_safety', 'half_yearly', 45),
    ('cleaning', 'monthly', 5),
    ('lift', 'half_yearly', 60),
    ('general', 'yearly', 90),
    ('hvac', 'monthly', 10),
    ('electrical', 'quarterly', 18),
    ('plumbing', 'quarterly', 25),
    ('fire_safety', 'yearly', 120),
    ('cleaning', 'monthly', 8),
    ('civil', 'quarterly', 30),
    ('general', 'half_yearly', 55),
    ('hvac', 'quarterly', 35),
    ('electrical', 'monthly', 12),
    ('plumbing', 'half_yearly', 50),
    ('fire_safety', 'quarterly', 28),
]

PPM_FREQUENCY_VALUES = {'monthly', 'quarterly', 'half_yearly', 'yearly'}

VOUCHER_TYPES = {
    'amc_contract': 'AMC Register',
    'amc_call': 'AMC Call',
    'var_work': 'VAR Work',
    'stock_amc': 'AMC Stock Issue',
    'stock_var': 'VAR Stock Issue',
    'stock_transfer': 'Stock Transfer',
    'stock_receipt': 'Stock Receipt',
    'ppm': 'PPM Schedule',
}


class CafmSampleLoader(models.TransientModel):
    _name = 'cpabooks.cafm.sample.loader'
    _description = 'CAFM Sample Loader'

    note = fields.Html(readonly=True, compute='_compute_note')

    @api.depends()
    def _compute_note(self):
        lines = [
            '<div><h3>CAFM Demo Data</h3>',
            '<p>Creates <strong>%d records per voucher / document type</strong>:</p><ul>' % DEMO_COUNT,
        ]
        for label in VOUCHER_TYPES.values():
            lines.append('<li>%s — %d rows</li>' % (label, DEMO_COUNT))
        lines.extend([
            '<li>Masters (location, group, contact, technician, manager, problem) — %d each</li>' % DEMO_COUNT,
            '<li>Projects, Units, Tenants — %d each</li>' % DEMO_COUNT,
            '</ul>',
            '<p>AMC calls are dated across <strong>last month, current month, last-year YTD, and current-year YTD</strong> so dashboard bar charts show bars.</p>',
            '<p>Tag: <code>%s</code>. Use <strong>Clean Demo Data</strong> before reload.</p></div>' % DEMO_TAG,
        ])
        html = ''.join(lines)
        for rec in self:
            rec.note = html

    def _tag(self, label):
        return '%s %s' % (DEMO_TAG, label)

    @classmethod
    def _ppm_frequency_value(cls, raw):
        """PPM uses yearly; AMC contracts use annually — never pass annually to PPM."""
        if raw == 'annually':
            return 'yearly'
        if raw in PPM_FREQUENCY_VALUES:
            return raw
        return 'quarterly'

    @classmethod
    def _ppm_profile(cls, index):
        profile = PPM_DEMO_PROFILES[index % len(PPM_DEMO_PROFILES)]
        service_type, frequency, due_days = profile
        return service_type, cls._ppm_frequency_value(frequency), due_days

    def _repair_demo_ppm_frequencies(self):
        """Fix partial loads from older loader code that wrote annually on PPM."""
        ppm_model = self.env['cpabooks.cafm.ppm']
        demo_ppms = ppm_model.search([('name', 'ilike', DEMO_TAG)])
        for ppm in demo_ppms:
            fixed = self._ppm_frequency_value(ppm.frequency)
            if ppm.frequency != fixed:
                ppm.write({'frequency': fixed})

    def _notify(self, title, message, ntype='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': True,
                'type': ntype,
            },
        }

    def _get_or_create_named_record(self, model_name, name, extra_values=None):
        record_model = self.env[model_name]
        record = record_model.search([('name', '=', name)], limit=1)
        values = dict(extra_values or {}, name=name)
        if record:
            record.write(values)
            return record
        return record_model.create(values)

    def _get_or_create_partner(self, name, email=False, mobile=False):
        partner_model = self.env['res.partner']
        partner = partner_model.browse()
        if email:
            partner = partner_model.search([('email', '=', email)], limit=1)
        if not partner and mobile:
            partner = partner_model.search([('mobile', '=', mobile)], limit=1)
        if not partner:
            partner = partner_model.search([('name', '=', name)], limit=1)
        values = {'name': name, 'email': email, 'mobile': mobile}
        if partner:
            partner.write(values)
            return partner
        return partner_model.create(values)

    def _get_or_create_project(self, code, name, location, partner, detail):
        project_model = self.env['project.project']
        project = project_model.search([('cafm_code', '=', code)], limit=1)
        values = {
            'name': name,
            'cafm_code': code,
            'cafm_location': location,
            'cafm_service_partner_id': partner.id,
            'cafm_contract_detail': detail,
        }
        if project:
            project.write(values)
            return project
        return project_model.create(values)

    def _get_or_create_unit(self, code, values):
        unit_model = self.env['cpabooks.cafm.unit']
        unit = unit_model.search([('code', '=', code)], limit=1)
        if unit:
            unit.write(values)
            return unit
        return unit_model.create(values)

    def _get_or_create_tenant(self, values):
        tenant_model = self.env['maintenance.tenant']
        tenant = tenant_model.browse()
        if values.get('email'):
            tenant = tenant_model.search([('email', '=', values.get('email'))], limit=1)
        if not tenant and values.get('mobile'):
            tenant = tenant_model.search([('mobile', '=', values.get('mobile'))], limit=1)
        if not tenant and values.get('name'):
            tenant = tenant_model.search([('name', '=', values.get('name'))], limit=1)
        if tenant:
            tenant.write(values)
            return tenant
        return tenant_model.create(values)

    def _demo_domain(self, field):
        return [(field, 'ilike', DEMO_TAG)]

    def _unlink_demo(self, model_name, field='notes', extra_domain=None):
        domain = list(self._demo_domain(field))
        if extra_domain:
            domain = extra_domain + domain
        records = self.env[model_name].search(domain)
        count = len(records)
        if records:
            records.unlink()
        return count

    @api.model
    def clean_demo_data(self):
        return self.create({}).action_clean_demo_data()

    @api.model
    def load_demo_data(self):
        return self.create({}).action_load_demo_data()

    def action_clean_demo_data(self):
        self.ensure_one()
        counts = {}
        counts['stock_issues'] = self._unlink_demo('cpabooks.cafm.stock.issue', 'remark')
        counts['var_works'] = self._unlink_demo('cpabooks.cafm.var.work', 'problem_description')
        counts['service_calls'] = self._unlink_demo('maintenance.request', 'address')
        counts['ppm'] = self._unlink_demo('cpabooks.cafm.ppm', 'name')
        counts['contracts'] = self._unlink_demo('cpabooks.cafm.contract', 'notes')

        tenant_recs = self.env['maintenance.tenant'].search([('email', 'ilike', '@cafm-demo.local')])
        counts['tenants'] = len(tenant_recs)
        tenant_recs.unlink()

        unit_records = self.env['cpabooks.cafm.unit'].search([('code', 'like', 'DEMO-U%')])
        counts['units'] = len(unit_records)
        unit_records.unlink()

        project_records = self.env['project.project'].search([('cafm_code', 'like', 'DEMO-P%')])
        counts['projects'] = len(project_records)
        project_records.unlink()

        for model_name, field in [
            ('cpabooks.cafm.contact.person', 'note'),
            ('cpabooks.cafm.customer.group', 'note'),
            ('cpabooks.cafm.location', 'note'),
            ('cpabooks.cafm.technician', 'note'),
            ('cpabooks.cafm.client.manager', 'note'),
            ('cpabooks.cafm.department', 'code'),
            ('cpabooks.cafm.problem.reported', 'name'),
        ]:
            key = model_name.split('.')[-1]
            counts[key] = self._unlink_demo(model_name, field)

        demo_partners = self.env['res.partner'].search([('email', 'ilike', '@cafm-demo.local')])
        counts['partners'] = len(demo_partners)
        demo_partners.unlink()

        legacy_contracts = self.env['cpabooks.cafm.contract'].search([
            ('notes', 'ilike', 'CAFM AMC Sample Data'),
        ])
        if legacy_contracts:
            counts['legacy_amc'] = len(legacy_contracts)
            legacy_contracts.unlink()

        summary = ', '.join('%s: %s' % (k, v) for k, v in sorted(counts.items()) if v)
        return self._notify(_('CAFM Demo Cleanup'), summary or _('No demo records found.'))

    def _load_demo_masters(self):
        city_names = [
            'Abu Dhabi', 'Dubai', 'Sharjah', 'Ajman', 'RAK',
            'Fujairah', 'UAQ', 'MBZ City', 'Khalifa City', 'Al Ain',
            'JLT', 'Marina', 'Business Bay', 'Mussafah', 'Reem Island',
            'Yas Island', 'Saadiyat', 'DIFC', 'Deira', 'JVC',
        ]
        buckets = {
            'locations': [],
            'groups': [],
            'contacts': [],
            'technicians': [],
            'managers': [],
            'problems': [],
        }
        for idx in range(DEMO_COUNT):
            n = idx + 1
            buckets['locations'].append(self._get_or_create_named_record(
                'cpabooks.cafm.location', self._tag('Location %02d' % n),
                {'note': self._tag('Location %02d' % n)},
            ))
            buckets['groups'].append(self._get_or_create_named_record(
                'cpabooks.cafm.customer.group', self._tag('Group %02d' % n),
                {'note': self._tag('Group %02d' % n)},
            ))
            buckets['contacts'].append(self._get_or_create_named_record(
                'cpabooks.cafm.contact.person', self._tag('Contact %02d' % n),
                {'mobile': '+9715000%05d' % (10000 + n), 'note': self._tag('Contact %02d' % n)},
            ))
            buckets['technicians'].append(self._get_or_create_named_record(
                'cpabooks.cafm.technician', self._tag('Technician %02d' % n),
                {'mobile': '+9715100%04d' % n, 'note': self._tag('Technician %02d' % n)},
            ))
            buckets['managers'].append(self._get_or_create_named_record(
                'cpabooks.cafm.client.manager', self._tag('Client Manager %02d' % n),
                {'email': 'manager%02d@cafm-demo.local' % n, 'note': self._tag('Manager %02d' % n)},
            ))
            buckets['problems'].append(self._get_or_create_named_record(
                'cpabooks.cafm.problem.reported', self._tag('Problem %02d' % n),
            ))
            if n <= 6:
                self._get_or_create_named_record(
                    'cpabooks.cafm.department', self._tag('Department %02d' % n),
                    {'code': self._tag('DEPT-%02d' % n)},
                )

        job_type = self.env['cpabooks.cafm.job.type'].search([('name', '=', 'AMC')], limit=1)
        if not job_type:
            job_type = self.env['cpabooks.cafm.job.type'].create({'name': 'AMC'})
        buckets['job_type'] = job_type
        buckets['work_types'] = self.env['cpabooks.cafm.work.type'].search([], limit=8)
        buckets['priorities'] = self.env['cpabooks.cafm.priority'].search([], order='sequence, id', limit=5)
        buckets['city_names'] = city_names
        return buckets

    def _ensure_demo_team(self):
        team = self.env['maintenance.team'].search([('name', '=', 'CAFM Demo Operations')], limit=1)
        if not team:
            team = self.env['maintenance.team'].create({
                'name': 'CAFM Demo Operations',
                'company_id': self.env.company.id,
            })
        return team

    def _load_base_portfolio(self, masters, team, today):
        """Projects, units, AMC contracts, PPM, tenants — DEMO_COUNT each."""
        contract_frequencies = ['monthly', 'quarterly', 'half_yearly', 'annually']
        manager_partner = self._get_or_create_partner(
            self._tag('Facilities Manager'), 'cafm.manager@cafm-demo.local', '+971500000001',
        )

        portfolio = {
            'projects': [],
            'units': [],
            'contracts': [],
            'tenants': [],
            'clients': [],
        }

        for idx in range(DEMO_COUNT):
            n = idx + 1
            client = self._get_or_create_partner(
                self._tag('Client %02d' % n),
                'client%02d@cafm-demo.local' % n,
                '+9715200%04d' % n,
            )
            location = masters['locations'][idx]
            group = masters['groups'][idx]
            contact = masters['contacts'][idx]
            city = masters['city_names'][idx]

            project = self._get_or_create_project(
                'DEMO-P%03d' % n,
                self._tag('Project %02d' % n),
                location.name,
                manager_partner,
                self._tag('Demo project %02d — %s' % (n, city)),
            )
            unit = self._get_or_create_unit('DEMO-U%03d' % n, {
                'name': 'Flat %03d' % (100 + n),
                'code': 'DEMO-U%03d' % n,
                'project_id': project.id,
                'unit_type': 'flat' if n % 4 else 'villa',
                'owner_id': client.id,
                'note': self._tag('Unit %02d' % n),
            })
            contract = self.env['cpabooks.cafm.contract'].search([
                ('notes', 'ilike', self._tag('AMC Contract %02d' % n)),
            ], limit=1)
            contract_values = {
                'client_id': client.id,
                'customer_group_id': group.id,
                'contact_person_id': contact.id,
                'contact_no': contact.mobile,
                'project_id': project.id,
                'project_location_id': location.id,
                'unit_id': unit.id,
                'contract_date': today - timedelta(days=15 * n),
                'contract_expiry': today + timedelta(days=365),
                'renewal_date': today + timedelta(days=365),
                'invoice_frequency': contract_frequencies[idx % len(contract_frequencies)],
                'total_contract_value': 15000.0 + (n * 1800),
                'contract_period_years': 1,
                'number_of_flats': 0,
                'unit_contract_type': 'flat',
                'sqft_qty': 1200.0 + (n * 60),
                'contract_status': 'active',
                'live_status': 'live',
                'notes': self._tag('AMC Contract %02d — %s' % (n, city)),
            }
            if contract:
                contract.write(contract_values)
            else:
                contract = self.env['cpabooks.cafm.contract'].create(contract_values)

            ppm = self.env['cpabooks.cafm.ppm'].search([
                ('name', 'ilike', DEMO_TAG),
                ('name', 'ilike', 'PPM %02d' % n),
            ], limit=1)
            ppm_service, ppm_frequency, ppm_due_days = self._ppm_profile(idx)
            ppm_values = {
                'name': self._tag('PPM %02d — %s / %s' % (
                    n, ppm_service.upper(), ppm_frequency.replace('_', ' ').title(),
                )),
                'project_id': project.id,
                'unit_id': unit.id,
                'frequency': ppm_frequency,
                'service_type': ppm_service,
                'start_date': today,
                'next_due_date': today + timedelta(days=ppm_due_days),
                'state': 'active',
            }
            if ppm:
                ppm.write(ppm_values)
            else:
                self.env['cpabooks.cafm.ppm'].create(ppm_values)

            tenant = self._get_or_create_tenant({
                'name': self._tag('Tenant %02d' % n),
                'email': 'tenant%02d@cafm-demo.local' % n,
                'mobile': '+9715300%04d' % n,
                'project_id': project.id,
                'cafm_unit_id': unit.id,
            })

            portfolio['projects'].append(project)
            portfolio['units'].append(unit)
            portfolio['contracts'].append(contract)
            portfolio['tenants'].append(tenant)
            portfolio['clients'].append(client)

        return portfolio

    def _demo_call_datetime(self, day, hour=10):
        """Combine a date with a stable time for call_date Datetime field."""
        return datetime.combine(day, time(hour=hour, minute=0, second=0))

    def _demo_chart_call_date(self, today, idx):
        """Spread demo AMC calls across dashboard chart windows (LM, CM, LY YTD, CY YTD)."""
        cm_start = today.replace(day=1)
        bucket = idx % 4
        slot = idx // 4
        if bucket == 0:
            day = max(1, min(today.day, 1 + (slot * 2) % max(today.day, 1)))
            return self._demo_call_datetime(cm_start + timedelta(days=day - 1), 9 + (slot % 6))
        if bucket == 1:
            lm_end = cm_start - timedelta(days=1)
            lm_start = lm_end.replace(day=1)
            day = max(1, min(lm_end.day, 3 + (slot * 3) % lm_end.day))
            return self._demo_call_datetime(lm_start + timedelta(days=day - 1), 11 + (slot % 5))
        if bucket == 2:
            ly_day = today - relativedelta(years=1)
            ly_day = ly_day.replace(day=max(1, min(ly_day.day, 5 + slot * 4)))
            return self._demo_call_datetime(ly_day, 13 + (slot % 4))
        months_back = 2 + (slot % 4)
        cy_day = today - relativedelta(months=months_back)
        cy_day = cy_day.replace(day=min(20, max(1, cy_day.day)))
        return self._demo_call_datetime(cy_day, 14 + (slot % 3))

    def _demo_chart_call_date_for_bucket(self, today, bucket, slot=0):
        """bucket: 0=current month, 1=last month, 2=last year YTD, 3=earlier current year."""
        return self._demo_chart_call_date(today, bucket + (slot * 4))

    def _demo_work_status_for_chart(self, idx):
        statuses = ['pending', 'work_ongoing', 'waiting_lpo', 'waiting_report', 'closed']
        return statuses[idx % len(statuses)]

    def _demo_income_account(self):
        revenue_type = self.env.ref('account.data_account_type_revenue', raise_if_not_found=False)
        domain = [
            ('company_id', '=', self.env.company.id),
            ('deprecated', '=', False),
        ]
        if revenue_type:
            domain.append(('user_type_id', '=', revenue_type.id))
        account = self.env['account.account'].search(domain, limit=1)
        if not account:
            account = self.env['account.account'].search([
                ('company_id', '=', self.env.company.id),
                ('deprecated', '=', False),
            ], limit=1)
        if not account:
            raise UserError(_('Please configure an income account before loading demo invoices.'))
        return account

    def _demo_invoice_for_call(self, call, sequence_no):
        if call.invoice_id:
            return call.invoice_id
        amount = 1200.0 + (sequence_no * 175)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': call.partner_id.id,
            'invoice_date': call.call_date.date() if call.call_date else fields.Date.context_today(self),
            'company_id': self.env.company.id,
            'currency_id': self.env.company.currency_id.id,
            'invoice_origin': call.name,
            'project_title': call.building or call.name,
            'invoice_line_ids': [(0, 0, {
                'name': self._tag('Chart demo invoice %02d' % sequence_no),
                'quantity': 1.0,
                'price_unit': amount,
                'account_id': self._demo_income_account().id,
            })],
        })
        call.write({'invoice_id': invoice.id})
        return invoice

    def _load_amc_calls(self, masters, portfolio, team, today):
        calls = []
        for idx in range(DEMO_COUNT):
            n = idx + 1
            project = portfolio['projects'][idx]
            unit = portfolio['units'][idx]
            contract = portfolio['contracts'][idx]
            tenant = portfolio['tenants'][idx]
            client = portfolio['clients'][idx]
            group = masters['groups'][idx]
            contact = masters['contacts'][idx]
            city = masters['city_names'][idx]
            work_type = masters['work_types'][idx % len(masters['work_types'])] if masters['work_types'] else False
            priority = masters['priorities'][idx % len(masters['priorities'])] if masters['priorities'] else False

            call = self.env['maintenance.request'].search([
                ('address', 'ilike', self._tag('AMC Call %02d' % n)),
            ], limit=1)
            call_values = {
                'name': self._tag('AMC Call %02d' % n),
                'call_type': 'amc',
                'maintenance_team_id': team.id,
                'partner_id': client.id,
                'tenant_id': tenant.id,
                'contract_id': contract.id,
                'l1_level_id': project.id,
                'l2_level_id': group.id,
                'cafm_project_id': project.id,
                'cafm_unit_id': unit.id,
                'building': project.name,
                'flat': unit.name,
                'work_type_id': work_type.id if work_type else False,
                'work_type': work_type.name if work_type else 'General',
                'job_type_id': masters['job_type'].id,
                'problem_reported_id': masters['problems'][idx].id,
                'problem': masters['problems'][idx].name,
                'problem_description': self._tag('AMC call problem %02d on %s' % (n, unit.code)),
                'priority_id': priority.id if priority else False,
                'technician_id': masters['technicians'][idx].id,
                'client_manager_id': masters['managers'][idx].id,
                'contact_name': contact.name,
                'contact_no': contact.mobile,
                'tenant_name': tenant.name,
                'property': 'CAFM',
                'address': self._tag('AMC Call %02d — %s / %s' % (n, city, unit.code)),
                'cafm_remark': self._tag('Demo AMC call %02d' % n),
                'work_status': self._demo_work_status_for_chart(idx),
                'required_materials': 'yes' if idx % 3 == 0 else 'no',
                'call_date': self._demo_chart_call_date(today, idx),
            }
            if call:
                call.write(call_values)
            else:
                call = self.env['maintenance.request'].create(call_values)
            if call.work_status == 'closed' and idx % 3 == 0:
                self._demo_invoice_for_call(call, n)
            calls.append(call)
        return calls

    def _load_chart_demo_calls(self, masters, portfolio, team, today):
        """Extra AMC calls so LM/CM/LY/CY dashboard bar charts show visible bars."""
        extra_profiles = [
            (1, 'closed', True),
            (1, 'work_ongoing', False),
            (1, 'waiting_lpo', False),
            (1, 'closed', True),
            (0, 'pending', False),
            (0, 'work_ongoing', False),
            (0, 'waiting_report', False),
            (0, 'closed', True),
            (2, 'closed', True),
            (2, 'work_ongoing', False),
            (2, 'waiting_lpo', False),
            (3, 'closed', False),
            (3, 'work_ongoing', False),
            (3, 'pending', False),
        ]
        bucket_slots = {0: 0, 1: 0, 2: 0, 3: 0}
        created = 0
        base = DEMO_COUNT
        for offset, (bucket, status, with_invoice) in enumerate(extra_profiles, start=1):
            n = base + offset
            idx = base + offset - 1
            slot = bucket_slots[bucket]
            bucket_slots[bucket] += 1
            label = ('CM', 'LM', 'LY', 'CY')[bucket]
            project = portfolio['projects'][idx % len(portfolio['projects'])]
            unit = portfolio['units'][idx % len(portfolio['units'])]
            contract = portfolio['contracts'][idx % len(portfolio['contracts'])]
            tenant = portfolio['tenants'][idx % len(portfolio['tenants'])]
            client = portfolio['clients'][idx % len(portfolio['clients'])]
            group = masters['groups'][idx % len(masters['groups'])]
            contact = masters['contacts'][idx % len(masters['contacts'])]
            work_type = masters['work_types'][idx % len(masters['work_types'])] if masters['work_types'] else False
            priority = masters['priorities'][idx % len(masters['priorities'])] if masters['priorities'] else False

            marker = self._tag('Chart %s Call %02d' % (label, offset))
            call = self.env['maintenance.request'].search([
                ('address', 'ilike', marker),
            ], limit=1)
            call_values = {
                'name': marker,
                'call_type': 'amc',
                'maintenance_team_id': team.id,
                'partner_id': client.id,
                'tenant_id': tenant.id,
                'contract_id': contract.id,
                'l1_level_id': project.id,
                'l2_level_id': group.id,
                'cafm_project_id': project.id,
                'cafm_unit_id': unit.id,
                'building': project.name,
                'flat': unit.name,
                'work_type_id': work_type.id if work_type else False,
                'work_type': work_type.name if work_type else 'General',
                'job_type_id': masters['job_type'].id,
                'problem_reported_id': masters['problems'][idx % len(masters['problems'])].id,
                'problem': masters['problems'][idx % len(masters['problems'])].name,
                'problem_description': self._tag('Chart seed call %s %02d' % (label, offset)),
                'priority_id': priority.id if priority else False,
                'technician_id': masters['technicians'][idx % len(masters['technicians'])].id,
                'client_manager_id': masters['managers'][idx % len(masters['managers'])].id,
                'contact_name': contact.name,
                'contact_no': contact.mobile,
                'tenant_name': tenant.name,
                'property': 'CAFM',
                'address': marker,
                'cafm_remark': self._tag('Dashboard chart seed %s' % label),
                'work_status': status,
                'required_materials': 'no',
                'call_date': self._demo_chart_call_date_for_bucket(today, bucket, slot),
            }
            if call:
                call.write(call_values)
            else:
                call = self.env['maintenance.request'].create(call_values)
            if with_invoice and status == 'closed':
                self._demo_invoice_for_call(call, n)
            created += 1
        return created

    def _load_var_works(self, masters, portfolio, calls, today):
        var_statuses = ['waiting_approval', 'work_ongoing', 'waiting_lpo', 'waiting_report', 'closed']
        created = 0
        for idx in range(DEMO_COUNT):
            n = idx + 1
            project = portfolio['projects'][idx]
            unit = portfolio['units'][idx]
            client = portfolio['clients'][idx]
            group = masters['groups'][idx]
            call = calls[idx % len(calls)]
            work_type = masters['work_types'][idx % len(masters['work_types'])] if masters['work_types'] else False
            status = var_statuses[idx % len(var_statuses)]

            var = self.env['cpabooks.cafm.var.work'].search([
                ('problem_description', 'ilike', self._tag('VAR Work %02d' % n)),
            ], limit=1)
            var_values = {
                'call_id': call.id,
                'partner_id': client.id,
                'cafm_unit_id': unit.id,
                'flat_villa': unit.name,
                'l2_level_id': group.id,
                'l3_level_id': project.id,
                'work_type_id': work_type.id if work_type else False,
                'problem_description': self._tag('VAR Work %02d — %s' % (n, status.replace('_', ' ').title())),
                'work_date': today - timedelta(days=idx % 20),
                'qt_date': today,
                'qt_amount': 3000.0 + (n * 150),
                'technician_id': masters['technicians'][idx].id,
                'status': status,
            }
            if var:
                var.write(var_values)
            else:
                self.env['cpabooks.cafm.var.work'].create(var_values)
            created += 1
        return created

    def _load_stock_issues(self, masters, portfolio, calls, today):
        stock_types = [
            ('amc', 'stock_amc'),
            ('var', 'stock_var'),
            ('transfer', 'stock_transfer'),
            ('receipt', 'stock_receipt'),
        ]
        counts = {}
        for issue_type, key in stock_types:
            counts[key] = 0
            for idx in range(DEMO_COUNT):
                n = idx + 1
                project = portfolio['projects'][idx]
                unit = portfolio['units'][idx]
                client = portfolio['clients'][idx]
                call = calls[idx % len(calls)]
                marker = self._tag('%s Stock %02d' % (issue_type.upper(), n))

                stock = self.env['cpabooks.cafm.stock.issue'].search([
                    ('remark', 'ilike', marker),
                ], limit=1)
                stock_values = {
                    'issue_type': issue_type,
                    'issue_date': today - timedelta(days=idx % 15),
                    'call_id': call.id,
                    'partner_id': client.id,
                    'cafm_unit_id': unit.id,
                    'flat_villa': unit.name,
                    'technician_id': masters['technicians'][idx].id,
                    'warehouse': self._tag('Store %s — %02d' % (issue_type, (n % 4) + 1)),
                    'remark': marker,
                    'state': 'done' if idx % 2 else 'draft',
                    'line_ids': [(0, 0, {
                        'item_name': self._tag('%s Item %02d' % (issue_type.upper(), n)),
                        'quantity': 1 + (idx % 5),
                        'uom': 'Nos',
                        'remark': self._tag('Line'),
                    })],
                }
                if stock:
                    stock.write({k: v for k, v in stock_values.items() if k != 'line_ids'})
                    if not stock.line_ids:
                        stock.write({'line_ids': stock_values['line_ids']})
                else:
                    self.env['cpabooks.cafm.stock.issue'].create(stock_values)
                counts[key] += 1
        return counts

    def action_load_demo_data(self):
        self.ensure_one()
        self._repair_demo_ppm_frequencies()
        masters = self._load_demo_masters()
        team = self._ensure_demo_team()
        today = fields.Date.context_today(self)

        portfolio = self._load_base_portfolio(masters, team, today)
        calls = self._load_amc_calls(masters, portfolio, team, today)
        chart_calls = self._load_chart_demo_calls(masters, portfolio, team, today)
        var_count = self._load_var_works(masters, portfolio, calls, today)
        stock_counts = self._load_stock_issues(masters, portfolio, calls, today)

        parts = [
            _('AMC Register: %d') % DEMO_COUNT,
            _('AMC Call: %d (+ %d chart seed)') % (len(calls), chart_calls),
            _('VAR Work: %d') % var_count,
            _('PPM: %d') % DEMO_COUNT,
        ]
        for key, label in VOUCHER_TYPES.items():
            if key.startswith('stock_') and key in stock_counts:
                parts.append('%s: %d' % (label, stock_counts[key]))

        message = _('Loaded %d demo rows per voucher type — %s') % (DEMO_COUNT, ' | '.join(parts))
        return self._notify(_('CAFM Demo Data Loaded'), message)

    def action_clean_sample_data(self):
        return self.action_clean_demo_data()

    def action_load_sample_data(self):
        return self.action_load_demo_data()

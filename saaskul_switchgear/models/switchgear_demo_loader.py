# -*- coding: utf-8 -*-

import logging
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class SwitchgearDemoLoader(models.AbstractModel):
    _name = 'switchgear.demo.loader'
    _description = 'Switchgear Demo Data Loader'

    _STACK_RESULT_KEYS = {
        'partners': 'partner',
        'leads': 'lead',
        'estimates': 'estimate',
        'sale_orders': 'sale_order',
        'projects': 'project',
        'boms': 'bom',
        'mos': 'mo',
        'quality_checks': 'quality_check',
        'purchase_orders': 'purchase_order',
        'design_documents': 'design_document',
        'tasks': 'task',
    }

    @contextmanager
    def _demo_savepoint(self):
        """Isolate a demo stack so a failure does not abort the whole batch."""
        with self.env.cr.savepoint():
            yield

    @contextmanager
    def _demo_optional(self):
        """Optional step: rollback on failure without aborting the outer transaction."""
        try:
            with self.env.cr.savepoint():
                yield
        except Exception as exc:
            _logger.info('Switchgear demo optional step skipped: %s', exc)

    @api.model
    def load_demo_batch(self, options):
        """Create N full switchgear/furniture demo stacks (standard processing cycle)."""
        profile = options.get('profile', 'switchgear')
        count = int(options.get('voucher_count', 25))
        company = self.env['res.company'].browse(options['company_id'])
        if not company:
            company = self.env.company
        create_timesheets = options.get('load_timesheets', True)
        create_pr = options.get('create_pr_when_no_stock', True)
        create_job_orders = options.get('create_job_orders', True)
        full_cycle = options.get('full_cycle', True)
        load_activities = options.get('load_activities', True)

        if count < 1 or count > 100:
            raise UserError(_('Voucher count must be between 1 and 100.'))

        self.env['switchgear.quality.team'].sudo()._get_default_team(company)
        catalog = self.with_company(company)._ensure_demo_catalog(profile, company)
        created = {
            'partners': [],
            'leads': [],
            'estimates': [],
            'sale_orders': [],
            'projects': [],
            'boms': [],
            'mos': [],
            'quality_checks': [],
            'purchase_orders': [],
            'design_documents': [],
            'tasks': [],
            'timesheet_lines': 0,
            'activities': 0,
            'errors': [],
        }

        for index in range(1, count + 1):
            try:
                with self._demo_savepoint():
                    stack = self._create_single_stack(
                        index, profile, company, catalog,
                        create_timesheets=create_timesheets,
                        create_pr=create_pr,
                        create_job_orders=create_job_orders,
                        full_cycle=full_cycle,
                        load_activities=load_activities,
                    )
            except Exception as exc:
                _logger.exception(
                    'Switchgear demo stack %s failed for %s: %s',
                    index, company.display_name, exc,
                )
                created['errors'].append({'index': index, 'error': str(exc)})
                continue
            for list_key, stack_key in self._STACK_RESULT_KEYS.items():
                val = stack.get(stack_key)
                if val:
                    created[list_key].append(val)
            created['timesheet_lines'] += stack.get('timesheet_lines', 0)
            created['activities'] += stack.get('activities', 0)
            for extra_est in stack.get('extra_estimates') or []:
                created['estimates'].append(extra_est)
            if stack.get('enquiry_lead'):
                created['leads'].append(stack['enquiry_lead'])
            for model_name in (
                'crm.lead', 'switchgear.estimate', 'sale.order',
                'mrp.production', 'stock.picking', 'project.project',
            ):
                if model_name in self.env:
                    self.env[model_name].flush()

        self._ensure_dashboard_kpi_minimums(company, min_count=6)
        self._backfill_demo_project_financials(company)
        return created

    @api.model
    def _company_has_usable_accounts(self, company):
        return self.env['account.account'].sudo().search_count([
            ('company_id', '=', company.id),
            ('deprecated', '=', False),
        ]) >= 2

    @api.model
    def _profile_label(self, profile, index):
        labels = {
            'switchgear': 'Switchgear',
            'furniture': 'Furniture',
        }
        return '%s Demo %02d' % (labels.get(profile, 'Demo'), index)

    @api.model
    def _ensure_demo_catalog(self, profile, company):
        Product = self.env['product.product'].sudo().with_company(company)
        Partner = self.env['res.partner'].sudo()
        prefix = 'DEMO-SG' if profile == 'switchgear' else 'DEMO-FN'

        def _product(xml_name, name, ptype='product', standard_price=100.0, list_price=150.0):
            ref = '%s-%s' % (prefix, xml_name)
            product = Product.search([
                ('default_code', '=', ref),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ], limit=1)
            if product:
                tmpl = product.product_tmpl_id.sudo()
                if tmpl.company_id != company:
                    tmpl.write({'company_id': company.id})
                return product
            tmpl = self.env['product.template'].sudo().create({
                'name': name,
                'default_code': ref,
                'type': 'service' if ptype == 'service' else 'product',
                'list_price': list_price,
                'standard_price': standard_price,
                'sale_ok': True,
                'purchase_ok': ptype != 'service',
                'company_id': company.id,
            })
            return tmpl.product_variant_id

        finished = _product(
            'FIN',
            '%s Panel Assembly' % ('Switchgear' if profile == 'switchgear' else 'Furniture Unit'),
            ptype='product',
            standard_price=5000,
            list_price=8000,
        )
        materials = []
        for mat_idx in range(1, 7):
            materials.append(_product(
                'MAT-%02d' % mat_idx,
                'Demo Material Component %02d' % mat_idx,
                standard_price=180.0 + (mat_idx * 35),
                list_price=220.0 + (mat_idx * 40),
            ))
        material = materials[0]
        labour = _product('LAB', 'Demo Labour Hours', ptype='service', standard_price=45, list_price=55)
        overhead = _product('OH', 'Demo Office Admin Overhead', ptype='service', standard_price=120, list_price=150)

        vendor = Partner.search([('name', '=', 'Demo Vendor (CPABooks)')], limit=1)
        if not vendor:
            vendor = Partner.create({
                'name': 'Demo Vendor (CPABooks)',
                'supplier_rank': 1,
                'company_id': company.id,
            })

        return {
            'finished': finished,
            'material': material,
            'materials': materials,
            'labour': labour,
            'overhead': overhead,
            'vendor': vendor,
        }

    @api.model
    def _create_single_stack(
        self, index, profile, company, catalog,
        create_timesheets=True, create_pr=True, create_job_orders=True,
        full_cycle=True, load_activities=True,
    ):
        demo_user_id = self._demo_user_for_company(company)
        if demo_user_id:
            self = self.with_user(demo_user_id).with_company(company)
        else:
            self = self.with_company(company)
        label = self._profile_label(profile, index)
        # Spread dashboard KPI states across stacks (each bucket gets samples over 25 loads).
        bucket = (index - 1) % 10
        confirm_so = bucket >= 5
        validate_delivery = full_cycle and bucket not in (1, 2)
        post_invoice = full_cycle and bucket not in (3, 4)
        post_payment = full_cycle and bucket == 9
        mo_progress = bucket in (6, 7)
        mo_done = bucket in (8, 9)
        mo_confirmed_only = bucket in (0, 1, 2, 3, 4, 5) and not mo_progress and not mo_done
        confirm_po = bucket not in (0,)

        Partner = self.env['res.partner'].sudo()
        partner_name = '%s Customer' % label
        partner = Partner.search([
            ('name', '=', partner_name),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        if not partner:
            partner = Partner.create({
                'name': partner_name,
                'company_id': company.id,
                'customer_rank': 1,
            })

        Lead = self.env['crm.lead'].sudo()
        existing_opp = Lead.search([
            ('name', '=', '%s Enquiry' % label),
            ('partner_id', '=', partner.id),
            ('type', '=', 'opportunity'),
            ('company_id', '=', company.id),
        ], limit=1)
        if existing_opp:
            return self._stack_from_existing_lead(
                existing_opp, partner, company, index, profile,
            )

        analytic = self.env['account.analytic.account'].sudo().create({
            'name': '%s Analytic' % label,
            'company_id': company.id,
            'partner_id': partner.id,
        })
        project_vals = {
            'name': '%s Project' % label,
            'partner_id': partner.id,
            'company_id': company.id,
        }
        if 'analytic_account_id' in self.env['project.project']._fields:
            project_vals['analytic_account_id'] = analytic.id
        project = self.env['project.project'].sudo().create(project_vals)

        demo_user = self._demo_user_for_company(company)

        enquiry_lead = self.env['crm.lead'].sudo().create({
            'name': '%s Open Enquiry' % label,
            'type': 'lead',
            'partner_id': partner.id,
            'expected_revenue': 8000.0 + (index * 250),
            'company_id': company.id,
            'user_id': demo_user,
        })

        lead = self.env['crm.lead'].sudo().create({
            'name': '%s Enquiry' % label,
            'type': 'opportunity',
            'partner_id': partner.id,
            'expected_revenue': 12000.0 + (index * 500),
            'company_id': company.id,
            'user_id': demo_user,
        })
        self._link_demo_project_crm(project, lead)

        estimate_vals = {
            'partner_id': partner.id,
            'date': fields.Date.today() + timedelta(days=index),
            'company_id': company.id,
            'project_id': project.id,
            'analytic_id': analytic.id,
            'opportunity_id': lead.id,
            'sales_person_id': demo_user,
            'profit_percent': 15.0,
            'description': 'Auto-loaded %s demo estimate' % profile,
        }
        estimate_vals.update(self._estimate_line_vals(catalog, index))
        estimate = self.env['switchgear.estimate'].sudo().create(estimate_vals)
        extra_estimates = []
        with self._demo_savepoint():
            draft_est = self._create_draft_estimate_sample(
                partner, project, analytic, lead, catalog, company, index,
            )
            extra_estimates.append(draft_est)
            extra_estimates.append(self._create_confirmed_only_estimate(
                partner, project, analytic, lead, catalog, company, index,
            ))

        estimate.action_job_confirm()
        estimate.action_approve()

        sale_order = False
        if confirm_so:
            with self._demo_optional():
                estimate.action_create_quotation()
            sale_order = estimate.sale_quotation_id
        else:
            with self._demo_savepoint():
                sale_order = self._create_demo_quotation_draft(
                    partner, project, analytic, estimate, catalog, company, index,
                )
        if sale_order:
            sale_order.sudo().write({
                'analytic_account_id': analytic.id,
                'project_id': project.id,
            })
            if hasattr(sale_order, 'job_quotation'):
                sale_order.job_quotation = True
            if confirm_so:
                try:
                    sale_order.action_confirm()
                except Exception:
                    sale_order.sudo().write({'state': 'sale'})

        bom = False
        mo = False
        qc = False
        po = False
        ts_count = 0

        if estimate.bom_product_id:
            with self._demo_savepoint():
                estimate.action_create_bom()
            bom = self.env['mrp.bom'].sudo().search([
                ('estimate_id', '=', estimate.id),
            ], limit=1, order='id desc')
            if bom:
                bom.sudo().write({
                    'project_id': project.id,
                    'partner_id': partner.id,
                    'sale_order_id': sale_order.id if sale_order else False,
                    'company_id': company.id,
                })
                if estimate.bom_product_id:
                    bom.sudo().write({
                        'product_id': estimate.bom_product_id.id,
                        'product_tmpl_id': estimate.bom_product_id.product_tmpl_id.id,
                        'product_qty': 1.0,
                        'product_uom_id': estimate.bom_product_id.uom_id.id,
                    })
                with self._demo_savepoint():
                    bom.sudo().with_company(company).action_create_mo()
                mo = self.env['mrp.production'].sudo().search([
                    ('bom_id', '=', bom.id),
                ], limit=1, order='id desc')
                if mo:
                    mo.sudo().write({
                        'project_id': project.id,
                        'partner_id': partner.id,
                    })
                    try:
                        mo.action_confirm()
                    except Exception:
                        pass
                    if mo_progress and mo.state == 'confirmed':
                        try:
                            mo.sudo().write({'state': 'progress'})
                        except Exception:
                            pass
                    elif mo_confirmed_only and mo.state not in ('confirmed', 'cancel', 'done'):
                        try:
                            mo.action_confirm()
                        except Exception:
                            pass
                    if mo_done and mo.state not in ('done', 'cancel'):
                        with self._demo_savepoint():
                            self._complete_demo_mo(mo, company)
                    if hasattr(mo, 'action_create_qc'):
                        try:
                            with self._demo_savepoint():
                                mo.action_create_qc()
                        except Exception as exc:
                            _logger.info(
                                'Switchgear demo: QC skipped for MO %s: %s',
                                mo.id, exc,
                            )
                        qc = self.env['switchgear.quality.check'].sudo().search([
                            ('production_id', '=', mo.id),
                        ], limit=1, order='id desc')
                        if qc and 'project_id' in qc._fields:
                            qc.project_id = project.id
                    if create_pr and mo.move_raw_ids:
                        with self._demo_savepoint():
                            po = self._maybe_create_demo_po(mo, catalog['vendor'], company)
                    self._maybe_create_demo_requisition(
                        project, partner, catalog, company, index,
                    )

        task = self._create_demo_project_task(
            project, label, company,
            amount=self._demo_project_contract_amount(lead, estimate, sale_order, index),
        )
        if create_timesheets:
            ts_count += self._create_demo_timesheets(
                project, analytic, catalog['labour'], index, company, task=task,
            )

        design_document = self._create_demo_design_document(
            partner, project, sale_order, estimate, company, index,
        )
        self._maybe_create_quality_alert(
            project, partner, company, index, product=catalog.get('finished'),
        )
        if po and confirm_po:
            with self._demo_savepoint():
                try:
                    po.button_confirm()
                except Exception as exc:
                    _logger.info('Switchgear demo: PO confirm skipped: %s', exc)

        delivery = False
        accounting = {}
        if full_cycle and sale_order:
            if validate_delivery:
                delivery = self._create_demo_delivery(sale_order, company)
            else:
                pickings = sale_order.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'outgoing'
                    and p.state not in ('done', 'cancel'),
                )
                delivery = pickings[:1]
        accounting = self._ensure_accounting_draft_samples(
            sale_order, partner, catalog['vendor'], company, index,
            project=project,
            analytic=analytic,
            post_invoice=post_invoice,
            post_payment=post_payment,
        ) or {}

        activity_count = 0
        if load_activities:
            activity_count = self._create_demo_activities_for_stack({
                'lead': lead,
                'enquiry_lead': enquiry_lead,
                'estimate': estimate,
                'sale_order': sale_order,
                'project': project,
                'task': task,
                'design_document': design_document,
                'bom': bom,
                'mo': mo,
                'quality_check': qc,
                'purchase_order': po,
                'delivery': delivery,
                'invoice': accounting.get('invoice'),
                'payment': accounting.get('payment'),
            }, company, index)

        return {
            'partner': partner,
            'lead': lead,
            'estimate': estimate,
            'extra_estimates': extra_estimates,
            'sale_order': sale_order,
            'project': project,
            'task': task,
            'design_document': design_document,
            'bom': bom,
            'mo': mo,
            'quality_check': qc,
            'purchase_order': po,
            'timesheet_lines': ts_count,
            'delivery': delivery,
            'invoice': accounting.get('invoice'),
            'payment': accounting.get('payment'),
            'enquiry_lead': enquiry_lead,
            'activities': activity_count,
        }

    @api.model
    def _record_supports_activities(self, record):
        if not record:
            return False
        return 'activity_ids' in record._fields

    @api.model
    def _get_demo_activity_type(self, kind='todo'):
        ActivityType = self.env['mail.activity.type'].sudo()
        labels = {
            'call': ['Call', 'Phone', 'Phonecall'],
            'email': ['Email', 'E-mail'],
            'meeting': ['Meeting'],
            'todo': ['To Do', 'Todo', 'To-Do', 'Reminder'],
        }
        for label in labels.get(kind, labels['todo']):
            found = ActivityType.search([('name', 'ilike', label)], limit=1)
            if found:
                return found
        return ActivityType.search([], limit=1)

    @api.model
    def _schedule_demo_activity(
        self, record, summary, days_offset=0, kind='todo',
        project=None, task=None, company=None,
    ):
        """Schedule one mail.activity on a document."""
        if not self._record_supports_activities(record):
            return False
        if 'mail.activity' not in self.env:
            return False
        activity_type = self._get_demo_activity_type(kind)
        if not activity_type:
            return False
        deadline = fields.Date.today() + timedelta(days=days_offset)
        vals = {
            'res_model_id': self.env['ir.model']._get_id(record._name),
            'res_id': record.id,
            'activity_type_id': activity_type.id,
            'summary': summary,
            'note': '<p>Switchgear demo scheduled activity.</p>',
            'date_deadline': deadline,
            'user_id': self._demo_user_for_company(company),
        }
        if company and 'company_id' in self.env['mail.activity']._fields:
            vals['company_id'] = company.id
        if project and 'project_id' in self.env['mail.activity']._fields:
            vals['project_id'] = project.id
        if task and 'task_id' in self.env['mail.activity']._fields:
            vals['task_id'] = task.id
        try:
            with self._demo_savepoint():
                self.env['mail.activity'].sudo().with_context(
                    skip_recurring_activity_generation=True,
                    mail_create_nolog=True,
                    tracking_disable=True,
                ).create(vals)
            return True
        except Exception as exc:
            _logger.info(
                'Switchgear demo: activity on %s(%s) skipped: %s',
                record._name, record.id, exc,
            )
            return False

    @api.model
    def _create_demo_activities_for_stack(self, stack, company, index):
        """Create scheduled activities on cycle documents for demo dashboards."""
        project = stack.get('project')
        task = stack.get('task')
        plans = [
            (stack.get('enquiry_lead') or stack.get('lead'), 'Follow up enquiry', -1, 'call'),
            (stack.get('estimate'), 'Review job estimate', 0, 'todo'),
            (stack.get('sale_order'), 'Confirm quotation with customer', 1, 'email'),
            (project, 'Project kick-off meeting', 2, 'meeting'),
            (task, 'Update task / next action', 0, 'todo'),
            (stack.get('design_document'), 'Submit design documents', 3, 'todo'),
            (stack.get('bom'), 'Verify BOM before production', 1, 'todo'),
            (stack.get('mo'), 'Monitor manufacturing order', 2, 'todo'),
            (stack.get('quality_check'), 'Complete quality check', 1, 'todo'),
            (stack.get('purchase_order'), 'Follow up LPO with vendor', -2, 'call'),
            (stack.get('delivery'), 'Prepare customer delivery', 1, 'todo'),
            (stack.get('invoice'), 'Send tax invoice to customer', 0, 'email'),
            (stack.get('payment'), 'Register customer payment', 2, 'todo'),
        ]
        created = 0
        for record, summary, offset, kind in plans:
            if self._schedule_demo_activity(
                record, summary, days_offset=offset, kind=kind,
                project=project, task=task, company=company,
            ):
                created += 1
        return created

    @api.model
    def _demo_move_line_vals(
        self, product, company, move_type, name, quantity, price_unit, analytic=None,
    ):
        Account = self.env['account.account'].sudo().with_company(company)
        fallback_type = 'income' if move_type in ('out_invoice', 'out_refund') else 'expense'
        account = Account.search([
            ('company_id', '=', company.id),
            ('deprecated', '=', False),
            ('user_type_id.type', '=', fallback_type),
        ], limit=1)
        if not account and product:
            if move_type in ('out_invoice', 'out_refund'):
                account = (
                    product.property_account_income_id
                    or product.categ_id.property_account_income_categ_id
                )
            else:
                account = (
                    product.property_account_expense_id
                    or product.categ_id.property_account_expense_categ_id
                )
        vals = {
            'name': name,
            'quantity': quantity,
            'price_unit': price_unit,
        }
        if account:
            vals['account_id'] = account.id
        if product:
            vals['product_id'] = product.id
        if analytic and 'analytic_account_id' in self.env['account.move.line']._fields:
            vals['analytic_account_id'] = analytic.id
        return vals

    @api.model
    def _material_line_count(self, index):
        """4–6 material lines per estimate (same BoM product, different components)."""
        return 4 + (index % 3)

    @api.model
    def _estimate_line_vals(self, catalog, index):
        materials = catalog.get('materials') or [catalog['material']]
        line_count = self._material_line_count(index)
        material_lines = []
        for line_idx in range(line_count):
            product = materials[line_idx % len(materials)]
            qty = 1.0 + (line_idx % 4)
            price = product.standard_price
            material_lines.append((0, 0, {
                'product_id': product.id,
                'quantity': qty,
                'price_unit': price,
                'uom_id': product.uom_id.id,
                'description': product.display_name,
            }))
        lab_qty = 1.0
        lab_hours = 4.0
        lab_price = catalog['labour'].list_price
        ovh_qty = 1.0
        ovh_price = catalog['overhead'].list_price
        return {
            'bom_product_id': catalog['finished'].id,
            'material_estimation_ids': material_lines,
            'labour_estimation_ids': [(0, 0, {
                'product_id': catalog['labour'].id,
                'quantity': lab_qty,
                'hours': lab_hours,
                'price_unit': lab_price,
                'uom_id': catalog['labour'].uom_id.id,
            })],
            'overhead_estimation_ids': [(0, 0, {
                'product_id': catalog['overhead'].id,
                'quantity': ovh_qty,
                'price_unit': ovh_price,
                'uom_id': catalog['overhead'].uom_id.id,
            })],
        }

    @api.model
    def _create_demo_quotation_draft(self, partner, project, analytic, estimate, catalog, company, index):
        """Draft/sent quotation for dashboard KPIs without confirming the sale order."""
        product = catalog['finished']
        SO = self.env['sale.order'].sudo()
        vals = {
            'partner_id': partner.id,
            'company_id': company.id,
            'analytic_account_id': analytic.id,
            'project_id': project.id,
            'job_estimate_id': estimate.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'price_unit': estimate.total_job_estimate or product.list_price,
            })],
        }
        if 'job_quotation' in SO._fields:
            vals['job_quotation'] = True
        so = SO.create(vals)
        if 'state' in SO._fields and so.state not in ('draft', 'sent'):
            try:
                so.write({'state': 'draft'})
            except Exception:
                pass
        estimate.sale_quotation_id = so.id
        return so

    @api.model
    def _create_confirmed_only_estimate(
        self, partner, project, analytic, lead, catalog, company, index,
    ):
        """Job estimate in confirmed state (dashboard: awaiting approval)."""
        vals = {
            'partner_id': partner.id,
            'date': fields.Date.today(),
            'company_id': company.id,
            'project_id': project.id,
            'analytic_id': analytic.id,
            'opportunity_id': lead.id,
            'bom_product_id': catalog['finished'].id,
            'sales_person_id': self.env.user.id,
            'profit_percent': 10.0,
            'description': 'Demo estimate awaiting approval %s' % index,
        }
        vals.update(self._estimate_line_vals(catalog, index))
        estimate = self.env['switchgear.estimate'].sudo().create(vals)
        estimate.action_job_confirm()
        return estimate

    @api.model
    def _create_draft_estimate_sample(self, partner, project, analytic, lead, catalog, company, index):
        vals = {
            'partner_id': partner.id,
            'date': fields.Date.today(),
            'company_id': company.id,
            'project_id': project.id,
            'analytic_id': analytic.id,
            'opportunity_id': lead.id,
            'bom_product_id': catalog['finished'].id,
            'sales_person_id': self.env.user.id,
            'profit_percent': 12.0,
            'description': 'Draft pipeline sample %s' % index,
        }
        vals.update(self._estimate_line_vals(catalog, index))
        estimate = self.env['switchgear.estimate'].sudo().create(vals)
        return estimate

    @api.model
    def _demo_partner_for_fillers(self, company, profile='switchgear'):
        partner = self._find_demo_partners(profile, company)[:1]
        if partner:
            return partner
        return self.env['res.partner'].sudo().create({
            'name': 'Switchgear Demo KPI Customer',
            'company_id': company.id,
            'customer_rank': 1,
        })

    @api.model
    def _ensure_dashboard_kpi_minimums(self, company, min_count=6):
        """Top up dashboard buckets that are often empty after partial demo loads."""
        if not self._company_has_usable_accounts(company):
            return
        company = company.sudo()
        cd = self._demo_company_domain(company)
        catalog = self._ensure_demo_catalog('switchgear', company)
        partner = self._demo_partner_for_fillers(company)
        vendor = catalog['vendor']

        SO = self.env['sale.order'].sudo()
        gap = min_count - SO.search_count(cd + [('state', 'in', ('draft', 'sent'))])
        for seq in range(max(gap, 0)):
            product = catalog['finished']
            try:
                with self._demo_savepoint():
                    SO.create({
                        'partner_id': partner.id,
                        'company_id': company.id,
                        'order_line': [(0, 0, {
                            'product_id': product.id,
                            'name': 'Demo quotation filler %s' % (seq + 1),
                            'product_uom_qty': 1.0,
                            'product_uom': product.uom_id.id,
                            'price_unit': product.list_price,
                        })],
                    })
            except Exception as exc:
                _logger.info('Switchgear demo KPI filler quotation skipped: %s', exc)

        MO = self.env['mrp.production'].sudo()
        Bom = self.env['mrp.bom'].sudo()
        bom = Bom.search([
            ('product_id', '=', catalog['finished'].id),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        gap = min_count - MO.search_count(cd + [
            ('state', 'not in', ('progress', 'done', 'cancel')),
        ])
        existing_mo_count = MO.search_count([('name', '=like', 'DEMO-MO-WAIT-%')])
        for seq in range(max(gap, 0)):
            try:
                with self._demo_savepoint():
                    mo_vals = {
                        'name': 'DEMO-MO-WAIT-%s' % (existing_mo_count + seq + 1),
                        'product_id': catalog['finished'].id,
                        'product_qty': 1.0,
                        'product_uom_id': catalog['finished'].uom_id.id,
                        'company_id': company.id,
                    }
                    if bom:
                        mo_vals['bom_id'] = bom.id
                    MO.create(mo_vals)
            except Exception as exc:
                _logger.info('Switchgear demo KPI filler MO skipped: %s', exc)

        done_gap = min_count - MO.search_count(cd + [('state', '=', 'done')])
        if done_gap > 0:
            self._ensure_demo_mo_done_minimums(company, min_count=done_gap)

        Move = self.env['account.move'].sudo()
        gap = min_count - Move.search_count(cd + [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ])
        drafts = Move.search(cd + [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'draft'),
        ], limit=max(gap, 0), order='id desc')
        for inv in drafts:
            try:
                with self._demo_savepoint():
                    inv.action_post()
            except Exception as exc:
                _logger.info('Switchgear demo KPI filler invoice post skipped: %s', exc)
        gap = min_count - Move.search_count(cd + [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ])
        for seq in range(max(gap, 0)):
            with self._demo_savepoint():
                inv = self._create_demo_customer_invoice_draft(
                    False, partner, company, 900 + seq,
                )
                if inv and inv.state == 'draft':
                    try:
                        inv.action_post()
                    except Exception as exc:
                        _logger.info('Switchgear demo KPI filler invoice post skipped: %s', exc)

        gap = min_count - Move.search_count(cd + [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'draft'),
        ])
        expense_account = self.env['account.account'].sudo().search([
            ('company_id', '=', company.id),
            ('deprecated', '=', False),
            ('user_type_id.type', '=', 'expense'),
        ], limit=1)
        for seq in range(max(gap, 0)):
            if not expense_account:
                break
            try:
                with self._demo_savepoint():
                    Move.create({
                        'move_type': 'in_invoice',
                        'partner_id': vendor.id,
                        'company_id': company.id,
                        'invoice_date': fields.Date.today(),
                        'invoice_line_ids': [(0, 0, {
                            'name': 'Demo vendor bill %s' % (900 + seq),
                            'account_id': expense_account.id,
                            'quantity': 1,
                            'price_unit': 150.0 + (seq * 25),
                        })],
                    })
            except Exception as exc:
                _logger.info('Switchgear demo KPI filler vendor bill skipped: %s', exc)

    @api.model
    def _create_demo_project_task(self, project, label, company, amount=0.0):
        Task = self.env['project.task'].sudo()
        vals = {
            'name': '%s — Site Task' % label,
            'project_id': project.id,
            'company_id': company.id,
        }
        if amount:
            vals['amount'] = amount
        if 'period' in Task._fields:
            vals['period'] = 'year'
        return Task.create(vals)

    @api.model
    def _ensure_demo_partner_accounts(self, partner, company=None):
        """Demo invoices fail when partner receivable/payable were cleared."""
        if not partner:
            return
        partner = partner.sudo()
        Partner = self.env['res.partner'].sudo()
        if hasattr(Partner, 'cpabooks_restore_missing_account_properties'):
            Partner.cpabooks_restore_missing_account_properties(partner.ids)
            return
        company = (company or partner.company_id or self.env.company).sudo()
        partner_co = partner.with_company(company)
        vals = {}
        if not partner_co.property_account_receivable_id:
            recv = company.partner_id.property_account_receivable_id
            if recv:
                vals['property_account_receivable_id'] = recv.id
        if not partner_co.property_account_payable_id:
            pay = company.partner_id.property_account_payable_id
            if pay:
                vals['property_account_payable_id'] = pay.id
        if vals:
            partner_co.write(vals)

    @api.model
    def _link_demo_project_crm(self, project, lead):
        """Keep project.crm_id and crm.lead.project_id in sync for list KPIs."""
        if not project or not lead:
            return
        project = project.sudo()
        lead = lead.sudo()
        if 'crm_id' in project._fields and not project.crm_id:
            project.crm_id = lead.id
        if 'project_id' in lead._fields and not lead.project_id:
            lead.project_id = project.id

    @api.model
    def _demo_project_contract_amount(self, lead, estimate, sale_order, index):
        if sale_order:
            return sale_order.amount_untaxed or sale_order.amount_total or 0.0
        if estimate and estimate.total_job_estimate:
            return estimate.total_job_estimate
        if lead and lead.expected_revenue:
            return lead.expected_revenue
        return 12000.0 + (int(index or 0) * 500)

    @api.model
    def _demo_stack_index_from_partner(self, partner, project=None):
        for source in (
            partner.name if partner else '',
            project.name if project else '',
        ):
            match = re.search(r'Demo\s+(\d+)', source)
            if match:
                return int(match.group(1))
        return 0

    @api.model
    def _sync_demo_project_financials(self, project):
        """Populate CRM link, task contract amount, and project on demo invoices/bills."""
        project = project.sudo()
        changed = False
        partner = project.partner_id
        Lead = self.env['crm.lead'].sudo()
        Estimate = self.env['switchgear.estimate'].sudo()
        Move = self.env['account.move'].sudo()

        lead = project.crm_id if 'crm_id' in project._fields else False
        estimate = Estimate.search([('project_id', '=', project.id)], order='id desc', limit=1)
        if not lead:
            lead = Lead.search([
                ('project_id', '=', project.id),
                ('type', '=', 'opportunity'),
            ], limit=1)
        if not lead and estimate:
            lead = estimate.opportunity_id
        if not lead and partner:
            label_guess = (project.name or '').replace(' Project', '')
            lead = Lead.search([
                ('name', '=', '%s Enquiry' % label_guess),
                ('partner_id', '=', partner.id),
                ('type', '=', 'opportunity'),
            ], limit=1)

        if lead:
            before_crm = project.crm_id.id if project.crm_id else False
            before_lead_project = lead.project_id.id if lead.project_id else False
            self._link_demo_project_crm(project, lead)
            if (project.crm_id.id if project.crm_id else False) != before_crm:
                changed = True
            if (lead.project_id.id if lead.project_id else False) != before_lead_project:
                changed = True

        sale_order = estimate.sale_quotation_id if estimate else False
        if not sale_order and lead:
            sale_order = lead.order_ids.filtered(lambda o: o.state != 'cancel')[:1]

        stack_index = self._demo_stack_index_from_partner(partner, project)
        amount = self._demo_project_contract_amount(lead, estimate, sale_order, stack_index)
        task = self.env['project.task'].sudo().search(
            [('project_id', '=', project.id)], limit=1, order='id',
        )
        if task and not task.amount and amount:
            task.write({'amount': amount})
            changed = True
        elif not task and amount:
            label = (project.name or 'Demo').replace(' Project', '')
            self._create_demo_project_task(project, label, project.company_id, amount=amount)
            changed = True

        analytic = project.analytic_account_id
        moves = Move.browse()
        if sale_order:
            moves |= sale_order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice')
            moves |= Move.search([
                ('invoice_origin', '=', sale_order.name),
                ('move_type', '=', 'out_invoice'),
            ])
        if partner:
            moves |= Move.search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('project_id', '=', False),
                ('invoice_line_ids.name', 'ilike', 'Demo draft invoice'),
            ], limit=3)
        if stack_index:
            moves |= Move.search([
                ('move_type', '=', 'in_invoice'),
                ('project_id', '=', False),
                ('invoice_line_ids.name', '=', 'Demo vendor bill %s' % stack_index),
                ('company_id', '=', project.company_id.id),
            ], limit=1)
            moves |= Move.search([
                ('move_type', '=', 'out_invoice'),
                ('project_id', '=', False),
                ('invoice_line_ids.name', '=', 'Demo draft invoice %s' % stack_index),
                ('company_id', '=', project.company_id.id),
            ], limit=1)

        if estimate:
            bom = self.env['mrp.bom'].sudo().search([('estimate_id', '=', estimate.id)], limit=1)
            if bom:
                mo = self.env['mrp.production'].sudo().search([('bom_id', '=', bom.id)], limit=1)
                if mo and 'mo_id' in self.env['purchase.order']._fields:
                    pos = self.env['purchase.order'].sudo().search([('mo_id', '=', mo.id)])
                    if pos:
                        moves |= Move.search([
                            ('move_type', '=', 'in_invoice'),
                            ('invoice_origin', 'in', pos.mapped('name')),
                            ('project_id', '=', False),
                        ])

        for move in moves:
            if move.project_id:
                continue
            move.write({'project_id': project.id})
            changed = True
            if analytic:
                for line in move.invoice_line_ids.filtered(lambda l: not l.analytic_account_id):
                    line.analytic_account_id = analytic.id

        if stack_index and not Move.search_count([
            ('project_id', '=', project.id),
            ('move_type', '=', 'out_invoice'),
        ]):
            inv = self._create_demo_customer_invoice_draft(
                sale_order, partner, project.company_id, stack_index,
                project=project, analytic=analytic,
            )
            if inv:
                changed = True
        if stack_index and not Move.search_count([
            ('project_id', '=', project.id),
            ('move_type', '=', 'in_invoice'),
        ]):
            catalog = self._ensure_demo_catalog('switchgear', project.company_id)
            vendor = catalog.get('vendor')
            if vendor:
                bill = self._create_demo_vendor_bill(
                    vendor, project.company_id, stack_index,
                    project=project, analytic=analytic,
                )
                if bill:
                    changed = True
        return changed

    @api.model
    def _backfill_demo_project_financials(self, company):
        """Repair CRM, contract amounts, and invoice links on existing demo projects."""
        company = company.sudo()
        partners = (
            self._find_demo_partners('switchgear', company)
            | self._find_demo_partners('furniture', company)
        )
        if not partners:
            return 0
        self._ensure_demo_partner_accounts(partners, company)
        projects = self.env['project.project'].sudo().search([
            ('partner_id', 'in', partners.ids),
        ])
        fixed = 0
        for project in projects:
            try:
                with self._demo_savepoint():
                    if self._sync_demo_project_financials(project):
                        fixed += 1
            except Exception as exc:
                _logger.info(
                    'Switchgear demo project financial backfill skipped for %s: %s',
                    project.id, exc,
                )
        if fixed:
            _logger.info(
                'Switchgear demo: synced financial KPIs on %s project(s) for %s',
                fixed, company.display_name,
            )
        return fixed

    @api.model
    def _create_demo_design_document(self, partner, project, sale_order, estimate, company, index):
        Design = self.env['switchgear.design.document'].sudo()
        return Design.create({
            'partner_id': partner.id,
            'project_id': project.id,
            'sale_order_id': sale_order.id if sale_order else False,
            'job_estimate_id': estimate.id,
            'company_id': company.id,
            'notes': 'Demo design register %s' % index,
            'sent_line_ids': [(0, 0, {
                'document_name': 'GA Drawing Rev %s' % index,
                'remarks': 'Issued to client',
            })],
            'received_line_ids': [(0, 0, {
                'document_name': 'Client approval %s' % index,
                'remarks': 'Signed return',
            })],
        })

    @api.model
    def _maybe_create_quality_alert(self, project, partner, company, index, product=None):
        team = self.env['switchgear.quality.team'].sudo()._get_default_team(company)
        vals = {
            'name': 'Demo QC alert %s' % index,
            'team_id': team.id,
            'partner_id': partner.id,
            'company_id': company.id,
            'project_id': project.id,
        }
        if product:
            vals['product_id'] = product.id
        try:
            with self._demo_savepoint():
                return self.env['switchgear.quality.alert'].sudo().create(vals)
        except Exception as exc:
            _logger.info('Switchgear demo: quality alert skipped: %s', exc)
            return False

    @api.model
    def _ensure_accounting_draft_samples(
        self, sale_order, partner, vendor, company, index,
        project=None, analytic=None,
        post_invoice=False, post_payment=False,
    ):
        """Ensure draft vendor bill, customer invoice, and draft payments exist."""
        if not self._company_has_usable_accounts(company):
            return {}
        self._create_demo_vendor_bill(vendor, company, index, project=project, analytic=analytic)
        self._create_demo_draft_payments(
            partner, vendor, company, index, force_draft=True,
        )
        result = {}
        draft_inv = self._create_demo_customer_invoice_draft(
            sale_order, partner, company, index,
            project=project, analytic=analytic,
        )
        if draft_inv:
            result['invoice'] = draft_inv
        if sale_order and post_invoice:
            posted = self._create_demo_invoice_and_payment(
                sale_order, partner, company,
                post_invoice=True,
                post_payment=post_payment,
            )
            if posted.get('invoice'):
                result['invoice'] = posted['invoice']
            if posted.get('payment'):
                result['payment'] = posted['payment']
        return result

    @api.model
    def _create_demo_customer_invoice_draft(
        self, sale_order, partner, company, index, project=None, analytic=None,
    ):
        """Create a draft customer invoice for dashboard KPI (even if SO not confirmed)."""
        Move = self.env['account.move'].sudo()
        catalog = self._ensure_demo_catalog('switchgear', company)
        product = catalog.get('finished') or self.env['product.product'].sudo().search([
            ('sale_ok', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        if not product:
            return False
        self._ensure_demo_partner_accounts(partner, company)
        line_vals = self._demo_move_line_vals(
            product, company, 'out_invoice',
            'Demo draft invoice %s' % index, 1, 500.0 + (index * 25),
            analytic=analytic or (project.analytic_account_id if project else False),
        )
        vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'company_id': company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, line_vals)],
        }
        if sale_order:
            vals['invoice_origin'] = sale_order.name
        if project and 'project_id' in Move._fields:
            vals['project_id'] = project.id
        draft = [False]
        with self._demo_optional():
            draft[0] = Move.create(vals)
        return draft[0]

    @api.model
    def _create_demo_vendor_bill(self, vendor, company, index, project=None, analytic=None):
        Move = self.env['account.move'].sudo()
        catalog = self._ensure_demo_catalog('switchgear', company)
        product = catalog.get('material') or self.env['product.product'].sudo().search([
            ('purchase_ok', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        if not product:
            return False
        self._ensure_demo_partner_accounts(vendor, company)
        line_vals = self._demo_move_line_vals(
            product, company, 'in_invoice',
            'Demo vendor bill %s' % index, 1, 100.0 + index,
            analytic=analytic or (project.analytic_account_id if project else False),
        )
        vals = {
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'company_id': company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, line_vals)],
        }
        if project and 'project_id' in Move._fields:
            vals['project_id'] = project.id
        created = [False]
        with self._demo_optional():
            created[0] = Move.create(vals)
        return created[0]

    @api.model
    def _create_demo_draft_payments(self, partner, vendor, company, index, force_draft=True):
        Payment = self.env['account.payment'].sudo()
        journal_bank = self.env['account.journal'].sudo().search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal_bank:
            return
        amount = 250.0 + (index * 10)
        payment_method_in = payment_method_out = False
        if 'payment_method_id' in Payment._fields:
            if hasattr(journal_bank, 'inbound_payment_method_ids'):
                method_in = journal_bank.inbound_payment_method_ids[:1]
                if method_in:
                    payment_method_in = method_in.id
            if hasattr(journal_bank, 'outbound_payment_method_ids'):
                method_out = journal_bank.outbound_payment_method_ids[:1]
                if method_out:
                    payment_method_out = method_out.id
        inbound_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': amount,
            'journal_id': journal_bank.id,
            'company_id': company.id,
        }
        outbound_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': vendor.id,
            'amount': amount * 0.6,
            'journal_id': journal_bank.id,
            'company_id': company.id,
        }
        if payment_method_in:
            inbound_vals['payment_method_id'] = payment_method_in
        if payment_method_out:
            outbound_vals['payment_method_id'] = payment_method_out
        with self._demo_optional():
            pay_in = Payment.create(inbound_vals)
            if force_draft and pay_in.state != 'draft':
                try:
                    pay_in.action_draft()
                except Exception:
                    pass
        with self._demo_optional():
            pay_out = Payment.create(outbound_vals)
            if force_draft and pay_out.state != 'draft':
                try:
                    pay_out.action_draft()
                except Exception:
                    pass
        if (index % 5) == 0:
            self._create_demo_journal_voucher(company, index)

    @api.model
    def _create_demo_journal_voucher(self, company, index):
        Move = self.env['account.move'].sudo()
        journal = self.env['account.journal'].sudo().search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            return False
        accounts = self.env['account.account'].sudo().search([
            ('company_id', '=', company.id),
            ('deprecated', '=', False),
        ], limit=2)
        if len(accounts) < 2:
            return False
        amount = 50.0 + index
        try:
            with self._demo_savepoint():
                return Move.create({
                    'move_type': 'entry',
                    'journal_id': journal.id,
                    'company_id': company.id,
                    'date': fields.Date.today(),
                    'ref': 'Demo JV %s' % index,
                    'line_ids': [
                        (0, 0, {
                            'name': 'Demo journal debit',
                            'account_id': accounts[0].id,
                            'debit': amount,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': 'Demo journal credit',
                            'account_id': accounts[1].id,
                            'debit': 0.0,
                            'credit': amount,
                        }),
                    ],
                })
        except Exception as exc:
            _logger.info('Switchgear demo: journal voucher skipped: %s', exc)
            return False

    @api.model
    def _stack_from_existing_lead(self, lead, partner, company, index, profile):
        """Reuse an already-loaded demo stack (safe on repeat demo load)."""
        Lead = self.env['crm.lead'].sudo()
        Estimate = self.env['switchgear.estimate'].sudo()
        estimates = Estimate.search([('opportunity_id', '=', lead.id)], order='id desc')
        estimate = estimates[:1]
        if estimate and len(estimate.material_estimation_ids) < 4:
            with self._demo_savepoint():
                catalog = self.with_company(company)._ensure_demo_catalog(profile, company)
                line_vals = self._estimate_line_vals(catalog, index)
                existing_products = set(estimate.material_estimation_ids.mapped('product_id').ids)
                new_lines = [
                    cmd for cmd in line_vals['material_estimation_ids']
                    if cmd[0] == 0 and cmd[2].get('product_id') not in existing_products
                ]
                if new_lines:
                    estimate.write({'material_estimation_ids': new_lines})
        sale_order = lead.order_ids.filtered(
            lambda o: o.state not in ('cancel',),
        )[:1]
        if not sale_order and estimate:
            sale_order = estimate.sale_quotation_id
        project = estimate.project_id if estimate and estimate.project_id else False
        if not project and sale_order:
            project = sale_order.project_id
        bom = self.env['mrp.bom'].sudo()
        mo = self.env['mrp.production'].sudo()
        if estimate:
            bom = bom.search([('estimate_id', '=', estimate.id)], limit=1, order='id desc')
            if bom:
                mo = mo.search([('bom_id', '=', bom.id)], limit=1, order='id desc')
        design = self.env['switchgear.design.document'].sudo().search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
        ], limit=1, order='id desc')
        task = self.env['project.task'].sudo()
        if project:
            task = task.search([('project_id', '=', project.id)], limit=1, order='id desc')
        po = self.env['purchase.order'].sudo()
        if mo and 'mo_id' in po._fields:
            po = po.search([('mo_id', '=', mo.id)], limit=1, order='id desc')
        qc = self.env['switchgear.quality.check'].sudo()
        if mo:
            qc = qc.search([('production_id', '=', mo.id)], limit=1, order='id desc')
        enquiry_lead = Lead.search([
            ('name', '=', '%s Open Enquiry' % self._profile_label(profile, index)),
            ('partner_id', '=', partner.id),
            ('type', '=', 'lead'),
            ('company_id', '=', company.id),
        ], limit=1)
        if project:
            self._sync_demo_project_financials(project)
        return {
            'partner': partner,
            'lead': lead,
            'estimate': estimate,
            'extra_estimates': estimates[1:] if len(estimates) > 1 else [],
            'sale_order': sale_order,
            'project': project,
            'task': task,
            'design_document': design,
            'bom': bom,
            'mo': mo,
            'quality_check': qc,
            'purchase_order': po,
            'timesheet_lines': 0,
            'enquiry_lead': enquiry_lead,
            'reused': True,
        }

    def _unlink_records(self, records, label='record'):
        if not records:
            return 0
        try:
            with self._demo_savepoint():
                records.unlink()
            return len(records)
        except Exception as exc:
            _logger.warning('Switchgear demo: could not unlink %s: %s', label, exc)
            return 0

    @api.model
    def _maybe_create_demo_po(self, mo, vendor, company):
        """Create a purchase order for components with insufficient stock."""
        POLine = self.env['purchase.order.line'].sudo()
        lines = []
        for move in mo.move_raw_ids:
            product = move.product_id
            available = product.with_context(company_id=company.id).qty_available
            need = move.product_uom_qty - available
            if need <= 0:
                continue
            lines.append((0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'product_qty': need,
                'product_uom': move.product_uom.id,
                'price_unit': product.standard_price or 1.0,
                'date_planned': fields.Datetime.now(),
            }))
        if not lines:
            return False
        po = self.env['purchase.order'].sudo().create({
            'partner_id': vendor.id,
            'company_id': company.id,
            'order_line': lines,
            'mo_id': mo.id,
        })
        return po

    @api.model
    def _create_demo_timesheets(self, project, analytic, labour_product, index, company, task=None):
        """Post analytic lines (and optional task timesheets) as labour cost samples."""
        count = 0
        employee = False
        if 'hr.employee' in self.env:
            employee = self.env['hr.employee'].sudo().search([
                ('company_id', '=', company.id),
            ], limit=1)
            if not employee:
                employee = self.env['hr.employee'].sudo().create({
                    'name': 'Demo Timesheet Worker',
                    'company_id': company.id,
                })
        unit_amount = 4.0 + (index % 4)
        amount = unit_amount * (labour_product.standard_price or 45.0)
        line_vals = {
            'name': 'Demo timesheet booking job %s' % index,
            'date': date.today() - timedelta(days=index % 14),
            'unit_amount': unit_amount,
            'amount': -amount,
            'account_id': analytic.id,
            'company_id': company.id,
        }
        if employee and 'employee_id' in self.env['account.analytic.line']._fields:
            line_vals['employee_id'] = employee.id
        if 'project_id' in self.env['account.analytic.line']._fields:
            line_vals['project_id'] = project.id
        if task and 'task_id' in self.env['account.analytic.line']._fields:
            line_vals['task_id'] = task.id
        self.env['account.analytic.line'].sudo().create(line_vals)
        count += 1
        if task and 'timesheet_ids' in task._fields:
            try:
                task.sudo().write({
                    'planned_hours': unit_amount + 2,
                    'timesheet_ids': [(0, 0, line_vals)],
                })
                count += 1
            except Exception:
                pass
        return count

    @api.model
    def _demo_requisition_employee(self, company):
        Employee = self.env['hr.employee'].sudo()
        employee = Employee.search([
            ('company_id', '=', company.id),
            ('name', '=', 'Demo Employee'),
        ], limit=1)
        if employee:
            return employee
        department = self.env['hr.department'].sudo().search([
            ('company_id', '=', company.id),
            ('name', '=', 'Demo Department'),
        ], limit=1)
        if not department:
            department = self.env['hr.department'].sudo().create({
                'name': 'Demo Department',
                'company_id': company.id,
            })
        return Employee.create({
            'name': 'Demo Employee',
            'company_id': company.id,
            'department_id': department.id,
        })

    @api.model
    def _maybe_create_demo_requisition(self, project, partner, catalog, company, index):
        if 'switchgear.purchase.requisition' not in self.env:
            return False
        Requisition = self.env['switchgear.purchase.requisition'].sudo()
        employee = self._demo_requisition_employee(company)
        picking_type = self.env['stock.picking.type'].sudo().search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', company.id),
        ], limit=1)
        if not picking_type:
            return False
        try:
            with self._demo_savepoint():
                return Requisition.create({
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'requisition_date': fields.Date.today(),
                    'project_id': project.id,
                    'company_id': company.id,
                    'picking_type_id': picking_type.id,
                    'requisition_line_ids': [(0, 0, {
                        'product_id': catalog['material'].id,
                        'description': catalog['material'].display_name,
                        'qty': 1.0 + (index % 3),
                        'uom_id': catalog['material'].uom_id.id,
                    })],
                })
        except Exception as exc:
            _logger.info('Switchgear demo: purchase requisition skipped: %s', exc)
            return False

    @api.model
    def _ensure_demo_mo_done_minimums(self, company, min_count=6):
        """Mark open demo MOs done so dashboards show a mix of states."""
        if min_count <= 0:
            return 0
        company = company.sudo()
        cd = self._demo_company_domain(company)
        MO = self.env['mrp.production'].sudo()
        candidates = MO.search(
            cd + [
                ('state', 'not in', ('done', 'cancel')),
                ('move_raw_ids', '!=', False),
            ],
            order='id desc',
        )
        completed = 0
        for mo in candidates:
            if completed >= min_count:
                break
            try:
                with self._demo_savepoint():
                    if self._complete_demo_mo(mo, company):
                        completed += 1
            except Exception as exc:
                _logger.info(
                    'Switchgear demo MO done backfill skipped for %s: %s',
                    mo.id, exc,
                )
        return completed

    @api.model
    def _demo_mo_stock_location(self, mo, company):
        warehouse = mo.picking_type_id.warehouse_id
        if not warehouse:
            warehouse = self.env['stock.warehouse'].sudo().search([
                ('company_id', '=', company.id),
            ], limit=1)
        return warehouse.lot_stock_id if warehouse else False

    @api.model
    def _ensure_demo_mo_component_stock(self, mo, company):
        location = self._demo_mo_stock_location(mo, company)
        if not location:
            return False
        Quant = self.env['stock.quant'].sudo()
        for move in mo.move_raw_ids:
            product = move.product_id
            if product.type not in ('product', 'consu'):
                continue
            needed = move.product_uom_qty or 0.0
            if needed <= 0:
                continue
            available = Quant._get_available_quantity(product, location)
            if available < needed:
                Quant._update_available_quantity(product, location, needed - available)
        return True

    @api.model
    def _finish_demo_mo_mark_done(self, mo):
        ctx = dict(
            self.env.context,
            skip_backorder=True,
            button_mark_done_production_ids=mo.ids,
        )
        for _attempt in range(4):
            res = mo.with_context(ctx).button_mark_done()
            if not isinstance(res, dict):
                return mo.state == 'done'
            model = res.get('res_model')
            action_ctx = dict(ctx, **res.get('context', {}))
            if model == 'mrp.immediate.production':
                wizard = self.env['mrp.immediate.production'].with_context(
                    dict(action_ctx, default_mo_ids=[(4, mo.id)]),
                ).create({})
                wizard.process()
                continue
            if model == 'mrp.consumption.warning':
                ctx['skip_consumption'] = True
                continue
            if model == 'mrp.production.backorder':
                ctx['skip_backorder'] = True
                continue
            break
        return mo.state == 'done'

    @api.model
    def _complete_demo_mo(self, mo, company):
        """Reserve components, consume, and mark a demo manufacturing order done."""
        mo = mo.sudo().with_company(company)
        if mo.state in ('done', 'cancel'):
            return True
        if not mo.move_raw_ids:
            return False
        try:
            self._ensure_demo_mo_component_stock(mo, company)
            if not mo.state or mo.state == 'draft':
                mo.action_confirm()
            else:
                (mo.move_raw_ids | mo.move_finished_ids).filtered(
                    lambda m: m.state == 'draft',
                )._action_confirm()
            mo.action_assign()
            qty = mo.product_qty or 1.0
            if 'qty_producing' in mo._fields:
                mo.qty_producing = qty
                if hasattr(mo, '_set_qty_producing'):
                    mo._set_qty_producing()
            for move in mo.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                if not move.quantity_done:
                    move.quantity_done = move.product_uom_qty
            return self._finish_demo_mo_mark_done(mo)
        except Exception as exc:
            _logger.info('Switchgear demo: MO %s completion skipped: %s', mo.id, exc)
            return False

    @api.model
    def _create_demo_delivery(self, sale_order, company):
        pickings = sale_order.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel'),
        )
        for picking in pickings:
            try:
                if picking.state == 'draft':
                    picking.action_confirm()
                if picking.state in ('confirmed', 'assigned'):
                    for move in picking.move_lines:
                        move.quantity_done = move.product_uom_qty
                    picking.button_validate()
            except Exception as exc:
                _logger.info('Switchgear demo: delivery validate skipped: %s', exc)
        return pickings[:1] if pickings else False

    @api.model
    def _create_demo_invoice_and_payment(
        self, sale_order, partner, company, post_invoice=True, post_payment=True,
    ):
        invoice = False
        payment = False
        try:
            if sale_order.invoice_status in ('to invoice', 'no'):
                invoices = sale_order._create_invoices()
                invoice = invoices[:1]
            else:
                invoice = sale_order.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice' and m.state != 'cancel',
                )[:1]
            if invoice and post_invoice and invoice.state == 'draft':
                invoice.action_post()
            if invoice and sale_order and sale_order.project_id and not invoice.project_id:
                invoice.write({'project_id': sale_order.project_id.id})
            if invoice and post_payment and invoice.payment_state != 'paid':
                payment = self._create_demo_payment(invoice, partner, company)
        except Exception as exc:
            _logger.info('Switchgear demo: invoice/payment skipped: %s', exc)
        return {'invoice': invoice, 'payment': payment}

    @api.model
    def _create_demo_payment(self, invoice, partner, company):
        Payment = self.env['account.payment'].sudo()
        journal = self.env['account.journal'].sudo().search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            return False
        payment = Payment.create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': invoice.amount_residual,
            'currency_id': invoice.currency_id.id,
            'journal_id': journal.id,
            'company_id': company.id,
        })
        try:
            payment.action_post()
            lines = invoice.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type in ('receivable', 'payable')
                and not line.reconciled,
            )
            if lines and payment.move_id:
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda line: line.account_id.user_type_id.type in ('receivable', 'payable')
                    and not line.reconciled,
                )
                if payment_lines:
                    (lines + payment_lines).reconcile()
        except Exception as exc:
            _logger.info('Switchgear demo: payment post skipped: %s', exc)
        return payment

    # -------------------------------------------------------------------------
    # Clean demo data
    # -------------------------------------------------------------------------

    @api.model
    def _demo_label_prefix(self, profile):
        labels = {'switchgear': 'Switchgear Demo', 'furniture': 'Furniture Demo'}
        return labels.get(profile, 'Switchgear Demo')

    @api.model
    def _demo_product_code_prefix(self, profile):
        return 'DEMO-SG' if profile == 'switchgear' else 'DEMO-FN'

    @api.model
    def _demo_company_domain(self, company):
        return [('company_id', 'in', [False, company.id])]

    @api.model
    def _demo_user_for_company(self, company):
        user = self.env.user
        if company in user.company_ids:
            return user.id
        company_user = self.env['res.users'].sudo().search([
            ('company_ids', 'in', company.id),
            ('share', '=', False),
            ('active', '=', True),
        ], limit=1)
        return company_user.id if company_user else False

    @api.model
    def _find_demo_leads(self, profile, company):
        label = self._demo_label_prefix(profile)
        name_domain = [
            '|', '|',
            ('name', '=like', '%s %% Enquiry' % label),
            ('name', '=like', '%s %% Open Enquiry' % label),
            ('name', '=like', '%s %%' % label),
        ]
        return self.env['crm.lead'].sudo().search(
            expression.AND([self._demo_company_domain(company), name_domain]),
        )

    @api.model
    def _find_demo_partners(self, profile, company):
        label = self._demo_label_prefix(profile)
        return self.env['res.partner'].sudo().search(
            expression.AND([
                self._demo_company_domain(company),
                [('name', '=like', '%s %% Customer' % label)],
            ]),
        )

    def _safe_unlink(self, records, label='records'):
        records = records.exists()
        if not records:
            return 0
        try:
            with self._demo_savepoint():
                records.unlink()
            return len(records)
        except Exception as exc:
            _logger.info('Switchgear demo clean: could not unlink %s: %s', label, exc)
            removed = 0
            for record in records:
                try:
                    with self._demo_savepoint():
                        record.unlink()
                        removed += 1
                except Exception:
                    pass
            return removed

    def _cancel_and_unlink_moves(self, moves):
        moves = moves.exists()
        if not moves:
            return 0
        for move in moves.filtered(lambda m: m.state == 'posted'):
            try:
                move.button_draft()
            except Exception:
                try:
                    move.button_cancel()
                except Exception:
                    pass
        return self._safe_unlink(moves, 'account moves')

    def _unlink_demo_lead_chain(self, lead):
        """Remove one demo CRM stack and related documents."""
        lead = lead.sudo()
        partner = lead.partner_id
        estimates = self.env['switchgear.estimate'].sudo().search([
            ('opportunity_id', '=', lead.id),
        ])
        sale_orders = lead.order_ids | estimates.mapped('sale_quotation_id')
        sale_orders = sale_orders.filtered(lambda o: o.state != 'cancel')

        payments = self.env['account.payment'].sudo().search([
            ('partner_id', '=', partner.id),
        ]) if partner else self.env['account.payment']
        self._safe_unlink(payments, 'payments')

        invoices = sale_orders.mapped('invoice_ids')
        self._cancel_and_unlink_moves(invoices)

        pickings = sale_orders.mapped('picking_ids')
        for picking in pickings:
            try:
                if picking.state not in ('done', 'cancel'):
                    picking.action_cancel()
            except Exception:
                pass
        self._safe_unlink(pickings, 'pickings')

        mos = self.env['mrp.production'].sudo()
        boms = self.env['mrp.bom'].sudo()
        if estimates:
            boms = boms.search([('estimate_id', 'in', estimates.ids)])
            mos = mos.search([('bom_id', 'in', boms.ids)])
        for mo in mos:
            try:
                if mo.state not in ('done', 'cancel'):
                    mo.action_cancel()
            except Exception:
                pass
        qc = self.env['switchgear.quality.check'].sudo().search([
            ('production_id', 'in', mos.ids),
        ]) if mos else self.env['switchgear.quality.check']
        self._safe_unlink(qc, 'quality checks')
        self._safe_unlink(mos, 'manufacturing orders')
        self._safe_unlink(boms, 'boms')

        pos = self.env['purchase.order'].sudo()
        if mos and 'mo_id' in pos._fields:
            pos = pos.search([('mo_id', 'in', mos.ids)])
        self._safe_unlink(pos, 'purchase orders')

        if 'switchgear.purchase.requisition' in self.env:
            projects = sale_orders.mapped('project_id') | estimates.mapped('project_id')
            reqs = self.env['switchgear.purchase.requisition'].sudo().search([
                ('project_id', 'in', projects.ids),
            ]) if projects else self.env['switchgear.purchase.requisition']
            self._safe_unlink(reqs, 'requisitions')

        for so in sale_orders:
            try:
                if so.state in ('sale', 'done'):
                    so.action_cancel()
            except Exception:
                pass
        projects = sale_orders.mapped('project_id') | estimates.mapped('project_id')
        analytics = estimates.mapped('analytic_id')

        self._safe_unlink(sale_orders, 'sale orders')
        self._safe_unlink(estimates, 'estimates')

        if partner and 'switchgear.design.document' in self.env:
            designs = self.env['switchgear.design.document'].sudo().search([
                ('partner_id', '=', partner.id),
            ])
            self._safe_unlink(designs, 'design documents')

        tasks = self.env['project.task'].sudo().search([
            ('project_id', 'in', projects.ids),
        ]) if projects else self.env['project.task']
        self._safe_unlink(tasks, 'tasks')
        self._safe_unlink(projects, 'projects')
        lines = self.env['account.analytic.line'].sudo().search([
            ('account_id', 'in', analytics.ids),
        ]) if analytics else self.env['account.analytic.line']
        self._safe_unlink(lines, 'analytic lines')
        self._safe_unlink(analytics, 'analytic accounts')

        self._safe_unlink(lead, 'crm lead')

    @api.model
    def clean_demo_batch(self, options):
        """Remove switchgear/furniture demo stacks for the active company."""
        profile = options.get('profile', 'switchgear')
        company = self.env['res.company'].browse(options.get('company_id'))
        if not company:
            company = self.env.company

        stats = {
            'leads_removed': 0,
            'partners_removed': 0,
            'products_removed': 0,
            'errors': [],
        }

        leads = self._find_demo_leads(profile, company)
        for lead in leads:
            try:
                with self._demo_savepoint():
                    self._unlink_demo_lead_chain(lead)
                    stats['leads_removed'] += 1
            except Exception as exc:
                _logger.exception('Switchgear demo clean lead %s: %s', lead.id, exc)
                stats['errors'].append({'lead': lead.id, 'error': str(exc)})

        partners = self._find_demo_partners(profile, company)
        stats['partners_removed'] += self._safe_unlink(partners, 'demo partners')

        prefix = self._demo_product_code_prefix(profile)
        products = self.env['product.product'].sudo().search([
            ('default_code', '=like', '%s-%%' % prefix),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ])
        templates = products.mapped('product_tmpl_id')
        stats['products_removed'] += self._safe_unlink(products, 'demo products')
        self._safe_unlink(templates, 'demo product templates')

        vendor = self.env['res.partner'].sudo().search([
            ('name', '=', 'Demo Vendor (CPABooks)'),
        ], limit=1)
        if vendor and vendor.supplier_rank and not vendor.customer_rank:
            self._safe_unlink(vendor, 'demo vendor')

        self.env.clear()
        return stats

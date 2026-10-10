# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import UserError


class SwitchgearDashboard(models.AbstractModel):
    _name = 'switchgear.dashboard'
    _description = 'Switchgear Workflow Dashboard'

    @api.model
    def action_open_switchgear_demo_wizard(self):
        """Open popup to load or clean switchgear demo data."""
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only Settings / Administrator users can manage switchgear demo data.'))
        action = self.env.ref(
            'saaskul_switchgear.action_switchgear_demo_wizard',
            raise_if_not_found=False,
        )
        if not action:
            raise UserError(_('Upgrade module "Saaskul Switchgear".'))
        result = action.read()[0]
        ctx = dict(self.env.context)
        ctx.setdefault('default_profile', 'switchgear')
        ctx.setdefault('default_voucher_count', 25)
        if 'cpabooks.demo.config' in self.env:
            config = self.env['cpabooks.demo.config'].sudo().search([
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if config and config.default_voucher_count:
                ctx['default_voucher_count'] = config.default_voucher_count
        result['context'] = ctx
        return result

    @api.model
    def action_load_switchgear_company_demo(self):
        """Load full switchgear process-cycle demo data for the active company."""
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only Settings / Administrator users can load switchgear demo data.'))
        company = self.env.company.sudo()
        voucher_count = 25
        if 'cpabooks.demo.config' in self.env:
            config = self.env['cpabooks.demo.config'].sudo().search([
                ('company_id', '=', company.id),
            ], limit=1)
            if config and config.default_voucher_count:
                voucher_count = config.default_voucher_count
        if 'switchgear.demo.loader' not in self.env:
            raise UserError(_(
                'Switchgear demo loader is not available. '
                'Upgrade module "Saaskul Switchgear".',
            ))
        result = self.env['switchgear.demo.loader'].sudo().load_demo_batch({
            'profile': 'switchgear',
            'voucher_count': voucher_count,
            'company_id': company.id,
            'load_timesheets': True,
            'create_pr_when_no_stock': True,
            'create_job_orders': True,
            'full_cycle': True,
        })
        stacks = len(result.get('estimates', []))
        failed = len(result.get('errors', []))
        parts = [
            _('%(stacks)s demo stack(s)') % {'stacks': stacks},
            _('%(leads)s CRM records') % {'leads': len(result.get('leads', []))},
            _('%(design)s design registers') % {'design': len(result.get('design_documents', []))},
            _('%(tasks)s project tasks') % {'tasks': len(result.get('tasks', []))},
            _('%(ts)s timesheet lines') % {'ts': result.get('timesheet_lines', 0)},
        ]
        message = _(
            'Loaded for %(company)s: %(summary)s. '
            'Refresh the dashboard to update all KPI boxes.'
        ) % {
            'company': company.name,
            'summary': ', '.join(parts),
        }
        if failed:
            message += ' ' + _('%s stack(s) failed (see server log).') % failed
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Switchgear demo data loaded'),
                'message': message,
                'type': 'success' if stacks else 'warning',
                'sticky': bool(failed or not stacks),
            },
        }

    @api.model
    def action_open_configuration(self):
        """Open switchgear / dashboard configuration (no removed switchgear.configuration model)."""
        if 'cpabooks.demo.config' in self.env:
            return self.env['cpabooks.demo.config'].action_open_switchgear_configuration()
        theme_action = self.env.ref(
            'app_odoo_customize.action_app_theme_config',
            raise_if_not_found=False,
        )
        if theme_action:
            return theme_action.read()[0]
        company = self.env.company
        return {
            'type': 'ir.actions.act_window',
            'name': 'Company',
            'res_model': 'res.company',
            'res_id': company.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def get_dashboard_data(self):
        company = self.env.company
        return {
            'title': 'Switchgear Dashboard',
            'subtitle': company.name,
            'kpis': self._dashboard_kpis(),
            'workflow': self._workflow_sections(),
        }

    def _company_domain(self, model_name):
        if model_name in self.env and 'company_id' in self.env[model_name]._fields:
            return [('company_id', 'in', [False, self.env.company.id])]
        return []

    @api.model
    def _dashboard_kpis(self):
        Lead = self.env['crm.lead'].sudo()
        Estimate = self.env['job.estimate'].sudo()
        SO = self.env['sale.order'].sudo()
        MO = self.env['mrp.production'].sudo()
        Picking = self.env['stock.picking'].sudo()
        cd = self._company_domain

        return [
            {
                'label': 'Open Enquiries',
                'value': Lead.search_count(cd('crm.lead') + [('type', '=', 'lead'), ('active', '=', True)]),
                'action_xmlid': 'crm.crm_lead_action_pipeline',
                'icon': 'fa-inbox',
            },
            {
                'label': 'Estimations (Draft)',
                'value': Estimate.search_count(cd('job.estimate') + [
                    ('state', 'in', ('draft', 'confirmed', 'approved')),
                ]),
                'action_xmlid': 'cost_estimate_customer_ld.action_job_estimate',
                'icon': 'fa-calculator',
            },
            {
                'label': 'Quotations',
                'value': SO.search_count(cd('sale.order') + [('state', 'in', ('draft', 'sent'))]),
                'action_xmlid': 'sale.action_quotations_with_onboarding',
                'icon': 'fa-file-text-o',
            },
            {
                'label': 'Sales Orders',
                'value': SO.search_count(cd('sale.order') + [('state', '=', 'sale')]),
                'action_xmlid': 'sale.action_orders',
                'icon': 'fa-shopping-cart',
            },
            {
                'label': 'Design Documents',
                'value': self.env['switchgear.design.document'].sudo().search_count(
                    cd('switchgear.design.document'),
                ),
                'action_xmlid': 'saaskul_switchgear.action_switchgear_design_document',
                'icon': 'fa-paperclip',
            },
            {
                'label': 'Manuf. Orders In Progress',
                'value': MO.search_count(cd('mrp.production') + [('state', 'in', ('confirmed', 'progress'))]),
                'action_xmlid': 'mrp.mrp_production_action',
                'icon': 'fa-cogs',
            },
            {
                'label': 'GRN Pending',
                'value': Picking.search_count(cd('stock.picking') + [
                    ('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel')),
                ]),
                'action_xmlid': 'saaskul_switchgear.action_switchgear_stock_incoming',
                'icon': 'fa-truck',
            },
            {
                'label': 'Delivery Pending',
                'value': Picking.search_count(cd('stock.picking') + [
                    ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel')),
                ]),
                'action_xmlid': 'saaskul_switchgear.action_switchgear_stock_outgoing',
                'icon': 'fa-send',
            },
        ]

    @api.model
    def _workflow_sections(self):
        cd = self._company_domain
        sections = []

        Lead = self.env['crm.lead'].sudo()
        sections.append({
            'id': 'customer',
            'title': 'Customer / Client',
            'theme': 'customer',
            'items': [
                self._item('CRM enquiries (leads)', Lead.search_count(cd('crm.lead') + [
                    ('type', '=', 'lead'), ('active', '=', True),
                ]), 'crm.crm_lead_action_pipeline', 'pending'),
                self._item('Open opportunities', Lead.search_count(cd('crm.lead') + [
                    ('type', '=', 'opportunity'), ('active', '=', True), ('probability', '<', 100),
                ]), 'crm.crm_lead_action_pipeline', 'progress'),
            ],
        })

        Estimate = self.env['job.estimate'].sudo()
        SO = self.env['sale.order'].sudo()
        sections.append({
            'id': 'customer_sales',
            'title': 'Estimation & Sales',
            'theme': 'customer',
            'items': [
                self._item('Job estimates — draft', Estimate.search_count(cd('job.estimate') + [
                    ('state', '=', 'draft'),
                ]), 'cost_estimate_customer_ld.action_job_estimate', 'pending'),
                self._item('Job estimates — awaiting approval', Estimate.search_count(cd('job.estimate') + [
                    ('state', 'in', ('confirmed', 'approved')),
                ]), 'cost_estimate_customer_ld.action_job_estimate', 'progress'),
                self._item('Quotations to confirm', SO.search_count(cd('sale.order') + [
                    ('state', 'in', ('draft', 'sent')),
                ]), 'sale.action_quotations_with_onboarding', 'pending'),
                self._item('Confirmed sales orders', SO.search_count(cd('sale.order') + [
                    ('state', '=', 'sale'),
                ]), 'sale.action_orders', 'progress'),
            ],
        })

        Design = self.env['switchgear.design.document'].sudo()
        BOM = self.env['mrp.bom'].sudo()
        MO = self.env['mrp.production'].sudo()
        engineering_items = [
            self._item(
                'Design documents',
                Design.search_count(cd('switchgear.design.document')),
                'saaskul_switchgear.action_switchgear_design_document',
                'progress',
            ),
            self._item('Bill of materials', BOM.search_count(cd('mrp.bom')), 'mrp.mrp_bom_form_action', 'progress'),
            self._item(
                'Manuf. order — waiting',
                MO.search_count(cd('mrp.production') + [
                    ('state', 'not in', ('progress', 'done', 'cancel')),
                ]),
                'mrp.mrp_production_action',
                'pending',
            ),
            self._item(
                'Manuf. order — in progress',
                MO.search_count(cd('mrp.production') + [('state', '=', 'progress')]),
                'mrp.mrp_production_action',
                'progress',
            ),
        ]

        if 'material.purchase.requisition' in self.env:
            Req = self.env['material.purchase.requisition'].sudo()
            req_domain = cd('material.purchase.requisition')
            if 'state' in Req._fields:
                engineering_items.append(
                    self._item(
                        'Purchase requisitions open',
                        Req.search_count(req_domain + [
                            ('state', 'not in', ('cancel', 'done', 'rejected')),
                        ]),
                        'bi_material_purchase_requisitions.action_material_purchase_requisition',
                        'pending',
                    ),
                )

        sections.append({
            'id': 'engineering',
            'title': 'Engineering & Production',
            'theme': 'engineering',
            'items': engineering_items,
        })

        if 'quality.alert' in self.env:
            QA = self.env['quality.alert'].sudo()
            qa_domain = cd('quality.alert')
            if 'stage_id' in QA._fields:
                sections[-1]['items'].append(
                    self._item('Quality alerts open', QA.search_count(qa_domain),
                               'cpabooks_quality_community.quality_alert_team_action', 'pending'),
                )

        PO = self.env['purchase.order'].sudo()
        Picking = self.env['stock.picking'].sudo()
        sections.append({
            'id': 'purchase',
            'title': 'Purchase / Store',
            'theme': 'purchase',
            'items': [
                self._item('Purchase RFQ / draft', PO.search_count(cd('purchase.order') + [
                    ('state', 'in', ('draft', 'sent', 'to approve')),
                ]), 'purchase.purchase_rfq', 'pending'),
                self._item('Purchase orders confirmed', PO.search_count(cd('purchase.order') + [
                    ('state', 'in', ('purchase', 'done')),
                ]), 'purchase.purchase_form_action', 'progress'),
                self._item('GRN — to receive', Picking.search_count(cd('stock.picking') + [
                    ('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel')),
                ]), 'saaskul_switchgear.action_switchgear_stock_incoming', 'pending'),
                self._item('Delivery — to ship', Picking.search_count(cd('stock.picking') + [
                    ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel')),
                ]), 'saaskul_switchgear.action_switchgear_stock_outgoing', 'pending'),
            ],
        })

        Move = self.env['account.move'].sudo()
        Payment = self.env['account.payment'].sudo()
        sections.append({
            'id': 'accounting',
            'title': 'Accounting',
            'theme': 'accounting',
            'items': [
                self._item('Customer invoices — draft', Move.search_count(cd('account.move') + [
                    ('move_type', '=', 'out_invoice'), ('state', '=', 'draft'),
                ]), 'account.action_move_out_invoice_type', 'pending'),
                self._item('Customer invoices — posted unpaid', Move.search_count(cd('account.move') + [
                    ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                ]), 'account.action_move_out_invoice_type', 'progress'),
                self._item('Vendor bills — draft', Move.search_count(cd('account.move') + [
                    ('move_type', '=', 'in_invoice'), ('state', '=', 'draft'),
                ]), 'account.action_move_in_invoice_type', 'pending'),
                self._item('Customer receipts', Payment.search_count(cd('account.payment') + [
                    ('payment_type', '=', 'inbound'), ('state', '=', 'draft'),
                ]), 'account.action_account_payments', 'pending'),
                self._item('Vendor payments', Payment.search_count(cd('account.payment') + [
                    ('payment_type', '=', 'outbound'), ('state', '=', 'draft'),
                ]), 'account.action_account_payments_payable', 'pending'),
            ],
        })

        DesignDoc = self.env['switchgear.design.document'].sudo()
        sections.insert(2, {
            'id': 'design_documents',
            'title': 'Design Documents',
            'theme': 'engineering',
            'items': [
                self._item(
                    'Design registers',
                    DesignDoc.search_count(cd('switchgear.design.document')),
                    'saaskul_switchgear.action_switchgear_design_document',
                    'progress',
                ),
                self._item(
                    'Documents sent (lines)',
                    self.env['switchgear.design.document.sent.line'].sudo().search_count([]),
                    'saaskul_switchgear.action_switchgear_design_document',
                    'pending',
                ),
                self._item(
                    'Documents received (lines)',
                    self.env['switchgear.design.document.received.line'].sudo().search_count([]),
                    'saaskul_switchgear.action_switchgear_design_document',
                    'pending',
                ),
            ],
        })

        return sections

    @api.model
    def _item(self, label, count, action_xmlid, status):
        return {
            'label': label,
            'count': count,
            'action_xmlid': action_xmlid,
            'status': status,
        }

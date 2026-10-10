# -*- coding: utf-8 -*-

import datetime

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    job_quotation = fields.Boolean(string='Is Job Quotation', default=True)
    bom_count = fields.Integer('# Bill of Material', compute='_compute_bom_count')
    bom_product_id = fields.Many2one('product.product', string='BOM Product')
    document_sent_ids = fields.One2many(
        'sale.order.document.sent.line',
        'order_id',
        string='Documents Sent',
        copy=True,
    )
    document_received_ids = fields.One2many(
        'sale.order.document.received.line',
        'order_id',
        string='Documents Received',
        copy=True,
    )
    # Fields used by cpabooks_job_order sale views — defined here so SO forms
    # stay open even when job_order fails to load on a server.
    job_count = fields.Integer(compute='_compute_job_count')
    show_job_order_button = fields.Boolean(compute='_compute_show_job_order_button')
    is_technical_submittal = fields.Boolean(string='Technical Submittal')
    ts_project = fields.Char(string='Project')
    ts_location = fields.Char(string='Location')
    ts_owner = fields.Char(string='Owner')
    ts_project_mgmt = fields.Char(string='Project Management')
    ts_consultant = fields.Char(string='Consultant')
    ts_mep_consultant = fields.Char(string='MEP Consultant')
    ts_main_consultant = fields.Char(string='Main Consultant')
    ts_mep_contractor = fields.Char(string='MEP Contractor')
    ts_designed_panels = fields.Char(string='Designed Panels')
    ts_reference_no = fields.Char(string='Reference No.')
    direct_sale = fields.Boolean(string='Direct Sale')

    def _compute_bom_count(self):
        for order in self:
            order.bom_count = self.env['mrp.bom'].search_count([('sale_order_id', '=', order.id)])

    @api.depends('state', 'order_line.product_uom_qty', 'order_line.job_order_qty')
    def _compute_show_job_order_button(self):
        for order in self:
            order.show_job_order_button = False
            if not order.job_quotation or order.state != 'sale':
                continue
            for line in order.order_line:
                remaining = line.product_uom_qty - (line.job_order_qty or 0.0)
                if remaining > 0:
                    order.show_job_order_button = True
                    break

    @api.depends('state')
    def _compute_job_count(self):
        JobOrder = self.env.get('quotation.job.order')
        for order in self:
            if JobOrder is not None:
                order.job_count = JobOrder.sudo().search_count([
                    ('quotation_no', '=', order.id),
                ])
            else:
                order.job_count = 0

    @api.onchange('direct_sale')
    def _onchange_direct_sale_job_quotation(self):
        for rec in self:
            rec.job_quotation = not bool(rec.direct_sale)

    def confirm_sale_order(self):
        """Confirm job quotations (button from cpabooks_job_order view).

        Implemented here so Confirm still works when job_order views are
        loaded but its Python models failed to register on the server.
        """
        for order in self:
            if (
                'is_project_create' in order._fields
                and order.is_project_create
                and not order.project_id
            ):
                project = order.env['project.project'].sudo().create({
                    'name': order.name,
                    'label_tasks': 'Task',
                    'user_id': order.env.user.id,
                    'partner_id': order.partner_id.id,
                    'privacy_visibility': 'portal',
                })
                analytic_acc = order.env['account.analytic.account'].sudo().create({
                    'name': project.name,
                    'partner_id': project.partner_id.id,
                })
                project.analytic_account_id = analytic_acc.id
                order.project_id = project.id
                order.analytic_account_id = project.analytic_account_id.id
            order.state = 'sale'
        return True

    def _cpabooks_optional_field(self, field_name, default=False):
        if field_name in self._fields:
            return self[field_name] or default
        return default

    def _cpabooks_job_order_lines(self):
        job_lines = []
        for line in self.order_line:
            job_qty = getattr(line, 'job_order_qty', 0.0) or 0.0
            qty = line.product_uom_qty - job_qty
            if qty <= 0:
                continue
            job_line = {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_uom': line.product_uom.id,
                'product_uom_qty': qty,
                'quotation_line_id': line.id,
            }
            if 'line_no' in line._fields:
                job_line['line_no'] = line.line_no
            job_lines.append(job_line)
        return job_lines

    def _cpabooks_job_order_context(self, job_lines):
        self.ensure_one()
        ctx = {
            'default_partner_id': self.partner_id.id,
            'default_project_id': self.project_id.id if 'project_id' in self._fields else False,
            'default_quotation_no': self.id,
            'default_validity_date': self.validity_date,
            'default_job_order_date': datetime.datetime.now().date(),
            'default_order_line': job_lines,
            'default_warehouse_id': self.warehouse_id.id,
            'default_sale_person': self.user_id.id,
        }
        field_map = {
            'enquiry_number': 'enquiry_number',
            'attention': 'attention',
            'subject': 'subject',
            'delivery_detail': 'delivery',
            'make_detail': 'make',
            'bank_detail_enable': 'bank_detail_enable',
        }
        for so_field, jo_field in field_map.items():
            if so_field in self._fields:
                ctx['default_%s' % jo_field] = self[so_field]
        return ctx

    def action_create_job_order(self):
        """Open job order form from quotation (button from cpabooks_job_order view)."""
        self.ensure_one()
        JobOrder = self.env.get('quotation.job.order')
        if JobOrder is None:
            raise ValidationError(_('Job Order module is not installed.'))

        form_view = self.env.ref(
            'cpabooks_job_order.view_job_order_form',
            raise_if_not_found=False,
        )
        if not form_view:
            raise ValidationError(_('Job Order form view is not available.'))

        job_lines = self._cpabooks_job_order_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Order'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'quotation.job.order',
            'views': [(form_view.id, 'form')],
            'target': 'current',
            'context': self._cpabooks_job_order_context(job_lines),
        }

    def show_job_order(self):
        """Smart button to open linked job order(s)."""
        self.ensure_one()
        JobOrder = self.env.get('quotation.job.order')
        if JobOrder is None:
            raise ValidationError(_('Job Order module is not installed.'))

        action = self.env['ir.actions.actions']._for_xml_id(
            'cpabooks_job_order.action_job_orders',
        )
        if self.job_count > 1:
            action['domain'] = [('quotation_no', '=', self.id)]
        else:
            form_view = self.env.ref(
                'cpabooks_job_order.view_job_order_form',
                raise_if_not_found=False,
            )
            if not form_view:
                raise ValidationError(_('Job Order form view is not available.'))
            job_order = JobOrder.sudo().search([
                ('quotation_no', '=', self.id),
            ], limit=1)
            form_view_tuple = [(form_view.id, 'form')]
            if 'views' in action:
                action['views'] = form_view_tuple + [
                    (state, view) for state, view in action['views'] if view != 'form'
                ]
            else:
                action['views'] = form_view_tuple
            action['res_id'] = job_order.id
        action['context'] = dict(self._context, default_quotation_no=self.id, create=False)
        return action

    def action_create_bom(self):
        if not self.bom_product_id:
            raise ValidationError(_('Please select BOM Product to create BOM'))
        if self.bom_product_id:
            bom_id = self.env['mrp.bom'].create({
                'product_id': self.bom_product_id.id,
                'product_tmpl_id': self.bom_product_id.product_tmpl_id.id,
                'product_qty': 1.0,
                'type': 'normal',
                'sale_order_id': self.id,
            })
            if bom_id:
                for line in self.order_line:
                    self.env['mrp.bom.line'].create({
                        'product_id': line.product_id.id,
                        'product_qty': line.product_uom_qty,
                        'bom_id': bom_id.id,
                        'product_uom_id': line.product_uom.id,
                    })

# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    task_id = fields.Many2one(
        'project.task',
        string='CRN No',
        domain="[('task_seq', '=like', 'CRN%')]",
        ondelete='set null',
    )

    @api.onchange('task_id')
    def _onchange_task_id_populate_from_crn(self):
        for order in self:
            task = order.task_id
            if not task:
                continue

            partner = task.partner_id or task.project_id.partner_id
            if partner:
                order.partner_id = partner
                if hasattr(order, 'onchange_partner_id'):
                    order.onchange_partner_id()
                elif hasattr(order, '_onchange_partner_id'):
                    order._onchange_partner_id()

            if task.project_id and 'project_id' in order._fields:
                order.project_id = task.project_id
            if task.analytic_account_id:
                order.analytic_account_id = task.analytic_account_id
            elif task.project_id and task.project_id.analytic_account_id:
                order.analytic_account_id = task.project_id.analytic_account_id
            if task.company_id:
                order.company_id = task.company_id
            if task.user_id:
                order.user_id = task.user_id
            if task.task_seq and not order.client_order_ref:
                order.client_order_ref = task.task_seq

            if task.task_seq and 'enquiry_number' in order._fields:
                order.enquiry_number = task.task_seq
            if 'attention' in order._fields:
                order.attention = task.client_person.display_name or False
            if 'subject' in order._fields:
                order.subject = (
                    task.complaint_title.display_name
                    or task.name
                    or task.task_seq
                    or False
                )
            if 'delivery_detail' in order._fields:
                order.delivery_detail = task.site_location.display_name or False

            note_parts = []
            if task.client_person:
                note_parts.append('Contact Person: %s' % task.client_person.display_name)
            if task.client_contact:
                note_parts.append('Contact Number: %s' % task.client_contact)
            if task.client_email:
                note_parts.append('Email: %s' % task.client_email)
            if task.complaint_title:
                note_parts.append('Complaint: %s' % task.complaint_title.display_name)
            if task.complaint_details:
                note_parts.append('Details: %s' % task.complaint_details)
            if task.site_location:
                note_parts.append('Site: %s' % task.site_location.display_name)
            if note_parts:
                order.note = '\n'.join(note_parts)

            if task.qt_no and not order.order_line:
                order.order_line = [(5, 0, 0)] + [
                    (0, 0, order._prepare_crn_order_line_vals(line))
                    for line in task.qt_no.order_line.filtered(lambda l: not l.display_type)
                ]

    def _prepare_crn_order_line_vals(self, line):
        return {
            'product_id': line.product_id.id,
            'name': line.name,
            'product_uom_qty': line.product_uom_qty,
            'product_uom': line.product_uom.id,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'tax_id': [(6, 0, line.tax_id.ids)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._sync_task_quotation_link()
        tasks = orders.mapped('task_id')
        tasks._update_fsm_stage_group()
        tasks._cpabooks_refresh_fsm_quotation_display()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'task_id' in vals:
            self._sync_task_quotation_link()
        if {'task_id', 'state'} & set(vals):
            tasks = self.mapped('task_id')
            tasks._update_fsm_stage_group()
            tasks._cpabooks_refresh_fsm_quotation_display()
        return res

    def _sync_task_quotation_link(self):
        for order in self.filtered('task_id'):
            order.task_id.qt_no = order.id

    def _check_crn_quotation_send_allowed(self):
        blocked = self.filtered(lambda o: o.task_id and o.state not in ('sale', 'done'))
        if blocked:
            raise UserError(_(
                'This quotation is linked to a CRN. Please confirm the quotation first, '
                'then send it to the customer.'
            ))

    def action_quotation_send(self):
        self._check_crn_quotation_send_allowed()
        return super().action_quotation_send()

    def action_quotation_sent(self):
        self._check_crn_quotation_send_allowed()
        return super().action_quotation_sent()

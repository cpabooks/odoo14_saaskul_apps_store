# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SwitchgearPurchaseRequisition(models.Model):
    _name = 'switchgear.purchase.requisition'
    _description = 'Switchgear Purchase Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'cpabooks.document.progress.mixin']
    _order = 'requisition_date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))
    employee_id = fields.Many2one('hr.employee', string='Requested By', tracking=True,
                                  default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', string='Department')
    requisition_date = fields.Date(string='Requisition Date', default=fields.Date.context_today, required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    project_id = fields.Many2one('project.project', string='Job Order', index=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', index=True)
    picking_type_id = fields.Many2one('stock.picking.type', string='Receipt Type',
                                      domain="[('code', '=', 'incoming')]",
                                      default=lambda self: self._default_picking_type())
    reason_for_requisition = fields.Text(string='Reason')
    requisition_line_ids = fields.One2many('switchgear.purchase.requisition.line', 'requisition_id',
                                           string='Products', copy=True)
    purchase_ids = fields.One2many('purchase.order', 'sg_requisition_id', string='Purchase Orders', copy=False)
    purchase_count = fields.Integer(compute='_compute_purchase_count')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('po_created', 'Purchase Order Created'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    @api.model
    def _default_picking_type(self):
        return self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', self.env.company.id),
        ], limit=1)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('switchgear.purchase.requisition') or _('New')
        return super().create(vals)

    @api.depends('purchase_ids')
    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = len(rec.purchase_ids)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id.department_id:
            self.department_id = self.employee_id.department_id

    def action_confirm(self):
        if any(not rec.requisition_line_ids for rec in self):
            raise UserError(_('Add at least one product before submitting the requisition.'))
        self.filtered(lambda r: r.state == 'draft').write({'state': 'confirmed'})
        return True

    def action_approve(self):
        self.filtered(lambda r: r.state == 'confirmed').write({'state': 'approved'})
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state != 'po_created').write({'state': 'cancel'})
        return True

    def action_draft(self):
        self.filtered(lambda r: r.state == 'cancel').write({'state': 'draft'})
        return True

    def action_create_po(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Approve the requisition before creating purchase orders.'))
        lines_by_vendor = {}
        for line in self.requisition_line_ids:
            vendor = line.vendor_id or line.product_id.seller_ids[:1].name
            if not vendor:
                raise UserError(_('Set a vendor on line "%s".') % line.product_id.display_name)
            lines_by_vendor.setdefault(vendor, self.env['switchgear.purchase.requisition.line'])
            lines_by_vendor[vendor] |= line
        orders = self.env['purchase.order']
        for vendor, lines in lines_by_vendor.items():
            vals = {
                'partner_id': vendor.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'sg_requisition_id': self.id,
                'project_id': self.project_id.id,
                'mo_id': self.production_id.id,
                'order_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.description or line.product_id.display_name,
                    'product_qty': line.qty,
                    'product_uom': (line.uom_id or line.product_id.uom_po_id).id,
                    'price_unit': line.product_id.standard_price,
                    'date_planned': fields.Datetime.now(),
                }) for line in lines],
            }
            if self.picking_type_id:
                vals['picking_type_id'] = self.picking_type_id.id
            orders |= self.env['purchase.order'].create(vals)
        self.state = 'po_created'
        return self.action_view_purchase_orders()

    def action_view_purchase_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('purchase.purchase_rfq')
        action['domain'] = [('sg_requisition_id', '=', self.id)]
        action['context'] = {}
        if len(self.purchase_ids) == 1:
            action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            action['res_id'] = self.purchase_ids.id
        return action


class SwitchgearPurchaseRequisitionLine(models.Model):
    _name = 'switchgear.purchase.requisition.line'
    _description = 'Switchgear Purchase Requisition Line'

    requisition_id = fields.Many2one('switchgear.purchase.requisition', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 domain="[('purchase_ok', '=', True)]")
    description = fields.Char(string='Description')
    qty = fields.Float(string='Quantity', default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_po_id
            self.vendor_id = self.product_id.seller_ids[:1].name

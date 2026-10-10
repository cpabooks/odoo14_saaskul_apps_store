# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SwitchgearEstimate(models.Model):
    _name = 'switchgear.estimate'
    _description = 'Switchgear Job Estimate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Estimate', readonly=True, copy=False, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency')
    user_id = fields.Many2one('res.users', string='Created By', default=lambda self: self.env.user)
    sales_person_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user)
    project_id = fields.Many2one('project.project', string='Job Order')
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    customer_ref = fields.Char(string='Customer Reference')
    description = fields.Text(string='Description')
    profit_percent = fields.Float(string='Profit (%)')
    sale_quotation_id = fields.Many2one('sale.order', string='Quotation', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('done', 'Quotation Created'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    opportunity_id = fields.Many2one('crm.lead', string='Opportunity', domain="[('type', '=', 'opportunity')]")
    crm_reference = fields.Char(string='CRM Reference', related='opportunity_id.enquiry_number')
    bom_id = fields.Many2one('mrp.bom', string='BoM Item Template')
    bom_reference = fields.Char(string='BOM Reference', related='bom_id.name')
    bom_product_id = fields.Many2one('product.product', string='BoM Item Name')
    bom_count = fields.Integer('# Bill of Material', compute='_compute_bom_count')

    material_estimation_ids = fields.One2many('switchgear.estimate.material', 'estimate_id', string='Materials', copy=True)
    labour_estimation_ids = fields.One2many('switchgear.estimate.labour', 'estimate_id', string='Labour', copy=True)
    overhead_estimation_ids = fields.One2many('switchgear.estimate.overhead', 'estimate_id', string='Overheads', copy=True)

    total_material_estimate = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    total_labour_estimate = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    total_overhead_estimate = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    total_cost_estimate = fields.Monetary(string='Total Cost', compute='_compute_totals', store=True,
                                          currency_field='currency_id')
    total_job_estimate = fields.Monetary(string='Total Estimate', compute='_compute_totals', store=True,
                                         currency_field='currency_id')
    quotation_count = fields.Integer(compute='_compute_quotation_count')

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('switchgear.estimate') or _('New')
        return super().create(vals)

    @api.depends('material_estimation_ids.subtotal', 'labour_estimation_ids.subtotal',
                 'overhead_estimation_ids.subtotal', 'profit_percent')
    def _compute_totals(self):
        for rec in self:
            rec.total_material_estimate = sum(rec.material_estimation_ids.mapped('subtotal'))
            rec.total_labour_estimate = sum(rec.labour_estimation_ids.mapped('subtotal'))
            rec.total_overhead_estimate = sum(rec.overhead_estimation_ids.mapped('subtotal'))
            rec.total_cost_estimate = (rec.total_material_estimate + rec.total_labour_estimate
                                       + rec.total_overhead_estimate)
            rec.total_job_estimate = rec.total_cost_estimate * (1.0 + (rec.profit_percent or 0.0) / 100.0)

    def _compute_quotation_count(self):
        for rec in self:
            rec.quotation_count = self.env['sale.order'].search_count([('job_estimate_id', '=', rec.id)])

    def _compute_bom_count(self):
        for rec in self:
            rec.bom_count = self.env['mrp.bom'].search_count([('estimate_id', '=', rec.id)])

    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        for rec in self:
            if not rec.bom_id:
                continue
            tmpl = rec.bom_id.product_tmpl_id
            rec.bom_product_id = rec.bom_id.product_id or tmpl.product_variant_id
            rec.material_estimation_ids = [(5, 0, 0)] + [(0, 0, {
                'product_id': line.product_id.id,
                'description': line.product_id.display_name,
                'quantity': line.product_qty,
                'uom_id': line.product_uom_id.id,
                'price_unit': line.product_id.standard_price,
            }) for line in rec.bom_id.bom_line_ids]

    @api.onchange('opportunity_id')
    def _onchange_opportunity_id(self):
        if self.opportunity_id and self.opportunity_id.partner_id:
            self.partner_id = self.opportunity_id.partner_id

    def action_job_confirm(self):
        for rec in self:
            if not (rec.material_estimation_ids or rec.labour_estimation_ids or rec.overhead_estimation_ids):
                raise UserError(_('Add at least one material, labour or overhead line before confirming.'))
        self.filtered(lambda r: r.state == 'draft').write({'state': 'confirmed'})
        return True

    def action_approve(self):
        self.filtered(lambda r: r.state == 'confirmed').write({'state': 'approved'})
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state != 'done').write({'state': 'cancel'})
        return True

    def action_set_to_draft(self):
        self.filtered(lambda r: r.state == 'cancel').write({'state': 'draft'})
        return True

    def _prepare_quotation_vals(self):
        self.ensure_one()
        product = self.bom_product_id
        if not product:
            raise UserError(_('Set the BoM item before creating the quotation.'))
        vals = {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'user_id': self.sales_person_id.id or self.env.user.id,
            'opportunity_id': self.opportunity_id.id,
            'origin': self.name,
            'client_order_ref': self.customer_ref,
            'job_estimate_id': self.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': self.description or product.display_name,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'price_unit': self.total_job_estimate,
            })],
        }
        if self.analytic_id:
            vals['analytic_account_id'] = self.analytic_id.id
        if self.project_id:
            vals['project_id'] = self.project_id.id
        return vals

    def action_create_quotation(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved estimates can be turned into a quotation.'))
        order = self.env['sale.order'].create(self._prepare_quotation_vals())
        self.write({'sale_quotation_id': order.id, 'state': 'done'})
        return self.action_view_quotations()

    def action_view_quotations(self):
        self.ensure_one()
        orders = self.env['sale.order'].search([('job_estimate_id', '=', self.id)])
        action = self.env['ir.actions.actions']._for_xml_id('sale.action_quotations_with_onboarding')
        action['domain'] = [('id', 'in', orders.ids)]
        action['context'] = {'default_job_estimate_id': self.id, 'default_partner_id': self.partner_id.id}
        if len(orders) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = orders.id
        return action

    def action_create_bom(self):
        self.ensure_one()
        bom = self._create_bom()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bill of Materials'),
            'res_model': 'mrp.bom',
            'res_id': bom.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_bom(self):
        self.ensure_one()
        if not self.bom_product_id:
            raise ValidationError(_('Please select BOM Product to create BOM'))
        bom = self.env['mrp.bom'].create({
            'product_id': self.bom_product_id.id,
            'product_tmpl_id': self.bom_product_id.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'normal',
            'estimate_id': self.id,
            'project_id': self.project_id.id,
            'partner_id': self.partner_id.id,
        })
        for line in self.material_estimation_ids.filtered(lambda l: l.product_id.type != 'service'):
            self.env['mrp.bom.line'].create({
                'bom_id': bom.id,
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'product_uom_id': (line.uom_id or line.product_id.uom_id).id,
            })
        return bom


class SwitchgearEstimateLineMixin(models.AbstractModel):
    _name = 'switchgear.estimate.line.mixin'
    _description = 'Switchgear Estimate Line'

    estimate_id = fields.Many2one('switchgear.estimate', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='estimate_id.company_id', store=True)
    currency_id = fields.Many2one(related='estimate_id.currency_id')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    price_unit = fields.Float(string='Unit Price', digits='Product Price')
    discount = fields.Float(string='Discount (%)')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True,
                               currency_field='currency_id')

    def _base_amount(self):
        self.ensure_one()
        return self.quantity * self.price_unit

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line._base_amount() * (1.0 - (line.discount or 0.0) / 100.0)

    def _default_price(self, product):
        return product.standard_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.price_unit = self._default_price(self.product_id)


class SwitchgearEstimateMaterial(models.Model):
    _name = 'switchgear.estimate.material'
    _inherit = 'switchgear.estimate.line.mixin'
    _description = 'Switchgear Estimate Material'


class SwitchgearEstimateLabour(models.Model):
    _name = 'switchgear.estimate.labour'
    _inherit = 'switchgear.estimate.line.mixin'
    _description = 'Switchgear Estimate Labour'

    hours = fields.Float(string='Hours', default=1.0)

    @api.constrains('hours')
    def _check_hours(self):
        if any(line.hours <= 0 for line in self):
            raise ValidationError(_('Labour hours must be greater than zero.'))

    def _base_amount(self):
        self.ensure_one()
        return self.quantity * self.price_unit * self.hours

    @api.depends('quantity', 'price_unit', 'discount', 'hours')
    def _compute_subtotal(self):
        super()._compute_subtotal()

    def _default_price(self, product):
        return product.list_price


class SwitchgearEstimateOverhead(models.Model):
    _name = 'switchgear.estimate.overhead'
    _inherit = 'switchgear.estimate.line.mixin'
    _description = 'Switchgear Estimate Overhead'

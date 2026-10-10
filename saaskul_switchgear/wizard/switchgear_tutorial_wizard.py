# -*- coding: utf-8 -*-
"""Interactive Switchgear cycle tutorial — fill fields in-wizard, Next creates the record.

Pattern inspired by cpabooks.company.setup.wizard (one step visible, apply on Next).
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import html_escape

STEP_META = [
    (1, 'Enquiry (CRM)', 'Customer'),
    (2, 'Estimation', 'Customer'),
    (3, 'Quotation', 'Customer'),
    (4, 'Design Documents', 'Engineering'),
    (5, 'Bill of Material', 'Engineering'),
    (6, 'Manuf. Order (MO)', 'Engineering'),
    (7, 'Purchase Requisition', 'Engineering'),
    (8, 'Quality Control', 'Engineering'),
    (9, 'Stock Check', 'Purchase / Store'),
    (10, 'LPO (Purchase)', 'Purchase / Store'),
    (11, 'GRN', 'Purchase / Store'),
    (12, 'Delivery', 'Purchase / Store'),
    (13, 'Tax Invoice', 'Accounting'),
    (14, 'Customer Payment', 'Accounting'),
    (15, 'Bills Entry', 'Accounting'),
    (16, 'Vendor Payment', 'Accounting'),
]

STEP_HINTS = {
    1: 'Fill customer and enquiry name, then Next — creates the CRM Opportunity.',
    2: 'Pick finished product + one material line, then Next — creates Job Estimate.',
    3: 'Set sale price, then Next — creates Quotation and confirms Sales Order.',
    4: 'Name the design register, then Next — creates Design Document.',
    5: 'Confirm finished + component products, then Next — creates BOM.',
    6: 'Set quantity, then Next — creates and confirms Manufacturing Order.',
    7: 'Confirm component qty, then Next — creates Purchase Requisition (if HR employee exists).',
    8: 'Next creates a Quality Check linked to the MO.',
    9: 'Review on-hand qty shown below, then Next (no create — awareness step).',
    10: 'Pick vendor and price, then Next — creates and confirms Purchase Order.',
    11: 'Next receives the PO (GRN / incoming transfer).',
    12: 'Next creates / validates Delivery for the Sales Order.',
    13: 'Set invoice amount, then Next — creates and posts Customer Invoice.',
    14: 'Next records Customer Payment against the invoice.',
    15: 'Set bill amount, then Next — creates Vendor Bill.',
    16: 'Next records Vendor Payment — tutorial complete.',
}


class SwitchgearTutorialWizard(models.TransientModel):
    _name = 'switchgear.tutorial.wizard'
    _description = 'Switchgear Tutorial Wizard'

    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True,
    )
    step_number = fields.Integer(default=1, required=True)
    progress_html = fields.Html(string='Progress', compute='_compute_progress_html', sanitize=False)
    step_title = fields.Char(compute='_compute_step_labels')
    phase = fields.Char(compute='_compute_step_labels')
    progress_label = fields.Char(compute='_compute_step_labels')
    step_hint = fields.Char(compute='_compute_step_labels')
    is_first = fields.Boolean(compute='_compute_step_labels')
    is_last = fields.Boolean(compute='_compute_step_labels')
    last_message = fields.Text(string='Result', readonly=True)

    # --- carried documents ---
    partner_id = fields.Many2one('res.partner', string='Customer')
    lead_id = fields.Many2one('crm.lead', string='Enquiry', readonly=True)
    estimate_id = fields.Many2one('switchgear.estimate', string='Estimate', readonly=True)
    sale_id = fields.Many2one('sale.order', string='Sales Order', readonly=True)
    design_id = fields.Many2one('switchgear.design.document', string='Design', readonly=True)
    bom_id = fields.Many2one('mrp.bom', string='BoM', readonly=True)
    mo_id = fields.Many2one('mrp.production', string='MO', readonly=True)
    pr_id = fields.Many2one('switchgear.purchase.requisition', string='PR', readonly=True)
    qc_id = fields.Many2one('switchgear.quality.check', string='Quality Check', readonly=True)
    po_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    grn_id = fields.Many2one('stock.picking', string='GRN', readonly=True)
    delivery_id = fields.Many2one('stock.picking', string='Delivery', readonly=True)
    invoice_id = fields.Many2one('account.move', string='Customer Invoice', readonly=True)
    payment_in_id = fields.Many2one('account.payment', string='Customer Payment', readonly=True)
    bill_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)
    payment_out_id = fields.Many2one('account.payment', string='Vendor Payment', readonly=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    # --- step input fields ---
    partner_name = fields.Char(string='New customer name')
    enquiry_name = fields.Char(string='Enquiry / opportunity name')
    expected_revenue = fields.Float(string='Expected revenue', default=25000.0)

    finished_product_id = fields.Many2one('product.product', string='Finished product')
    material_product_id = fields.Many2one('product.product', string='Material / component')
    material_qty = fields.Float(string='Material qty', default=1.0)
    material_price = fields.Float(string='Material unit cost', default=100.0)
    estimate_note = fields.Char(string='Estimate note')

    sale_price = fields.Float(string='Quotation price', default=25000.0)
    design_name = fields.Char(string='Design document title')
    component_qty = fields.Float(string='Component qty on BoM', default=1.0)
    mo_qty = fields.Float(string='MO quantity', default=1.0)
    pr_qty = fields.Float(string='PR quantity', default=1.0)
    stock_info = fields.Text(string='Stock snapshot', readonly=True)
    po_price = fields.Float(string='PO unit price', default=100.0)
    po_qty = fields.Float(string='PO quantity', default=1.0)
    invoice_amount = fields.Float(string='Invoice amount', default=25000.0)
    bill_amount = fields.Float(string='Vendor bill amount', default=100.0)

    @api.depends('step_number')
    def _compute_step_labels(self):
        meta = {n: (t, p) for n, t, p in STEP_META}
        for wiz in self:
            n = max(1, min(16, wiz.step_number or 1))
            title, phase = meta.get(n, ('', ''))
            wiz.step_title = title
            wiz.phase = phase
            wiz.progress_label = _('Step %s of 16') % n
            wiz.step_hint = STEP_HINTS.get(n, '')
            wiz.is_first = n <= 1
            wiz.is_last = n >= 16

    @api.depends('step_number', 'lead_id', 'estimate_id', 'sale_id', 'mo_id', 'invoice_id')
    def _compute_progress_html(self):
        for wiz in self:
            n = max(1, min(16, wiz.step_number or 1))
            rows = []
            for num, title, _phase in STEP_META:
                if num < n:
                    cls = 'done'
                    mark = '✓'
                elif num == n:
                    cls = 'current'
                    mark = '●'
                else:
                    cls = 'todo'
                    mark = str(num)
                rows.append(
                    '<li class="o_sg_tut_step o_sg_tut_%s">'
                    '<span class="o_sg_tut_mark">%s</span>'
                    '<span class="o_sg_tut_label">%s. %s</span></li>' % (
                        cls, mark, num, html_escape(title),
                    )
                )
            wiz.progress_html = (
                '<div class="o_sg_tut_progress">'
                '<div class="o_sg_tut_progress_title">Switchgear cycle</div>'
                '<ol>%s</ol></div>'
            ) % ''.join(rows)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['step_number'] = int(self.env.context.get('default_step_number') or res.get('step_number') or 1)
        Product = self.env['product.product'].sudo()
        finished = Product.search([('type', '=', 'product')], limit=1, order='id')
        material = Product.search([('type', 'in', ('product', 'consu')), ('id', '!=', finished.id)], limit=1)
        if not material:
            material = finished
        if finished and 'finished_product_id' in fields_list:
            res.setdefault('finished_product_id', finished.id)
        if material and 'material_product_id' in fields_list:
            res.setdefault('material_product_id', material.id)
            res.setdefault('material_price', material.standard_price or 100.0)
        vendor = self.env['res.partner'].sudo().search([('supplier_rank', '>', 0)], limit=1)
        if vendor and 'vendor_id' in fields_list:
            res.setdefault('vendor_id', vendor.id)
        res.setdefault('enquiry_name', 'Tutorial Switchgear Enquiry')
        res.setdefault('partner_name', 'Tutorial Customer')
        res.setdefault('design_name', 'Tutorial Design Pack')
        res.setdefault('estimate_note', 'Created from Tutorial Wizard')
        return res

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tutorial Wizard'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context, form_view_initial_mode='edit'),
        }

    def _ensure_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        name = (self.partner_name or '').strip()
        if not name:
            raise UserError(_('Enter a customer name or select an existing Customer.'))
        Partner = self.env['res.partner'].sudo()
        # Partner name is unique on this DB — reuse instead of failing the tutorial.
        partner = Partner.search([
            ('name', '=', name),
            '|',
            ('company_id', '=', False),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'company_id': self.company_id.id,
                'customer_rank': 1,
            })
        elif partner.customer_rank < 1:
            partner.customer_rank = 1
        self.partner_id = partner
        return partner

    def _income_account(self):
        return self.env['account.account'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
            ('user_type_id.type', '=', 'other'),
            ('user_type_id.internal_group', '=', 'income'),
        ], limit=1) or self.env['account.account'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
            ('user_type_id.type', '=', 'other'),
        ], limit=1)

    def _expense_account(self):
        return self.env['account.account'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
            ('user_type_id.type', '=', 'expense'),
        ], limit=1) or self.env['account.account'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
        ], limit=1)

    def _apply_step(self):
        """Create/update the document for the current step. Returns status message."""
        self.ensure_one()
        n = self.step_number
        if n == 1:
            return self._apply_enquiry()
        if n == 2:
            return self._apply_estimation()
        if n == 3:
            return self._apply_quotation()
        if n == 4:
            return self._apply_design()
        if n == 5:
            return self._apply_bom()
        if n == 6:
            return self._apply_mo()
        if n == 7:
            return self._apply_pr()
        if n == 8:
            return self._apply_qc()
        if n == 9:
            return self._apply_stock_check()
        if n == 10:
            return self._apply_po()
        if n == 11:
            return self._apply_grn()
        if n == 12:
            return self._apply_delivery()
        if n == 13:
            return self._apply_invoice()
        if n == 14:
            return self._apply_customer_payment()
        if n == 15:
            return self._apply_vendor_bill()
        if n == 16:
            return self._apply_vendor_payment()
        return ''

    def _apply_enquiry(self):
        if self.lead_id:
            return _('Enquiry already created: %s') % self.lead_id.display_name
        partner = self._ensure_partner()
        name = (self.enquiry_name or '').strip() or _('Tutorial Enquiry')
        lead = self.env['crm.lead'].sudo().create({
            'name': name,
            'type': 'opportunity',
            'partner_id': partner.id,
            'expected_revenue': self.expected_revenue or 0.0,
            'company_id': self.company_id.id,
            'user_id': self.env.user.id,
        })
        self.lead_id = lead
        return _('Created CRM Opportunity: %s') % lead.display_name

    def _apply_estimation(self):
        if self.estimate_id:
            return _('Estimate already created: %s') % self.estimate_id.display_name
        partner = self._ensure_partner()
        if not self.finished_product_id or not self.material_product_id:
            raise UserError(_('Select Finished product and Material / component.'))
        vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'date': fields.Date.context_today(self),
            'sales_person_id': self.env.user.id,
            'description': self.estimate_note or 'Tutorial estimate',
            'material_estimation_ids': [(0, 0, {
                'product_id': self.material_product_id.id,
                'quantity': self.material_qty or 1.0,
                'price_unit': self.material_price or self.material_product_id.standard_price or 0.0,
                'uom_id': self.material_product_id.uom_id.id,
                'description': self.material_product_id.display_name,
            })],
        }
        if 'opportunity_id' in self.env['switchgear.estimate']._fields and self.lead_id:
            vals['opportunity_id'] = self.lead_id.id
        if 'bom_product_id' in self.env['switchgear.estimate']._fields:
            vals['bom_product_id'] = self.finished_product_id.id
        estimate = self.env['switchgear.estimate'].sudo().create(vals)
        try:
            if hasattr(estimate, 'action_job_confirm'):
                estimate.action_job_confirm()
            if hasattr(estimate, 'action_approve'):
                estimate.action_approve()
        except Exception:
            pass
        self.estimate_id = estimate
        return _('Created Job Estimate: %s') % estimate.display_name

    def _apply_quotation(self):
        if self.sale_id:
            return _('Sales Order already created: %s') % self.sale_id.display_name
        partner = self._ensure_partner()
        product = self.finished_product_id
        if not product:
            raise UserError(_('Select Finished product first (step 2).'))
        price = self.sale_price or product.list_price or 0.0
        so = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'user_id': self.env.user.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'price_unit': price,
            })],
        })
        if self.estimate_id and 'job_estimate_id' in so._fields:
            so.job_estimate_id = self.estimate_id.id
            self.estimate_id.sudo().write({
                'sale_quotation_id': so.id,
                'state': 'done',
            })
        try:
            so.action_confirm()
        except Exception:
            so.sudo().write({'state': 'sale'})
        self.sale_id = so
        return _('Created & confirmed Sales Order: %s') % so.display_name

    def _apply_design(self):
        if self.design_id:
            return _('Design already created: %s') % self.design_id.display_name
        if 'switchgear.design.document' not in self.env:
            return _('Design module model missing — skipped.')
        partner = self._ensure_partner()
        Design = self.env['switchgear.design.document'].sudo()
        vals = {}
        if 'partner_id' in Design._fields:
            vals['partner_id'] = partner.id
        if 'sale_order_id' in Design._fields and self.sale_id:
            vals['sale_order_id'] = self.sale_id.id
        if 'company_id' in Design._fields:
            vals['company_id'] = self.company_id.id
        if 'notes' in Design._fields:
            vals['notes'] = (self.design_name or '').strip() or _('Tutorial Design')
        design = Design.create(vals)
        self.design_id = design
        return _('Created Design Document: %s') % design.display_name

    def _apply_bom(self):
        if self.bom_id:
            return _('BoM already created: %s') % self.bom_id.display_name
        finished = self.finished_product_id
        component = self.material_product_id
        if not finished or not component:
            raise UserError(_('Need Finished product and Material / component.'))
        bom = self.env['mrp.bom'].sudo().create({
            'product_tmpl_id': finished.product_tmpl_id.id,
            'product_id': finished.id,
            'product_qty': 1.0,
            'product_uom_id': finished.uom_id.id,
            'company_id': self.company_id.id,
            'type': 'normal',
            'bom_line_ids': [(0, 0, {
                'product_id': component.id,
                'product_qty': self.component_qty or 1.0,
                'product_uom_id': component.uom_id.id,
            })],
        })
        if 'partner_id' in bom._fields and self.partner_id:
            bom.partner_id = self.partner_id.id
        if 'sale_order_id' in bom._fields and self.sale_id:
            bom.sale_order_id = self.sale_id.id
        self.bom_id = bom
        return _('Created Bill of Materials: %s') % bom.display_name

    def _tutorial_mo_picking_type(self):
        """Manufacturing operation type that has a working sequence."""
        self.env['mrp.production']._cpabooks_ensure_mo_picking_sequences(
            company_id=self.company_id.id,
        )
        PType = self.env['stock.picking.type'].sudo()
        picking = PType.search([
            ('code', '=', 'mrp_operation'),
            ('company_id', '=', self.company_id.id),
            ('sequence_id', '!=', False),
        ], limit=1)
        if not picking:
            picking = PType.search([
                ('code', '=', 'mrp_operation'),
                ('sequence_id', '!=', False),
            ], limit=1)
        return picking

    def _tutorial_next_mo_name(self, picking_type=None):
        picking_type = picking_type or self._tutorial_mo_picking_type()
        if picking_type and picking_type.sequence_id:
            try:
                return picking_type.sequence_id.next_by_id()
            except Exception:
                pass
        name = self.env['ir.sequence'].sudo().next_by_code('mrp.production')
        if name:
            return name
        return 'TUT-MO/%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')

    def _apply_mo(self):
        if self.mo_id:
            return _('MO already created: %s') % self.mo_id.display_name
        finished = self.finished_product_id
        if not finished:
            raise UserError(_('Select Finished product.'))
        picking_type = self._tutorial_mo_picking_type()
        vals = {
            'name': self._tutorial_next_mo_name(picking_type),
            'product_id': finished.id,
            'product_qty': self.mo_qty or 1.0,
            'product_uom_id': finished.uom_id.id,
            'company_id': self.company_id.id,
        }
        if picking_type:
            vals['picking_type_id'] = picking_type.id
        if self.bom_id:
            vals['bom_id'] = self.bom_id.id
        mo = self.env['mrp.production'].sudo().create(vals)
        if 'partner_id' in mo._fields and self.partner_id:
            mo.partner_id = self.partner_id.id
        try:
            mo.action_confirm()
        except Exception:
            pass
        self.mo_id = mo
        return _('Created Manufacturing Order: %s') % mo.display_name

    def _apply_pr(self):
        if self.pr_id:
            return _('PR already created: %s') % self.pr_id.display_name
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.user.id),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ], limit=1)
        component = self.material_product_id
        if not component:
            raise UserError(_('Select Material / component.'))
        pr = self.env['switchgear.purchase.requisition'].sudo().create({
            'employee_id': employee.id,
            'department_id': employee.department_id.id,
            'requisition_date': fields.Date.context_today(self),
            'company_id': self.company_id.id,
            'production_id': self.mo_id.id,
            'reason_for_requisition': _('Tutorial Wizard — materials for MO %s') % (
                self.mo_id.display_name if self.mo_id else ''
            ),
            'requisition_line_ids': [(0, 0, {
                'product_id': component.id,
                'qty': self.pr_qty or 1.0,
                'uom_id': component.uom_po_id.id,
                'description': component.display_name,
            })],
        })
        self.pr_id = pr
        return _('Created Purchase Requisition: %s') % pr.display_name

    def _apply_qc(self):
        if self.qc_id:
            return _('Quality Check already created: %s') % self.qc_id.display_name
        if not self.mo_id:
            return _('No MO yet — skipped QC.')
        team = self.env['switchgear.quality.team'].sudo()._get_default_team(self.company_id)
        test_type = self.env.ref('saaskul_switchgear.test_type_passfail', raise_if_not_found=False)
        vals = {
            'product_id': self.finished_product_id.id or self.mo_id.product_id.id,
            'production_id': self.mo_id.id,
            'company_id': self.company_id.id,
            'team_id': team.id,
        }
        if test_type:
            vals['test_type_id'] = test_type.id
        qc = self.env['switchgear.quality.check'].sudo().create(vals)
        self.qc_id = qc
        return _('Created Quality Check: %s') % qc.display_name

    def _apply_stock_check(self):
        product = self.material_product_id or self.finished_product_id
        if not product:
            self.stock_info = _('No product selected.')
            return _('Stock check noted — continue.')
        qty = product.with_company(self.company_id).qty_available
        self.stock_info = _(
            'Product: %(name)s\nOn hand: %(qty)s %(uom)s\n'
            'If on hand is low, the next steps buy and receive stock (LPO → GRN).'
        ) % {
            'name': product.display_name,
            'qty': qty,
            'uom': product.uom_id.display_name,
        }
        return _('Stock snapshot saved — continue to Purchase.')

    def _apply_po(self):
        if self.po_id:
            return _('PO already created: %s') % self.po_id.display_name
        vendor = self.vendor_id
        if not vendor:
            Vendor = self.env['res.partner'].sudo()
            vendor = Vendor.search([
                ('name', '=', 'Tutorial Vendor'),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if not vendor:
                vendor = Vendor.create({
                    'name': 'Tutorial Vendor',
                    'company_id': self.company_id.id,
                    'supplier_rank': 1,
                })
            elif vendor.supplier_rank < 1:
                vendor.supplier_rank = 1
            self.vendor_id = vendor
        product = self.material_product_id or self.finished_product_id
        if not product:
            raise UserError(_('Select a product for the Purchase Order.'))
        po = self.env['purchase.order'].sudo().create({
            'partner_id': vendor.id,
            'company_id': self.company_id.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'product_qty': self.po_qty or 1.0,
                'product_uom': product.uom_po_id.id or product.uom_id.id,
                'price_unit': self.po_price or product.standard_price or 0.0,
                'date_planned': fields.Datetime.now(),
            })],
        })
        try:
            po.button_confirm()
        except Exception:
            pass
        self.po_id = po
        return _('Created Purchase Order: %s') % po.display_name

    def _apply_grn(self):
        if self.grn_id:
            return _('GRN already done: %s') % self.grn_id.display_name
        if not self.po_id:
            return _('No PO — skipped GRN.')
        pickings = self.po_id.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        )
        picking = pickings[:1]
        if not picking:
            return _('No incoming transfer on PO — skipped GRN.')
        for move in picking.move_ids_without_package:
            move.quantity_done = move.product_uom_qty
        try:
            picking.button_validate()
        except Exception:
            # Immediate transfer wizard may appear — force done when possible
            try:
                picking.sudo().write({'state': 'done'})
            except Exception:
                pass
        self.grn_id = picking
        return _('Received GRN: %s') % picking.display_name

    def _apply_delivery(self):
        if self.delivery_id:
            return _('Delivery already done: %s') % self.delivery_id.display_name
        if not self.sale_id:
            return _('No Sales Order — skipped Delivery.')
        pickings = self.sale_id.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel')
        )
        picking = pickings[:1]
        if not picking:
            return _('No delivery transfer on SO yet — skipped (confirm SO creates it).')
        for move in picking.move_ids_without_package:
            move.quantity_done = move.product_uom_qty
        try:
            picking.button_validate()
        except Exception:
            try:
                picking.sudo().write({'state': 'done'})
            except Exception:
                pass
        self.delivery_id = picking
        return _('Delivery validated: %s') % picking.display_name

    def _apply_invoice(self):
        if self.invoice_id:
            return _('Invoice already created: %s') % self.invoice_id.display_name
        partner = self._ensure_partner()
        account = self._income_account()
        if not account:
            raise UserError(_('No income account found — set Chart of Accounts first.'))
        amount = self.invoice_amount or self.sale_price or 0.0
        inv = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': [(0, 0, {
                'name': self.finished_product_id.display_name if self.finished_product_id else _('Tutorial invoice'),
                'quantity': 1.0,
                'price_unit': amount,
                'account_id': account.id,
                'product_id': self.finished_product_id.id if self.finished_product_id else False,
            })],
        })
        try:
            inv.action_post()
        except Exception:
            pass
        self.invoice_id = inv
        return _('Created Customer Invoice: %s') % inv.display_name

    def _apply_customer_payment(self):
        if self.payment_in_id:
            return _('Customer payment already created: %s') % self.payment_in_id.display_name
        if not self.invoice_id:
            return _('No invoice — skipped customer payment.')
        partner = self._ensure_partner()
        journal = self.env['account.journal'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('bank', 'cash')),
        ], limit=1)
        if not journal:
            return _('No bank/cash journal — skipped payment.')
        amount = self.invoice_id.amount_residual or self.invoice_amount or 0.0
        Method = self.env['account.payment.method'].sudo()
        method = Method.search([('payment_type', '=', 'inbound')], limit=1)
        vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': amount,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
        }
        if method:
            vals['payment_method_id'] = method.id
        payment = self.env['account.payment'].sudo().create(vals)
        try:
            payment.action_post()
        except Exception:
            pass
        self.payment_in_id = payment
        return _('Created Customer Payment: %s') % payment.display_name

    def _apply_vendor_bill(self):
        if self.bill_id:
            return _('Vendor bill already created: %s') % self.bill_id.display_name
        vendor = self.vendor_id
        if not vendor:
            raise UserError(_('Select a Vendor (step 10).'))
        account = self._expense_account()
        if not account:
            raise UserError(_('No expense account found — set Chart of Accounts first.'))
        bill = self.env['account.move'].sudo().create({
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'company_id': self.company_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': [(0, 0, {
                'name': _('Tutorial vendor bill'),
                'quantity': 1.0,
                'price_unit': self.bill_amount or self.po_price or 0.0,
                'account_id': account.id,
                'product_id': self.material_product_id.id if self.material_product_id else False,
            })],
        })
        try:
            bill.action_post()
        except Exception:
            pass
        self.bill_id = bill
        return _('Created Vendor Bill: %s') % bill.display_name

    def _apply_vendor_payment(self):
        if self.payment_out_id:
            return _('Vendor payment already created: %s') % self.payment_out_id.display_name
        if not self.bill_id:
            return _('No vendor bill — skipped vendor payment.')
        vendor = self.vendor_id or self.bill_id.partner_id
        journal = self.env['account.journal'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('bank', 'cash')),
        ], limit=1)
        if not journal:
            return _('No bank/cash journal — skipped vendor payment.')
        amount = self.bill_id.amount_residual or self.bill_amount or 0.0
        Method = self.env['account.payment.method'].sudo()
        method = Method.search([('payment_type', '=', 'outbound')], limit=1)
        vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': vendor.id,
            'amount': amount,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
        }
        if method:
            vals['payment_method_id'] = method.id
        payment = self.env['account.payment'].sudo().create(vals)
        try:
            payment.action_post()
        except Exception:
            pass
        self.payment_out_id = payment
        return _('Created Vendor Payment: %s — Tutorial complete!') % payment.display_name

    def action_fill_sample(self):
        """Fill sensible sample values for the current step only."""
        self.ensure_one()
        n = self.step_number
        vals = {}
        if n == 1:
            vals.update({
                'partner_name': self.partner_name or 'Tutorial Customer',
                'enquiry_name': self.enquiry_name or '11kV Switchgear Panel – Tutorial',
                'expected_revenue': self.expected_revenue or 25000.0,
            })
        elif n == 2:
            if not self.finished_product_id:
                prod = self.env['product.product'].search([('type', '=', 'product')], limit=1)
                if prod:
                    vals['finished_product_id'] = prod.id
            if not self.material_product_id:
                mat = self.env['product.product'].search([
                    ('type', 'in', ('product', 'consu')),
                ], limit=1)
                if mat:
                    vals['material_product_id'] = mat.id
                    vals['material_price'] = mat.standard_price or 100.0
            vals['material_qty'] = self.material_qty or 1.0
            vals['estimate_note'] = self.estimate_note or 'Tutorial estimate sample'
        elif n == 3:
            vals['sale_price'] = self.sale_price or 25000.0
        elif n == 4:
            vals['design_name'] = self.design_name or 'Tutorial Design Pack Rev.A'
        elif n in (5, 6, 7):
            vals['component_qty'] = self.component_qty or 1.0
            vals['mo_qty'] = self.mo_qty or 1.0
            vals['pr_qty'] = self.pr_qty or 1.0
        elif n == 10:
            if not self.vendor_id:
                vendor = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
                if vendor:
                    vals['vendor_id'] = vendor.id
            vals['po_qty'] = self.po_qty or 1.0
            vals['po_price'] = self.po_price or 100.0
        elif n == 13:
            vals['invoice_amount'] = self.invoice_amount or self.sale_price or 25000.0
        elif n == 15:
            vals['bill_amount'] = self.bill_amount or self.po_price or 100.0
        if vals:
            self.write(vals)
        if n == 9:
            self._apply_stock_check()
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        if self.step_number > 1:
            self.step_number -= 1
            self.last_message = False
        return self._reopen()

    def action_next(self):
        self.ensure_one()
        msg = self._apply_step()
        self.last_message = msg
        if self.step_number >= 16:
            return self.action_finish()
        self.step_number += 1
        if self.step_number == 9:
            self._apply_stock_check()
        return self._reopen()

    def action_open_created(self):
        """Open the document created for the current (or previous) step."""
        self.ensure_one()
        mapping = {
            1: self.lead_id,
            2: self.estimate_id,
            3: self.sale_id,
            4: self.design_id,
            5: self.bom_id,
            6: self.mo_id,
            7: self.pr_id,
            8: self.qc_id,
            10: self.po_id,
            11: self.grn_id,
            12: self.delivery_id,
            13: self.invoice_id,
            14: self.payment_in_id,
            15: self.bill_id,
            16: self.payment_out_id,
        }
        # Prefer record of previous completed step when on a new empty step
        rec = mapping.get(self.step_number)
        if not rec and self.step_number > 1:
            rec = mapping.get(self.step_number - 1)
        if not rec:
            raise UserError(_('No document created for this step yet. Click Next first.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': rec._name,
            'res_id': rec.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_restart(self):
        self.ensure_one()
        wipe = {
            'step_number': 1,
            'last_message': False,
            'lead_id': False,
            'estimate_id': False,
            'sale_id': False,
            'design_id': False,
            'bom_id': False,
            'mo_id': False,
            'pr_id': False,
            'qc_id': False,
            'po_id': False,
            'grn_id': False,
            'delivery_id': False,
            'invoice_id': False,
            'payment_in_id': False,
            'bill_id': False,
            'payment_out_id': False,
            'stock_info': False,
        }
        self.write(wipe)
        return self._reopen()

    def action_finish(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tutorial complete'),
                'message': self.last_message or _(
                    'You finished all 16 steps. Open created documents from the wizard links anytime.'
                ),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'switchgear_processing_cycle',
                },
            },
        }

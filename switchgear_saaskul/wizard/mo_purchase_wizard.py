# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SwitchgearMoPurchaseWizard(models.TransientModel):
    _name = 'switchgear.mo.purchase.wizard'
    _description = 'Create Purchase Order from Manufacturing Order'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    line_ids = fields.One2many('switchgear.mo.purchase.wizard.line', 'wizard_id', string='Components')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        production = self.env['mrp.production'].browse(self.env.context.get('active_id'))
        if not production:
            return res
        res['production_id'] = production.id
        already_ordered = self.env['purchase.order'].search([
            ('mo_id', '=', production.id), ('state', '!=', 'cancel'),
        ]).order_line.product_id
        lines = []
        for move in production.move_raw_ids.filtered(lambda m: m.product_id not in already_ordered):
            product = move.product_id
            lines.append((0, 0, {
                'product_id': product.id,
                'name': product.description_purchase or product.display_name,
                'product_qty': move.product_uom_qty,
                'product_uom': move.product_uom.id,
                'price_unit': product.standard_price,
            }))
        res['line_ids'] = lines
        return res

    def action_create_purchase_order(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Every component of this manufacturing order is already on a purchase order.'))
        production = self.production_id
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'origin': production.name,
            'mo_id': production.id,
            'project_id': production.project_id.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_qty,
                'product_uom': (line.product_uom or line.product_id.uom_po_id).id,
                'price_unit': line.price_unit,
                'date_planned': fields.Datetime.now(),
            }) for line in self.line_ids],
        })
        production.message_post(body=_('Purchase order %s created for the components of this order.') % order.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SwitchgearMoPurchaseWizardLine(models.TransientModel):
    _name = 'switchgear.mo.purchase.wizard.line'
    _description = 'Create Purchase Order Wizard Line'

    wizard_id = fields.Many2one('switchgear.mo.purchase.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    name = fields.Char(string='Description', required=True)
    product_qty = fields.Float(string='Quantity', required=True, digits='Product Unit of Measure')
    product_uom = fields.Many2one('uom.uom', string='UoM')
    price_unit = fields.Float(string='Unit Price', required=True, digits='Product Price')
    product_subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')
    qty_on_hand = fields.Float(string='On Hand', related='product_id.qty_available')

    @api.depends('product_qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.product_subtotal = line.product_qty * line.price_unit

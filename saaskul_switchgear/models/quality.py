# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class QualityCheck(models.Model):
    _inherit = 'quality.check'

    project_id = fields.Many2one('project.project', string='Project')
    delivery_picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        compute='_compute_delivery_picking',
    )
    can_deliver = fields.Boolean(
        compute='_compute_delivery_picking',
    )
    delivery_done = fields.Boolean(
        compute='_compute_delivery_picking',
    )

    @api.depends(
        'quality_state', 'production_id', 'picking_id',
        'production_id.bom_id.sale_order_id',
        'production_id.origin',
    )
    def _compute_delivery_picking(self):
        Picking = self.env['stock.picking']
        for check in self:
            picking = check._find_delivery_picking()
            check.delivery_picking_id = picking
            check.delivery_done = bool(picking and picking.state == 'done')
            check.can_deliver = bool(
                check.quality_state == 'pass'
                and picking
                and picking.state not in ('done', 'cancel')
            )

    def _find_delivery_picking(self):
        self.ensure_one()
        if self.picking_id and self.picking_id.picking_type_code == 'outgoing':
            return self.picking_id

        sale_order = self._get_related_sale_order()
        if sale_order:
            picking = sale_order.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing'
                and p.state not in ('done', 'cancel')
            )[:1]
            if picking:
                return picking

        production = self.production_id
        if production:
            Picking = self.env['stock.picking']
            picking = Picking.search([
                ('origin', '=', production.name),
                ('picking_type_code', '=', 'outgoing'),
                ('state', 'not in', ('done', 'cancel')),
                ('company_id', '=', production.company_id.id),
            ], limit=1)
            if picking:
                return picking
            if hasattr(production, 'picking_ids'):
                outgoing = production.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'outgoing'
                    and p.state not in ('done', 'cancel')
                )
                if outgoing:
                    return outgoing[:1]
        return self.env['stock.picking']

    def _get_related_sale_order(self):
        self.ensure_one()
        production = self.production_id
        if production and production.bom_id and production.bom_id.sale_order_id:
            return production.bom_id.sale_order_id

        if 'job_order_id' in self._fields and self.job_order_id:
            jo = self.job_order_id
            if 'quotation_no' in jo._fields and jo.quotation_no:
                return jo.quotation_no

        if production and production.origin:
            sale_order = self.env['sale.order'].search([
                ('name', '=', production.origin),
                ('company_id', '=', production.company_id.id),
            ], limit=1)
            if sale_order:
                return sale_order

        if production and production.procurement_group_id:
            sale_lines = production.procurement_group_id.stock_move_ids.mapped(
                'sale_line_id'
            )
            if sale_lines:
                return sale_lines.order_id[:1]

        return self.env['sale.order']

    def _prepare_mo_for_delivery(self, production):
        """Try to finish MO so finished goods are available for delivery."""
        if not production or production.state == 'done':
            return
        if production.state not in ('confirmed', 'progress'):
            return
        try:
            if production.move_raw_ids and all(
                m.state in ('done', 'cancel') for m in production.move_raw_ids
            ):
                production.button_mark_done()
                return
            if 'qty_producing' in production._fields:
                production.qty_producing = production.product_uom_qty
            production.button_mark_done()
        except Exception:
            pass

    def _validate_delivery_picking(self, picking):
        for move in picking.move_lines:
            if not move.quantity_done:
                move.quantity_done = move.product_uom_qty or move.reserved_availability
        try:
            picking.button_validate()
        except Exception:
            picking.action_done()

    def action_deliver_product(self):
        """Validate customer delivery after quality check passed."""
        self.ensure_one()
        if self.quality_state != 'pass':
            raise UserError(_('Quality check must be passed before delivery.'))

        picking = self._find_delivery_picking()
        if not picking:
            raise UserError(_(
                'No open delivery order found for this manufacturing order.\n'
                'Confirm the sales quotation first so a delivery is created.'
            ))

        if picking.state == 'done':
            return self.action_open_delivery()

        if self.production_id:
            self._prepare_mo_for_delivery(self.production_id)

        self._validate_delivery_picking(picking)
        return self.action_open_delivery()

    def action_open_delivery(self):
        self.ensure_one()
        picking = self.delivery_picking_id or self._find_delivery_picking()
        if not picking:
            raise UserError(_('No delivery order linked to this quality check.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Order'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

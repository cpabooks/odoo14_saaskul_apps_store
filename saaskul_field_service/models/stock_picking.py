from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    issue_crn_number = fields.Char(
        string='CRN Number',
        related='issue_project_task_id.task_seq',
        readonly=True,
        store=True,
    )
    issue_customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='issue_project_task_id.partner_id',
        readonly=True,
        store=True,
    )
    issue_source_document = fields.Char(
        string='Source Document',
        compute='_compute_issue_source_document',
        readonly=True,
        store=True,
    )
    is_material_return = fields.Boolean(
        string='Material Return',
        compute='_compute_is_material_return',
        store=True,
    )
    use_fsm_issue_operations_ui = fields.Boolean(
        string='FSM Issue Operations UI',
        compute='_compute_use_fsm_issue_operations_ui',
        help='Issue notes linked to a CRN always show Operations and Detailed Operations.',
    )

    @api.depends('issue_project_task_id')
    def _compute_use_fsm_issue_operations_ui(self):
        for picking in self:
            picking.use_fsm_issue_operations_ui = bool(picking.issue_project_task_id)

    @api.depends('move_lines.origin_returned_move_id')
    def _compute_is_material_return(self):
        for picking in self:
            picking.is_material_return = any(picking.move_lines.mapped('origin_returned_move_id'))

    @api.model
    def action_recompute_material_return_flags(self):
        pickings = self.sudo().search([('move_lines.origin_returned_move_id', '!=', False)])
        pickings._compute_is_material_return()
        return True

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        if 'picking_type_id' in fields_list and not result.get('picking_type_id'):
            default_type = self.env['ir.default'].sudo().get('stock.picking', 'picking_type_id')
            if default_type:
                result['picking_type_id'] = default_type
        return result

    @api.depends('issue_project_task_id', 'issue_project_task_id.qt_no', 'issue_project_task_id.qt_no_text')
    def _compute_issue_source_document(self):
        sale_order_model = self.env['sale.order'] if self.env.registry.get('sale.order') else False
        for picking in self:
            source = False
            task = picking.issue_project_task_id
            if task:
                if task.qt_no:
                    source = task.qt_no.name
                elif (task.qt_no_text or '').strip():
                    source = (task.qt_no_text or '').strip()
                elif sale_order_model is not False:
                    order = sale_order_model.search([('task_id', '=', task.id)], limit=1, order='id desc')
                    source = order.name if order else False
            picking.issue_source_document = source

    @api.onchange('issue_project_task_id')
    def _onchange_issue_project_task_id_populate_crn_details(self):
        result = super()._onchange_issue_project_task_id()
        for picking in self:
            task = picking.issue_project_task_id
            if not task:
                continue
            picking.partner_id = task.partner_id or task.project_id.partner_id
            if task.qt_no:
                picking.origin = task.qt_no.name
            elif (task.qt_no_text or '').strip():
                picking.origin = (task.qt_no_text or '').strip()
            elif picking.issue_source_document:
                picking.origin = picking.issue_source_document
            elif task.task_seq:
                picking.origin = task.task_seq
            picking._fill_move_locations_from_picking()
        return result

    @api.onchange('picking_type_id', 'location_id', 'location_dest_id')
    def _onchange_locations_propagate_to_moves(self):
        for picking in self:
            picking._fill_move_locations_from_picking()

    def _fill_move_locations_from_picking(self):
        self.ensure_one()
        source_location = self.location_id
        dest_location = self.location_dest_id
        if not source_location and self.picking_type_id:
            source_location = self.picking_type_id.default_location_src_id
        if not dest_location and self.picking_type_id:
            dest_location = self.picking_type_id.default_location_dest_id
        if not source_location and not dest_location:
            return
        for move in self.move_ids_without_package:
            if source_location and not move.location_id:
                move.location_id = source_location
            if dest_location and not move.location_dest_id:
                move.location_dest_id = dest_location

    @api.onchange('picking_type_id')
    def _onchange_remember_issue_picking_type_id(self):
        if self.picking_type_id:
            self.env['ir.default'].sudo().set(
                'stock.picking',
                'picking_type_id',
                self.picking_type_id.id,
            )

    def _sync_issue_material_request_lines(self):
        material_line_model = self.env['material.request.line'].sudo()
        task_ids = set()
        for picking in self.filtered(lambda rec: rec.state == 'done' and rec.issue_project_task_id):
            task_ids.add(picking.issue_project_task_id.id)

        for task in self.env['project.task'].sudo().browse(list(task_ids)):
            done_pickings = self.env['stock.picking'].sudo().search([
                ('issue_project_task_id', '=', task.id),
                ('state', '=', 'done'),
            ], order='id')
            done_moves = done_pickings.move_ids_without_package.filtered(
                lambda rec: rec.state != 'cancel' and rec.product_id and rec.quantity_done > 0
            )
            if not done_moves:
                continue

            existing_lines = material_line_model.search([('task_id', '=', task.id)])
            line_by_move = {
                line.issue_move_id.id: line
                for line in existing_lines
                if 'issue_move_id' in line._fields and line.issue_move_id
            }
            unlinked_lines_by_product = {}
            for line in existing_lines:
                if 'issue_move_id' in line._fields and line.issue_move_id:
                    continue
                unlinked_lines_by_product.setdefault(line.product_id.id, self.env['material.request.line'])
                unlinked_lines_by_product[line.product_id.id] |= line

            for move in done_moves.sorted(key=lambda rec: (rec.picking_id.id, rec.id)):
                line = line_by_move.get(move.id)
                sync_vals = {
                    'description': move.name or move.product_id.display_name,
                    'quantity': move.quantity_done,
                    'issue_move_id': move.id,
                }
                if 'test_quantity_issued' in material_line_model._fields:
                    sync_vals['test_quantity_issued'] = move.quantity_done
                if line:
                    line.write(sync_vals)
                else:
                    candidate = self.env['material.request.line']
                    product_lines = unlinked_lines_by_product.get(move.product_id.id)
                    if product_lines:
                        candidate = product_lines[0]
                        unlinked_lines_by_product[move.product_id.id] -= candidate
                    if candidate:
                        candidate.write(sync_vals)
                        line_by_move[move.id] = candidate
                    else:
                        created_line = material_line_model.create(dict(
                            sync_vals,
                            task_id=task.id,
                            product_id=move.product_id.id,
                        ))
                        line_by_move[move.id] = created_line

    def _cpabooks_delivery_partner_from_sale(self):
        """Resolve delivery address from linked sale order or procurement group."""
        self.ensure_one()
        if self.partner_id or self.issue_project_task_id:
            return self.env['res.partner']
        order = self.env['sale.order']
        if 'sale_id' in self._fields and self.sale_id:
            order = self.sale_id
        elif self.origin:
            order = order.search([('name', '=', self.origin)], limit=1)
        partner = self.env['res.partner']
        if order:
            partner = order.partner_shipping_id or order.partner_id
        elif self.group_id.partner_id:
            partner = self.group_id.partner_id
        return partner

    def _cpabooks_sync_delivery_partner_from_sale(self):
        for picking in self:
            partner = picking._cpabooks_delivery_partner_from_sale()
            if partner:
                picking.partner_id = partner

    @api.model
    def _cpabooks_fix_missing_delivery_partners(self):
        pickings = self.sudo().search([
            ('partner_id', '=', False),
            ('issue_project_task_id', '=', False),
            ('picking_type_id.code', '=', 'outgoing'),
            ('state', '!=', 'cancel'),
        ])
        pickings._cpabooks_sync_delivery_partner_from_sale()
        return True

    def action_reset_to_draft_for_delivery(self):
        """Reset outgoing delivery to draft so the delivery address can be set."""
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                raise UserError(_('Reset to draft is only available on delivery orders.'))
            if picking.state == 'done':
                raise UserError(_(
                    'Completed deliveries cannot be reset to draft. '
                    'Use Return or create a new delivery order.'
                ))
            if picking.state == 'cancel':
                picking.move_lines.write({'state': 'draft'})
            else:
                picking.move_lines.filtered(
                    lambda move: move.state not in ('cancel', 'draft')
                )._do_unreserve()
                picking.move_lines.filtered(
                    lambda move: move.state not in ('cancel',)
                ).write({'state': 'draft'})
            picking.write({'state': 'draft', 'is_locked': False})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        for picking in pickings.filtered('picking_type_id'):
            self.env['ir.default'].sudo().set('stock.picking', 'picking_type_id', picking.picking_type_id.id)
        pickings._cpabooks_sync_delivery_partner_from_sale()
        return pickings

    def write(self, vals):
        result = super().write(vals)
        if vals.get('picking_type_id'):
            self.env['ir.default'].sudo().set('stock.picking', 'picking_type_id', vals['picking_type_id'])
        if 'partner_id' not in vals:
            self.filtered(
                lambda picking: not picking.partner_id and not picking.issue_project_task_id
            )._cpabooks_sync_delivery_partner_from_sale()
        return result

    def _set_issue_note_done_quantities(self):
        for picking in self.filtered(lambda rec: rec.issue_project_task_id and rec.state not in ('done', 'cancel')):
            for move in picking.move_ids_without_package.filtered(
                    lambda rec: rec.state not in ('done', 'cancel') and rec.product_id):
                rounding = move.product_uom.rounding
                if not float_is_zero(move.quantity_done, precision_rounding=rounding):
                    continue

                reserved_lines = move.move_line_ids.filtered(
                    lambda line: (
                        line.state not in ('done', 'cancel')
                        and not float_is_zero(line.product_uom_qty, precision_rounding=line.product_uom_id.rounding)
                    )
                )
                if reserved_lines:
                    for line in reserved_lines:
                        if float_is_zero(line.qty_done, precision_rounding=line.product_uom_id.rounding):
                            line.qty_done = line.product_uom_qty
                    continue

                move._set_quantity_done(move.product_uom_qty)

    def action_set_quantities_to_reservation(self):
        self._set_issue_note_done_quantities()
        for move in self.filtered(lambda rec: not rec.issue_project_task_id).move_ids_without_package.filtered(
                lambda rec: rec.state not in ('done', 'cancel') and rec.product_id):
            if float_is_zero(move.quantity_done, precision_rounding=move.product_uom.rounding):
                move._set_quantity_done(move.reserved_availability or move.product_uom_qty)
        return True

    def action_confirm(self):
        result = super().action_confirm()
        self._set_issue_note_done_quantities()
        return result

    def action_assign(self):
        result = super().action_assign()
        self._set_issue_note_done_quantities()
        return result

    def button_validate(self):
        self._set_issue_note_done_quantities()
        return super().button_validate()

    def _action_done(self):
        result = super()._action_done()
        self._sync_issue_material_request_lines()
        return result


# Load extensions with this module (no separate __init__ change required).
from . import stock_move  # noqa: E402,F401

# -*- coding: utf-8 -*-
"""Material Issue Note (MIN) and Material Return Note (MRN) on stock.picking."""
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    issue_project_task_id = fields.Many2one(
        'project.task',
        string="CRN Number",
        domain=[('material_line_ids', '!=', False), ('issue_note_done', '=', False)],
    )
    issue_project_id = fields.Many2one(
        related='issue_project_task_id.project_id',
        string="Project",
        store=True,
    )
    is_stock_issue_note = fields.Boolean(
        string='Material Issue Note',
        default=False,
        copy=False,
        help='Material Issue Note (MIN): materials issued from store.',
    )
    is_stock_return_note = fields.Boolean(
        string='Material Return Note',
        default=False,
        copy=False,
        help='Material Return Note (MRN): return against a Material Issue Note.',
    )
    stock_issue_picking_id = fields.Many2one(
        'stock.picking',
        string='Material Issue Note',
        domain=(
            "[('state', '=', 'done'), '|', "
            "('is_stock_issue_note', '=', True), "
            "('issue_project_task_id', '!=', False)]"
        ),
        copy=False,
        help='Search / select the Material Issue Note (MIN) to return quantities against.',
    )
    material_line_ids = fields.One2many(
        'material.request.line',
        'task_id',
        compute='_compute_material_line_ids',
        string='Material Lines',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('default_is_stock_issue_note'):
            res['is_stock_issue_note'] = True
        if ctx.get('default_is_stock_return_note'):
            res['is_stock_return_note'] = True
            res['is_stock_issue_note'] = False
        return res

    def _action_done(self):
        res = super()._action_done()
        tasks = self.filtered(lambda picking: picking.issue_project_task_id).mapped('issue_project_task_id')
        tasks._update_issue_note_done()
        return res

    def _compute_material_line_ids(self):
        for rec in self:
            if rec.issue_project_task_id:
                rec.material_line_ids = rec.issue_project_task_id.material_line_ids
            else:
                rec.material_line_ids = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('issue_project_task_id') and not vals.get('is_stock_return_note'):
                vals['is_stock_issue_note'] = True
            if vals.get('stock_issue_picking_id') or vals.get('is_stock_return_note'):
                vals['is_stock_return_note'] = True
                vals['is_stock_issue_note'] = False
        return super().create(vals_list)

    @api.onchange('issue_project_task_id')
    def _onchange_issue_project_task_id(self):
        for rec in self:
            if not rec.issue_project_task_id:
                continue
            rec.is_stock_issue_note = True
            rec.is_stock_return_note = False
            task = rec.issue_project_task_id
            rec.partner_id = task.partner_id or task.project_id.partner_id
            rec.move_ids_without_package = [(5, 0, 0)]
            move_lines = []
            for material_line in task.material_line_ids:
                pending_qty = material_line.quantity - material_line.quantity_done
                if pending_qty <= 0:
                    continue
                vals = {
                    'name': material_line.description or material_line.product_id.name,
                    'product_id': material_line.product_id.id,
                    'product_uom_qty': pending_qty,
                    'product_uom': material_line.product_id.uom_id.id,
                }
                if rec.location_id:
                    vals['location_id'] = rec.location_id.id
                if rec.location_dest_id:
                    vals['location_dest_id'] = rec.location_dest_id.id
                move_lines.append((0, 0, vals))
            rec.move_ids_without_package = move_lines

    @api.onchange('stock_issue_picking_id')
    def _onchange_stock_issue_picking_id(self):
        """Load returnable qty from the selected Material Issue Note (MIN)."""
        for rec in self:
            issue = rec.stock_issue_picking_id
            if not issue:
                continue
            rec.is_stock_return_note = True
            rec.is_stock_issue_note = False
            rec.partner_id = issue.partner_id
            rec.issue_project_task_id = issue.issue_project_task_id
            rec.origin = issue.name
            if issue.location_id and issue.location_dest_id:
                rec.location_id = issue.location_dest_id
                rec.location_dest_id = issue.location_id
            prior_returns = self.env['stock.picking'].search([
                ('stock_issue_picking_id', '=', issue.id),
                ('is_stock_return_note', '=', True),
                ('state', '=', 'done'),
                ('id', '!=', rec._origin.id if rec._origin else 0),
            ])
            returned_by_product = {}
            for ret in prior_returns:
                for move in ret.move_ids_without_package.filtered(lambda m: m.state == 'done'):
                    pid = move.product_id.id
                    returned_by_product[pid] = returned_by_product.get(pid, 0.0) + (
                        move.quantity_done or move.product_uom_qty or 0.0
                    )
            rec.move_ids_without_package = [(5, 0, 0)]
            moves = []
            for move in issue.move_ids_without_package.filtered(lambda m: m.state == 'done'):
                qty = (move.quantity_done or move.product_uom_qty or 0.0) - returned_by_product.get(
                    move.product_id.id, 0.0
                )
                if qty <= 0:
                    continue
                moves.append((0, 0, {
                    'name': move.name or move.product_id.display_name,
                    'product_id': move.product_id.id,
                    'product_uom_qty': qty,
                    'product_uom': move.product_uom.id,
                    'location_id': rec.location_id.id,
                    'location_dest_id': rec.location_dest_id.id,
                }))
            rec.move_ids_without_package = moves


class StockMove(models.Model):
    _inherit = 'stock.move'

    rate = fields.Float(related="product_id.standard_price", readonly=False, string="Rate")
    amount = fields.Float(compute="_compute_amount", string="Amount")

    @api.depends('rate', 'quantity_done')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.rate * rec.quantity_done

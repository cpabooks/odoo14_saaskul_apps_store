# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    name = fields.Char(string='Number', required=True, copy=False, index=True, default=lambda self: _('New'))
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    mo_count = fields.Integer('# Manufacturing Order', compute='_compute_mo_count')
    estimate_id = fields.Many2one('job.estimate', string='Job Estimation')
    project_id = fields.Many2one('project.project', string='Job Order')
    partner_id = fields.Many2one('res.partner', string='Customer')
    estimate_reference = fields.Char(string='Estimation Reference', related='estimate_id.name')
    create_product_variant_id = fields.Many2one('product.template', string="Create Product Variants")

    def _compute_mo_count(self):
        for bom in self:
            bom.mo_count = self.env['mrp.production'].search_count([('bom_id', '=', bom.id)])

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('mrp.bom') or _('New')
            vals['create_product_variant_id'] = None
        return super(MrpBom, self).create(vals)

    def write(self, vals):
        if 'create_product_variant_id' in vals.keys():
            vals.pop('create_product_variant_id', None)
        return super(MrpBom, self).write(vals)

    def action_create_mo(self):
        for rec in self:
            product = rec._cpabooks_resolve_mo_product() if hasattr(
                rec, '_cpabooks_resolve_mo_product',
            ) else self.env['product.product'].sudo().search([
                ('product_tmpl_id', '=', rec.product_tmpl_id.id),
            ], limit=1)
            if not product:
                raise UserError(_('Cannot create manufacturing order: BOM has no product.'))
            mo_id = self.env['mrp.production'].create({
                'product_id': product.id,
                'product_qty': rec.product_qty or 1.0,
                'product_uom_id': product.uom_id.id,
                'bom_id': rec.id,
                'project_id': rec.project_id.id,
                'partner_id': rec.partner_id.id,
                'company_id': rec.company_id.id,
            })
            mo_id.onchange_product_id()
            mo_id._onchange_bom_id()
            mo_id._onchange_move_raw()
            mo_id._compute_allowed_product_ids()
            mo_id._onchange_move_finished()
            mo_id._onchange_location()
            mo_id._onchange_location_dest()
            mo_id._onchange_workorder_ids()

    def explode(self, product, quantity, picking_type=False):
        """
            Explodes the BoM and creates two lists with all the information you need: bom_done and line_done
            Quantity describes the number of times you need the BoM: so the quantity divided by the number created by the BoM
            and converted into its UoM
        """
        from collections import defaultdict

        graph = defaultdict(list)
        V = set()

        def check_cycle(v, visited, recStack, graph):
            visited[v] = True
            recStack[v] = True
            for neighbour in graph[v]:
                if visited[neighbour] == False:
                    if check_cycle(neighbour, visited, recStack, graph) == True:
                        return True
                elif recStack[neighbour] == True:
                    return True
            recStack[v] = False
            return False

        boms_done = [(self, {'qty': quantity, 'product': product, 'original_qty': quantity, 'parent_line': False,'product_qty': quantity})]
        lines_done = []
        V |= set([product.product_tmpl_id.id])

        bom_lines = [(bom_line, product, quantity, False) for bom_line in self.bom_line_ids]
        for bom_line in self.bom_line_ids:
            V |= set([bom_line.product_id.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(bom_line.product_id.product_tmpl_id.id)
        while bom_lines:
            current_line, current_product, current_qty, parent_line = bom_lines[0]
            bom_lines = bom_lines[1:]

            if current_line._skip_bom_line(current_product):
                continue

            line_quantity = current_qty * current_line.product_qty
            bom = self._bom_find(product=current_line.product_id, picking_type=picking_type or self.picking_type_id, company_id=self.company_id.id, bom_type='phantom')
            if bom:
                converted_line_quantity = current_line.product_uom_id._compute_quantity(line_quantity / bom.product_qty, bom.product_uom_id)
                bom_lines = [(line, current_line.product_id, converted_line_quantity, current_line) for line in bom.bom_line_ids] + bom_lines
                for bom_line in bom.bom_line_ids:
                    graph[current_line.product_id.product_tmpl_id.id].append(bom_line.product_id.product_tmpl_id.id)
                    if bom_line.product_id.product_tmpl_id.id in V and check_cycle(bom_line.product_id.product_tmpl_id.id, {key: False for  key in V}, {key: False for  key in V}, graph):
                        raise UserError(_('Recursion error!  A product with a Bill of Material should not have itself in its BoM or child BoMs!'))
                    V |= set([bom_line.product_id.product_tmpl_id.id])
                boms_done.append((bom, {'qty': converted_line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': current_line}))
            else:
                # We round up here because the user expects that if he has to consume a little more, the whole UOM unit
                # should be consumed.
                rounding = current_line.product_uom_id.rounding
                line_quantity = float_round(line_quantity, precision_rounding=rounding, rounding_method='UP')
                lines_done.append((current_line, {'qty': line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': parent_line}))

        return boms_done, lines_done

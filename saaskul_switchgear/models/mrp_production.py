# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    project_id = fields.Many2one('project.project', string='Job Order')
    partner_id = fields.Many2one('res.partner', string='Customer')
    bom_reference = fields.Char(string='BOM Reference', related='bom_id.name')
    po_count = fields.Integer(compute='_compute_pr')
    qc_count = fields.Integer(
        string='# Quality Checks',
        compute='_compute_qc_count',
    )

    @api.model
    def _cpabooks_ensure_mo_picking_sequences(self, company_id=False):
        """Link mrp_operation picking types to a working MO sequence.

        Community / lean DBs often have Manufacturing picking type with empty
        sequence_id → core create() runs next_by_id() on empty → id=false SQL error.
        """
        Sequence = self.env['ir.sequence'].sudo()
        PType = self.env['stock.picking.type'].sudo()
        domain = [('code', '=', 'mrp_operation'), ('sequence_id', '=', False)]
        if company_id:
            domain = [
                ('code', '=', 'mrp_operation'),
                ('sequence_id', '=', False),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', company_id),
            ]
        picking_types = PType.search(domain)
        if not picking_types and company_id:
            picking_types = PType.search([
                ('code', '=', 'mrp_operation'),
                ('sequence_id', '=', False),
            ])
        if not picking_types:
            return Sequence

        seq = Sequence.search([('code', '=', 'mrp.production')], limit=1)
        if not seq:
            seq = Sequence.search([
                ('name', 'ilike', 'Manufacturing Order'),
                ('code', '=', False),
            ], limit=1)
            if seq and not seq.code:
                seq.code = 'mrp.production'
        if not seq:
            seq = Sequence.create({
                'name': 'Manufacturing Orders',
                'code': 'mrp.production',
                'prefix': 'WH/MO/',
                'padding': 5,
                'company_id': False,
            })
        picking_types.write({'sequence_id': seq.id})
        return seq

    @api.model
    def create(self, values):
        values = dict(values)
        if not values.get('name', False) or values['name'] == _('New'):
            company_id = values.get('company_id') or self.env.company.id
            self._cpabooks_ensure_mo_picking_sequences(company_id=company_id)
            picking_type_id = values.get('picking_type_id') or self._get_default_picking_type()
            picking_type = self.env['stock.picking.type'].browse(picking_type_id) if picking_type_id else self.env['stock.picking.type']
            name = False
            if picking_type and picking_type.sequence_id:
                try:
                    name = picking_type.sequence_id.next_by_id()
                except Exception:
                    name = False
            if not name:
                name = self.env['ir.sequence'].sudo().next_by_code('mrp.production')
            if not name:
                name = 'MO/%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
            values['name'] = name
        return super(MrpProduction, self).create(values)

    def _compute_pr(self):
        for production in self:
            production.po_count = self.env['purchase.order'].search_count([
                ('mo_id', '=', production.id),
            ]) if production.id else 0

    def _compute_qc_count(self):
        for production in self:
            if 'quality.check' in self.env:
                production.qc_count = self.env['quality.check'].search_count([
                    ('production_id', '=', production.id),
                ])
            else:
                production.qc_count = 0

    def action_view_relavent_po(self):
        self.ensure_one()
        return {
            'name': _('Requests for Quotation'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('mo_id', '=', self.id)],
        }

    def action_view_quality_checks(self):
        self.ensure_one()
        if 'quality.check' not in self.env:
            return True
        action = self.env.ref(
            'cpabooks_quality_community.quality_check_action_mo',
            raise_if_not_found=False,
        )
        if action:
            result = action.read()[0]
            result['domain'] = [('production_id', '=', self.id)]
            result['context'] = dict(
                self.env.context,
                default_production_id=self.id,
                search_default_production_id=self.id,
            )
            return result
        return {
            'name': _('Quality Checks'),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check',
            'view_mode': 'tree,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id},
        }

    def action_create_qc(self):
        if 'quality.check' not in self.env:
            return True
        test_type = self.env.ref(
            'cpabooks_quality_community.test_type_passfail', raise_if_not_found=False,
        )
        if not test_type:
            return True
        team = self.env['quality.alert.team'].search([], limit=1)
        if not team:
            return True
        for rec in self:
            self.env['quality.check'].create({
                'product_id': rec.product_id.id,
                'production_id': rec.id,
                'company_id': rec.company_id.id,
                'team_id': team.id if team else False,
                'test_type_id': test_type.id,
            })
        return True

    def action_create_pr(self):
        print("**")

    # def _get_move_raw_values(self, product_id, product_uom_qty, product_uom, operation_id=False, bom_line=False):
    #     data=super(MrpProduction, self)._get_move_raw_values( product_id, product_uom_qty, product_uom, operation_id=False, bom_line=False)
    #     data['product_qty']=product_uom_qty
    #     return data

    def write(self,val_list):
        if 'product_qty' in val_list:
            val_list['product_qty']=self.product_qty
        return super(MrpProduction, self).write(val_list)

    # def action_confirm(self):
    #     super(MrpProduction, self).action_confirm()
    #
    #     for rec in self.move_raw_ids:
    #         if not rec.production_id:
    #             rec.production_id=self.id
    #             rec.raw_material_production_id=self.id



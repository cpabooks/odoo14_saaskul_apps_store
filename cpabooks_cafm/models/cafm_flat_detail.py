# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CafmFlatDetail(models.Model):
    _name = 'cpabooks.cafm.flat.detail'
    _description = 'CAFM Flat / Villa Detail'
    _order = 'contract_id, sequence, id'

    contract_id = fields.Many2one('cpabooks.cafm.contract', string='Contract', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sr. No.', default=1)
    contract_type = fields.Selection([
        ('villa', 'Villa'),
        ('flat', 'Flat'),
    ], string='Contract Type', default='villa', required=True)
    flat_code = fields.Char(string='Flat Code', copy=False)
    flat_name = fields.Char(string='Flat / Villa Name')
    tenant_unit_id = fields.Many2one(
        'cpabooks.cafm.unit',
        string='Tenant Name',
        help='Select or create a Villa / Flat unit (same form as Villa / Flat master).',
    )
    contact_mobile = fields.Char(string='Cont. Mobile')

    @api.onchange('tenant_unit_id')
    def _onchange_tenant_unit_id(self):
        unit = self.tenant_unit_id
        if not unit:
            return
        if unit.unit_type in ('flat', 'villa'):
            self.contract_type = unit.unit_type
        if unit.code:
            self.flat_code = unit.code
        if unit.name:
            self.flat_name = unit.name
        partner = unit.tenant_partner_id
        if partner:
            self.contact_mobile = partner.mobile or partner.phone or self.contact_mobile

    @api.model
    def create(self, vals):
        vals = self._prepare_auto_values(vals)
        return super().create(vals)

    def write(self, vals):
        if vals.get('contract_type'):
            for rec in self:
                new_vals = dict(vals)
                new_vals = rec._prepare_auto_values(new_vals, existing=rec, force=True)
                super(CafmFlatDetail, rec).write(new_vals)
            return True
        return super().write(vals)

    def action_generate_flat_details(self):
        for rec in self:
            rec.write(rec._prepare_auto_values({}, existing=rec, force=True))

    def _prepare_auto_values(self, vals, existing=False, force=False):
        contract_id = vals.get('contract_id') or (existing.contract_id.id if existing else False)
        contract_type = vals.get('contract_type') or (existing.contract_type if existing else False)
        if not contract_type and contract_id:
            contract_type = self.env['cpabooks.cafm.contract'].browse(contract_id).unit_contract_type
            vals['contract_type'] = contract_type
        contract_type = contract_type or 'villa'
        if not vals.get('sequence') and not existing:
            vals['sequence'] = self._next_sequence(contract_id)
        if (not vals.get('flat_code') and not existing) or force:
            vals['flat_code'] = self._next_flat_code(contract_id, contract_type, existing=existing, sequence=vals.get('sequence'))
        flat_code = vals.get('flat_code') or (existing.flat_code if existing else False)
        if flat_code and ((not vals.get('flat_name') and not existing) or force):
            vals['flat_name'] = flat_code
        return vals

    def _next_sequence(self, contract_id):
        if not contract_id:
            return 1
        last_line = self.search([('contract_id', '=', contract_id)], order='sequence desc, id desc', limit=1)
        return (last_line.sequence or 0) + 1

    def _next_flat_code(self, contract_id, contract_type, existing=False, sequence=False):
        prefix_map = {
            'flat': 'Flat',
            'villa': 'Villa',
        }
        prefix = prefix_map.get(contract_type, 'Villa')
        domain = [
            ('contract_id', '=', contract_id),
            ('contract_type', '=', contract_type),
        ]
        if existing:
            domain.append(('id', '!=', existing.id))
        number = 1000 + (sequence or len(self.search(domain)) + 1)
        return '%s-%s' % (prefix, number)

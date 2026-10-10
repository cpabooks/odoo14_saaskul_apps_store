# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class JobEstimate(models.Model):
    _inherit = 'job.estimate'

    # enquiry_number = fields.Char(string='Enquiry Number')
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity', domain="[('type', '=', 'opportunity')]")
    # bom_id=fields.Many2one('mrp.bom',string='Bill of Material')
    bom_id=fields.Many2one('mrp.bom',string='BoM Item Template')
    bom_reference = fields.Char(string='BOM Reference', related='bom_id.name')
    # bom_product_id = fields.Many2one('product.product', string='BOM Product')
    bom_product_id = fields.Many2one('product.product', string='BoM Item Name')
    bom_count = fields.Integer('# Bill of Material', compute='_compute_bom_count')
    crm_reference = fields.Char(string='CRM Reference', related='opportunity_id.enquiry_number')

    @api.onchange('bom_id')
    def get_bom_product(self):
        for rec in self:
            rec.material_estimation_ids=[(5,0,0)]
            test=self.env['product.product'].sudo().search([('product_tmpl_id','=',rec.bom_id.product_tmpl_id.id)]).id
            rec.bom_product_id=self.env['product.product'].sudo().search([('product_tmpl_id','=',rec.bom_id.product_tmpl_id.id)]).id
            estimation_lines=[]
            if rec.bom_id.bom_line_ids:
                for line in rec.bom_id.bom_line_ids:
                    # rec.material_estimation_ids
                    vals=(0,0,{
                        'product_id':line.product_id.id,
                        'type':'material',
                        'quantity':line.product_qty,
                        'uom_id':line.product_uom_id.id,
                        'price_unit':line.product_id.lst_price,
                        'subtotal':line.product_qty*line.product_id.lst_price


                    })
                    estimation_lines.append(vals)
            rec.material_estimation_ids=estimation_lines


    def _compute_bom_count(self):
        for job in self:
            job.bom_count = self.env['mrp.bom'].search_count([('estimate_id', '=', job.id)])

    def action_create_bom(self):
        if not self.bom_product_id:
            raise ValidationError(_('Please select BOM Product to create BOM'))
        if self.bom_product_id:
            bom_id = self.env['mrp.bom'].create({
                'product_id': self.bom_product_id.id,
                'product_tmpl_id': self.bom_product_id.product_tmpl_id.id,
                'product_qty': 1.0,
                'type': 'normal',
                'estimate_id': self.id,
                'project_id': self.project_id.id,
                'partner_id': self.partner_id.id,
            })
            if bom_id:
                for line in self.material_estimation_ids:
                    self.env['mrp.bom.line'].create({
                        'product_id': line.product_id.id,
                        'product_qty': line.quantity,
                        'bom_id': bom_id.id,
                        'product_uom_id': line.uom_id.id,
                    })
                for line in self.labour_estimation_ids:
                    self.env['mrp.bom.line'].create({
                        'product_id': line.product_id.id,
                        'product_qty': line.hours,
                        'bom_id': bom_id.id,
                        'product_uom_id': line.uom_id.id,
                    })
                for line in self.overhead_estimation_ids:
                    self.env['mrp.bom.line'].create({
                        'product_id': line.product_id.id,
                        'product_qty': line.quantity,
                        'bom_id': bom_id.id,
                        'product_uom_id': line.uom_id.id,
                    })

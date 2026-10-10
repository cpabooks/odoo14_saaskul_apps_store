# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class RecipeBook(models.Model):
    _name = 'saaskul.recipe'
    _description = 'Recipe Book'
    _inherit = ['mail.thread'] if False else []
    _order = 'name'

    name = fields.Char(required=True, tracking=False)
    code = fields.Char()
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    branch = fields.Char(help='Branch/location name. Kept generic for Odoo 14 CE/EE compatibility.')
    sale_product_id = fields.Many2one('product.product', string='Sales Item', required=True, domain=[('sale_ok','=',True)])
    image_1920 = fields.Image(string='Menu Image')
    category = fields.Selection([('sushi','Sushi'),('japanese','Japanese'),('arabic','Arabic'),('other','Other')], default='other')
    portion_qty = fields.Float(default=1.0, string='Portion / Sale Qty')
    line_ids = fields.One2many('saaskul.recipe.line','recipe_id', string='Ingredients')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    standard_cost = fields.Monetary(compute='_compute_cost', store=True, currency_field='currency_id', string='Standard / Theoretical Cost')
    selling_price = fields.Monetary(related='sale_product_id.lst_price', currency_field='currency_id', readonly=True)
    potential_cost_pct = fields.Float(compute='_compute_cost', store=True, string='Potential Food Cost %')
    margin = fields.Monetary(compute='_compute_cost', store=True, currency_field='currency_id')
    active = fields.Boolean(default=True)
    notes = fields.Text()

    @api.depends('line_ids.qty','line_ids.unit_cost','sale_product_id.lst_price')
    def _compute_cost(self):
        for r in self:
            r.standard_cost = sum(r.line_ids.mapped('line_cost'))
            r.margin = r.selling_price - r.standard_cost
            r.potential_cost_pct = r.selling_price and (r.standard_cost / r.selling_price * 100.0) or 0.0

    def action_sales(self):
        self.ensure_one()
        return {'type':'ir.actions.act_window','name':_('Sales Lines'),'res_model':'sale.order.line','view_mode':'tree,form','domain':[('product_id','=',self.sale_product_id.id),('order_id.state','in',['sale','done'])]}

class RecipeLine(models.Model):
    _name = 'saaskul.recipe.line'
    _description = 'Recipe Ingredient'
    _order = 'sequence,id'
    sequence = fields.Integer(default=10)
    recipe_id = fields.Many2one('saaskul.recipe', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Ingredient / Prep Item', required=True, domain=[('purchase_ok','=',True)])
    qty = fields.Float(required=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', required=True)
    unit_cost = fields.Float(related='product_id.standard_price', readonly=True)
    line_cost = fields.Float(compute='_compute_line_cost', store=True)
    @api.depends('qty','unit_cost')
    def _compute_line_cost(self):
        for l in self: l.line_cost = l.qty * l.unit_cost

class PrepRecipe(models.Model):
    _name='saaskul.prep.recipe'; _description='Prep / Sub Recipe'
    name=fields.Char(required=True); code=fields.Char(); company_id=fields.Many2one('res.company',default=lambda s:s.env.company,required=True)
    product_id=fields.Many2one('product.product',string='Prep Product',required=True)
    batch_yield=fields.Float(required=True,default=1.0); uom_id=fields.Many2one('uom.uom',required=True)
    line_ids=fields.One2many('saaskul.prep.recipe.line','prep_id')
    batch_cost=fields.Float(compute='_cost',store=True); unit_cost=fields.Float(compute='_cost',store=True)
    @api.depends('line_ids.line_cost','batch_yield')
    def _cost(self):
        for r in self:
            r.batch_cost=sum(r.line_ids.mapped('line_cost')); r.unit_cost=r.batch_yield and r.batch_cost/r.batch_yield or 0
class PrepRecipeLine(models.Model):
    _name='saaskul.prep.recipe.line'; _description='Prep Recipe Ingredient'
    prep_id=fields.Many2one('saaskul.prep.recipe',required=True,ondelete='cascade'); product_id=fields.Many2one('product.product',required=True)
    qty=fields.Float(required=True); uom_id=fields.Many2one('uom.uom',required=True); unit_cost=fields.Float(related='product_id.standard_price'); line_cost=fields.Float(compute='_c',store=True)
    @api.depends('qty','unit_cost')
    def _c(self):
        for x in self:x.line_cost=x.qty*x.unit_cost

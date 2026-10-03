# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class DailyClosing(models.Model):
    _name='saaskul.recipe.closing'; _description='Daily Ingredient Closing Stock'; _order='date desc, branch, product_id'
    date=fields.Date(required=True,default=fields.Date.context_today); company_id=fields.Many2one('res.company',default=lambda s:s.env.company,required=True)
    branch=fields.Char(required=True); product_id=fields.Many2one('product.product',required=True,string='Ingredient')
    uom_id=fields.Many2one(related='product_id.uom_id',store=True); opening_qty=fields.Float(); purchase_qty=fields.Float(); transfer_in_qty=fields.Float(); transfer_out_qty=fields.Float(); waste_qty=fields.Float()
    actual_closing_qty=fields.Float(string='Chef Closing Qty',required=True); actual_consumption=fields.Float(compute='_calc',store=True)
    theoretical_consumption=fields.Float(string='Expected from Sales'); expected_closing_qty=fields.Float(compute='_calc',store=True); variance_qty=fields.Float(compute='_calc',store=True); variance_pct=fields.Float(compute='_calc',store=True)
    state=fields.Selection([('ok','OK'),('warning','Check'),('variance','Variance')],compute='_calc',store=True)
    @api.depends('opening_qty','purchase_qty','transfer_in_qty','transfer_out_qty','waste_qty','actual_closing_qty','theoretical_consumption')
    def _calc(self):
      for r in self:
        available=r.opening_qty+r.purchase_qty+r.transfer_in_qty-r.transfer_out_qty-r.waste_qty
        r.actual_consumption=available-r.actual_closing_qty
        r.expected_closing_qty=available-r.theoretical_consumption
        r.variance_qty=r.actual_consumption-r.theoretical_consumption
        r.variance_pct=r.theoretical_consumption and r.variance_qty/r.theoretical_consumption*100 or 0
        a=abs(r.variance_pct); r.state='ok' if a<=3 else ('warning' if a<=8 else 'variance')

class ConsumptionAnalysis(models.Model):
    _name='saaskul.recipe.consumption'; _description='Recipe Consumption Analysis'; _auto=False
    date=fields.Date(); company_id=fields.Many2one('res.company'); branch=fields.Char(); recipe_id=fields.Many2one('saaskul.recipe'); sale_product_id=fields.Many2one('product.product'); ingredient_id=fields.Many2one('product.product')
    sold_qty=fields.Float(); recipe_qty=fields.Float(); theoretical_qty=fields.Float(); unit_cost=fields.Float(); theoretical_cost=fields.Float(); sales_value=fields.Float(); potential_cost_pct=fields.Float()
    def init(self):
      self.env.cr.execute('DROP VIEW IF EXISTS saaskul_recipe_consumption CASCADE')
      self.env.cr.execute('''CREATE VIEW saaskul_recipe_consumption AS (
        SELECT row_number() over() AS id, so.date_order::date AS date, so.company_id, r.branch, r.id recipe_id, sol.product_id sale_product_id,
        rl.product_id ingredient_id, sum(sol.product_uom_qty) sold_qty, rl.qty recipe_qty,
        sum(sol.product_uom_qty*rl.qty) theoretical_qty, max(p.value_float) unit_cost,
        sum(sol.product_uom_qty*rl.qty*coalesce(p.value_float,0)) theoretical_cost,
        sum(sol.price_subtotal) sales_value,
        CASE WHEN sum(sol.price_subtotal)<>0 THEN sum(sol.product_uom_qty*rl.qty*coalesce(p.value_float,0))/sum(sol.price_subtotal)*100 ELSE 0 END potential_cost_pct
        FROM sale_order_line sol JOIN sale_order so ON so.id=sol.order_id JOIN saaskul_recipe r ON r.sale_product_id=sol.product_id
        JOIN saaskul_recipe_line rl ON rl.recipe_id=r.id
        LEFT JOIN ir_property p ON p.name='standard_price' AND p.res_id=('product.product,'||rl.product_id::text) AND (p.company_id=so.company_id OR p.company_id IS NULL)
        WHERE so.state IN ('sale','done') GROUP BY so.date_order::date,so.company_id,r.branch,r.id,sol.product_id,rl.product_id,rl.qty
      )''')

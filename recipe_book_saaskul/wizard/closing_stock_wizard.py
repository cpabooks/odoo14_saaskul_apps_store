from odoo import fields, models
class ClosingWizard(models.TransientModel):
 _name='saaskul.recipe.closing.wizard'; _description='Create Daily Closing Lines'
 date=fields.Date(default=fields.Date.context_today,required=True); branch=fields.Char(required=True)
 def action_create(self):
  products=self.env['saaskul.recipe.line'].search([]).mapped('product_id')
  for p in products:
   self.env['saaskul.recipe.closing'].create({'date':self.date,'branch':self.branch,'product_id':p.id,'actual_closing_qty':0})
  return {'type':'ir.actions.act_window','res_model':'saaskul.recipe.closing','view_mode':'tree,form','domain':[('date','=',self.date),('branch','=',self.branch)]}

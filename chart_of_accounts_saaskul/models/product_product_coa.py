from odoo import api, models, fields, _

class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    @api.depends('product_tmpl_id.coa_code')
    def _compute_coa_code(self):
        for product in self:
            product.coa_code = product.product_tmpl_id.coa_code

    coa_code = fields.Char('COA-Code', readonly=True, compute=_compute_coa_code)




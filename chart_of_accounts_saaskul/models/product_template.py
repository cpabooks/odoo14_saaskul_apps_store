from odoo import api, fields, models
# Odoo 19 removed these constants from base.res_partner.
WARNING_MESSAGE = [('no-message', 'No Message'), ('warning', 'Warning'), ('block', 'Blocking Message')]
WARNING_HELP = 'Selecting the "Warning" option will notify user with the message, Selecting "Blocking Message" will throw an exception with the message and block the flow. The Message has to be written in the next field.'


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    coa_code = fields.Char(string='COA-Code', readonly=True)

    purchase_line_warn = fields.Selection(
        WARNING_MESSAGE, 'Purchase Order Line Warning',
        required=False, help=WARNING_HELP, default='no-message',
    )

    @api.model
    def _cpabooks_ensure_default_product_category(self):
        Category = self.env['product.category'].sudo()
        categ = Category.search([('name', '=ilike', 'all')], limit=1, order='id asc')
        if not categ:
            categ = Category.search([], limit=1, order='id asc')
        if not categ:
            categ = Category.create({'name': 'All'})
        return categ

    @api.model
    def _cpabooks_ensure_default_uom(self):
        Uom = self.env['uom.uom'].sudo()
        uom = Uom.search([('name', '=ilike', 'units')], limit=1)
        if not uom:
            uom = Uom.search([('name', '=ilike', 'unit')], limit=1)
        if uom:
            return uom
        # Prefer existing reference UoM in Unit category (never create a 2nd reference)
        UomCateg = self.env['uom.category'].sudo()
        category = UomCateg.search([('name', '=ilike', 'unit%')], limit=1)
        if category:
            uom = Uom.search([
                ('category_id', '=', category.id),
                ('uom_type', '=', 'reference'),
            ], limit=1)
            if uom:
                return uom
            uom = Uom.search([('category_id', '=', category.id)], limit=1)
            if uom:
                return uom
        uom = Uom.search([], limit=1, order='id asc')
        if uom:
            return uom
        if not category:
            category = UomCateg.create({'name': 'Unit'})
        return Uom.create({
            'name': 'Units',
            'category_id': category.id,
            'factor': 1.0,
            'uom_type': 'reference',
        })

    @api.model
    def _cpabooks_default_product_vals(self, name, company):
        categ = self._cpabooks_ensure_default_product_category()
        uom = self._cpabooks_ensure_default_uom()
        # 'product' (storable) exists only when stock is installed.
        ptype = 'consu'  # Odoo 19: storable goods are consu + is_storable
        return {
            'name': name,
            'type': ptype,
            'sale_ok': True,
            'purchase_ok': True,
            'categ_id': categ.id,
            'uom_id': uom.id,
            'purchase_line_warn': 'no-message',
            'company_id': company.id,
        }

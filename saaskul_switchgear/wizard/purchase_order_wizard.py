# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

import time

import pytz

from odoo import api, fields, models, _
from datetime import datetime, date
# import odoo.addons_community.decimal_precision as dp
from odoo.exceptions import UserError


# class getpurchase(models.Model):
#     _inherit = 'purchase.order'
#     so_created = fields.Boolean(default=False, copy=False)
#     new_order_line_ids = fields.One2many('getpurchase.orderdata', 'new_order_line_id', string="Order Line")


class createPR(models.TransientModel):
    _name = 'create.pr'
    _description = "Create PR"

    new_order_line_ids = fields.One2many('getproduction.data', 'new_order_line_id1', string="Order Line")

    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)

    @api.model
    def default_get(self, default_fields):
        res = super(createPR, self).default_get(default_fields)
        record = self.env['mrp.production'].browse(self._context.get('active_ids', []))
        update = []
        get_existing_po=self.env['purchase.order'].sudo().search([('mo_id','=',record.id),('state','!=','cancel')])
        product_ids = []
        if get_existing_po:
            for line in get_existing_po.order_line:
                product_ids.append(line.product_id.id)
        for record in record.move_raw_ids:
            if record.product_id.id not in product_ids:
                update.append((0, 0, {
                    'product_id': record.product_id.id,
                    'name': record.product_id.description_purchase if record.product_id.description_purchase else record.product_id.name,
                    'product_qty': record.product_uom_qty,
                    'product_uom': record.product_uom.id,
                    'price_unit': record.product_id.standard_price,
                    # 'price_unit' : round(record.price_subtotal/record.product_qty,2),
                    # 'product_subtotal' : record.price_subtotal,
                    'product_subtotal': record.product_id.standard_price * record.product_uom_qty,
                    # 'date_planned': datetime.today(),
                    # 'tax_id':record.taxes_id.ids,
                }))

            res.update({'new_order_line_ids': update})
        return res

    def action_create_sale_order(self):
        record = self.env['purchase.order'].browse(self._context.get('active_ids', []))
        self.ensure_one()
        res = self.env['sale.order'].browse(self._context.get('id', []))
        value = []
        for data in self.new_order_line_ids:
            value.append([0, 0, {
                'product_id': data.product_id.id,
                'name': data.name,
                'product_qty': data.product_qty,
                'product_uom':data.product_uom.id,
                'price_unit': data.price_unit,

            }])
        res.create({'partner_id': self.partner_id.id,
                    'date_order': self.date_order,
                    'order_line': value,
                    # 'remarks' : record.name,
                    'po_ref': record.name,
                    'fpo_ref': record.remote_origin,

                    })
        print(res)
        date_time = pytz.timezone('Asia/Dhaka')
        local_time = datetime.now(date_time)
        dt_string = local_time.strftime("%d-%m-%Y %H:%M:%S")


        self.env['mail.message'].create({
            'model': record._name,
            'res_id': record.id,
            'message_type': 'notification',
            'body': f'Sales Order Created for Purcahse Order <b >{record.name}</b> at <b style="color:red;">{dt_string}</b>',
        })
        return

    def action_create_pr(self):
        record = self.env['mrp.production'].browse(self._context.get('active_ids', []))
        self.ensure_one()
        res = self.env['purchase.order'].browse(self._context.get('id', []))
        value = []
        for data in self.new_order_line_ids:
            value.append([0, 0, {
                'product_id': data.product_id.id,
                'name': data.name,
                'product_qty': data.product_qty,
                'product_uom': data.product_uom.id,
                'price_unit': data.price_unit,
                'date_planned':datetime.now().date(),
                'display_type':''
            }])
        res.create({'partner_id': self.partner_id.id,
                    'order_line': value,
                    'mo_id':record.id,

                    })
        print(res)
        date_time = pytz.timezone('Asia/Dhaka')
        local_time = datetime.now(date_time)
        dt_string = local_time.strftime("%d-%m-%Y %H:%M:%S")


        self.env['mail.message'].create({
            'model': record._name,
            'res_id': record.id,
            'message_type': 'notification',
            'body': f'Sales Order Created for Purcahse Order <b >{record.name}</b> at <b style="color:red;">{dt_string}</b>',
        })

        # return {
        #     'name': _('Quotation'),
        #     'type': 'ir.actions.act_window',
        #     'res_model': 'sale.order',
        #     'view_mode': 'form',
        #     'res_id': so.id
        #     # 'domain': [('id', '=', so.id)],
        #
        # }
        return


class getproduction(models.TransientModel):
    _name = 'getproduction.data'
    _description = "Get Production Data"

    new_order_line_id = fields.Many2one('create.pr')
    new_order_line_id1 = fields.Many2one('create.pr')
    product_id = fields.Many2one('product.product', string="Product", required=True)
    name = fields.Char(string="Description", required=True)
    product_qty = fields.Float(string='Quantity', required=True)
    product_uom=fields.Many2one('uom.uom', string="UoM")
    price_unit = fields.Float(string="Unit Price", required=True)
    product_subtotal = fields.Float(string="Sub Total", compute='_compute_total')
    qty_on_hand=fields.Float(string="Quantity On hand", compute='_compute_quantities')
    # date_planned = fields.Datetime(string='Receipt Date')

    # tax_id=fields.Many2many('account.tax',string="Taxes")

    @api.depends('product_qty', 'price_unit')
    def _compute_total(self):
        for record in self:
            record.product_subtotal = record.product_qty * record.price_unit

    def _compute_quantities(self):
        for rec in self:
            products = rec.product_id
            res = products._compute_quantities_dict(self._context.get('lot_id'), self._context.get('owner_id'), self._context.get('package_id'), self._context.get('from_date'), self._context.get('to_date'))
            for product in products:
                rec.qty_on_hand = res[product.id]['qty_available']









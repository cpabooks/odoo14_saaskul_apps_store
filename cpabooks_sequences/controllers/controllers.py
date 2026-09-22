# -*- coding: utf-8 -*-
# from odoo import http


# class CpabooksSequences(http.Controller):
#     @http.route('/cpabooks_sequences/cpabooks_sequences/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/cpabooks_sequences/cpabooks_sequences/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('cpabooks_sequences.listing', {
#             'root': '/cpabooks_sequences/cpabooks_sequences',
#             'objects': http.request.env['cpabooks_sequences.cpabooks_sequences'].search([]),
#         })

#     @http.route('/cpabooks_sequences/cpabooks_sequences/objects/<model("cpabooks_sequences.cpabooks_sequences"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('cpabooks_sequences.object', {
#             'object': obj
#         })

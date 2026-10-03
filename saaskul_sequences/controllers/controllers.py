# -*- coding: utf-8 -*-
# from odoo import http


# class SaaskulSequences(http.Controller):
#     @http.route('/saaskul_sequences/saaskul_sequences/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/saaskul_sequences/saaskul_sequences/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('saaskul_sequences.listing', {
#             'root': '/saaskul_sequences/saaskul_sequences',
#             'objects': http.request.env['saaskul_sequences.saaskul_sequences'].search([]),
#         })

#     @http.route('/saaskul_sequences/saaskul_sequences/objects/<model("saaskul_sequences.saaskul_sequences"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('saaskul_sequences.object', {
#             'object': obj
#         })

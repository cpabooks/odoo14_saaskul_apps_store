# -*- coding: utf-8 -*-
# from odoo import http


# class SaaskulSequences(http.Controller):
#     @http.route('/re_sequences_saaskul/re_sequences_saaskul/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/re_sequences_saaskul/re_sequences_saaskul/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('re_sequences_saaskul.listing', {
#             'root': '/re_sequences_saaskul/re_sequences_saaskul',
#             'objects': http.request.env['re_sequences_saaskul.re_sequences_saaskul'].search([]),
#         })

#     @http.route('/re_sequences_saaskul/re_sequences_saaskul/objects/<model("re_sequences_saaskul.re_sequences_saaskul"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('re_sequences_saaskul.object', {
#             'object': obj
#         })

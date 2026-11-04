# -*- coding: utf-8 -*-
# from odoo import http


# class CpabooksChartOfAccountV1(http.Controller):
#     @http.route('/chart_of_accounts_saaskul/chart_of_accounts_saaskul/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/chart_of_accounts_saaskul/chart_of_accounts_saaskul/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('chart_of_accounts_saaskul.listing', {
#             'root': '/chart_of_accounts_saaskul/chart_of_accounts_saaskul',
#             'objects': http.request.env['chart_of_accounts_saaskul.chart_of_accounts_saaskul'].search([]),
#         })

#     @http.route('/chart_of_accounts_saaskul/chart_of_accounts_saaskul/objects/<model("chart_of_accounts_saaskul.chart_of_accounts_saaskul"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('chart_of_accounts_saaskul.object', {
#             'object': obj
#         })

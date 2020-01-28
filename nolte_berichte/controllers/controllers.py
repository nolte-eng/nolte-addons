# -*- coding: utf-8 -*-
from odoo import http

# class Berichte(http.Controller):
#     @http.route('/berichte/berichte/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/berichte/berichte/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('berichte.listing', {
#             'root': '/berichte/berichte',
#             'objects': http.request.env['berichte.berichte'].search([]),
#         })

#     @http.route('/berichte/berichte/objects/<model("berichte.berichte"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('berichte.object', {
#             'object': obj
#         })
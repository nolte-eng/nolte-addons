# -*- coding: utf-8 -*-
from odoo import http

 # class Nolte(http.Controller):
 #     @http.route('/nolte/nolte/', auth='public')
 #    def index(self, **kw):
 #         return "Hello, world"
 #
 #     @http.route('/nolte/nolte/objects/', auth='public')
 #     def list(self, **kw):
 #         return http.request.render('nolte.listing', {
 #             'root': '/nolte/nolte',
 #             'objects': http.request.env['nolte.nolte'].search([]),
 #         })
 #
 #    @http.route('/nolte/nolte/objects/<model("nolte.nolte"):obj>/', auth='public')
 #     def object(self, obj, **kw):
 #         return http.request.render('nolte.object', {
 #             'object': obj
 #         })
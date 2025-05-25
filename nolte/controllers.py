# -*- coding: utf-8 -*-
from odoo import http

class NolteController(http.Controller):
    @http.route('/nolte/nolte/', auth='public', website=True)
    def index(self, **kw):
        return "Hello, world from Odoo 18!"

    @http.route('/nolte/nolte/objects/', auth='public', website=True)
    def list(self, **kw):
        objects = http.request.env['nolte.eng'].search([])
        return http.request.render('nolte.listing', {
            'root': '/nolte/nolte',
            'objects': objects,
        })

    @http.route('/nolte/nolte/objects/<model(\"nolte.eng\"):obj>/', auth='public', website=True)
    def object(self, obj, **kw):
        return http.request.render('nolte.object', {
            'object': obj
        })

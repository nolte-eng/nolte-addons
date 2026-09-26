# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Farook Al Ameen (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import http
from odoo.http import request


class WebsiteForm(http.Controller):
    @http.route(['/call_for_price/submit'], type='http', csrf=True,
                auth="public", website=True, methods=['POST'])
    def call_for_price(self, **post):
        """Function for store the call for price queries to backend"""
        try:
            product_id = int(post.get('product_id', 0))
            quantity = max(1, int(post.get('quantity', 1) or 1))
        except (TypeError, ValueError):
            return request.redirect('/shop')

        product = request.env['product.template'].sudo().browse(product_id).exists()
        if not product or not product.price_call:
            return request.redirect('/shop')

        request.env['call.price'].sudo().create({
            'product_id': product.id,
            'first_name': (post.get('first_name') or '').strip(),
            'last_name': (post.get('last_name') or '').strip(),
            'phone': (post.get('phone') or '').strip(),
            'email': (post.get('email') or '').strip(),
            'quantity': quantity,
            'message': (post.get('message') or '').strip(),
        })
        return request.render("website.contactus_thanks")

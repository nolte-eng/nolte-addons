from odoo import http
from odoo.http import request


class MitarbeiterportalController(http.Controller):
    @http.route("/mitarbeiterportal", type="http", auth="user", website=True, sitemap=False)
    def mitarbeiterportal(self, **kwargs):
        return request.render("nolte_mitarbeiterportal.portal_home")

import base64
import json

from odoo import http
from odoo.http import request


class FaltenbalgConfiguratorController(http.Controller):

    def _shape_ui_config(self):
        return {
            "straight": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "show_height": False, "hint": "Ideal für lineare Achsen und klassische Führungsabdeckungen. Gesamtlänge entspricht Lmax."},
            "u": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Tiefe links (C)"}, {"key": "e", "label": "Tiefe rechts (D"}], "hint": "Für dreiseitige Umschließung von Führungen. Zusätzlich bitte D und E angeben."},
            "l": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Tiefe (C)"}], "hint": "Wenn zwei Seiten geschützt werden müssen."},
            "c": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Tiefe links (C)"}, {"key": "e", "label": "Tiefe rechts (D)"}, {"key": "e", "label": "Absatz links (E)"}, {"key": "f", "label": "Absatz rechts (F)"}], "hint": "Geeignet für seitlich offene Geometrien. Bitte D, E, F und G ergänzen."},
            "g": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "c", "label": "Tiefe links (C)"}, {"key": "f", "label": "Tiefe rechts (D)"}, {"key": "e", "label": "Absatz rechts (E)"}], "hint": "Für versetzte oder eingreifende Einbausituationen. Bitte E, F und G ergänzen."},
            "box": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Höhe D"}], "hint": "Mehrseitiger Schutz für komplexere Anwendungen."},
            "pult": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Vordere Höhe D"}], "hint": "Schräge Pultform, z. B. für Bedien- oder Dachbereiche."},
            "roof": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "hint": "Symmetrische Dachform für obere Abdeckungen."},
            "kastenbalg": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Höhe D"}], "hint": "Kastenform für mehrseitige Abdeckungen."},
            "special": {"labels": ["Breite (A)", "Faltentiefe (B)", "Gesamtlänge"], "extra_fields": [{"key": "d", "label": "Optionales Tiefe links (C)"}, {"key": "e", "label": "Optionales Tiefe rechts (D)"}, {"key": "f", "label": "Optionales Absatz links (E)"}, {"key": "g", "label": "Optionales Absatz rechts (F)"}], "hint": "Sonderform: bitte Skizze oder Foto ergänzen."},
        }

    @http.route(["/faltenbalg-konfigurator", "/shop/faltenbalg/configurator/<model('product.template'):product>"], type="http", auth="public", website=True, sitemap=True)
    def faltenbalg_configurator(self, product=None, **kwargs):
        if not product:
            product = request.env["product.template"].sudo().search([("website_published", "=", True), ("is_faltenbalg_configurator", "=", True)], limit=1)
        inquiry_model = request.env["faltenbalg.inquiry"]
        values = {
            "product": product,
            "page_name": "faltenbalg_configurator",
            "shape_options": [opt for opt in inquiry_model._fields["shape"].selection if opt[0] != "kastenbalg"],
            "material_options": inquiry_model._fields["material"].selection,
            "axis_options": inquiry_model._fields["axis"].selection,
            "position_options": inquiry_model._fields["installation_position"].selection,
            "shape_ui_json": json.dumps(self._shape_ui_config()),
        }
        return request.render("nolte_faltenbalg_configurator.faltenbalg_configurator_page", values)

    @http.route("/faltenbalg-konfigurator/submit", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def faltenbalg_configurator_submit(self, **post):
        product_id = int(post.get("product_tmpl_id")) if post.get("product_tmpl_id") else False
        vals = {
            "product_tmpl_id": product_id,
            "company_name": post.get("company_name"),
            "contact_name": post.get("contact_name"),
            "email": post.get("email"),
            "phone": post.get("phone"),
            "shape": post.get("shape") or "straight",
            "axis": post.get("axis") or "other",
            "installation_position": post.get("installation_position") or "horizontal",
            "width_mm": float(post.get("width_mm") or 0.0),
            "depth_mm": float(post.get("depth_mm") or 0.0),
            "length_mm": float(post.get("length_mm") or 0.0),
            "lmin_mm": float(post.get("lmin_mm") or 0.0),
            "hub_mm": float(post.get("hub_mm") or 0.0),
            "fold_pitch_mm": float(post.get("fold_pitch_mm") or 0.0),
            "fold_count": int(float(post.get("fold_count") or 0)),
            "height_mm": float(post.get("height_mm") or 0.0),
            "extra_e_mm": float(post.get("extra_e_mm") or 0.0),
            "extra_f_mm": float(post.get("extra_f_mm") or 0.0),
            "extra_g_mm": float(post.get("extra_g_mm") or 0.0),
            "quantity": int(float(post.get("quantity") or 1)),
            "material": post.get("material") or "standard",
            "application": post.get("application"),
            "note": post.get("note"),
            "source_url": request.httprequest.referrer,
        }

        inquiry = request.env["faltenbalg.inquiry"].sudo().create(vals)

        upload = request.httprequest.files.get("drawing_file")
        if upload and upload.filename:
            attachment = request.env["ir.attachment"].sudo().create({
                "name": upload.filename,
                "datas": base64.b64encode(upload.read()),
                "res_model": "faltenbalg.inquiry",
                "res_id": inquiry.id,
                "mimetype": upload.mimetype,
            })
            inquiry.attachment_ids = [(4, attachment.id)]

        return request.render("nolte_faltenbalg_configurator.faltenbalg_configurator_success", {
            "inquiry": inquiry,
            "product": inquiry.product_tmpl_id,
            "page_name": "faltenbalg_configurator_success",
        })

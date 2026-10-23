import hashlib
import re

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request


class CustomerOnlineSignature(http.Controller):
    def _find(self, token):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token or ""):
            return request.env["nolte.service.signature.request"].sudo().browse()
        record = request.env["nolte.service.signature.request"].sudo().search([
            ("token_hash", "=", hashlib.sha256(token.encode()).hexdigest()),
            ("state", "in", ["pending", "signed"]),
            ("expires_at", ">", fields.Datetime.now()),
        ], limit=1)
        if record and record.report_id.state != "awaiting_signature" and record.state != "signed":
            return record.browse()
        return record

    def _secure_response(self, response):
        response.headers.update({
            "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'none'",
        })
        return response

    @http.route("/nolte_stundenbericht/sign/<string:token>", type="http", auth="public", methods=["GET", "POST"], sitemap=False)
    def sign_report(self, token, **post):
        record = self._find(token)
        error = None
        if record and request.httprequest.method == "POST":
            if record.state == "signed":
                pass  # A repeated browser submission never signs or emails twice.
            elif post.get("confirm_read") != "yes":
                error = "Bitte bestätigen Sie, dass Sie den Bericht geprüft haben."
            else:
                try:
                    with request.env.cr.savepoint():
                        record._accept(post.get("signer_name"), post.get("signature"))
                except UserError as exc:
                    error = str(exc)
                    record.invalidate_recordset()
        response = request.render("nolte_stundenbericht.online_signature_page", {
            "signature_request": record, "token": token if record else "", "error": error,
            "csrf_token": request.csrf_token(),
        })
        if not record:
            response.status_code = 404
        return self._secure_response(response)

    @http.route("/nolte_stundenbericht/sign/<string:token>/document/<string:document_format>", type="http", auth="public", methods=["GET"], sitemap=False)
    def signature_document(self, token, document_format):
        record = self._find(token)
        if not record or document_format not in ("html", "pdf"):
            response = request.make_response("Dieser Link ist nicht gültig.", headers=[("Content-Type", "text/plain; charset=utf-8")])
            response.status_code = 404
            return self._secure_response(response)
        if document_format == "html" and record.state == "pending":
            content, mimetype = record.html_snapshot, "text/html; charset=utf-8"
        else:
            attachment = record.report_id.customer_pdf_attachment_id if record.state == "signed" else record.pdf_attachment_id
            content, mimetype = attachment.raw, "application/pdf"
        response = request.make_response(content, headers=[("Content-Type", mimetype)])
        return self._secure_response(response)

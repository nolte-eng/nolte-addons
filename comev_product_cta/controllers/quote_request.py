import logging

from markupsafe import escape

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ProductQuoteRequest(http.Controller):

    @staticmethod
    def _selected_variant(product, values):
        """Return only a variant that really belongs to the requested template."""
        variant_id = values.get("product_variant_id")
        if variant_id:
            try:
                variant = request.env["product.product"].sudo().browse(int(variant_id)).exists()
            except (TypeError, ValueError):
                variant = request.env["product.product"]
            if variant and variant.product_tmpl_id == product:
                return variant

        attribute_values = values.get("attribute_values", "")
        try:
            selected_ids = {int(value) for value in attribute_values.split(",") if value}
        except (TypeError, ValueError):
            selected_ids = set()
        if selected_ids:
            for variant in product.product_variant_ids.sudo().filtered("active"):
                variant_value_ids = set(variant.product_template_attribute_value_ids.ids)
                if variant_value_ids == selected_ids:
                    return variant

        return product.product_variant_id if product.product_variant_count == 1 else request.env["product.product"]

    @http.route(
        [
            "/maschinen/anfrage/<model(\"product.template\"):product>",
            "/comev/anfrage/<model(\"product.template\"):product>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET", "POST"],
    )
    def product_quote_request(self, product, **post):
        if not product.website_published or not product.is_comev_product:
            return request.not_found()

        variant = self._selected_variant(product, post or request.params)
        render_values = {
            "product": product,
            "variant": variant,
            "attribute_values": post.get("attribute_values", request.params.get("attribute_values", "")),
            "product_variant_id": variant.id if variant else False,
        }

        if request.httprequest.method == "POST":
            # Unsichtbares Bot-Feld: echte Besucher lassen es leer.
            if post.get("website_url"):
                return request.render("comev_product_cta.quote_request_thanks", render_values)

            required = ("name", "email", "privacy")
            missing = [field for field in required if not post.get(field)]
            if missing:
                return request.render(
                    "comev_product_cta.quote_request_form",
                    {
                        **render_values,
                        "values": post,
                        "error": "Bitte füllen Sie alle Pflichtfelder aus.",
                    },
                )

            manufacturer = product.product_cta_manufacturer or "Nicht angegeben"
            variant_name = variant.display_name if variant else product.name
            description = """Anfrage über die Shop-Produktseite

Hersteller: {manufacturer}
Produkt: {product}
Produktvariante: {variant}
Interne Referenz: {reference}
Produkt-URL: {url}

Nachricht:
{message}
""".format(
                manufacturer=manufacturer,
                product=product.name,
                variant=variant_name,
                reference=(variant.default_code or "-") if variant else "-",
                url=product.website_url or "",
                message=post.get("message", ""),
            )

            lead_model = request.env["crm.lead"].sudo()
            lead_values = {
                "name": "Angebotsanfrage: %s" % variant_name,
                # Als Verkaufschance ist die Anfrage direkt in der CRM-Pipeline sichtbar.
                "type": "opportunity",
                "contact_name": post.get("name", "").strip(),
                "partner_name": post.get("company", "").strip(),
                "email_from": post.get("email", "").strip(),
                "phone": post.get("phone", "").strip(),
                "description": description,
            }
            # website_id is not installed on crm.lead in every Odoo 19 setup.
            if "website_id" in lead_model._fields:
                lead_values["website_id"] = request.website.id
            if "team_id" in lead_model._fields:
                sales_team = request.env["crm.team"].sudo().search(
                    [("active", "=", True)], order="sequence, id", limit=1
                )
                if sales_team:
                    lead_values["team_id"] = sales_team.id

            lead = lead_model.create(lead_values)
            self._send_request_emails(product, variant, post, lead)
            return request.render("comev_product_cta.quote_request_thanks", render_values)

        return request.render(
            "comev_product_cta.quote_request_form",
            {**render_values, "values": {}, "error": False},
        )

    @staticmethod
    def _send_request_emails(product, variant, post, lead):
        """Send notifications without losing the CRM request if SMTP is unavailable."""
        mail_model = request.env["mail.mail"].sudo()
        company = request.website.company_id
        email_from = company.email_formatted or company.email
        recipient = (product.product_cta_notification_email or company.email or "").strip()
        customer_email = post.get("email", "").strip()
        variant_name = variant.display_name if variant else product.name
        reference = (variant.default_code or "-") if variant else "-"
        manufacturer = product.product_cta_manufacturer or ""

        safe_message = escape(post.get("message", "")).replace("\n", "<br/>")
        internal_body = """
            <p>Über den Onlineshop ist eine neue Angebotsanfrage eingegangen.</p>
            <table>
                <tr><td><strong>Hersteller:</strong></td><td>{manufacturer}</td></tr>
                <tr><td><strong>Produktvariante:</strong></td><td>{variant}</td></tr>
                <tr><td><strong>Interne Referenz:</strong></td><td>{reference}</td></tr>
                <tr><td><strong>Name:</strong></td><td>{name}</td></tr>
                <tr><td><strong>Unternehmen:</strong></td><td>{company}</td></tr>
                <tr><td><strong>E-Mail:</strong></td><td>{email}</td></tr>
                <tr><td><strong>Telefon:</strong></td><td>{phone}</td></tr>
            </table>
            <p><strong>Anforderungen:</strong><br/>{message}</p>
            <p>CRM-Verkaufschance: {lead}</p>
        """.format(
            manufacturer=escape(manufacturer),
            variant=escape(variant_name),
            reference=escape(reference),
            name=escape(post.get("name", "")),
            company=escape(post.get("company", "")),
            email=escape(customer_email),
            phone=escape(post.get("phone", "")),
            message=safe_message,
            lead=escape(lead.display_name),
        )

        try:
            if recipient:
                mail_model.create({
                    "subject": "Neue Angebotsanfrage: %s" % variant_name,
                    "email_from": email_from or recipient,
                    "email_to": recipient,
                    "reply_to": customer_email or email_from or recipient,
                    "body_html": internal_body,
                    "auto_delete": True,
                }).send()

            if product.product_cta_customer_confirmation and customer_email:
                confirmation_body = """
                    <p>Guten Tag {name},</p>
                    <p>vielen Dank für Ihre Anfrage zur <strong>{variant}</strong>.</p>
                    <p>Wir haben Ihre Angaben erhalten und melden uns persönlich bei Ihnen, um Modell, Ausstattung und Optionen abzustimmen.</p>
                    <p>Mit freundlichen Grüßen<br/>Nolte Sales</p>
                """.format(
                    name=escape(post.get("name", "")),
                    variant=escape(variant_name),
                )
                mail_model.create({
                    "subject": "Ihre Anfrage zur %s" % variant_name,
                    "email_from": email_from or recipient,
                    "email_to": customer_email,
                    "reply_to": recipient or email_from,
                    "body_html": confirmation_body,
                    "auto_delete": True,
                }).send()
        except Exception:
            _logger.exception("E-Mail-Versand für Produktanfrage %s fehlgeschlagen", lead.id)

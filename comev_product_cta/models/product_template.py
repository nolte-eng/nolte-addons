from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_comev_product = fields.Boolean(
        string="Produktaktionen aktiv",
        help="Blendet auf der Shop-Produktseite Anfrage-, Detail- und Prospektaktionen ein.",
    )
    product_cta_manufacturer = fields.Char(
        string="Hersteller / Marke",
        help="Zum Beispiel COMEV, DELTA, ABENE oder Belotti.",
    )
    comev_detail_url = fields.Char(
        string="Technische Detailseite",
        help="Interne oder externe Adresse der ausführlichen Produktseite.",
    )
    comev_brochure_url = fields.Char(
        string="Prospekt-URL",
        help="Öffentliche URL des PDF-Prospekts. Bei leerem Feld wird kein Download angezeigt.",
    )
    product_cta_website_page_id = fields.Many2one(
        "website.page",
        string="Technische Detailseite",
        ondelete="set null",
        help="Vorhandene Produktseite aus Website auswählen.",
    )
    product_cta_brochure_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Produktprospekt",
        ondelete="set null",
        domain="[('mimetype', '=', 'application/pdf')]",
        help="Vorhandenen PDF-Prospekt aus den Dateianhängen auswählen.",
    )
    product_cta_detail_href = fields.Char(
        compute="_compute_product_cta_links",
        compute_sudo=True,
        store=True,
    )
    product_cta_brochure_href = fields.Char(
        compute="_compute_product_cta_links",
        compute_sudo=True,
        store=True,
    )
    product_cta_notification_email = fields.Char(
        string="Benachrichtigung an",
        default="info@nolte-eng.de",
        help="An diese Adresse wird bei jeder Produktanfrage eine E-Mail gesendet.",
    )
    product_cta_customer_confirmation = fields.Boolean(
        string="Eingangsbestätigung an Interessenten",
        default=True,
        help="Sendet dem Interessenten zusätzlich eine kurze Bestätigung per E-Mail.",
    )

    @api.depends(
        "product_cta_website_page_id",
        "product_cta_website_page_id.url",
        "product_cta_brochure_attachment_id",
        "comev_detail_url",
        "comev_brochure_url",
    )
    def _compute_product_cta_links(self):
        for product in self:
            product.product_cta_detail_href = (
                product.product_cta_website_page_id.url or product.comev_detail_url
            )
            attachment = product.product_cta_brochure_attachment_id
            product.product_cta_brochure_href = (
                f"/web/content/{attachment.id}?download=1"
                if attachment
                else product.comev_brochure_url
            )

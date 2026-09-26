from odoo import models
from odoo.tools import html2plaintext
from .payment_note import clean_payment_note


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _nolte_next_payment_note(self):
        self.ensure_one()
        return clean_payment_note(self.payment_term_id.note)

    def _nolte_next_customer_reference(self):
        self.ensure_one()
        # Standard Odoo contact reference; never substitute a database ID.
        return self.partner_id.commercial_partner_id.ref or self.partner_id.ref or ""

    def _nolte_next_show_note(self):
        self.ensure_one()
        # Preserve the legacy protection against exposing CSV import diagnostics.
        return not html2plaintext(self.note or "").strip().casefold().startswith("csv import:")

from odoo import models
from odoo.tools import html2plaintext


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _nolte_is_csv_import_note(self):
        """Keep CSV-import diagnostics out of customer-facing PDFs."""
        self.ensure_one()
        note = html2plaintext(self.note or "").strip()
        return note.casefold().startswith("csv import:")

    def _nolte_pdf_note_lines(self):
        """Split exceptionally long imported notes into printable blocks."""
        self.ensure_one()
        lines = [html2plaintext(line).strip() for line in (self.note or "").splitlines()]
        lines = [line for line in lines if line]
        return lines if len(lines) > 10 else []

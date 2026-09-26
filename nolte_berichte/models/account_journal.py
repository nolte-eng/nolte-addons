from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _compute_has_invalid_statements(self):
        """Ignore known legacy import gaps while retaining current warnings."""
        legacy_cutoff = fields.Date.to_date("2024-01-01")
        affected = self.env["account.bank.statement"].search([
            ("journal_id", "in", self.ids),
            ("date", ">=", legacy_cutoff),
            "|",
            ("is_valid", "=", False),
            ("is_complete", "=", False),
        ]).journal_id
        affected.has_invalid_statements = True
        (self - affected).has_invalid_statements = False

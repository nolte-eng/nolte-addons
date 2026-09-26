from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    nolte_next_sale_enabled = fields.Boolean(
        string="Neues Layout für alle Angebote und Aufträge",
        default=False,
        help="Ersetzt die Ausgabe des normalen Verkaufsberichts für diese Firma. "
             "Ohne Aktivierung ist nur der zusätzliche Druckeintrag verfügbar.",
    )
    nolte_next_director_1 = fields.Char(string="Geschäftsführer 1 (neuer Bericht)")
    nolte_next_director_2 = fields.Char(string="Geschäftsführer 2 (neuer Bericht)")

    def _nolte_next_directors(self):
        self.ensure_one()
        # Read-only bridge: no dependency on the old module, no legacy field ownership.
        return [value for value in (
            self.nolte_next_director_1 or (self.ceo_01 if "ceo_01" in self._fields else False),
            self.nolte_next_director_2 or (self.ceo_02 if "ceo_02" in self._fields else False),
        ) if value]

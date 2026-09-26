from odoo import _, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def action_open_pricelist_items(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Preislistenpositionen: %s", self.display_name),
            "res_model": "product.pricelist.item",
            "view_mode": "list,form",
            "domain": [("pricelist_id", "=", self.id)],
            "context": {
                "default_pricelist_id": self.id,
                "search_default_pricelist_id": self.id,
            },
        }

    def action_open_add_variants_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Produktvarianten zur Preisliste hinzufügen"),
            "res_model": "nolte.pricelist.variant.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pricelist_id": self.id},
        }

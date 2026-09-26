from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round


class PricelistVariantWizard(models.TransientModel):
    _name = "nolte.pricelist.variant.wizard"
    _description = "Produktvarianten zu einer Preisliste hinzufügen"

    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Preisliste",
        required=True,
        readonly=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Produkt",
        required=True,
        domain="[('sale_ok', '=', True)]",
    )
    variant_count = fields.Integer(
        string="Anzahl Varianten",
        compute="_compute_variant_count",
    )
    price_source = fields.Selection(
        [
            ("list_price", "Verkaufspreis der Variante"),
            ("standard_price", "Kosten der Variante"),
            ("zero", "0,00"),
        ],
        string="Preisquelle",
        required=True,
        default="list_price",
    )
    percentage = fields.Float(
        string="Preisänderung in %",
        default=0.0,
        help="Beispiel: 5 erhöht den Ausgangspreis um 5 %, -5 reduziert ihn um 5 %.",
    )
    rounding = fields.Float(
        string="Rundung",
        default=0.01,
        help="Beispiele: 0,01 = Cent; 1 = volle Euro; 100 = volle 100 Euro. 0 deaktiviert die Rundung.",
    )
    overwrite_existing = fields.Boolean(
        string="Bestehende Variantenpreise überschreiben",
        default=False,
        help="Aktualisiert bestehende feste Regeln derselben Variante mit Mindestmenge 0 und ohne Zeitraum.",
    )
    include_archived = fields.Boolean(
        string="Archivierte Varianten einbeziehen",
        default=False,
    )

    @api.depends("product_tmpl_id", "include_archived")
    def _compute_variant_count(self):
        for wizard in self:
            if not wizard.product_tmpl_id:
                wizard.variant_count = 0
                continue
            variants = wizard.product_tmpl_id.with_context(
                active_test=not wizard.include_archived
            ).product_variant_ids
            wizard.variant_count = len(variants)

    def _get_source_price(self, variant):
        self.ensure_one()
        if self.price_source == "standard_price":
            price = variant.standard_price
        elif self.price_source == "zero":
            price = 0.0
        else:
            price = variant.lst_price

        price *= 1.0 + (self.percentage / 100.0)
        if self.rounding and self.rounding > 0:
            price = float_round(price, precision_rounding=self.rounding)
        return price

    def action_generate(self):
        self.ensure_one()
        if not self.product_tmpl_id:
            raise UserError(_("Bitte wählen Sie ein Produkt aus."))

        variants = self.product_tmpl_id.with_context(
            active_test=not self.include_archived
        ).product_variant_ids
        if not variants:
            raise UserError(_("Für das ausgewählte Produkt wurden keine Varianten gefunden."))

        Item = self.env["product.pricelist.item"]
        existing_items = Item.search([
            ("pricelist_id", "=", self.pricelist_id.id),
            ("product_id", "in", variants.ids),
            ("applied_on", "=", "0_product_variant"),
            ("min_quantity", "=", 0),
            ("date_start", "=", False),
            ("date_end", "=", False),
        ])
        existing_by_product = {item.product_id.id: item for item in existing_items}

        created = 0
        updated = 0
        skipped = 0
        values_to_create = []

        for variant in variants:
            fixed_price = self._get_source_price(variant)
            existing = existing_by_product.get(variant.id)
            if existing:
                if self.overwrite_existing:
                    existing.write({
                        "compute_price": "fixed",
                        "fixed_price": fixed_price,
                    })
                    updated += 1
                else:
                    skipped += 1
                continue

            values_to_create.append({
                "pricelist_id": self.pricelist_id.id,
                "applied_on": "0_product_variant",
                "product_id": variant.id,
                "compute_price": "fixed",
                "fixed_price": fixed_price,
                "min_quantity": 0,
            })

        if values_to_create:
            Item.create(values_to_create)
            created = len(values_to_create)

        message = _(
            "Varianten verarbeitet: %(total)s · Neu: %(created)s · Aktualisiert: %(updated)s · Übersprungen: %(skipped)s",
            total=len(variants),
            created=created,
            updated=updated,
            skipped=skipped,
        )
        self.pricelist_id.message_post(body=message)

        return {
            "type": "ir.actions.act_window",
            "name": _("Preislistenpositionen: %s", self.pricelist_id.display_name),
            "res_model": "product.pricelist.item",
            "view_mode": "list,form",
            "domain": [("pricelist_id", "=", self.pricelist_id.id)],
            "context": {"default_pricelist_id": self.pricelist_id.id},
        }

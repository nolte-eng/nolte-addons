# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    partner_id = fields.Many2one(
        "res.partner",
        string="Kunde",
        help="Kunde, bei dem diese Maschine/Anlage steht.",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Maschinenmodell (Produkt)",
        help="Maschinenmodell als Produkt. Von dort wird die Stückliste (BOM) für die Ersatzteil-Übersicht und den PDF-Katalog ermittelt.",
    )

    bom_id = fields.Many2one(
        "mrp.bom",
        string="Stückliste (automatisch)",
        compute="_compute_bom_id",
        store=False,
        help="Gefundene Standard-Stückliste für das ausgewählte Maschinenmodell (Produkt oder Template).",
    )

    @api.depends("product_id", "company_id")
    def _compute_bom_id(self):
        Bom = self.env["mrp.bom"]
        for rec in self:
            rec.bom_id = False
            if not rec.product_id:
                continue

            company = rec.company_id or self.env.company
            domain_company = [("company_id", "in", [company.id, False])]

            bom = Bom.search(
                [("product_id", "=", rec.product_id.id)] + domain_company,
                order="company_id desc, sequence, id",
                limit=1,
            )
            if not bom:
                bom = Bom.search(
                    [("product_tmpl_id", "=", rec.product_id.product_tmpl_id.id)] + domain_company,
                    order="company_id desc, sequence, id",
                    limit=1,
                )
            rec.bom_id = bom or False

    def _ensure_product_and_bom(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Bitte zuerst ein Maschinenmodell (Produkt) am Equipment auswählen."))
        if not self.bom_id:
            raise UserError(_(
                "Für das ausgewählte Maschinenmodell wurde keine Stückliste (BOM) gefunden. "
                "Bitte im Fertigungsmodul eine BOM anlegen (für Produkt oder Vorlage)."
            ))

    def action_view_spare_parts(self):
        self.ensure_one()
        self._ensure_product_and_bom()
        # Odoo 17+ uses view type 'list' (tree is kept for legacy, but may error in some clients)
        return {
            "type": "ir.actions.act_window",
            "name": _("Ersatzteile"),
            "res_model": "mrp.bom.line",
            "view_mode": "list,form",
            "target": "current",
            "domain": [("bom_id", "=", self.bom_id.id)],
            "context": {
                "default_bom_id": self.bom_id.id,
                "search_default_bom_id": self.bom_id.id,
            },
        }

    def action_print_spare_parts_catalog(self):
        self.ensure_one()
        self._ensure_product_and_bom()
        return self.env.ref("nolte_machine_spareparts.action_report_spare_parts_catalog").report_action(self)

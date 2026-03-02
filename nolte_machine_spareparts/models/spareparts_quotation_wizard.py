# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class NolteSparepartsQuotationWizard(models.TransientModel):
    _name = "nolte.spareparts.quotation.wizard"
    _description = "Ersatzteile -> Angebot Wizard"

    equipment_id = fields.Many2one("maintenance.equipment", required=True, readonly=True)
    partner_id = fields.Many2one(related="equipment_id.partner_id", store=False, readonly=True)
    bom_id = fields.Many2one(related="equipment_id.bom_id", store=False, readonly=True)

    target = fields.Selection(
        [("new", "Neues Angebot"), ("existing", "Bestehendes Angebot ergänzen")],
        default="new",
        required=True,
    )
    existing_order_id = fields.Many2one(
        "sale.order",
        string="Bestehendes Angebot",
        domain="[('partner_id','=',partner_id), ('state','in',('draft','sent'))]",
    )
    merge_same_product = fields.Boolean(
        string="Gleiche Artikel zusammenfassen",
        default=True,
        help="Wenn aktiviert und das Angebot bereits eine Position mit demselben Artikel enthält, wird die Menge erhöht statt eine neue Position anzulegen.",
    )

    line_ids = fields.One2many("nolte.spareparts.quotation.wizard.line", "wizard_id", string="Positionen")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        equipment_id = self.env.context.get("default_equipment_id") or self.env.context.get("active_id")
        if equipment_id and "equipment_id" in fields_list:
            res["equipment_id"] = equipment_id
        return res

    @api.onchange("equipment_id")
    def _onchange_equipment_id(self):
        if not self.equipment_id:
            return
        if not self.equipment_id.partner_id:
            raise UserError(_("Am Equipment ist kein Kunde gesetzt. Bitte zuerst den Kunden auswählen."))
        if not self.equipment_id.bom_id:
            self.line_ids = [(5, 0, 0)]
            return

        lines = []
        for l in self.equipment_id.bom_id.bom_line_ids:
            lines.append((0, 0, {
                "selected": True,
                "product_id": l.product_id.id,
                "quantity": l.product_qty,
                "product_uom_id": l.product_uom_id.id,
            }))
        self.line_ids = [(5, 0, 0)] + lines

    def _get_or_create_order(self):
        self.ensure_one()
        if not self.equipment_id.partner_id:
            raise UserError(_("Am Equipment ist kein Kunde gesetzt."))

        if self.target == "existing":
            if not self.existing_order_id:
                raise UserError(_("Bitte ein bestehendes Angebot auswählen."))
            return self.existing_order_id

        return self.env["sale.order"].create({
            "partner_id": self.equipment_id.partner_id.id,
            "origin": self.equipment_id.name or "",
        })

    def action_create_or_update_quotation(self):
        self.ensure_one()
        if not self.line_ids.filtered("selected"):
            raise UserError(_("Bitte mindestens eine Position auswählen."))

        order = self._get_or_create_order()

        for wline in self.line_ids.filtered("selected"):
            if not wline.product_id:
                continue

            if self.merge_same_product:
                existing_line = self.env["sale.order.line"].search([
                    ("order_id", "=", order.id),
                    ("display_type", "=", False),
                    ("product_id", "=", wline.product_id.id),
                ], limit=1)
                if existing_line:
                    existing_line.product_uom_qty += wline.quantity
                    continue

            self.env["sale.order.line"].create({
                "order_id": order.id,
                "product_id": wline.product_id.id,
                "product_uom_qty": wline.quantity,
                "product_uom": wline.product_uom_id.id or wline.product_id.uom_id.id,
            })

        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }


class NolteSparepartsQuotationWizardLine(models.TransientModel):
    _name = "nolte.spareparts.quotation.wizard.line"
    _description = "Ersatzteile -> Angebot Wizard Zeile"

    wizard_id = fields.Many2one("nolte.spareparts.quotation.wizard", required=True, ondelete="cascade")
    selected = fields.Boolean(default=True)
    product_id = fields.Many2one("product.product", string="Artikel", required=True)
    quantity = fields.Float(string="Menge", default=1.0)
    product_uom_id = fields.Many2one("uom.uom", string="ME")

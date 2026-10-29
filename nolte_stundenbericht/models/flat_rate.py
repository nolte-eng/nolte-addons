from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ServiceFlatRate(models.Model):
    _name = "nolte.service.flat.rate"
    _description = "Pauschale für Einsatzberichte"
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(string="Pauschale", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    company_id = fields.Many2one("res.company", string="Unternehmen", required=True, default=lambda self: self.env.company)
    product_id = fields.Many2one("product.product", string="Artikel", required=True, check_company=True, domain="[('sale_ok', '=', True)]")

    def write(self, values):
        if {"product_id", "company_id"}.intersection(values):
            for rate in self:
                if any(values.get(key, rate[key].id) != rate[key].id for key in ("product_id", "company_id")) and self.env["nolte.service.report.flat.rate"].sudo().search_count([("flat_rate_id", "=", rate.id)]):
                    raise UserError(_("Diese Pauschale wird bereits in Berichten verwendet. Bitte archivieren und für einen anderen Artikel eine neue Pauschale anlegen."))
        return super().write(values)


class ServiceReportFlatRate(models.Model):
    _name = "nolte.service.report.flat.rate"
    _description = "Ausgewählte Einsatzpauschale"
    _inherit = "nolte.signature.child.guard"
    _order = "id"
    _check_company_auto = True

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="report_id.company_id", store=True)
    flat_rate_id = fields.Many2one("nolte.service.flat.rate", required=True, ondelete="restrict", check_company=True, readonly=True)
    name = fields.Char(string="Pauschale", required=True, readonly=True)
    product_id = fields.Many2one("product.product", string="Artikel", required=True, ondelete="restrict", check_company=True, readonly=True)
    sale_line_id = fields.Many2one("sale.order.line", string="Angebotsposition", readonly=True, copy=False, ondelete="set null", check_company=True)
    _unique_rate = models.Constraint("UNIQUE(report_id, flat_rate_id)", "Eine Pauschale darf pro Bericht nur einmal ausgewählt werden.")


class ServiceReport(models.Model):
    _inherit = "nolte.service.report"

    flat_rate_line_ids = fields.One2many("nolte.service.report.flat.rate", "report_id", string="Pauschalen", copy=False, readonly=True)

    def preview_customer_snapshot(self):
        snapshot = super().preview_customer_snapshot()
        snapshot["flatRates"] = [{"name": line.name} for line in self.flat_rate_line_ids]
        return snapshot

    def _sync_flat_rates(self, selected_ids):
        self.ensure_one()
        self.check_access("write")
        self._lock_customer_confirmation()
        if self.state not in ("draft", "returned"):
            raise UserError(_("Pauschalen können nur vor der Kundenbestätigung geändert werden."))
        if not isinstance(selected_ids, list) or len(selected_ids) > 200 or any(type(value) is not int or value <= 0 for value in selected_ids):
            raise ValidationError(_("Die Pauschalenauswahl ist ungültig."))
        ids = set(selected_ids)
        existing = {line.flat_rate_id.id: line for line in self.sudo().flat_rate_line_ids}
        rates = self.env["nolte.service.flat.rate"].with_context(active_test=False).search([
            ("id", "in", list(ids)), ("company_id", "=", self.company_id.id),
        ])
        if set(rates.ids) != ids:
            raise UserError(_("Mindestens eine Pauschale ist für dieses Unternehmen nicht verfügbar."))
        for rate in rates:
            if rate.id in existing:
                continue
            product = rate.sudo().product_id
            if not rate.active or not product.active or not product.sale_ok:
                raise UserError(_("Die Pauschale „%s“ ist nicht mehr auswählbar.") % rate.name)
            self.env["nolte.service.report.flat.rate"].sudo().create({
                "report_id": self.id, "flat_rate_id": rate.id,
                "name": rate.name, "product_id": product.id,
            })
        self.sudo().flat_rate_line_ids.filtered(lambda line: line.flat_rate_id.id not in ids).unlink()

    def _transfer_flat_rates(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Bitte zuerst einen Verkaufsauftrag für die Pauschalen zuordnen."))
        self._check_sale_order_transfer_target(lock=True)
        for selection in self.flat_rate_line_ids:
            if selection.sale_line_id:
                if selection.sale_line_id.order_id != self.sale_order_id:
                    raise UserError(_("Die Pauschale ist bereits mit einem anderen Angebot verknüpft."))
                continue
            product = selection.product_id
            if not product.active or not product.sale_ok or (product.company_id and product.company_id != self.company_id):
                raise UserError(_("Bitte den hinterlegten Artikel der Pauschale „%s“ prüfen.") % selection.name)
            # Standard sale computations supply description, pricelist price,
            # UoM, fiscal-position taxes and discounts. Never trust client prices.
            selection.sale_line_id = self.env["sale.order.line"].with_company(self.company_id).create({
                "order_id": self.sale_order_id.id, "product_id": product.id,
                "product_uom_qty": 1, "sequence": 90,
            })

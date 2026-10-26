from odoo import _, fields, models
from odoo.exceptions import AccessError


class ResCompany(models.Model):
    _inherit = "res.company"

    nolte_checklist_template_id = fields.Many2one(
        "nolte.service.checklist.template", copy=False, ondelete="restrict",
        groups="nolte_stundenbericht.group_stundenbericht_manager",
    )


class NolteServiceChecklistTemplate(models.Model):
    _name = "nolte.service.checklist.template"
    _description = "Zentrale Checklisten-Vorlage"
    _order = "sequence, name, id"

    name = fields.Char(string="Vorlagenname", required=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(default=True)
    visibility = fields.Selection([
        ("internal", "Intern – nur Monteure und Prüfer"),
        ("customer", "Kundencheckliste – erscheint im PDF"),
    ], string="Verwendung", required=True, default="customer")
    company_id = fields.Many2one("res.company", string="Unternehmen", default=lambda self: self.env.company)
    line_ids = fields.One2many("nolte.service.checklist.template.line", "template_id", string="Prüfpunkte", copy=True)

    def _default_for_current_company(self):
        template = self.browse(self.env.company.sudo().nolte_checklist_template_id.id)
        return template.filtered(lambda item: item.active and item.visibility == "customer" and item.company_id == self.env.company)

    def action_open_configuration(self):
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager"):
            raise AccessError(_("Nur Administratoren dürfen den Einsatzabschluss bearbeiten."))
        company = self.env.company
        self.env.cr.execute("SELECT id FROM res_company WHERE id = %s FOR UPDATE", [company.id])
        company.invalidate_recordset(["nolte_checklist_template_id"])
        template = self._default_for_current_company()
        if not template:
            template = self.create({"name": "Einsatzabschluss", "visibility": "customer", "company_id": company.id})
            company.sudo().nolte_checklist_template_id = template
        return {
            "type": "ir.actions.act_window", "name": "Einsatzabschluss",
            "res_model": self._name, "res_id": template.id,
            "views": [(self.env.ref("nolte_stundenbericht.view_nolte_service_checklist_template_form").id, "form")],
            "target": "current",
        }


class NolteServiceChecklistTemplateLine(models.Model):
    _name = "nolte.service.checklist.template.line"
    _description = "Prüfpunkt einer zentralen Checklisten-Vorlage"
    _order = "sequence, id"

    template_id = fields.Many2one("nolte.service.checklist.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Prüfpunkt", required=True)
    note = fields.Char(string="Vorbelegte Bemerkung")

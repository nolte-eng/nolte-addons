from odoo import fields, models


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


class NolteServiceChecklistTemplateLine(models.Model):
    _name = "nolte.service.checklist.template.line"
    _description = "Prüfpunkt einer zentralen Checklisten-Vorlage"
    _order = "sequence, id"

    template_id = fields.Many2one("nolte.service.checklist.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Prüfpunkt", required=True)
    note = fields.Char(string="Vorbelegte Bemerkung")

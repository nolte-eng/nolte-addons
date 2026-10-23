from odoo import fields, models


class NolteServiceWorkTemplate(models.Model):
    _name = "nolte.service.work.template"
    _description = "Textvorlage für ausgeführte Arbeiten"
    _order = "sequence, name, id"

    name = fields.Char(string="Vorlagenname", required=True, index=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(default=True)
    body = fields.Text(string="Vorlagentext", required=True, translate=False)
    company_id = fields.Many2one(
        "res.company", string="Unternehmen", default=lambda self: self.env.company,
        help="Ohne Unternehmen ist die Vorlage unternehmensübergreifend verfügbar.",
    )

from odoo import fields, models


class NolteMachineType(models.Model):
    _name = "nolte.machine.type"
    _description = "Maschinentyp für Serviceeinsätze"
    _order = "name"

    name = fields.Char(string="Maschinentyp", required=True, index=True)

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Dieser Maschinentyp ist bereits angelegt.",
    )

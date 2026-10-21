from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    stundenbericht_source = fields.Selection(
        [("csv", "CSV"), ("app", "App"), ("both", "Parallelbetrieb")],
        string="Stundenbericht-Quelle",
        default="csv",
        required=True,
        help="Steuert die zulässige Quelle während der schrittweisen Umstellung.",
    )
    stundenbericht_app_active_from = fields.Date(
        string="App aktiv ab",
        help="Ab diesem Datum wird die mobile Erfassung als reguläre Quelle erwartet.",
    )

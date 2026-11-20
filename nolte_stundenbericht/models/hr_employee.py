from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Retained for compatibility with historical data/imports; no longer controls sync.
    stundenbericht_source = fields.Selection(
        [("csv", "CSV"), ("app", "App"), ("both", "Parallelbetrieb")],
        string="Stundenbericht-Quelle",
        default="csv",
        required=True,
        groups="hr.group_hr_user",
        help="Veraltete Einstellung ohne Auswirkung auf die Spesenübergabe.",
    )
    stundenbericht_app_active_from = fields.Date(
        string="App aktiv ab",
        groups="hr.group_hr_user",
        help="Historisches Umstellungsdatum ohne Auswirkung auf die Spesenübergabe.",
    )

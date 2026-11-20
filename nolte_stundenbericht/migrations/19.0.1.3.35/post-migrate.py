"""Remove only unsigned, unlinked empty draft days; retain signed/integrated evidence."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["nolte.service.report"].search([("state", "=", "draft")])._discard_empty_planning_days()

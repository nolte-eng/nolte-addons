"""Refresh generated service events with internal visibility and assignees."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    events = env["calendar.event"].with_context(active_test=False).search([
        ("nolte_service_task_id", "!=", False),
    ])
    events.nolte_service_task_id.with_context(active_test=False)._sync_nolte_calendar()

"""Populate technician selectors without changing existing event dates."""
from odoo import SUPERUSER_ID, api, Command


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Later versions expose the selector directly from the task. There is
    # no stored selector to populate and writing it would re-plan old events.
    if env["calendar.event"]._fields["nolte_service_technician_ids"].related:
        return
    events = env["calendar.event"].with_context(
        active_test=False, nolte_calendar_sync=True, no_mail_to_attendees=True,
        skip_attendee_notification=True, dont_notify=True, tracking_disable=True,
    ).search([("nolte_service_task_id", "!=", False)])
    for event in events:
        assignees = event.nolte_service_task_id.user_ids.filtered(lambda user: user.active and not user.share)
        event.write({"nolte_service_technician_ids": [Command.set(assignees.ids)]})

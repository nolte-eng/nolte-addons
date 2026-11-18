"""Update visibility and participants without rewriting existing appointment times."""
from odoo import SUPERUSER_ID, api, Command


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    events = env["calendar.event"].with_context(
        active_test=False, no_mail_to_attendees=True, skip_attendee_notification=True,
        dont_notify=True, tracking_disable=True, mail_create_nosubscribe=True,
    ).search([("nolte_service_task_id", "!=", False)])
    for event in events:
        task = event.nolte_service_task_id
        organizer = task.create_uid if task.create_uid.active and not task.create_uid.share else env.user
        assignees = task.user_ids.filtered(lambda user: user.active and not user.share)
        partners = (assignees | organizer).partner_id
        values = {}
        if event.privacy != "confidential":
            values["privacy"] = "confidential"
        if set(event.partner_ids.ids) != set(partners.ids):
            values["partner_ids"] = [Command.set(partners.ids)]
        if values:
            event.write(values)

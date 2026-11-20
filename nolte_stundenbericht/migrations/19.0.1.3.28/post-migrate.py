"""Use native Enterprise dates and remove the redundant calendar assignment relation."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['project.task'].with_context(
        active_test=False, install_mode=True, tracking_disable=True, mail_auto_subscribe_no_notify=True,
    )
    if 'planned_date_begin' in tasks._fields:
        legacy = tasks.search([('nolte_service_date_start_value', '!=', False)])
        for task in legacy:
            previous = task.nolte_service_date_start_value
            if task.planned_date_begin and task._nolte_planning_date(task.planned_date_begin) != previous:
                raise ValueError('Conflicting Enterprise and legacy planning dates on task %s' % task.id)
            if not task.planned_date_begin:
                values = {'nolte_service_date_start': previous}
                if task.is_fsm and not task.date_deadline:
                    values['nolte_service_date_end'] = previous
                task.write(values)
            task.write({'nolte_service_date_start_value': False})
    cr.execute('DROP TABLE IF EXISTS nolte_calendar_technician_rel')

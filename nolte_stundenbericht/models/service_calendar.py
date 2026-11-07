from datetime import datetime, time
from markupsafe import Markup

from odoo import _, api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError


class ServiceCalendarEvent(models.Model):
    _inherit = 'calendar.event'

    nolte_service_task_id = fields.Many2one(
        'project.task', string='Serviceeinsatz', readonly=True, copy=False,
        index=True, ondelete='set null', groups='nolte_stundenbericht.group_stundenbericht_user')
    _nolte_service_task_unique = models.Constraint(
        'UNIQUE(nolte_service_task_id)', 'Für einen Serviceeinsatz darf nur ein Kalendertermin vorhanden sein.')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('nolte_service_task_id') for v in vals_list):
            raise AccessError(_('Die Verknüpfung zum Serviceeinsatz wird von der Einsatzplanung verwaltet.'))
        return super().create(vals_list)

    def write(self, values):
        if 'nolte_service_task_id' in values and not self.env.su:
            raise AccessError(_('Die Verknüpfung zum Serviceeinsatz wird von der Einsatzplanung verwaltet.'))
        return super().write(values)


class ServiceTaskCalendar(models.Model):
    _inherit = 'project.task'

    nolte_service_date_start = fields.Date(string='Einsatzbeginn', help='Ohne Beginn gilt das Einsatzende als einzelner Einsatztag.')
    nolte_service_date_end = fields.Date(
        string='Einsatzende', compute='_compute_nolte_service_date_end', inverse='_inverse_nolte_service_date_end')
    nolte_calendar_event_id = fields.Many2one('calendar.event', string='Kalendertermin', readonly=True, copy=False)

    @api.depends('date_deadline')
    def _compute_nolte_service_date_end(self):
        for task in self:
            task.nolte_service_date_end = fields.Date.to_date(task.date_deadline)

    def _inverse_nolte_service_date_end(self):
        for task in self:
            task.date_deadline = task.nolte_service_date_end or False

    def _nolte_period_start(self):
        self.ensure_one()
        return self.nolte_service_date_start or fields.Date.to_date(self.date_deadline)

    @api.constrains('nolte_service_date_start', 'date_deadline')
    def _check_nolte_service_period(self):
        for task in self.filtered('nolte_service_planning'):
            end = fields.Date.to_date(task.date_deadline)
            if task.nolte_service_date_start and end and end < task.nolte_service_date_start:
                raise ValidationError(_('Das Einsatzende darf nicht vor dem Einsatzbeginn liegen.'))

    @api.model
    def _nolte_calendar_values(self, values):
        values = dict(values)
        if 'nolte_service_date_end' in values:
            values['date_deadline'] = values.pop('nolte_service_date_end') or False
        return values

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create([self._nolte_calendar_values(v) for v in vals_list])
        if not self.env.context.get('install_mode'):
            records._sync_nolte_calendar()
        return records

    def write(self, values):
        values = self._nolte_calendar_values(values)
        watched = {'nolte_service_date_start', 'date_deadline', 'user_ids', 'name', 'partner_id',
                   'nolte_service_location', 'nolte_service_location_name', 'active', 'state', 'project_id'}
        with self.env.cr.savepoint():
            for task in self.sorted('id'):
                update = dict(values)
                # Moving the deadline of a one-day appointment moves the
                # whole appointment; explicit multi-day starts stay fixed.
                if ('date_deadline' in update and 'nolte_service_date_start' not in update
                        and task.nolte_service_date_start
                        and task.nolte_service_date_start == fields.Date.to_date(task.date_deadline)):
                    update['nolte_service_date_start'] = fields.Date.to_date(update['date_deadline'])
                super(ServiceTaskCalendar, task).write(update)
                if not self.env.context.get('install_mode') and watched.intersection(update):
                    task._sync_nolte_calendar()
        return True

    def _sync_nolte_calendar(self):
        """One private, internal all-day event per authorized service task."""
        self.check_access('read')
        events = self.env['calendar.event'].sudo().with_context(
            active_test=False, no_mail_to_attendees=True, skip_attendee_notification=True,
            dont_notify=True, tracking_disable=True, mail_create_nosubscribe=True,
            skip_contact_description=True)
        for task in self.sorted('id'):
            # Serializes creation, date edits and assignment updates for this task.
            task._nolte_lock_shared_data()
            task.invalidate_recordset(['date_deadline', 'nolte_service_date_start', 'user_ids', 'active', 'state'])
            event = events.search([('nolte_service_task_id', '=', task.id)], limit=1)
            start = task._nolte_period_start()
            valid = task.nolte_service_planning and task.active and task.state != '1_canceled' and start
            if not valid:
                if event and event.active:
                    event.write({'active': False})
                continue
            end = fields.Date.to_date(task.date_deadline) or start
            organizer = task.create_uid if task.create_uid.active and not task.create_uid.share else self.env.user
            assignees = task.user_ids.filtered(lambda user: user.active and not user.share)
            partners = (assignees | organizer).partner_id
            customer = task._nolte_customer()
            title = ' · '.join(p for p in (customer.name, task.name) if p)
            values = {
                'name': title, 'allday': True,
                'start': datetime.combine(start, time(8)),
                'stop': datetime.combine(end, time(18)),
                'user_id': organizer.id, 'partner_ids': [Command.set(partners.ids)],
                'privacy': 'private', 'show_as': 'busy', 'active': True,
                'location': task.nolte_service_location or False,
                # A native res_model/res_id link also creates a meeting
                # activity and can e-mail its organizer during backfills.
                # Keep our explicit task link without generating activities.
                'res_model_id': False, 'res_id': False,
                'description': Markup('<p><a href="/odoo/project.task/%s">Einsatzauftrag öffnen</a></p>') % task.id,
            }
            if event:
                # Avoid repeated native calendar notifications / attendee rebuilds
                # when the linked report merely writes unchanged master fields.
                delta = {k: v for k, v in values.items() if k != 'partner_ids'
                         and (event[k].id if event._fields[k].type == 'many2one' else event[k]) != v}
                if set(event.partner_ids.ids) != set(partners.ids):
                    delta['partner_ids'] = values['partner_ids']
                if delta:
                    event.write(delta)
            else:
                event = events.create({**values, 'nolte_service_task_id': task.id})
            if task.nolte_calendar_event_id.id != event.id:
                task.sudo().write({'nolte_calendar_event_id': event.id})

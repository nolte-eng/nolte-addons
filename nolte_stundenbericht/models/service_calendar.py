from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from markupsafe import Markup

from odoo import _, api, fields, models, Command
from odoo.fields import Domain
from odoo.exceptions import AccessError, UserError, ValidationError


class ServiceCalendarEvent(models.Model):
    _inherit = 'calendar.event'

    nolte_service_task_id = fields.Many2one(
        'project.task', string='Serviceeinsatz', readonly=True, copy=False,
        index=True, ondelete='set null', groups='nolte_stundenbericht.group_stundenbericht_user')
    nolte_service_technician_ids = fields.Many2many(
        related='nolte_service_task_id.user_ids', readonly=False, compute_sudo=False,
        string='Servicetechniker', domain="[('share', '=', False), ('active', '=', True)]",
        groups='nolte_stundenbericht.group_stundenbericht_user')

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
        if self.env.su and self.env.context.get('nolte_calendar_sync'):
            return super().write(values)
        watched = {'start', 'stop', 'start_date', 'stop_date', 'allday',
                   'nolte_service_technician_ids', 'active'}
        if not watched.intersection(values):
            return super().write(values)
        self.check_access('write')
        # Lock tasks before events, matching the planning-to-calendar direction.
        tasks = self.env['project.task'].browse(self.sudo().nolte_service_task_id.ids)
        tasks.check_access('write')
        for task in tasks.sorted('id'):
            task._nolte_lock_shared_data()
        with self.env.cr.savepoint():
            for event in self:
                target = event
                if event.sudo().nolte_service_task_id:
                    target = event.with_context(no_mail_to_attendees=True, skip_attendee_notification=True,
                                                dont_notify=True, tracking_disable=True)
                event_values = dict(values)
                if event.sudo().nolte_service_task_id:
                    event_values.pop('nolte_service_technician_ids', None)
                elif 'nolte_service_technician_ids' in values:
                    raise ValidationError(_('Servicetechniker können nur einem verknüpften Einsatz zugeordnet werden.'))
                super(ServiceCalendarEvent, target).write(event_values)
            for event in self:
                task = self.env['project.task'].browse(event.sudo().nolte_service_task_id.id)
                if not task:
                    continue
                if not event.allday:
                    raise UserError(_('Einsatztermine werden ganztägig geplant. Bitte Beginn und Ende als Datum angeben.'))
                update = {}
                if {'start', 'stop', 'start_date', 'stop_date', 'allday'}.intersection(values):
                    update.update(nolte_service_date_start=event.start_date, nolte_service_date_end=event.stop_date)
                if 'nolte_service_technician_ids' in values:
                    update['user_ids'] = values['nolte_service_technician_ids']
                if 'active' in values:
                    update['active'] = event.active
                if update:
                    task.with_context(mail_auto_subscribe_no_notify=True).write(update)
                    if 'nolte_service_technician_ids' in values:
                        company = task.company_id or self.env.company
                        if any(user.share or not user.active or company not in user.company_ids for user in task.user_ids):
                            raise ValidationError(_('Bitte aktive interne Servicetechniker des Einsatzunternehmens auswählen.'))
            return True

    def unlink(self):
        if self.sudo().nolte_service_task_id:
            raise UserError(_('Bitte den Einsatz in der Planung archivieren. Dadurch wird auch sein Kalendertermin ausgeblendet.'))
        return super().unlink()


class ServiceTaskCalendar(models.Model):
    _inherit = 'project.task'

    nolte_service_date_start_value = fields.Date(copy=True)
    nolte_service_date_start = fields.Date(
        string='Einsatzbeginn', compute='_compute_nolte_service_date_start',
        inverse='_inverse_nolte_service_date_start', search='_search_nolte_service_date_start',
        help='Ohne Beginn gilt das Einsatzende als einzelner Einsatztag.')
    nolte_service_date_end = fields.Date(
        string='Einsatzende', compute='_compute_nolte_service_date_end', inverse='_inverse_nolte_service_date_end')
    nolte_calendar_event_id = fields.Many2one('calendar.event', string='Kalendertermin', readonly=True, copy=False)

    @api.depends(lambda self: ['planned_date_begin', 'company_id.resource_calendar_id.tz']
                 if 'planned_date_begin' in self._fields else ['nolte_service_date_start_value'])
    def _compute_nolte_service_date_start(self):
        for task in self:
            task.nolte_service_date_start = (
                task._nolte_planning_date(task.planned_date_begin)
                if 'planned_date_begin' in task._fields else task.nolte_service_date_start_value
            )

    @api.model
    def _search_nolte_service_date_start(self, operator, value):
        if 'planned_date_begin' not in self._fields:
            return [('nolte_service_date_start_value', operator, value)]
        if operator in ('in', 'not in'):
            matches = Domain.OR([Domain(self._search_nolte_service_date_start('=', item)) for item in value])
            return matches if operator == 'in' else ~matches
        if not value:
            return [('planned_date_begin', operator, value)]
        day = fields.Date.to_date(value)
        company_domains = []
        for company in self.env.companies:
            timezone = ZoneInfo(company.resource_calendar_id.tz or 'UTC')
            start = datetime.combine(day, time(), tzinfo=timezone).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            stop = datetime.combine(day + timedelta(days=1), time(), tzinfo=timezone).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            matches = Domain('planned_date_begin', '>=', start) & Domain('planned_date_begin', '<', stop)
            if operator == '!=':
                matches = ~matches
            elif operator != '=':
                boundary_operator, boundary = {
                    '>': ('>=', stop), '>=': ('>=', start),
                    '<': ('<', start), '<=': ('<', stop),
                }[operator]
                matches = Domain('planned_date_begin', boundary_operator, boundary)
            company_domain = Domain('company_id', '=', company.id)
            if company == self.env.company:
                company_domain |= Domain('company_id', '=', False)
            company_domains.append(company_domain & matches)
        return Domain.OR(company_domains)

    def _inverse_nolte_service_date_start(self):
        for task in self:
            task.write(task._nolte_calendar_values({'nolte_service_date_start': task.nolte_service_date_start}))

    @api.depends('date_deadline', 'company_id.resource_calendar_id.tz')
    def _compute_nolte_service_date_end(self):
        for task in self:
            task.nolte_service_date_end = task._nolte_planning_date(task.date_deadline)

    def _inverse_nolte_service_date_end(self):
        for task in self:
            task.write(task._nolte_calendar_values({'nolte_service_date_end': task.nolte_service_date_end}))

    def _nolte_planning_date(self, value):
        if not value or 'planned_date_begin' not in self._fields:
            return fields.Date.to_date(value)
        company = self.company_id or self.env.company
        timezone = company.resource_calendar_id.tz or 'UTC'
        return fields.Datetime.context_timestamp(
            self.with_context(tz=timezone), fields.Datetime.to_datetime(value)
        ).date()

    def _nolte_period_start(self):
        self.ensure_one()
        return self.nolte_service_date_start or self._nolte_planning_date(self.date_deadline)

    @api.constrains('nolte_service_date_start_value', 'date_deadline')
    def _check_nolte_service_period(self):
        for task in self.filtered('nolte_service_planning'):
            end = task._nolte_planning_date(task.date_deadline)
            if task.nolte_service_date_start and end and end < task.nolte_service_date_start:
                raise ValidationError(_('Das Einsatzende darf nicht vor dem Einsatzbeginn liegen.'))

    def _nolte_calendar_values(self, values):
        values = dict(values)
        service_dates_changed = {'nolte_service_date_start', 'nolte_service_date_end'}.intersection(values)
        enterprise = 'planned_date_begin' in self._fields
        deadline = values.get('date_deadline')
        date_only = (isinstance(deadline, date) and not isinstance(deadline, datetime)) or (
            isinstance(deadline, str) and len(deadline) == 10
        )
        if enterprise and service_dates_changed and date_only and 'nolte_service_date_end' not in values:
            values['nolte_service_date_end'] = values.pop('date_deadline')
        company = self.env['res.company'].browse(values.get('company_id')) if values.get('company_id') else self.company_id
        company = company or self.env.company
        timezone = ZoneInfo(company.resource_calendar_id.tz or 'UTC')
        for alias, target, hour in (
            ('nolte_service_date_start', 'planned_date_begin' if enterprise else 'nolte_service_date_start_value', 8),
            ('nolte_service_date_end', 'date_deadline', 18),
        ):
            if alias not in values:
                continue
            day = fields.Date.to_date(values.pop(alias))
            if not enterprise or not day:
                converted = day or False
            else:
                previous = self[target] if self else False
                clock = (fields.Datetime.to_datetime(previous).replace(tzinfo=ZoneInfo('UTC'))
                         .astimezone(timezone).time()) if previous else time(hour)
                converted = datetime.combine(day, clock, tzinfo=timezone).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            if target in values and fields.Datetime.to_datetime(values[target]) != fields.Datetime.to_datetime(converted):
                raise ValidationError(_('Die Einsatzdaten und die Planungsdaten widersprechen sich.'))
            values[target] = converted
        if enterprise and service_dates_changed:
            project = self.env['project.project'].browse(values.get('project_id')) if values.get('project_id') else self.project_id
            if 'is_fsm' in project._fields and project.is_fsm:
                start = values.get('planned_date_begin', self.planned_date_begin if self else False)
                end = values.get('date_deadline', self.date_deadline if self else False)
                # Native Field Service requires a complete interval. The old
                # one-date service input represents a single-day appointment.
                if bool(start) != bool(end):
                    timestamp = fields.Datetime.to_datetime(start or end).replace(tzinfo=ZoneInfo('UTC'))
                    day = timestamp.astimezone(timezone).date()
                    missing = 'date_deadline' if start else 'planned_date_begin'
                    clock = time(18) if start else time(8)
                    values[missing] = datetime.combine(day, clock, tzinfo=timezone).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        return values

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create([self._nolte_calendar_values(v) for v in vals_list])
        if not self.env.context.get('install_mode'):
            records._sync_nolte_calendar()
        return records

    def write(self, values):
        watched = {'nolte_service_date_start_value', 'planned_date_begin', 'date_deadline', 'user_ids', 'name', 'partner_id',
                   'nolte_service_location', 'nolte_service_location_name', 'active', 'state', 'project_id'}
        with self.env.cr.savepoint():
            for task in self.sorted('id'):
                update = task._nolte_calendar_values(values)
                # Moving the deadline of a one-day appointment moves the
                # whole appointment; explicit multi-day starts stay fixed.
                if ('planned_date_begin' not in task._fields and 'date_deadline' in update
                        and 'nolte_service_date_start_value' not in update
                        and task.nolte_service_date_start
                        and task.nolte_service_date_start == fields.Date.to_date(task.date_deadline)):
                    update['nolte_service_date_start_value'] = fields.Date.to_date(update['date_deadline'])
                super(ServiceTaskCalendar, task).write(update)
                if not self.env.context.get('install_mode') and watched.intersection(update):
                    task._sync_nolte_calendar()
        return True

    def _sync_nolte_calendar(self):
        """One internally visible all-day event per authorized service task."""
        self.check_access('read')
        events = self.env['calendar.event'].sudo().with_context(
            active_test=False, no_mail_to_attendees=True, skip_attendee_notification=True,
            dont_notify=True, tracking_disable=True, mail_create_nosubscribe=True,
            skip_contact_description=True, nolte_calendar_sync=True)
        for task in self.sorted('id'):
            # Serializes creation, date edits and assignment updates for this task.
            task._nolte_lock_shared_data()
            task.invalidate_recordset(
                ['date_deadline', 'nolte_service_date_start', 'nolte_service_date_start_value', 'user_ids', 'active', 'state']
                + (['planned_date_begin'] if 'planned_date_begin' in task._fields else [])
            )
            event = events.search([('nolte_service_task_id', '=', task.id)], limit=1)
            start = task._nolte_period_start()
            valid = task.nolte_service_planning and task.active and task.state != '1_canceled' and start
            if not valid:
                if event and event.active:
                    event.write({'active': False})
                continue
            end = task._nolte_planning_date(task.date_deadline) or start
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
                'privacy': 'confidential', 'show_as': 'busy', 'active': True,
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
                # All-day dates are canonical in Odoo. Avoid rewriting equivalent
                # clock times and resetting an organizer's attendee response.
                if event.allday and event.start_date == start and event.stop_date == end:
                    delta.pop('start', None)
                    delta.pop('stop', None)
                if delta:
                    event.write(delta)
            else:
                event = events.create({**values, 'nolte_service_task_id': task.id})
            if task.nolte_calendar_event_id.id != event.id:
                task.sudo().write({'nolte_calendar_event_id': event.id})

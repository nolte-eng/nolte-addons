"""Shared service master data for both intake paths; signed evidence is separate."""
from odoo import _, api, models, fields, Command
from odoo.exceptions import AccessError, UserError


SHARED = {
    'partner_id': 'partner_id',
    'service_location': 'nolte_service_location',
    'service_location_name': 'nolte_service_location_name',
    'service_location_contact_name': 'nolte_service_location_contact_name',
    'service_location_contact_phone': 'nolte_service_location_contact_phone',
    'machine_number': 'nolte_machine_number',
    'machine_type': 'nolte_machine_type',
}


def value(record, name):
    result = record._nolte_customer() if name == 'partner_id' and record._name == 'project.task' else record[name]
    return result.id if name == 'partner_id' else (result or False)


def editable(report):
    return (report.state in ('draft', 'returned') and not report.customer_snapshot_payload
            and not report.customer_pdf_attachment_id and not report.customer_signature
            and not report.is_closed)


def changes(source, before, target, mapping):
    """Propagate an explicit edit only if the other side still agrees or is empty."""
    result = {}
    for source_name, target_name in mapping.items():
        new, old, existing = value(source, source_name), before[source_name], value(target, target_name)
        if existing == new or (not new and new == old):
            continue
        if existing and existing != old:
            raise UserError(_(
                'Abweichende Einsatz-Stammdaten bei „%(record)s“: %(field)s. '
                'Bitte den gewünschten Wert ausdrücklich in der Planung oder im Stundenbericht übernehmen; '
                'die vorhandenen Angaben wurden nicht überschrieben.'
            ) % {'record': target.display_name, 'field': target._fields[target_name].string})
        result[target_name] = new
    return result


class ServiceTask(models.Model):
    _inherit = 'project.task'

    def _nolte_lock_shared_data(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM project_task WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(list(SHARED.values()) + (['x_customer_id'] if 'x_customer_id' in self._fields else []))

    def _nolte_customer(self):
        if not self:
            return self.env['res.partner']
        self.ensure_one()
        return self.partner_id or (self.x_customer_id if 'x_customer_id' in self._fields else self.env['res.partner'])

    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and arch.xpath('//field[@name="nolte_service_planning"]'):
            for node in arch.xpath('//field[@name="partner_id" and contains(@class, "nolte_service_customer")]'):
                node.set('invisible', 'not nolte_service_planning')
            for node in arch.xpath('//field[@name="partner_id" and not(ancestor::field) and not(ancestor::page) and not(contains(@class, "nolte_service_customer"))]'):
                original = node.get('invisible')
                node.set('invisible', '(%s) or nolte_service_planning' % original if original else 'nolte_service_planning')
            for node in arch.xpath('//field[@name="x_customer_id"]'):
                original = node.get('invisible')
                node.set('invisible', '(%s) or nolte_service_planning' % original if original else 'nolte_service_planning')
        return arch, view

    def _nolte_normalize_customer_values(self, values):
        result = dict(values)
        if 'x_customer_id' in self._fields and {'partner_id', 'x_customer_id'}.intersection(result):
            if ('partner_id' in result and 'x_customer_id' in result
                    and (result['partner_id'] or False) != (result['x_customer_id'] or False)):
                raise UserError(_('Die beiden Kundenfelder enthalten unterschiedliche Kunden. Bitte einen einheitlichen Kunden auswählen.'))
            customer = result.get('partner_id') if 'partner_id' in result else result['x_customer_id']
            result.update(partner_id=customer or False, x_customer_id=customer or False)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            project = self.env['project.project'].browse(values.get('project_id') or self.env.context.get('default_project_id'))
            prepared.append(self._nolte_normalize_customer_values(values) if project.with_context(lang=None).name == 'Aussendienst' else values)
        records = super().create(prepared)
        for task in records.filtered('nolte_service_planning'):
            customer = task._nolte_customer()
            if 'x_customer_id' in task._fields and customer and (task.partner_id != customer or task.x_customer_id != customer):
                task.write({'partner_id': customer.id})
        if not self.env.context.get('install_mode') and not self.env.context.get('nolte_skip_report_preparation'):
            for task in records.filtered('nolte_service_planning'):
                task._nolte_ensure_planning_report()
        return records

    def _nolte_ensure_planning_report(self):
        """Prepare exactly one report after a native service task was created."""
        self.ensure_one()
        self.check_access('read')
        reports = self.env['nolte.service.report'].sudo()
        if not self.nolte_service_planning:
            return reports.browse()
        self._nolte_lock_shared_data()
        company = self.company_id or self.env.company
        existing = reports.search([('task_id', '=', self.id), ('company_id', '=', company.id)], limit=1)
        if existing:
            return existing
        if self._nolte_closed_for_mobile():
            return reports.browse()
        group = self.env.ref('nolte_stundenbericht.group_stundenbericht_user')
        employees = self.env['hr.employee'].sudo().search([
            ('user_id', 'in', self.user_ids.ids), ('active', '=', True),
            ('user_id.group_ids', 'in', group.id), ('company_id', '=', company.id),
        ], order='name, id')
        owner = employees.filtered(lambda employee: employee.user_id == self.env.user)[:1] or employees[:1]
        service_date = self._nolte_period_start() or fields.Date.context_today(self)
        template = self.env['nolte.service.checklist.template'].sudo().with_company(company)._default_for_current_company()
        report = reports.with_context(tracking_disable=True, mail_create_nosubscribe=True,
            mail_auto_subscribe_no_notify=True).create({
            'task_id': self.id, 'company_id': company.id,
            'owner_user_id': owner.user_id.id if owner else self.create_uid.id,
            'service_date': service_date, 'planning_draft': True,
            'partner_id': self._nolte_customer().id or False,
            **{r: value(self, t) for r, t in SHARED.items() if r != 'partner_id'},
            'employee_assignment_ids': [Command.create({'employee_id': e.id}) for e in employees],
            'member_ids': [Command.create({'employee_id': e.id, 'service_date': service_date}) for e in employees],
            'checklist_ids': [Command.create({'name': line.name, 'note': line.note or False,
                'visibility': 'customer', 'checked': False, 'sequence': line.sequence}) for line in template.line_ids],
        })
        self._sync_nolte_planning_drafts()
        return report

    def write(self, values):
        if self.env.context.get('install_mode') or self.env.context.get('nolte_shared_sync'):
            return super().write(values)
        if not set(values).intersection(set(SHARED.values()) | {'x_customer_id'}):
            return super().write(values)
        self.check_access('write')
        with self.env.cr.savepoint():
            for task in self.sorted('id'):
                if not task.nolte_service_planning:
                    super(ServiceTask, task).write(values)
                    continue
                task._nolte_lock_shared_data()
                before = {name: value(task, name) for name in SHARED.values()}
                update = task._nolte_normalize_customer_values(values)
                super(ServiceTask, task).write(update)
                # Native task write access was checked above. Only its open,
                # same-company report master fields may be propagated.
                reports = self.env['nolte.service.report'].sudo().search([
                    ('task_id', '=', task.id), ('company_id', '=', task.company_id.id or self.env.company.id),
                    ('state', 'in', ['draft', 'returned']),
                ])
                for report in reports:
                    report._lock_customer_confirmation()
                    if editable(report):
                        delta = changes(task, before, report, {t: r for r, t in SHARED.items()})
                        if delta:
                            report.with_context(nolte_shared_sync=True, tracking_disable=True, mail_auto_subscribe_no_notify=True).write({**delta, 'server_revision': report.server_revision + 1})
        return True


class ServiceReport(models.Model):
    _inherit = 'nolte.service.report'

    def _nolte_task_for_shared_data(self):
        self.ensure_one()
        task = self.task_id
        if not task or not task.nolte_service_planning:
            return self.env['project.task']
        task.check_access('read')
        if (not self.env.su and task.user_ids and self.env.user not in task.user_ids
                and not self.env.user.has_group('nolte_stundenbericht.group_stundenbericht_approver')):
            raise AccessError(_('Sie dürfen nur die Stammdaten eines Ihnen zugewiesenen Serviceeinsatzes ergänzen.'))
        if task.company_id and task.company_id != self.company_id:
            raise AccessError(_('Einsatzauftrag und Stundenbericht gehören zu unterschiedlichen Unternehmen.'))
        return task

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('install_mode') or self.env.context.get('nolte_shared_sync'):
            return super().create(vals_list)
        with self.env.cr.savepoint():
            records = super().create(vals_list)
            for report in records:
                report._nolte_sync_shared_data({name: False for name in SHARED})
        return records

    def write(self, values):
        if self.env.context.get('install_mode') or self.env.context.get('nolte_shared_sync') or not (set(SHARED) | {'task_id'}).intersection(values):
            return super().write(values)
        self.check_access('write')
        with self.env.cr.savepoint():
            for report in self.sorted('id'):
                task = report._nolte_task_for_shared_data()
                if task:
                    task._nolte_lock_shared_data()
                before = {name: value(report, name) for name in SHARED}
                if 'task_id' in values and values['task_id'] != report.task_id.id:
                    before = {name: False for name in SHARED}
                update = dict(values)
                if 'server_revision' not in update and any(name in update and (update[name] or False) != before[name] for name in SHARED):
                    update['server_revision'] = report.server_revision + 1
                super(ServiceReport, report).write(update)
                report._nolte_sync_shared_data(before)
        return True

    def _nolte_sync_shared_data(self, before):
        if not editable(self):
            return
        task = self._nolte_task_for_shared_data()
        if not task:
            return
        task._nolte_lock_shared_data()
        # Empty report fields inherit planning defaults. A report-specific
        # nonempty edit goes the other direction, subject to conflict checks.
        missing = {r: (task._nolte_customer().id if r == 'partner_id' else value(task, t))
                   for r, t in SHARED.items() if not value(self, r) and value(task, t)}
        if missing:
            self.with_context(nolte_shared_sync=True).write(missing)
        delta = changes(self, before, task, SHARED)
        customer = self.partner_id
        if 'x_customer_id' in task._fields and customer and task.x_customer_id != customer:
            if task.x_customer_id and task.x_customer_id.id not in (before['partner_id'], customer.id):
                raise UserError(_('Planung und Stundenbericht enthalten unterschiedliche Kunden. Bitte die Kundenzuordnung prüfen.'))
            delta['x_customer_id'] = customer.id
        if delta:
            # Authorized owner may complete only the master fields of this
            # linked service task. No assignments, stages, rights or times.
            task.sudo().with_context(tracking_disable=True, mail_auto_subscribe_no_notify=True).write(delta)

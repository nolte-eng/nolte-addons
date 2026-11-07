from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import ast
from lxml import etree

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from ..controllers import api_v1


@tagged("post_install", "-at_install")
class TestManualTask(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tech = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Manual task technician", "login": "test_manual_task_tech",
            "group_ids": [Command.set([self.env.ref("base.group_user").id,
                self.env.ref("nolte_stundenbericht.group_stundenbericht_user").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)],
        })
        self.employee = self.env["hr.employee"].create({"name": self.tech.name, "user_id": self.tech.id})
        self.project = self.env["project.project"].search([
            ("name", "=", "Aussendienst"), ("company_id", "=", self.env.company.id),
        ], order="sequence, id", limit=1) or self.env["project.project"].create({
            "name": "Aussendienst", "company_id": self.env.company.id,
        })
        for sequence, name in enumerate(("Ungeplant", "Einsatz geplant")):
            if not self.env["project.task.type"].search([("name", "=", name), ("project_ids", "in", self.project.id)], limit=1):
                self.env["project.task.type"].create({"name": name, "sequence": sequence,
                    "project_ids": [Command.link(self.project.id)]})
        self.payload = {"mobileUuid": str(uuid4()), "mobileRevision": 1,
            "serviceDate": fields.Date.to_string(fields.Date.today()),
            "employeeId": self.employee.id, "manualCustomerName": "Manual task customer",
            "manualCustomerStreet": "Teststrasse 1", "manualContactName": "Test contact",
            "machineNumber": "129", "machineType": "Test machine", "workDescription": "Inspection <test>"}
        self.api = api_v1.NolteStundenberichtApiV1()

    def upsert(self, payload):
        with patch.object(api_v1, "request", SimpleNamespace(env=self.env["nolte.service.report"].with_user(self.tech).env)):
            return self.api.upsert_report(payload)

    def _shared_task(self, **values):
        return self.env['project.task'].with_context(nolte_skip_report_preparation=True).create({
            'name': 'Shared service data', 'project_id': self.project.id,
            'user_ids': [Command.set(self.tech.ids)], **values})

    def _shared_report(self, task, **values):
        return self.env['nolte.service.report'].create({
            'name': 'SYNC-TEST', 'task_id': task.id, 'owner_user_id': self.tech.id,
            'member_ids': [Command.create({'employee_id': self.employee.id, 'service_date': fields.Date.today()})],
            **values})

    def test_project_creation_uses_canonical_customer_and_legacy_alias(self):
        customer = self.env['res.partner'].create({'name': 'Canonical customer'})
        vals = {'x_customer_id': customer.id} if 'x_customer_id' in self.env['project.task']._fields else {'partner_id': customer.id}
        task = self._shared_task(**vals, nolte_service_location='Site 1', nolte_machine_number='M-1')
        self.assertEqual(task.partner_id, customer)
        report = self._shared_report(task)
        self.assertEqual(report.partner_id, customer)
        self.assertEqual(report.service_location, 'Site 1')
        self.assertEqual(report.machine_number, 'M-1')
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            assignment = next(item for item in self.api.bootstrap()['assignments'] if item['id'] == task.id)
            self.assertEqual(assignment['customerId'], customer.id)
            self.assertEqual(assignment['customerName'], customer.display_name)
            self.assertEqual(self.api.load_report(report.id)['taskDefaults']['customerId'], customer.id)
        if 'x_customer_id' in task._fields:
            self.assertEqual(task.x_customer_id, customer)
            task.write({'x_customer_id': False})
            self.assertFalse(task.partner_id)
            self.assertFalse(report.partner_id)

    def test_report_completion_updates_planning_and_reloads_with_technician_rights(self):
        customer = self.env['res.partner'].create({'name': 'Completed customer'})
        task = self._shared_task()
        report = self._shared_report(task)
        previous_revision = report.server_revision
        report.with_user(self.tech).write({'partner_id': customer.id, 'service_location': 'Factory street 3',
            'service_location_contact_name': 'Site contact', 'machine_type': 'Machine type'})
        self.assertEqual(task.partner_id, customer)
        if 'x_customer_id' in task._fields:
            self.assertEqual(task.x_customer_id, customer)
        self.assertEqual(task.nolte_service_location, 'Factory street 3')
        self.assertEqual(task.nolte_service_location_contact_name, 'Site contact')
        self.assertGreater(report.server_revision, previous_revision)
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            loaded = self.api.load_report(report.id)
            self.assertEqual(loaded['partnerId'], customer.id)
            self.assertEqual(loaded['taskDefaults']['customerName'], customer.display_name)
            self.assertEqual(loaded['taskDefaults']['serviceLocation'], 'Factory street 3')
        replacement = self.env['res.partner'].create({'name': 'Explicitly corrected customer'})
        report.with_user(self.tech).write({'partner_id': replacement.id})
        self.assertEqual(task.partner_id, replacement)
        if 'x_customer_id' in task._fields:
            self.assertEqual(task.x_customer_id, replacement)

    def test_planning_edits_update_drafts_but_preserve_confirmed_and_pending_evidence(self):
        customer = self.env['res.partner'].create({'name': 'Shared customer'})
        task = self._shared_task(partner_id=customer.id, nolte_machine_number='Old machine')
        draft = self._shared_report(task)
        signed = self._shared_report(task, state='customer_confirmed', customer_snapshot_payload='{"frozen":true}', machine_number='Signed machine')
        pending = self._shared_report(task)
        pending.with_context(nolte_shared_sync=True).write({'state': 'awaiting_signature', 'customer_snapshot_payload': '{"pending":true}', 'machine_number': 'Pending machine'})
        previous_revision = draft.server_revision
        task.write({'nolte_machine_number': 'New machine', 'nolte_service_location': 'New site'})
        self.assertEqual(draft.machine_number, 'New machine')
        self.assertEqual(draft.service_location, 'New site')
        self.assertGreater(draft.server_revision, previous_revision)
        self.assertEqual(signed.machine_number, 'Signed machine')
        self.assertEqual(signed.customer_snapshot_payload, '{"frozen":true}')
        self.assertEqual(pending.machine_number, 'Pending machine')
        self.assertEqual(pending.customer_snapshot_payload, '{"pending":true}')

    def test_conflicting_master_data_is_reported_and_changes_are_rolled_back(self):
        from odoo.exceptions import UserError
        customer_a = self.env['res.partner'].create({'name': 'Customer A'})
        customer_b = self.env['res.partner'].create({'name': 'Customer B'})
        task = self._shared_task(partner_id=customer_a.id)
        report = self._shared_report(task)
        # Simulate an older divergent record without invoking new synchronization.
        report.with_context(nolte_shared_sync=True).write({'partner_id': customer_b.id})
        with self.assertRaises(UserError):
            task.write({'partner_id': False, 'nolte_machine_number': 'Must roll back'})
        self.assertEqual(task.partner_id, customer_a)
        self.assertFalse(task.nolte_machine_number)
        self.assertEqual(report.partner_id, customer_b)
        # Explicitly choose the already present report customer in planning.
        task.write({'partner_id': customer_b.id})
        self.assertEqual(task.partner_id, report.partner_id)
        if 'x_customer_id' in task._fields:
            with self.assertRaises(UserError):
                task.write({'partner_id': customer_a.id, 'x_customer_id': customer_b.id})

    def test_mobile_load_prefers_saved_report_over_legacy_planning_defaults(self):
        customer = self.env['res.partner'].create({'name': 'Stored report customer'})
        task = self._shared_task()
        report = self._shared_report(task)
        report.with_context(nolte_shared_sync=True).write({'partner_id': customer.id,
            'service_location': 'Saved site', 'machine_number': 'Saved number'})
        task.with_context(nolte_shared_sync=True).write({'nolte_service_location': 'Older planning value'})
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            loaded = self.api.load_report(report.id)
            self.assertEqual(loaded['taskDefaults']['customerId'], customer.id)
            self.assertEqual(loaded['taskDefaults']['serviceLocation'], 'Saved site')
            self.assertEqual(loaded['taskDefaults']['machineNumber'], 'Saved number')
        result = self.upsert(dict(self.payload, mobileUuid=report.mobile_uuid, mobileRevision=1,
            taskId=task.id, serverRevision=report.server_revision, machineNumber='Saved number',
            serviceLocation='Saved site', machineType=False))
        self.assertEqual(self.env['nolte.service.report'].browse(result['id']).partner_id, customer)

    def test_older_device_revision_cannot_erase_a_backend_customer_correction(self):
        from odoo.exceptions import UserError
        task = self._shared_task()
        report = self._shared_report(task)
        old_revision = report.server_revision
        customer = self.env['res.partner'].create({'name': 'Backend correction'})
        report.write({'partner_id': customer.id})
        with self.assertRaises(UserError):
            self.upsert(dict(self.payload, mobileUuid=report.mobile_uuid, mobileRevision=1,
                taskId=task.id, serverRevision=old_revision))
        self.assertEqual(report.partner_id, customer)
        self.assertEqual(task.partner_id, customer)

    def test_shared_data_does_not_grant_other_task_or_report_access(self):
        from odoo.exceptions import AccessError
        other = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Other service owner', 'login': 'test_sync_other_owner',
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                self.env.ref('nolte_stundenbericht.group_stundenbericht_user').id])]})
        task = self._shared_task(user_ids=[Command.set(other.ids)])
        report = self._shared_report(task)
        with self.assertRaises(AccessError):
            report.with_user(self.tech).write({'service_location': 'Not authorized'})
        self.assertFalse(task.nolte_service_location)
        self.assertFalse(report.service_location)
        own_task = self._shared_task()
        foreign_report = self._shared_report(own_task, owner_user_id=other.id)
        with self.assertRaises(AccessError):
            foreign_report.with_user(self.tech).write({'service_location': 'Not authorized'})
        self.assertFalse(own_task.nolte_service_location)

    def test_service_form_uses_standard_customer_and_hides_legacy_alias(self):
        form = self.env['project.task'].with_user(self.tech).get_view(view_type='form')
        root = etree.fromstring(form['arch'])
        canonical = root.xpath('//field[@name="partner_id" and @invisible="not nolte_service_planning"]')
        self.assertTrue(canonical)
        for legacy in root.xpath('//field[@name="x_customer_id"]'):
            self.assertIn('nolte_service_planning', legacy.get('invisible', ''))

    def test_native_project_creation_prepares_visible_report_and_reuses_it(self):
        customer = self.env['res.partner'].create({'name': 'Native project customer'})
        task = self.env['project.task'].create({
            'name': 'Maschinenstillstand test', 'project_id': self.project.id,
            'partner_id': customer.id, 'user_ids': [Command.set(self.tech.ids)],
            'nolte_machine_number': '22360024', 'nolte_service_location': 'Site street 1',
            'description': '<p>Technician instructions</p>'})
        reports = self.env['nolte.service.report'].search([('task_id', '=', task.id)])
        self.assertEqual(len(reports), 1)
        self.assertTrue(reports.planning_draft)
        self.assertFalse(reports.is_closed)
        self.assertEqual(reports.owner_user_id, self.tech)
        self.assertEqual(reports.partner_id, customer)
        self.assertEqual(reports.machine_number, '22360024')
        self.assertEqual(reports.service_location, 'Site street 1')
        self.assertEqual(reports.member_ids.employee_id, self.employee)
        self.assertFalse(reports.member_ids.segment_ids)
        self.assertFalse(reports.work_description)
        self.assertFalse(reports.display_service_date)
        self.assertEqual(task._nolte_ensure_planning_report().id, reports.id)
        self.assertEqual(self.env['nolte.service.report'].search_count([('task_id', '=', task.id)]), 1)
        with patch.object(api_v1, 'request', SimpleNamespace(env=reports.with_user(self.tech).env)):
            self.assertIn(reports.id, [r['id'] for r in self.api.recent_reports()])
            self.assertEqual(self.api.claim_task(task.id)['reportId'], reports.id)
            loaded = self.api.load_report(reports.id)
            self.assertEqual(loaded['partnerId'], customer.id)
            for key in ('contactName', 'contactPhone', 'contactEmail'):
                self.assertEqual(loaded['taskDefaults'][key], '')
            self.assertEqual(loaded['taskDefaults']['workOrderDescription'], 'Technician instructions')
        backend = self.env.ref('nolte_stundenbericht.action_nolte_service_report')
        import ast
        self.assertIn(reports, self.env['nolte.service.report'].with_user(self.tech).search(ast.literal_eval(backend.domain)))

    def test_native_dated_unassigned_task_can_be_claimed_without_duplicate_report(self):
        task = self.env['project.task'].create({'name': 'Native unassigned dated task',
            'project_id': self.project.id, 'date_deadline': '2026-11-12', 'user_ids': [Command.clear()]})
        report = self.env['nolte.service.report'].search([('task_id', '=', task.id)])
        self.assertEqual(len(report), 1)
        self.assertEqual(fields.Date.to_string(report.display_service_date), '2026-11-12')
        self.assertEqual(task.stage_id.name, 'Einsatz geplant')
        self.assertFalse(report.member_ids)
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            result = self.api.claim_task(task.id)
        self.assertEqual(result['reportId'], report.id)
        self.assertEqual(report.owner_user_id, self.tech)
        self.assertEqual(report.member_ids.employee_id, self.employee)
        self.assertEqual(self.env['nolte.service.report'].search_count([('task_id', '=', task.id)]), 1)
        internal_project = self.env['project.project'].create({'name': 'Not a service project'})
        internal = self.env['project.task'].create({'name': 'Internal task', 'project_id': internal_project.id})
        self.assertFalse(self.env['nolte.service.report'].search([('task_id', '=', internal.id)]))

    def test_service_period_calendar_updates_without_duplicates_or_email_invitations(self):
        from odoo.exceptions import ValidationError
        customer = self.env['res.partner'].create({'name': 'Calendar customer', 'email': 'customer@calendar.example.invalid'})
        wizard = self.env['nolte.service.intake.wizard'].with_context(mail_auto_subscribe_no_notify=True).create({
            'name': 'Calendar multi-day service', 'project_id': self.project.id, 'partner_id': customer.id,
            'planned_date': '2026-11-10', 'planned_end_date': '2026-11-12',
            'technician_ids': [Command.set(self.employee.ids)], 'service_location': 'Factory Street 4'})
        before_mails = self.env['mail.mail'].search_count([])
        with patch.object(type(self.env['mail.mail']), 'send', side_effect=AssertionError('Calendar must not send mail')):
            report = self.env['nolte.service.report'].browse(wizard.action_create_service_task()['res_id'])
        task = report.task_id
        event = task.nolte_calendar_event_id
        self.assertTrue(event)
        self.assertTrue(event.allday)
        self.assertEqual(fields.Date.to_string(event.start_date), '2026-11-10')
        self.assertEqual(fields.Date.to_string(event.stop_date), '2026-11-12')
        self.assertIn(self.tech.partner_id, event.partner_ids)
        self.assertNotIn(customer, event.partner_ids)
        self.assertEqual(event.privacy, 'private')
        self.assertEqual(event.location, 'Factory Street 4')
        self.assertIn(customer.name, event.name)
        self.assertEqual(fields.Date.to_string(report.service_date), '2026-11-10')
        self.assertEqual(self.env['mail.mail'].search_count([]), before_mails)
        # Normal technician calendar access works without HR/admin privileges.
        event.with_user(self.tech).read(['name', 'start', 'stop', 'allday'])
        report.write({'state': 'customer_confirmed', 'customer_snapshot_payload': '{"frozen":true}'})
        with patch.object(type(self.env['mail.mail']), 'send', side_effect=AssertionError('Calendar must not send mail')):
            task.write({'nolte_service_date_start': '2026-11-15', 'nolte_service_date_end': '2026-11-17'})
        self.assertEqual(task.nolte_calendar_event_id.id, event.id)
        self.assertEqual(fields.Date.to_string(event.start_date), '2026-11-15')
        self.assertEqual(fields.Date.to_string(event.stop_date), '2026-11-17')
        self.assertEqual(report.customer_snapshot_payload, '{"frozen":true}')
        self.assertEqual(fields.Date.to_string(report.service_date), '2026-11-10')
        self.assertEqual(fields.Date.to_string(report.member_ids.service_date), '2026-11-10')
        with self.assertRaises(ValidationError):
            task.write({'nolte_service_date_end': '2026-11-14'})
        self.assertEqual(fields.Date.to_string(event.stop_date), '2026-11-17')
        task.write({'nolte_service_date_start': False, 'date_deadline': False})
        self.assertFalse(event.active)
        task.write({'date_deadline': '2026-11-20'})
        self.assertTrue(event.active)
        self.assertEqual(task.nolte_calendar_event_id.id, event.id)
        self.assertEqual(fields.Date.to_string(event.start_date), '2026-11-20')
        self.assertEqual(fields.Date.to_string(event.stop_date), '2026-11-20')
        self.assertEqual(self.env['calendar.event'].with_context(active_test=False).search_count([('nolte_service_task_id', '=', task.id)]), 1)
        self.assertEqual(self.env['mail.mail'].search_count([]), before_mails)

    def test_calendar_no_date_assignment_changes_and_unrelated_events(self):
        from odoo.exceptions import AccessError
        task = self.env['project.task'].create({'name': 'Undated calendar service',
            'project_id': self.project.id, 'user_ids': [Command.set(self.tech.ids)]})
        self.assertFalse(task.nolte_calendar_event_id)
        unrelated = self.env['calendar.event'].with_context(no_mail_to_attendees=True).create({
            'name': 'Unrelated appointment', 'start': '2026-11-10 10:00:00', 'stop': '2026-11-10 11:00:00'})
        before = unrelated.read(['name', 'start', 'stop', 'partner_ids'])[0]
        task.write({'date_deadline': '2026-11-11'})
        event = task.nolte_calendar_event_id
        task.write({'date_deadline': '2026-11-12'})
        self.assertEqual(fields.Date.to_string(event.start_date), '2026-11-12')
        self.assertEqual(fields.Date.to_string(event.stop_date), '2026-11-12')
        other = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Second calendar technician', 'login': 'test_calendar_second_tech',
            'group_ids': [Command.set(self.tech.group_ids.ids)]})
        task.write({'user_ids': [Command.set(other.ids)]})
        self.assertIn(other.partner_id, event.partner_ids)
        self.assertNotIn(self.tech.partner_id, event.partner_ids)
        self.assertEqual(unrelated.read(['name', 'start', 'stop', 'partner_ids'])[0], before)
        with self.assertRaises(AccessError):
            unrelated.with_user(self.tech).write({'nolte_service_task_id': task.id})
        task.write({'active': False})
        self.assertFalse(event.active)
        task.write({'active': True})
        self.assertTrue(event.active)

    def test_calendar_background_update_does_not_create_meeting_activity_or_mail(self):
        task = self.env['project.task'].with_user(self.tech).sudo().with_context(
            mail_auto_subscribe_no_notify=True, nolte_skip_report_preparation=True).create({
                'name': 'Planner differs from creator', 'project_id': self.project.id,
                'user_ids': [Command.set(self.tech.ids)]})
        self.assertEqual(task.create_uid, self.tech)
        mails = self.env['mail.mail'].search_count([])
        activities = self.env['mail.activity'].search_count([])
        with patch.object(type(self.env['mail.mail']), 'send', side_effect=AssertionError('Calendar must not send mail')):
            task.with_user(self.env.ref('base.user_admin')).sudo().write({'date_deadline': '2026-11-18'})
        self.assertTrue(task.nolte_calendar_event_id)
        self.assertFalse(task.nolte_calendar_event_id.activity_ids)
        self.assertEqual(self.env['mail.mail'].search_count([]), mails)
        self.assertEqual(self.env['mail.activity'].search_count([]), activities)

    def test_manual_sync_creates_one_task_and_preserves_link_on_retry(self):
        result = self.upsert(self.payload)
        report = self.env["nolte.service.report"].browse(result["id"])
        task = report.task_id
        self.assertTrue(task)
        self.assertEqual(result["taskId"], task.id)
        self.assertEqual(task.project_id, self.project)
        self.assertEqual(task.user_ids, self.tech)
        self.assertEqual(task.nolte_machine_number, "129")
        self.assertIn("Inspection &lt;test&gt;", task.description)
        self.assertIn("Teststrasse 1", task.description)
        self.assertFalse(task.partner_id, "Free-text customers must not create contact records implicitly")
        self.upsert(dict(self.payload, mobileRevision=2, taskId=False, serverRevision=result["serverRevision"]))
        self.assertEqual(report.task_id, task)
        self.assertEqual(self.env["project.task"].search_count([("name", "=", task.name)]), 1)

    def test_blank_draft_does_not_create_task_and_existing_task_is_reused(self):
        result = self.upsert(dict(self.payload, manualCustomerName=""))
        self.assertFalse(result["taskId"])
        partner = self.env["res.partner"].create({"name": "Manual task known customer"})
        task = self.env["project.task"].with_context(nolte_skip_report_preparation=True).create({"name": "Existing service task", "project_id": self.project.id,
            "partner_id": partner.id, "user_ids": [Command.set(self.tech.ids)]})
        result = self.upsert(dict(self.payload, mobileUuid=str(uuid4()), taskId=task.id, machineNumber=False, machineType=False))
        report = self.env["nolte.service.report"].browse(result["id"])
        self.assertEqual(report.task_id, task)
        self.assertEqual(report.partner_id, partner)

    def test_known_customer_is_transferred_to_generated_task(self):
        partner = self.env["res.partner"].create({"name": "Known manual customer"})
        result = self.upsert(dict(self.payload, partnerId=partner.id, manualCustomerName=""))
        task = self.env["nolte.service.report"].browse(result["id"]).task_id
        self.assertEqual(task.partner_id, partner)
        if "x_customer_id" in task._fields:
            self.assertEqual(task.x_customer_id, partner)

    def test_company_search_and_customer_link_round_trip(self):
        company = self.env["res.partner"].create({"name": "NS Search Factory", "is_company": True,
            "street": "Search Street 1", "zip": "54321", "city": "Searchstadt", "email": "search@example.invalid"})
        self.env["res.partner"].create([
            {"name": "NS Search Person", "is_company": False},
            {"name": "NS Search inactive", "is_company": True, "active": False},
            {"name": "NS Search child", "is_company": True, "parent_id": company.id},
        ])
        with patch.object(type(self.env["payment.provider"]), "copy", return_value=self.env["payment.provider"]):
            other_company = self.env["res.company"].create({"name": "Other search company"})
        foreign = self.env["res.partner"].create({"name": "NS Search foreign", "is_company": True, "company_id": other_company.id})
        user_env = self.env["nolte.service.report"].with_user(self.tech).env
        with patch.object(api_v1, "request", SimpleNamespace(env=user_env)):
            self.assertEqual(self.api.search_companies(query="N"), [])
            found = self.api.search_companies(query="NS Search")
            self.assertEqual([item["id"] for item in found], [company.id])
            self.assertEqual(found[0]["street"], "Search Street 1")
            self.assertEqual(found[0]["email"], "search@example.invalid")
            self.assertIn(company.id, [item["id"] for item in self.api.search_companies(query="Searchstadt")])
        result = self.upsert(dict(self.payload, partnerId=company.id, manualCustomerName=company.name,
            manualCustomerStreet=company.street, manualContactEmail=company.email))
        report = self.env["nolte.service.report"].browse(result["id"])
        self.assertEqual(report.partner_id, company)
        self.assertEqual(report.task_id.partner_id, company)
        self.assertEqual(company.street, "Search Street 1")
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.upsert(dict(self.payload, mobileUuid=str(uuid4()), partnerId=foreign.id))

    def test_intake_location_contact_can_be_created_and_is_copied(self):
        view = self.env.ref("nolte_stundenbericht.view_nolte_service_intake_wizard_form")
        node = etree.fromstring(view.arch_db).xpath("//field[@name='service_location_contact_id']")[0]
        options = ast.literal_eval(node.get("options"))
        self.assertFalse(options.get("no_create", False))
        self.assertFalse(options["no_create_edit"])
        self.assertTrue(options["no_quick_create"], "Use the full address form instead of name-only quick creation")
        self.assertIn("default_is_company", node.get("context"))
        contact = self.env["res.partner"].create({"name": "New intake test site", "is_company": True,
            "company_id": self.env.company.id, "street": "Site Street 4", "zip": "12345", "city": "Site City", "phone": "123"})
        wizard = self.env["nolte.service.intake.wizard"].new({"service_location_contact_id": contact.id})
        wizard._onchange_service_location_contact_id()
        self.assertEqual(wizard.service_location_name, contact.name)
        self.assertIn("Site Street 4", wizard.service_location)
        self.assertIn("12345 Site City", wizard.service_location)
        self.assertEqual(wizard.service_location_contact_phone, "123")

    def test_intake_email_defaults_to_contact_and_keeps_customer_master_unchanged(self):
        customer = self.env['res.partner'].create({'name': 'Email customer', 'email': 'office@intake.example.invalid'})
        contact = self.env['res.partner'].create({'name': 'Email contact', 'parent_id': customer.id, 'email': 'contact@intake.example.invalid'})
        wizard = self.env['nolte.service.intake.wizard'].new({'partner_id': customer.id})
        wizard._onchange_partner_id()
        self.assertEqual(wizard.customer_email, customer.email)
        wizard.service_contact_id = contact
        wizard._onchange_service_contact_id()
        self.assertEqual(wizard.customer_email, contact.email)
        wizard.customer_email = 'custom@intake.example.invalid'
        self.assertEqual(customer.email, 'office@intake.example.invalid')
        self.assertEqual(contact.email, 'contact@intake.example.invalid')

    def test_intake_creates_visible_draft_and_retries_reuse_task_and_report(self):
        partner = self.env["res.partner"].create({"name": "Intake draft customer", "is_company": True, "customer_rank": 1})
        template = self.env["nolte.service.checklist.template"].create({"name": "Intake default completion",
            "visibility": "customer", "company_id": self.env.company.id,
            "line_ids": [Command.create({"name": "Test completion point", "note": "Default note"})]})
        self.env.company.sudo().nolte_checklist_template_id = template
        wizard = self.env["nolte.service.intake.wizard"].create({"name": "Intake creates both records",
            "partner_id": partner.id, "project_id": self.project.id,
            "technician_ids": [Command.set(self.employee.ids)], "planned_date": "2026-11-02",
            "service_location": "Site Street 1", "machine_number": "M-129",
            "customer_email": "delivery@intake.example.invalid",
            "work_description": "Instructions, NOT performed work"})
        before_tasks = self.env["project.task"].search_count([])
        action = wizard.action_create_service_task()
        report = self.env["nolte.service.report"].browse(action["res_id"])
        self.assertEqual(action["res_model"], "nolte.service.report")
        self.assertEqual(report, wizard.created_report_id)
        self.assertEqual(report.state, "draft")
        self.assertFalse(report.is_closed)
        self.assertEqual(report.owner_user_id, self.tech)
        self.assertEqual(report.partner_id, partner)
        self.assertEqual(report.project_id, self.project)
        self.assertEqual(fields.Date.to_string(report.service_date), "2026-11-02")
        self.assertEqual(report.manual_contact_email, "delivery@intake.example.invalid")
        self.assertFalse(partner.email)
        self.assertEqual(report.machine_number, "M-129")
        self.assertEqual(report.service_location, "Site Street 1")
        self.assertFalse(report.work_description)
        self.assertIn("Instructions, NOT performed work", report.task_id.description)
        self.assertEqual(report.member_ids.employee_id, self.employee)
        self.assertFalse(report.member_ids.segment_ids)
        self.assertEqual(report.employee_assignment_ids.employee_id, self.employee)
        self.assertEqual(report.checklist_ids.name, "Test completion point")
        self.assertFalse(report.checklist_ids.checked)
        self.assertEqual(wizard.action_create_service_task()["res_id"], report.id)
        self.assertEqual(self.env["project.task"].search_count([]), before_tasks + 1)
        self.assertEqual(self.env["nolte.service.report"].search_count([("task_id", "=", report.task_id.id)]), 1)
        with patch.object(api_v1, "request", SimpleNamespace(env=report.with_user(self.tech).env)):
            self.assertIn(report.id, [item["id"] for item in self.api.recent_reports()])
            loaded = self.api.load_report(report_id=report.id)
            self.assertEqual(loaded["taskId"], report.task_id.id)

    def test_intake_without_date_or_technician_stays_unplanned(self):
        customer = self.env["res.partner"].create({"name": "Unplanned intake customer", "customer_rank": 1})
        stages = self.env["project.task.type"]
        for name in ("Ungeplant", "Einsatz geplant"):
            if not stages.search([("name", "=", name), ("project_ids", "in", self.project.id)], limit=1):
                stages.create({"name": name, "project_ids": [Command.link(self.project.id)]})
        wizard = self.env["nolte.service.intake.wizard"].create({"name": "Unplanned test intake",
            "project_id": self.project.id, "partner_id": customer.id})
        self.assertFalse(wizard.planned_date)
        report = self.env["nolte.service.report"].browse(wizard.action_create_service_task()["res_id"])
        task = report.task_id
        self.assertEqual(task.stage_id.name, "Ungeplant")
        self.assertFalse(task.date_deadline)
        self.assertFalse(task.user_ids)
        self.assertTrue(report.planning_draft)
        self.assertFalse(report.display_service_date)
        self.assertFalse(report.member_ids)
        self.assertFalse(report.is_closed)
        self.assertEqual(report.owner_user_id, self.env.user)
        task.write({"date_deadline": "2026-11-05 00:00:00"})
        self.assertEqual(task.stage_id.name, "Einsatz geplant")
        self.assertEqual(fields.Date.to_string(report.display_service_date), "2026-11-05")
        self.assertFalse(report.member_ids, "A date does not imply an employee assignment")
        task.write({"user_ids": [Command.set(self.tech.ids)]})
        self.assertEqual(report.owner_user_id, self.tech)
        self.assertEqual(report.member_ids.employee_id, self.employee)
        self.assertEqual(fields.Date.to_string(report.member_ids.service_date), "2026-11-05")
        with patch.object(api_v1, "request", SimpleNamespace(env=report.with_user(self.tech).env)):
            self.assertEqual(self.api.load_report(report_id=report.id)["id"], report.id)
        task.write({"date_deadline": False})
        self.assertEqual(task.stage_id.name, "Ungeplant")
        self.assertFalse(report.display_service_date)
        task.write({"user_ids": [Command.clear()]})
        self.assertEqual(report.owner_user_id, report.create_uid)
        self.assertFalse(report.member_ids)
        task.write({"state": "1_done"})
        original_date = report.service_date
        task.write({"date_deadline": "2026-11-08 00:00:00", "user_ids": [Command.set(self.tech.ids)]})
        self.assertEqual(report.owner_user_id, report.create_uid)
        self.assertEqual(report.service_date, original_date)
        self.assertFalse(report.member_ids, "Completed tasks must not reassign prepared reports")

    def test_date_without_technician_is_planned_and_started_report_is_not_reassigned(self):
        customer = self.env["res.partner"].create({"name": "Dated intake customer", "customer_rank": 1})
        wizard = self.env["nolte.service.intake.wizard"].create({"name": "Dated unassigned intake",
            "project_id": self.project.id, "partner_id": customer.id, "planned_date": "2026-11-06"})
        report = self.env["nolte.service.report"].browse(wizard.action_create_service_task()["res_id"])
        task = report.task_id
        self.assertEqual(task.stage_id.name, "Einsatz geplant")
        self.assertFalse(task.user_ids)
        self.assertFalse(report.member_ids)
        task.write({"user_ids": [Command.set(self.tech.ids)]})
        self.assertEqual(report.owner_user_id, self.tech)
        report.member_ids.write({"segment_ids": [Command.create({"segment_type": "work", "start_time": "08:00", "end_time": "09:00"})]})
        original_date = report.service_date
        task.write({"date_deadline": "2026-11-07 00:00:00", "user_ids": [Command.clear()]})
        self.assertEqual(report.owner_user_id, self.tech)
        self.assertEqual(report.service_date, original_date)
        self.assertEqual(report.display_service_date, original_date)
        self.assertFalse(report.planning_draft)
        self.assertTrue(report.member_ids.segment_ids)

    def test_planner_can_assign_team_report_to_selected_responsible_technician(self):
        planner = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Intake planner", "login": "test_intake_planner",
            "group_ids": [Command.set([self.env.ref("base.group_user").id,
                self.env.ref("nolte_stundenbericht.group_stundenbericht_approver").id,
                self.env.ref("project.group_project_user").id,
                # Existing intake planning uses the private hr.employee
                # many2many, so the test planner needs its usual staff access.
                self.env.ref("hr.group_hr_user").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)]})
        other_user = self.tech.with_context(no_reset_password=True).copy({"login": "test_intake_team_other", "name": "Other intake technician"})
        other_employee = self.env["hr.employee"].create({"name": other_user.name, "user_id": other_user.id})
        customer = self.env["res.partner"].create({"name": "Team intake customer", "customer_rank": 1})
        wizard = self.env["nolte.service.intake.wizard"].with_user(planner).create({
            "name": "Team planned report", "partner_id": customer.id, "project_id": self.project.id,
            "technician_ids": [Command.set((self.employee | other_employee).ids)],
            "report_owner_employee_id": other_employee.id})
        action = wizard.action_create_service_task()
        report = self.env["nolte.service.report"].browse(action["res_id"])
        self.assertEqual(report.owner_user_id, other_user)
        self.assertEqual(set(report.member_ids.employee_id.ids), {self.employee.id, other_employee.id})
        self.assertEqual(set(report.task_id.user_ids.ids), {self.tech.id, other_user.id})
        self.assertTrue(report.with_user(other_user).has_access("write"))
        self.assertFalse(report.with_user(self.tech).has_access("write"), "Do not broaden team editing rights implicitly")

    def test_navigation_opens_existing_draft_without_creating_records(self):
        result = self.upsert(self.payload)
        report = self.env["nolte.service.report"].browse(result["id"]).with_user(self.tech)
        action = report.task_id.action_open_nolte_stundenbericht()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("report_id=%s" % report.id, action["url"])
        self.assertIn("task_id=%s" % report.task_id.id, action["url"])
        self.assertEqual(report.action_open_service_task()["res_id"], report.task_id.id)
        self.assertEqual(self.env["nolte.service.report"].search_count([("task_id", "=", report.task_id.id)]), 1)

    def test_backend_project_menu_opens_company_service_project(self):
        action = self.env["nolte.service.report"].with_user(self.tech).action_open_service_project()
        self.assertEqual(action, {"type": "ir.actions.act_url",
            "url": "/odoo/project/%s/tasks" % self.project.id, "target": "self"})
        menu = self.env.ref("nolte_stundenbericht.menu_nolte_service_project")
        self.assertEqual(menu.with_context(lang="en_US").name, "Planung")
        self.assertEqual(menu.parent_id, self.env.ref("nolte_stundenbericht.menu_nolte_stundenbericht_root"))
        self.assertEqual(menu.action.with_user(self.tech).run()["url"], action["url"])

    def test_navigation_new_task_and_multiple_or_confirmed_reports(self):
        task = self.env["project.task"].with_context(nolte_skip_report_preparation=True).create({"name": "Navigation task", "project_id": self.project.id,
            "user_ids": [Command.set(self.tech.ids)]})
        action = task.with_user(self.tech).action_open_nolte_stundenbericht()
        self.assertEqual(action["url"], "/my/stundenbericht?task_id=%s" % task.id)
        self.assertFalse(self.env["nolte.service.report"].search([("task_id", "=", task.id)]))
        result = self.upsert(dict(self.payload, taskId=task.id))
        report = self.env["nolte.service.report"].browse(result["id"])
        report.state = "customer_confirmed"
        action = task.with_user(self.tech).action_open_nolte_stundenbericht()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_id"], report.id)
        other = report.copy({"name": "Second navigation report", "state": "draft", "mobile_uuid": str(uuid4())})
        action = task.with_user(self.tech).action_open_nolte_stundenbericht()
        self.assertEqual(action["domain"], [("id", "in", [other.id, report.id])])

    def test_free_order_claim_reuses_prepared_report_and_blocks_second_technician(self):
        from odoo.exceptions import UserError
        customer = self.env['res.partner'].create({'name': 'Claim customer'})
        wizard = self.env['nolte.service.intake.wizard'].create({
            'name': 'Available intake', 'project_id': self.project.id, 'partner_id': customer.id})
        report = self.env['nolte.service.report'].browse(wizard.action_create_service_task()['res_id'])
        task = report.task_id
        with patch.object(api_v1, 'request', SimpleNamespace(env=task.with_user(self.tech).env)):
            self.assertIn(task.id, [x['id'] for x in self.api.bootstrap()['assignments']])
            claimed = self.api.claim_task(task.id)
            self.assertEqual(claimed['reportId'], report.id)
            self.assertEqual(self.api.claim_task(task.id), claimed)
            self.assertEqual(self.api.load_report(report.id)['mobileUuid'], report.mobile_uuid)
        self.assertEqual(task.user_ids, self.tech)
        self.assertEqual(report.owner_user_id, self.tech)
        self.assertEqual(report.member_ids.employee_id, self.employee)
        other = self.tech.with_context(no_reset_password=True).copy({'login': 'test_claim_other', 'name': 'Other claiming technician'})
        self.env['hr.employee'].create({'name': other.name, 'user_id': other.id})
        with patch.object(api_v1, 'request', SimpleNamespace(env=task.with_user(other).env)):
            self.assertNotIn(task.id, [x['id'] for x in self.api.bootstrap()['assignments']])
            with self.assertRaises(UserError):
                self.api.claim_task(task.id)
        self.assertEqual(self.env['nolte.service.report'].search_count([('task_id', '=', task.id)]), 1)

    def test_archiving_keeps_state_and_history_but_hides_report_and_order(self):
        from odoo.exceptions import UserError
        result = self.upsert(self.payload)
        report = self.env['nolte.service.report'].browse(result['id'])
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            with self.assertRaises(UserError):
                self.api.archive_report(report.id)
        report.state = 'customer_confirmed'
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            self.assertTrue(self.api.archive_report(report.id)['archived'])
            self.assertNotIn(report.id, [x['id'] for x in self.api.recent_reports()])
            self.assertNotIn(report.task_id.id, [x['id'] for x in self.api.bootstrap()['assignments']])
            with self.assertRaises(UserError):
                self.api.load_report(report.id)
            with self.assertRaises(UserError):
                self.api.upsert_report(dict(self.payload, mobileRevision=2))
        self.assertTrue(report.is_closed)
        self.assertEqual(report.state, 'customer_confirmed')
        self.assertTrue(report.exists())
        report.with_user(self.tech).action_unarchive_manual()
        self.assertFalse(report.is_closed)
        self.assertEqual(report.state, 'customer_confirmed')
        report.state = 'billed'
        report.archived_manually = True
        report.with_user(self.tech).action_unarchive_manual()
        self.assertTrue(report.is_closed, 'Manual restore must not undo automatic financial closure')

    def test_planning_archive_hides_linked_reports_and_can_be_restored(self):
        from odoo.exceptions import AccessError
        result = self.upsert(self.payload)
        report = self.env['nolte.service.report'].browse(result['id'])
        task = report.task_id
        original_task_state = task.state
        with self.assertRaises(AccessError):
            task.with_user(self.tech).action_nolte_archive_service()
        planner = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Archive planner', 'login': 'test_archive_planner',
            'group_ids': [Command.set([self.env.ref('nolte_stundenbericht.group_stundenbericht_approver').id,
                                      self.env.ref('project.group_project_user').id])],
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)]})
        task.user_ids = [Command.link(planner.id)]
        report.state = 'customer_confirmed'
        draft = report.copy({'state': 'draft'})
        action = task.with_user(planner).action_nolte_archive_service()
        self.assertEqual(action['url'], '/odoo/project/%s/tasks' % self.project.id)
        self.assertFalse(task.active)
        self.assertTrue(report.is_closed)
        self.assertTrue(draft.is_closed)
        self.assertEqual(report.state, 'customer_confirmed')
        self.assertEqual(draft.state, 'draft')
        self.assertEqual(task.state, original_task_state)
        with patch.object(api_v1, 'request', SimpleNamespace(env=report.with_user(self.tech).env)):
            self.assertNotIn(task.id, [x['id'] for x in self.api.bootstrap()['assignments']])
            self.assertNotIn(report.id, [x['id'] for x in self.api.recent_reports()])
        task.with_user(planner).action_nolte_restore_service()
        self.assertTrue(task.active)
        self.assertFalse(report.is_closed)
        self.assertFalse(draft.is_closed)
        report.archived_manually = True
        task.with_user(planner).action_nolte_archive_service()
        task.with_user(planner).action_nolte_restore_service()
        self.assertTrue(report.is_closed, 'Restoring planning must preserve independent manual report archiving')
        self.assertFalse(draft.is_closed)

    def test_closed_tasks_are_hidden_even_when_stage_is_not_folded(self):
        from odoo.exceptions import AccessError
        other_project = self.env['project.project'].create({'name': 'Internal workshop', 'company_id': self.env.company.id})
        internal = self.env['project.task'].with_context(nolte_skip_report_preparation=True).create({'name': 'Workshop lifting equipment', 'project_id': other_project.id,
            'user_ids': [Command.set(self.tech.ids)]})
        task = self.env['project.task'].with_context(nolte_skip_report_preparation=True).create({'name': 'Done but not folded', 'project_id': self.project.id,
            'state': '1_done', 'user_ids': [Command.set(self.tech.ids)]})
        free_done = self.env['project.task'].with_context(nolte_skip_report_preparation=True).create({'name': 'Unassigned done', 'project_id': self.project.id, 'state': '1_done'})
        with patch.object(api_v1, 'request', SimpleNamespace(env=task.with_user(self.tech).env)):
            ids = [x['id'] for x in self.api.bootstrap()['assignments']]
            self.assertNotIn(task.id, ids)
            self.assertNotIn(free_done.id, ids)
            self.assertNotIn(internal.id, ids)
            with self.assertRaises(AccessError):
                self.api.claim_task(internal.id)

    def test_direct_bootstrap_rejects_closed_task(self):
        stage = self.env["project.task.type"].create({"name": "Closed navigation stage", "fold": True,
            "project_ids": [Command.link(self.project.id)]})
        task = self.env["project.task"].with_context(nolte_skip_report_preparation=True).create({"name": "Old navigation task", "project_id": self.project.id,
            "stage_id": stage.id, "user_ids": [Command.set(self.tech.ids)]})
        from odoo.exceptions import AccessError
        with patch.object(api_v1, "request", SimpleNamespace(env=task.with_user(self.tech).env)), self.assertRaises(AccessError):
            self.api.bootstrap(task_id=task.id)
        task.user_ids = False
        with patch.object(api_v1, "request", SimpleNamespace(env=task.with_user(self.tech).env)), self.assertRaises(AccessError):
            self.api.bootstrap(task_id=task.id)

    def test_backend_form_reads_without_attendance_or_sales_access(self):
        report = self.env['nolte.service.report'].create({'owner_user_id': self.tech.id,
            'member_ids': [Command.create({'employee_id': self.employee.id, 'service_date': fields.Date.today()})]})
        model = report.with_user(self.tech)
        self.assertFalse(self.env['hr.attendance'].with_user(self.tech).has_access('read'))
        self.assertFalse(self.env['sale.order.line'].with_user(self.tech).has_access('read'))
        view = model.get_view(view_id=self.env.ref('nolte_stundenbericht.view_nolte_service_report_form').id, view_type='form')
        arch = etree.fromstring(view['arch'])
        self.assertFalse(arch.xpath('//field[@name="attendance_ids"]'))
        self.assertFalse(arch.xpath('//field[@name="billing_sale_line_ids"]'))
        # Match the web client's child-field specification across both tabs;
        # merely creating a wizard does not exercise the subsequent form read.
        child_names = set(arch.xpath('//field[@name="member_ids"]//field/@name'))
        specification = {'name': {}, 'member_ids': {'fields': {name: {} for name in child_names}}}
        data = model.web_read(specification)
        self.assertEqual(data[0]['id'], report.id)
        self.assertEqual(data[0]['member_ids'][0]['employee_id'], self.employee.id)
        # Authorized attendance staff still see the technical link.
        reader = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Attendance form reader', 'login': 'test_attendance_form_reader',
            'group_ids': [Command.set([self.env.ref('nolte_stundenbericht.group_stundenbericht_approver').id,
                                      self.env.ref('hr_attendance.group_hr_attendance_user').id])],
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)]})
        allowed_view = report.with_user(reader).get_view(view_id=self.env.ref('nolte_stundenbericht.view_nolte_service_report_form').id, view_type='form')
        self.assertTrue(etree.fromstring(allowed_view['arch']).xpath('//field[@name="attendance_ids"]'))

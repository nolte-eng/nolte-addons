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
        task = self.env["project.task"].create({"name": "Existing service task", "project_id": self.project.id,
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
        task = self.env["project.task"].create({"name": "Navigation task", "project_id": self.project.id,
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
        internal = self.env['project.task'].create({'name': 'Workshop lifting equipment', 'project_id': other_project.id,
            'user_ids': [Command.set(self.tech.ids)]})
        task = self.env['project.task'].create({'name': 'Done but not folded', 'project_id': self.project.id,
            'state': '1_done', 'user_ids': [Command.set(self.tech.ids)]})
        free_done = self.env['project.task'].create({'name': 'Unassigned done', 'project_id': self.project.id, 'state': '1_done'})
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
        task = self.env["project.task"].create({"name": "Old navigation task", "project_id": self.project.id,
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

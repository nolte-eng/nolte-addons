from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
from pathlib import Path

from lxml import html

from psycopg2 import IntegrityError
from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from ..controllers.api_v1 import NolteStundenberichtApiV1
from ..controllers import api_v1


@tagged("post_install", "-at_install")
class TestChecklistSync(TransactionCase):
    def setUp(self):
        super().setUp()
        self.api = NolteStundenberichtApiV1()
        self.reports = self.env["nolte.service.report"].create([
            {"name": "CHECKLIST-SYNC-A"}, {"name": "CHECKLIST-SYNC-B"},
        ])
        self.key = str(uuid4())
        self.item = {"checklistUuid": self.key, "name": "Internal check", "visibility": "internal", "note": "Keep this note", "checked": True}

    def test_reused_id_in_another_report_is_independent(self):
        first, second = self.reports
        self.api._sync_checklist(first, [self.item])
        self.api._sync_checklist(second, [dict(self.item, name="Second check", checked=False)])
        self.assertNotEqual(first.checklist_ids.id, second.checklist_ids.id)
        self.assertEqual(first.checklist_ids.note, "Keep this note")
        self.assertTrue(first.checklist_ids.checked)
        self.assertFalse(second.checklist_ids.checked)
        self.api._sync_checklist(second, [])
        self.assertFalse(second.checklist_ids)
        self.assertEqual(len(first.checklist_ids), 1)

    def test_repeated_payload_and_ids_update_instead_of_create(self):
        first = self.reports[0]
        self.api._sync_checklist(first, [self.item, dict(self.item, checked=False)])
        item_id = first.checklist_ids.id
        self.assertFalse(first.checklist_ids.checked)
        self.api._sync_checklist(first, [dict(self.item, checked=True)])
        self.assertEqual(first.checklist_ids.id, item_id)
        self.assertEqual(len(first.checklist_ids), 1)
        self.assertTrue(first.checklist_ids.checked)
        self.api._sync_checklist(first, [{"checklistUuid": self.key, "name": "Edited"}])
        self.assertEqual(first.checklist_ids.visibility, "internal")

    def test_database_still_rejects_duplicates_inside_one_report(self):
        first = self.reports[0]
        self.api._sync_checklist(first, [self.item])
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env["nolte.service.report.checklist"].create({
                "report_id": first.id, "mobile_uuid": self.key, "name": "Duplicate",
            })

    def test_single_customer_checklist_and_pdf_boxes(self):
        report = self.reports[0]
        self.api._sync_checklist(report, [self.item,
            {"checklistUuid": str(uuid4()), "name": "Customer completed", "visibility": "customer", "checked": True, "note": "Not for PDF"},
            {"checklistUuid": str(uuid4()), "name": "Customer open", "visibility": "customer", "checked": False},
        ])
        template_model = self.env["nolte.service.checklist.template"]
        internal = template_model.create({"name": "Legacy internal", "visibility": "internal"})
        customer = template_model.create({"name": "Visible checklist", "visibility": "customer"})
        self.env.company.sudo().nolte_checklist_template_id = customer
        technician = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Checklist test technician", "login": "test_nolte_single_checklist",
            "group_ids": [Command.set([self.env.ref("base.group_user").id, self.env.ref("nolte_stundenbericht.group_stundenbericht_user").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)],
        })
        with patch.object(api_v1, "request", SimpleNamespace(env=report.with_user(technician).env)):
            catalog = self.api.checklist_templates()
        self.assertIn(customer.id, [item["id"] for item in catalog])
        self.assertNotIn(internal.id, [item["id"] for item in catalog])
        rendered, _ = self.env["ir.actions.report"]._render_qweb_html(
            "nolte_stundenbericht.action_report_customer_service_report", report.ids)
        document = html.fromstring(rendered)
        boxes = document.xpath('//span[@class="ns-rate-checkbox"]')
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].text_content(), "X")
        self.assertIn("Customer completed", document.text_content())
        self.assertNotIn("Customer open", document.text_content())
        self.assertNotIn("Not for PDF", document.text_content())
        self.assertNotIn("Internal check", document.text_content())
        self.assertEqual(len(report.checklist_ids), 3, "Legacy internal entries remain stored")
        self.assertEqual(report.checklist_ids.filtered(lambda item: item.checked and item.visibility == "customer").note, "Not for PDF")

    def test_pdf_completion_after_flat_rates_and_hidden_without_checks(self):
        report = self.reports[0]
        product = self.env["product.product"].create({"name": "Completion test article", "type": "service"})
        rate = self.env["nolte.service.flat.rate"].create({"name": "Completion test rate", "product_id": product.id})
        report._sync_flat_rates([rate.id])
        self.api._sync_checklist(report, [{"checklistUuid": str(uuid4()), "name": "Completed point", "visibility": "customer", "checked": True, "note": "Private completion note"}])
        rendered, _ = self.env["ir.actions.report"]._render_qweb_html(
            "nolte_stundenbericht.action_report_customer_service_report", report.ids)
        document = html.fromstring(rendered)
        headings = document.xpath('//section/h2/text()')
        self.assertEqual(headings.index("Einsatzabschluss"), headings.index("Pauschalen") + 1)
        boxes = document.xpath('//span[@class="ns-rate-checkbox"]')
        self.assertEqual([box.text_content() for box in boxes], ["X", "X"])
        self.assertNotIn("Private completion note", document.text_content())
        report.checklist_ids.checked = False
        rendered, _ = self.env["ir.actions.report"]._render_qweb_html(
            "nolte_stundenbericht.action_report_customer_service_report", report.ids)
        document = html.fromstring(rendered)
        self.assertNotIn("Einsatzabschluss", document.xpath('//section/h2/text()'))
        self.assertNotIn("Completed point", document.text_content())
        self.assertEqual(report.checklist_ids.note, "Private completion note")

    def test_one_company_default_and_manager_configuration(self):
        template_model = self.env["nolte.service.checklist.template"]
        manager = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Checklist configuration manager", "login": "test_nolte_checklist_manager",
            "group_ids": [Command.set([self.env.ref("base.group_user").id, self.env.ref("nolte_stundenbericht.group_stundenbericht_manager").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)],
        })
        self.env.company.sudo().nolte_checklist_template_id = False
        action = template_model.with_user(manager).action_open_configuration()
        again = template_model.with_user(manager).action_open_configuration()
        self.assertEqual(action["res_id"], again["res_id"])
        chosen = template_model.browse(action["res_id"])
        self.assertEqual(chosen.company_id, self.env.company)
        self.assertEqual(chosen.visibility, "customer")
        template_model.create({"name": "Unused second template", "visibility": "customer"})
        self.assertEqual(template_model._default_for_current_company(), chosen)
        self.assertEqual(action["views"][0][1], "form")

    def test_upgrade_preserves_customer_default_without_publishing_internal(self):
        with patch.object(type(self.env["payment.provider"]), "copy", return_value=self.env["payment.provider"]):
            company = self.env["res.company"].create({"name": "Checklist migration company"})
        templates = self.env["nolte.service.checklist.template"]
        internal = templates.create({"name": "Private", "visibility": "internal", "company_id": company.id})
        customer = templates.create({"name": "Pauschalen", "visibility": "customer", "company_id": company.id,
                                     "line_ids": [Command.create({"name": "Existing point"})]})
        path = Path(__file__).parents[1] / "migrations/19.0.1.1.8/post-einsatzabschluss-default.py"
        spec = importlib.util.spec_from_file_location("checklist_default_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.cr, "19.0.1.0.8")
        self.env.invalidate_all()
        self.assertEqual(company.nolte_checklist_template_id, customer)
        self.assertEqual(customer.name, "Einsatzabschluss")
        self.assertEqual(customer.line_ids.name, "Existing point")
        self.assertEqual(internal.visibility, "internal")

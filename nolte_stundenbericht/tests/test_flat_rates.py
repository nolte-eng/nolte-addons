from unittest.mock import patch
from types import SimpleNamespace
import json

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from ..controllers import api_v1


@tagged("post_install", "-at_install")
class TestFlatRates(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tech = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Flat-rate test technician", "login": "test_nolte_flat_rates",
            "group_ids": [Command.set([self.env.ref("base.group_user").id, self.env.ref("nolte_stundenbericht.group_stundenbericht_user").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)],
        })
        self.product = self.env["product.product"].create({"name": "Flat-rate test article", "type": "service", "list_price": 23.5, "invoice_policy": "order"})
        self.rate = self.env["nolte.service.flat.rate"].create({"name": "Test Pauschale", "product_id": self.product.id})
        self.partner = self.env["res.partner"].create({"name": "Flat-rate test customer"})
        self.partner.property_product_pricelist = self.env["product.pricelist"].create({"name": "Flat-rate test pricelist", "currency_id": self.env.company.currency_id.id})
        self.report = self.env["nolte.service.report"].create({"name": "TEST-FLAT-RATES", "partner_id": self.partner.id, "owner_user_id": self.tech.id})

    def test_sync_repeat_remove_and_snapshot(self):
        report = self.report.with_user(self.tech)
        report._sync_flat_rates([self.rate.id, self.rate.id])
        line = self.report.flat_rate_line_ids
        self.assertEqual(len(line), 1)
        report._sync_flat_rates([self.rate.id])
        self.assertEqual(self.report.flat_rate_line_ids, line)
        self.assertEqual(line.product_id, self.product)
        other = self.product.copy({"name": "Different article"})
        with self.assertRaises(UserError):
            self.rate.product_id = other
        self.rate.active = False
        report._sync_flat_rates([self.rate.id])
        self.assertEqual(self.report.flat_rate_line_ids, line)
        report._sync_flat_rates([])
        self.assertFalse(self.report.flat_rate_line_ids)

    def test_acl_company_validation_and_frozen_selection(self):
        with self.assertRaises(AccessError):
            self.rate.with_user(self.tech).write({"name": "Not permitted"})
        with self.assertRaises(AccessError):
            self.env["nolte.service.report.flat.rate"].with_user(self.tech).create({"report_id": self.report.id, "flat_rate_id": self.rate.id, "name": "Forged", "product_id": self.product.id})
        # Company creation copies payment providers. That unrelated integration
        # is outside this test (some migrated test databases retain old codes).
        with patch.object(type(self.env["payment.provider"]), "copy", return_value=self.env["payment.provider"]):
            other_company = self.env["res.company"].create({"name": "Flat-rate other company"})
        other_rate = self.env["nolte.service.flat.rate"].create({"name": "Foreign", "company_id": other_company.id, "product_id": self.product.id})
        with self.assertRaises(UserError):
            self.report._sync_flat_rates([other_rate.id])
        with self.assertRaises(ValidationError):
            self.report._sync_flat_rates([{"id": self.rate.id, "price": 0}])
        self.report._sync_flat_rates([self.rate.id])
        self.report.state = "awaiting_signature"
        with self.assertRaises(UserError):
            self.report.with_user(self.tech)._sync_flat_rates([])

    def test_customer_pdf_names_only_and_frozen_snapshot(self):
        self.report._sync_flat_rates([self.rate.id])
        snapshot = self.report.with_user(self.tech).preview_customer_snapshot()
        self.assertEqual(snapshot["flatRates"], [{"name": "Test Pauschale"}])
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "nolte_stundenbericht.action_report_customer_service_report", self.report.ids)
        self.assertIn(b"Test Pauschale", html)
        self.assertIn(b'class="ns-rate-checkbox"', html)
        self.assertIn(b'>X</span>', html)
        self.assertNotIn(self.product.name.encode(), html)
        self.report.customer_snapshot_payload = json.dumps(snapshot)
        self.rate.name = "Changed configuration name"
        self.assertEqual(self.report.customer_snapshot_for_pdf()["flatRates"], [{"name": "Test Pauschale"}])

    def test_approval_is_once_and_reaches_invoice(self):
        self.report.write({"service_location_name": "Test factory", "service_location": "Factory Street 12, 12345 Teststadt"})
        self.report._sync_flat_rates([self.rate.id])
        for suffix in ["work", "work_ot30", "work_ot50", "travel", "travel_ot30", "travel_ot50", "km", "overnight", "allowance"]:
            self.env["ir.config_parameter"].set_param("nolte_overtime_billing.product_%s_id" % suffix, str(self.product.id))
        self.report.state = "under_review"
        self.report.action_approve_billing()
        selection = self.report.flat_rate_line_ids
        line = selection.sale_line_id
        self.assertTrue(line)
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.product_uom_qty, 1)
        self.assertAlmostEqual(line.price_unit, 23.5)
        self.report.action_approve_billing()
        self.assertEqual(selection.sale_line_id, line)
        self.assertEqual(len(self.report.sale_order_id.order_line.filtered(lambda item: item.product_id == self.product)), 1)
        notes = self.report.sale_order_id.order_line.filtered(lambda line: line.display_type == "line_note")
        self.assertEqual(len(notes), 1)
        self.assertIn("Einsatzort: Test factory, Factory Street 12, 12345 Teststadt", notes.name)
        with patch.object(type(self.env["mail.mail"]), "send", return_value=True), patch.object(type(self.env["mail.mail"]), "_send", return_value=True):
            self.report.sale_order_id.action_confirm()
            invoice = self.report.sale_order_id._create_invoices()
        self.assertEqual(len(invoice.invoice_line_ids.filtered(lambda item: item.product_id == self.product)), 1)
        self.assertIn("Einsatzort: Test factory, Factory Street 12, 12345 Teststadt", "\n".join(invoice.invoice_line_ids.mapped("name")))

    def test_sales_note_only_includes_explicit_service_location(self):
        self.partner.write({"street": "Customer Street 5", "zip": "54321", "city": "Teststadt"})
        note = self.report._sale_order_service_note()
        self.assertNotIn("Einsatzort:", note)
        self.assertNotIn("Customer Street 5", note)
        self.assertIn("Service Techniker:", note)
        self.assertIn("Maschinen Nr.:", note)
        self.assertIn("Zeitraum:", note)
        self.report.write({"service_location": "Different Street 8"})
        note = self.report._sale_order_service_note()
        self.assertIn("Einsatzort: Different Street 8", note)
        self.assertNotIn("Customer Street 5", note)
        self.report.write({"service_location": False, "service_location_name": "Factory only"})
        note = self.report._sale_order_service_note()
        self.assertIn("Einsatzort: Factory only", note)
        self.assertNotIn("Customer Street 5", note)

    def test_mobile_api_round_trip_and_older_clients(self):
        employee = self.env["hr.employee"].create({"name": "Flat-rate test technician", "user_id": self.tech.id, "company_id": self.env.company.id})
        user_env = self.report.with_user(self.tech).env
        payload = {"mobileUuid": self.report.mobile_uuid, "mobileRevision": 1,
                   "employeeId": employee.id, "serviceDate": "2026-10-26",
                   "employeeDays": [], "flatRateIds": [self.rate.id]}
        with patch.object(api_v1, "request", SimpleNamespace(env=user_env)):
            api = api_v1.NolteStundenberichtApiV1()
            self.assertIn(self.rate.id, [item["id"] for item in api.flat_rates()])
            result = api.upsert_report(payload)
            self.assertEqual(result["flatRates"], [{"id": self.rate.id, "name": self.rate.name}])
            payload.update(mobileRevision=2, serverRevision=result["serverRevision"])
            result = api.upsert_report(payload)
            self.assertEqual(len(result["flatRates"]), 1)
            # An old app without a Pauschalen field must not erase selections.
            payload.pop("flatRateIds")
            payload.update(mobileRevision=3, serverRevision=result["serverRevision"])
            self.assertEqual(len(api.upsert_report(payload)["flatRates"]), 1)

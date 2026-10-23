import base64
import hashlib
import io
import re
from datetime import timedelta
from unittest.mock import patch

from PIL import Image, ImageDraw
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOnlineSignature(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.technician = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Test signature technician", "login": "test_nolte_signature",
            "group_ids": [Command.set([cls.env.ref("base.group_user").id, cls.env.ref("nolte_stundenbericht.group_stundenbericht_user").id])],
            "company_id": cls.env.company.id, "company_ids": [Command.set(cls.env.company.ids)],
        })
        cls.env["ir.config_parameter"].set_param("nolte_stundenbericht.signature_base_url", "https://example.invalid")

    def _prepare(self):
        report = self.env["nolte.service.report"].with_context(force_report_rendering=True).create({
            "name": "TEST-ONLINE-SIGNATURE", "owner_user_id": self.technician.id,
            "manual_customer_name": "Test customer", "manual_contact_email": "customer@example.invalid",
            "work_description": "Customer-visible work", "internal_note": "PRIVATE_INTERNAL_NOTE",
        })
        self.env["nolte.service.report.checklist"].create([
            {"report_id": report.id, "name": "PRIVATE_INTERNAL_CHECK", "visibility": "internal"},
            {"report_id": report.id, "name": "Visible customer check", "visibility": "customer"},
        ])
        if not report.company_id.email:
            report.company_id.email = "service@example.invalid"
        action = report.with_user(self.technician).action_request_online_signature()
        token = re.search(r"/sign/([A-Za-z0-9_-]{43})", str(action["context"]["default_body"])).group(1)
        record = self.env["nolte.service.signature.request"].with_context(force_report_rendering=True).search([("report_id", "=", report.id)])
        return report, record, token

    def test_frozen_snapshot_and_revocation(self):
        report, record, token = self._prepare()
        self.assertEqual(record.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn("PRIVATE_INTERNAL", record.html_snapshot)
        self.assertIn("Visible customer check", record.html_snapshot)
        with self.assertRaises(UserError):
            report.write({"work_description": "Changed"})
        with self.assertRaises(UserError):
            self.env["nolte.service.report.checklist"].with_context(default_report_id=report.id).create({"name": "Bypass"})
        with self.assertRaises(AccessError):
            record.with_user(self.technician).read(["token_hash"])
        report.with_user(self.technician).action_revoke_online_signature()
        self.assertEqual(record.state, "revoked")
        self.assertEqual(report.state, "returned")
        self.assertFalse(report.customer_snapshot_payload)

    def test_sign_once_and_expiry(self):
        report, record, _token = self._prepare()
        image = Image.new("RGBA", (300, 100), "white")
        ImageDraw.Draw(image).line([(10, 50), (70, 10), (150, 80)], fill="black", width=3)
        output = io.BytesIO()
        image.save(output, format="PNG")
        signature = base64.b64encode(output.getvalue()).decode()
        record.expires_at = fields.Datetime.now() - timedelta(days=1)
        with self.assertRaises(UserError):
            record.with_user(self.env.ref("base.public_user")).sudo()._accept("Test customer", signature)
        record.expires_at = fields.Datetime.now() + timedelta(days=1)
        frozen = report.customer_snapshot_payload
        with patch.object(type(report), "action_sync_after_customer_confirmation", return_value=True):
            record.with_user(self.env.ref("base.public_user")).sudo()._accept("Test customer", signature)
        self.assertEqual(report.customer_snapshot_payload, frozen)
        self.assertEqual(report.state, "customer_confirmed")
        self.assertTrue(report.customer_pdf_attachment_id.raw.startswith(b"%PDF-"))
        domain = [("model", "=", report._name), ("res_id", "=", report.id), ("email_to", "=", "customer@example.invalid")]
        mails = self.env["mail.mail"].search(domain)
        self.assertEqual(len(mails), 1)
        with self.assertRaises(UserError):
            record._accept("Test customer", signature)
        self.assertEqual(self.env["mail.mail"].search_count(domain), 1)

    def test_settings_are_scoped_and_admin_only(self):
        settings_model = self.env["nolte.service.signature.settings"]
        with self.assertRaises(AccessError):
            settings_model.with_user(self.technician).create({})
        admin = self.env.ref("base.user_admin")
        settings = settings_model.with_user(admin).create({"stundenbericht_signature_base_url": "http://example.invalid"})
        with self.assertRaises(UserError):
            settings.action_save()
        parameters = self.env["ir.config_parameter"]
        parameters.set_param("nolte_signature_test_unrelated", "unchanged")
        settings.stundenbericht_signature_base_url = "https://example.invalid"
        settings.action_save()
        self.assertEqual(parameters.get_param("nolte_stundenbericht.signature_base_url"), "https://example.invalid")
        self.assertEqual(parameters.get_param("nolte_signature_test_unrelated"), "unchanged")

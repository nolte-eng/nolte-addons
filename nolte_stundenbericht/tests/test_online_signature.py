import base64
import hashlib
import io
import re
from datetime import timedelta
from unittest.mock import patch
from lxml import html

from PIL import Image, ImageDraw
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOnlineSignature(TransactionCase):
    def test_report_mail_returns_to_report_without_changing_other_composers(self):
        report = self.env['nolte.service.report'].create({'name': 'COMPOSER-RETURN', 'owner_user_id': self.technician.id})
        composer = self.env['mail.compose.message'].create({
            'model': report._name, 'res_ids': str(report.ids), 'composition_mode': 'comment',
            'subject': 'Return test', 'body': 'Test body',
        })
        # Exercise the real public send action, suppressing only dispatch.
        # No outgoing mail is created or sent by this regression test.
        with patch.object(type(composer), '_action_send_mail', return_value=(self.env['mail.mail'], self.env['mail.message'])) as dispatch:
            action = composer.action_send_mail()
            dispatch.assert_called_once_with(auto_commit=False)
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['target'], 'self')
        self.assertEqual(action['url'], '/odoo/action-%s/%s' % (self.env.ref('nolte_stundenbericht.action_nolte_service_report').id, report.id))
        composer.write({'model': 'res.partner', 'res_ids': str(self.env.company.partner_id.ids)})
        with patch.object(type(composer), '_action_send_mail', return_value=(self.env['mail.mail'], self.env['mail.message'])):
            self.assertEqual(composer.action_send_mail()['tag'], 'action_send_mail_callback')
        composer.write({'model': report._name, 'res_ids': str(report.ids)})
        with patch.object(type(composer), '_action_send_mail', side_effect=UserError('Dispatch failed')):
            with self.assertRaises(UserError):
                composer.action_send_mail()

    def test_pdf_special_characters_are_safe_and_preserved(self):
        model = self.env["nolte.service.report"]
        source = '100552 · Siemens 3RV20 → 3RV24 – 20 °C € <script>alert("x")</script> &'
        encoded = str(model.pdf_text(source))
        fragment = html.fragment_fromstring('<div>' + encoded + '</div>')
        self.assertFalse(fragment.xpath('.//script'))
        self.assertEqual(fragment.text_content(), source)
        self.assertEqual(str(model.pdf_text('Übernachtung')), 'Uebernachtung')
        renderer = self.env['ir.actions.report']
        paperformat = self.env.ref('nolte_stundenbericht.paperformat_customer_service_report')
        args = renderer._build_wkhtmltopdf_args(paperformat, False)
        self.assertEqual(args[args.index('--encoding') + 1], 'utf-8')
        other_format = paperformat.copy({'name': 'Unrelated report format'})
        self.assertNotIn('--encoding', renderer._build_wkhtmltopdf_args(other_format, False))

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
            {"report_id": report.id, "name": "Visible customer check", "visibility": "customer", "checked": True},
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

    def test_employee_sender_keeps_service_address_and_all_three_mail_paths(self):
        from email.utils import parseaddr
        self.env.company.email = 'service@sender.example.invalid'
        self.technician.email = 'user@sender.example.invalid'
        employee = self.env['hr.employee'].create({
            'name': 'Report Technician', 'user_id': self.technician.id,
            'company_id': self.env.company.id, 'work_email': 'technician@sender.example.invalid'})
        report = self.env['nolte.service.report'].create({
            'name': 'EMPLOYEE-SENDER', 'owner_user_id': self.technician.id,
            'manual_contact_email': 'customer@sender.example.invalid',
            'member_ids': [Command.create({'employee_id': employee.id, 'service_date': fields.Date.today()})]})
        identity = report.with_user(self.technician)._customer_mail_identity()
        self.assertEqual(parseaddr(identity['email_from']), ('Report Technician', 'service@sender.example.invalid'))
        self.assertEqual(parseaddr(identity['reply_to']), ('Report Technician', 'technician@sender.example.invalid'))
        renderer = self.env['ir.actions.report']
        with patch.object(type(renderer), '_render_qweb_pdf', return_value=(b'%PDF-1.4 test', 'pdf')), \
             patch.object(type(renderer), '_render_qweb_html', return_value=(b'<html></html>', 'html')):
            action = report.with_user(self.technician).action_request_online_signature()
        context = action['context']
        self.assertEqual(context['default_email_from'], identity['email_from'])
        self.assertEqual(context['default_reply_to'], identity['reply_to'])
        composer = self.env['mail.compose.message'].with_user(self.technician).with_context(context).create({})
        values = composer._prepare_mail_values(report.ids)[report.id]
        self.assertEqual(parseaddr(values['email_from'])[1], 'service@sender.example.invalid')
        self.assertEqual(parseaddr(values['reply_to'])[1], 'technician@sender.example.invalid')
        recipients = self.env['res.partner'].browse(context['default_partner_ids'][0][2])
        self.assertIn('service@sender.example.invalid', recipients.mapped('email'))
        self.assertIn('customer@sender.example.invalid', recipients.mapped('email'))
        report.with_user(self.technician).action_revoke_online_signature()
        report.customer_pdf_attachment_id = self.env['ir.attachment'].create({
            'name': 'Test PDF', 'raw': b'%PDF-1.4 test', 'res_model': report._name, 'res_id': report.id})
        action = report.with_user(self.technician).action_send_customer_pdf()
        self.assertEqual(action['context']['default_email_from'], identity['email_from'])
        self.assertEqual(action['context']['default_reply_to'], identity['reply_to'])
        # Queue only; TransactionCase rolls this back without any SMTP dispatch.
        report._queue_signed_customer_copy('customer@sender.example.invalid', 'service@sender.example.invalid')
        mail = self.env['mail.mail'].search([('model', '=', report._name), ('res_id', '=', report.id)], order='id desc', limit=1)
        self.assertEqual(mail.email_from, identity['email_from'])
        self.assertEqual(mail.reply_to, identity['reply_to'])
        self.assertEqual(mail.email_cc, 'service@sender.example.invalid')

    def test_employee_reply_fallback_never_changes_company_sender(self):
        from email.utils import parseaddr
        self.env.company.email = 'service@fallback.example.invalid'
        self.technician.email = 'user@fallback.example.invalid'
        report = self.env['nolte.service.report'].create({'owner_user_id': self.technician.id})
        identity = report.with_user(self.technician)._customer_mail_identity()
        self.assertEqual(parseaddr(identity['email_from'])[1], 'service@fallback.example.invalid')
        self.assertEqual(parseaddr(identity['reply_to'])[1], 'user@fallback.example.invalid')
        self.technician.email = False
        identity = report.with_user(self.technician)._customer_mail_identity()
        self.assertEqual(parseaddr(identity['reply_to'])[1], 'service@fallback.example.invalid')
        self.assertEqual(parseaddr(identity['email_from'])[1], 'service@fallback.example.invalid')

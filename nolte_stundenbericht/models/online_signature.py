import base64
import hashlib
import io
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from PIL import Image
from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class ServiceSignatureRequest(models.Model):
    _name = "nolte.service.signature.request"
    _description = "Geschützte Kunden-Unterschriftsanfrage"
    _order = "id desc"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    token_hash = fields.Char(required=True, index=True, groups="base.group_system")
    state = fields.Selection([("pending", "Ausstehend"), ("signed", "Unterschrieben"), ("revoked", "Widerrufen")], default="pending", required=True)
    expires_at = fields.Datetime(required=True)
    requested_by_id = fields.Many2one("res.users", required=True)
    customer_email = fields.Char(required=True)
    company_email = fields.Char(required=True)
    snapshot_hash = fields.Char(required=True)
    html_snapshot = fields.Text(copy=False)
    pdf_attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    signed_at = fields.Datetime()
    signer_name = fields.Char()
    sent_at = fields.Datetime()

    def _lock(self):
        self.ensure_one()
        # All prepare/cancel/sign operations acquire locks in this order.
        self.report_id._lock_customer_confirmation()
        self.env.cr.execute("SELECT id FROM nolte_service_signature_request WHERE id=%s FOR UPDATE", [self.id])
        self.invalidate_recordset()

    def _accept(self, signer_name, signature):
        self._lock()
        if self.state != "pending" or self.expires_at <= fields.Datetime.now():
            raise UserError(_("Dieser Unterschriftslink ist abgelaufen oder wurde bereits verwendet. Bitte einen neuen Link anfordern."))
        # The token authorizes this single confirmation, not an Odoo login.
        # Run internal chatter/integrations as the employee who issued it.
        report = self.report_id.with_user(self.requested_by_id).sudo().with_company(self.report_id.company_id)
        if report.state != "awaiting_signature" or report.customer_snapshot_hash != self.snapshot_hash:
            raise UserError(_("Die Anfrage ist nicht mehr gültig."))
        signer_name = str(signer_name or "").strip()
        if not signer_name or len(signer_name) > 200:
            raise UserError(_("Bitte Ihren vollständigen Namen eintragen."))
        encoded = str(signature or "").removeprefix("data:image/png;base64,")
        if len(encoded) > 1500000:
            raise UserError(_("Die Unterschrift ist zu groß."))
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != "PNG" or not (10 <= image.width <= 2000 and 10 <= image.height <= 1000):
                    raise ValueError()
                image.load()
                rgba = image.convert("RGBA")
                paper = Image.new("RGBA", rgba.size, "white")
                paper.alpha_composite(rgba)
                if paper.convert("L").getextrema()[0] > 245:
                    raise ValueError()
        except Exception as error:
            raise UserError(_("Bitte eine gültige Unterschrift zeichnen.")) from error
        report._finalize_customer_confirmation(signer_name, encoded, frozen=True)
        self.write({"state": "signed", "signed_at": report.customer_signed_at, "signer_name": signer_name})
        report._queue_signed_customer_copy(self.customer_email, self.company_email)


class SignatureSettings(models.TransientModel):
    _name = "nolte.service.signature.settings"
    _description = "Einstellungen der Online-Unterschrift"

    stundenbericht_signature_base_url = fields.Char(
        string="Öffentliche HTTPS-Adresse für Kundenlinks",
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param("nolte_stundenbericht.signature_base_url"),
        help="Zum Beispiel https://nolte-eng.de. Leer = Odoo-Systembasisadresse. In Produktion muss diese Adresse ohne Tailscale erreichbar sein.",
    )

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Nur Administratoren dürfen die öffentliche Kundenadresse ändern."))
        value = (self.stundenbericht_signature_base_url or "").strip().rstrip("/")
        if value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
                raise UserError(_("Bitte eine gültige HTTPS-Adresse eingeben."))
        self.env["ir.config_parameter"].sudo().set_param("nolte_stundenbericht.signature_base_url", value or False)
        return {"type": "ir.actions.act_window_close"}


class ServiceReport(models.Model):
    _inherit = "nolte.service.report"

    state = fields.Selection(selection_add=[("awaiting_signature", "Kundenbestätigung ausstehend"), ("customer_confirmed",)], ondelete={"awaiting_signature": "set default"})
    returned_signed_pdf = fields.Binary(string="Unterschriebener PDF-Rücklauf", attachment=True, copy=False, groups="nolte_stundenbericht.group_stundenbericht_approver")
    returned_pdf_filename = fields.Char(string="Dateiname", copy=False, groups="nolte_stundenbericht.group_stundenbericht_approver")
    returned_pdf_signer = fields.Char(string="Unterzeichner im PDF-Rücklauf", copy=False, groups="nolte_stundenbericht.group_stundenbericht_approver")

    def _lock_customer_confirmation(self):
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute("SELECT id FROM nolte_service_report WHERE id=%s FOR UPDATE", [self.id])
        self.invalidate_recordset()

    def _check_signature_pending(self):
        for report in self.sorted("id"):
            report._lock_customer_confirmation()
        if any(report.state == "awaiting_signature" for report in self):
            raise UserError(_("Die Kundenfassung ist für die Online-Unterschrift festgeschrieben. Bitte zuerst die Unterschriftsanfrage widerrufen, bevor Sie Berichtsdaten ändern."))

    def write(self, values):
        protected = {"service_date", "partner_id", "company_id", "task_id", "owner_user_id", "manual_customer_name", "manual_customer_street", "manual_customer_zip", "manual_customer_city", "manual_contact_name", "manual_contact_phone", "manual_contact_email", "service_location", "service_location_name", "service_location_contact_name", "service_location_contact_phone", "machine_number", "machine_type", "overnight_count", "public_note", "work_description", "work_result", "member_ids", "employee_assignment_ids", "material_ids", "checklist_ids", "photo_ids"}
        if protected.intersection(values):
            self._check_signature_pending()
        # Only dedicated server methods may change a pending confirmation or
        # its frozen evidence; a normal RPC write must not bypass revocation.
        if not self.env.su and {"state", "customer_snapshot_payload", "customer_snapshot_hash", "customer_signature", "customer_pdf_attachment_id", "customer_signed_at", "customer_signer_name"}.intersection(values):
            self._check_signature_pending()
        return super().write(values)

    def _signature_recipients(self):
        contact = self.task_id.nolte_service_contact_id if self.task_id else self.env["res.partner"]
        customer = self.manual_contact_email or contact.email or self.partner_id.email
        company = self.company_id.email or self.company_id.partner_id.email
        if not customer or not company:
            raise UserError(_("Bitte Kunden-E-Mail und Service-E-Mail des eigenen Unternehmens hinterlegen."))
        return customer, company

    def action_request_online_signature(self):
        self.ensure_one()
        self.check_access("write")
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(_("Keine Berechtigung für Unterschriftsanfragen."))
        actor = self.env.user
        report = self.sudo()
        report._lock_customer_confirmation()
        if report.state not in ("draft", "returned"):
            raise UserError(_("Eine neue Anfrage ist nur für einen unbestätigten Bericht möglich. Eine bestehende Anfrage bitte zuerst widerrufen."))
        customer, company = report._signature_recipients()
        identity = report._customer_mail_identity(company)
        # Technicians need no general Contact/Creation privilege merely to
        # send to the two addresses on a report they are allowed to access.
        recipients = self.env["res.partner"].sudo()
        for email in (customer, company):
            recipients |= recipients.find_or_create(email, assert_valid_email=True)
        base_url = self.env["ir.config_parameter"].sudo().get_param("nolte_stundenbericht.signature_base_url") or self.get_base_url()
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise UserError(_("Für Kundenlinks muss eine gültige HTTPS-Basisadresse konfiguriert sein."))
        snapshot = json.dumps(report.preview_customer_snapshot(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(snapshot.encode()).hexdigest()
        report.write({"state": "awaiting_signature", "customer_snapshot_payload": snapshot, "customer_snapshot_hash": digest, "server_revision": report.server_revision + 1})
        token = secrets.token_urlsafe(32)
        request_record = self.env["nolte.service.signature.request"].sudo().create({
            "report_id": report.id, "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": fields.Datetime.now() + timedelta(days=14), "requested_by_id": actor.id,
            "customer_email": customer, "company_email": company, "snapshot_hash": digest,
        })
        renderer = self.env["ir.actions.report"].sudo()
        report_ref = "nolte_stundenbericht.action_report_customer_service_report"
        html, _fmt = renderer._render_qweb_html(report_ref, report.ids)
        html = re.sub(rb"<script\b[^>]*>.*?</script\s*>", b"", html, flags=re.I | re.S)
        style = b"<style>html,body,#wrapwrap{width:100%!important;max-width:none!important;margin:0!important;padding:0!important;background:#fff}body{overflow-x:auto!important}main{min-width:740px}.ns-footer{position:static!important}</style>"
        html = html.replace(b"</head>", style + b"</head>", 1)
        pdf, _fmt = renderer._render_qweb_pdf(report_ref, report.ids)
        attachment = self.env["ir.attachment"].sudo().create({"name": "Stundenbericht_%s_zur_Unterschrift.pdf" % report.name.replace("/", "-"), "raw": pdf, "mimetype": "application/pdf", "res_model": report._name, "res_id": report.id})
        request_record.write({"html_snapshot": html.decode("utf-8"), "pdf_attachment_id": attachment.id})
        url = "%s/nolte_stundenbericht/sign/%s" % (base_url.rstrip("/"), token)
        report.message_post(body=_("Online-Unterschriftsanfrage von %s vorbereitet. Die Kundenfassung ist festgeschrieben; bitte die vorbereitete E-Mail senden. Der Link ist 14 Tage gültig.") % actor.name)
        return {"type": "ir.actions.act_window", "name": _("Kundenunterschrift anfordern"), "res_model": "mail.compose.message", "view_mode": "form", "target": "new", "context": {
            "default_model": self._name, "default_res_ids": self.ids, "default_composition_mode": "comment", "default_subtype_xmlid": "mail.mt_comment",
            "default_partner_ids": [(6, 0, recipients.ids)], "default_email_from": identity["email_from"], "default_reply_to": identity["reply_to"],
            "default_notify_author": True, "default_notify_skip_followers": True,
            "default_subject": _("Bitte um Bestätigung: Stundenbericht %s") % report.name,
            "default_body": Markup("<p>Guten Tag,</p><p>bitte prüfen und unterschreiben Sie unseren Stundenbericht %s über diesen geschützten Link:</p><p><a href=\"%s\">Stundenbericht ansehen und unterschreiben</a></p><p>Der Link ist 14 Tage gültig. Nach der Bestätigung erhalten Sie den unterschriebenen Bericht als PDF. Alternativ können Sie die angehängte PDF unterschrieben zurücksenden.</p><p>Freundliche Grüße<br/>%s</p>") % (report.name, url, report.company_id.name),
            "default_attachment_ids": [(6, 0, [attachment.id])],
            "default_nolte_signature_request_id": request_record.id,
        }}

    def action_revoke_online_signature(self):
        self.check_access("write")
        for original in self:
            report = original.sudo()
            report._lock_customer_confirmation()
            if report.state != "awaiting_signature":
                raise UserError(_("Es gibt keine ausstehende Unterschriftsanfrage."))
            self.env["nolte.service.signature.request"].sudo().search([("report_id", "=", report.id), ("state", "=", "pending")]).write({"state": "revoked"})
            report.write({"state": "returned", "customer_snapshot_payload": False, "customer_snapshot_hash": False, "server_revision": report.server_revision + 1})
            report.message_post(body=_("Online-Unterschriftsanfrage widerrufen. Alte Links sind ungültig; der Bericht kann wieder bearbeitet werden."))
        return True

    def action_accept_returned_pdf(self):
        self.ensure_one()
        self.check_access("write")
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_approver"):
            raise AccessError(_("Nur Prüfer dürfen einen PDF-Rücklauf bestätigen."))
        if self.state != "awaiting_signature" or not self.returned_signed_pdf or not (self.returned_pdf_signer or "").strip():
            raise UserError(_("Bitte eine unterschriebene PDF und den Namen des Unterzeichners für die ausstehende Anfrage hinterlegen."))
        try:
            raw = base64.b64decode(self.returned_signed_pdf, validate=True)
            if not raw.startswith(b"%PDF-") or len(raw) > 15 * 1024 * 1024:
                raise ValueError()
        except Exception as error:
            raise UserError(_("Bitte eine gültige PDF-Datei mit höchstens 15 MB hochladen.")) from error
        report = self.sudo()
        report._finalize_customer_confirmation(self.returned_pdf_signer.strip(), False, frozen=True, uploaded_pdf=raw)
        self.env["nolte.service.signature.request"].sudo().search([("report_id", "=", self.id), ("state", "=", "pending")]).write({"state": "signed", "signed_at": report.customer_signed_at, "signer_name": report.customer_signer_name})
        report.message_post(body=_("Unterschriebener PDF-Rücklauf durch %s geprüft und hinterlegt.") % self.env.user.name)
        report._queue_signed_customer_copy(*report._signature_recipients())
        return True

    def _finalize_customer_confirmation(self, signer_name, signature, frozen=False, uploaded_pdf=None):
        self.ensure_one()
        self._lock_customer_confirmation()
        allowed = ("awaiting_signature",) if frozen else ("draft", "returned")
        if self.state not in allowed:
            raise UserError(_("Der Bericht wurde bereits bestätigt oder geändert."))
        values = {"state": "customer_confirmed", "customer_signer_name": signer_name, "customer_signed_at": fields.Datetime.now(), "customer_signature": signature, "server_revision": self.server_revision + 1}
        if not frozen:
            snapshot = json.dumps(self.preview_customer_snapshot(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            values.update(customer_snapshot_payload=snapshot, customer_snapshot_hash=hashlib.sha256(snapshot.encode()).hexdigest())
        self.write(values)
        if uploaded_pdf is None:
            pdf, _fmt = self.env["ir.actions.report"].sudo()._render_qweb_pdf("nolte_stundenbericht.action_report_customer_service_report", self.ids)
        else:
            pdf = uploaded_pdf
        attachment = self.env["ir.attachment"].sudo().create({"name": "Kunden-Stundenbericht_%s.pdf" % self.name.replace("/", "-"), "raw": pdf, "mimetype": "application/pdf", "res_model": self._name, "res_id": self.id})
        self.customer_pdf_attachment_id = attachment
        self.message_post(body=_("Kundenfassung bestätigt von %s.") % signer_name)
        if self.task_id:
            stage = self.env["project.task.type"].search([("name", "ilike", "Servicebericht prüfen"), ("project_ids", "in", self.task_id.project_id.id)], limit=1)
            if stage:
                self.task_id.stage_id = stage
        self.action_sync_after_customer_confirmation()

    def _queue_signed_customer_copy(self, customer_email, company_email):
        self.ensure_one()
        self.env["mail.mail"].sudo().create({
            "subject": _("Unterschriebener Stundenbericht %s") % self.name,
            "body_html": Markup("<p>Guten Tag,</p><p>vielen Dank für die Bestätigung. Anbei erhalten Sie den unterschriebenen Stundenbericht %s.</p><p>Freundliche Grüße<br/>%s</p>") % (self.name, self.company_id.name),
            **self._customer_mail_identity(company_email), "email_to": customer_email,
            "email_cc": company_email if customer_email.strip().casefold() != company_email.strip().casefold() else False,
            "attachment_ids": [(4, self.customer_pdf_attachment_id.id)], "model": self._name, "res_id": self.id, "auto_delete": False,
        })


class PendingSignatureChild(models.AbstractModel):
    _name = "nolte.signature.child.guard"
    _description = "Schreibschutz der angefragten Kundenfassung"

    @api.model_create_multi
    def create(self, vals_list):
        reports = self.env["nolte.service.report"]
        for values in vals_list:
            parent_field = "member_id" if self._name == "nolte.service.report.segment" else "report_id"
            parent_id = values.get(parent_field) or self.default_get([parent_field]).get(parent_field)
            if self._name == "nolte.service.report.segment":
                reports |= self.env["nolte.service.report.member"].browse(parent_id).report_id
            else:
                reports |= self.env["nolte.service.report"].browse(parent_id)
        reports._check_signature_pending()
        return super().create(vals_list)

    def write(self, values):
        self.mapped("report_id")._check_signature_pending()
        if values.get("report_id"):
            self.env["nolte.service.report"].browse(values["report_id"])._check_signature_pending()
        if self._name == "nolte.service.report.segment" and values.get("member_id"):
            self.env["nolte.service.report.member"].browse(values["member_id"]).report_id._check_signature_pending()
        return super().write(values)

    def unlink(self):
        self.mapped("report_id")._check_signature_pending()
        return super().unlink()


class GuardMember(models.Model):
    _inherit = ["nolte.service.report.member", "nolte.signature.child.guard"]
    _name = "nolte.service.report.member"


class GuardEmployee(models.Model):
    _inherit = ["nolte.service.report.employee", "nolte.signature.child.guard"]
    _name = "nolte.service.report.employee"


class GuardSegment(models.Model):
    _inherit = ["nolte.service.report.segment", "nolte.signature.child.guard"]
    _name = "nolte.service.report.segment"


class GuardMaterial(models.Model):
    _inherit = ["nolte.service.report.material", "nolte.signature.child.guard"]
    _name = "nolte.service.report.material"


class GuardChecklist(models.Model):
    _inherit = ["nolte.service.report.checklist", "nolte.signature.child.guard"]
    _name = "nolte.service.report.checklist"


class GuardPhotoAttachment(models.Model):
    _inherit = "ir.attachment"

    def _check_pending_report_photo(self):
        if self.ids:
            reports = self.env["nolte.service.report"].sudo().search([("state", "=", "awaiting_signature"), ("photo_ids", "in", self.ids)])
            reports._check_signature_pending()

    def write(self, values):
        if {"datas", "raw", "db_datas", "store_fname", "name", "res_model", "res_id"}.intersection(values):
            self._check_pending_report_photo()
        return super().write(values)

    def unlink(self):
        self._check_pending_report_photo()
        return super().unlink()


class SignatureMailComposer(models.TransientModel):
    _inherit = "mail.compose.message"

    nolte_signature_request_id = fields.Many2one("nolte.service.signature.request", readonly=True)

    def action_send_mail(self):
        self.ensure_one()
        result = super().action_send_mail()
        res_ids = self._evaluate_res_ids()
        if self.model == "nolte.service.report" and self.composition_mode == "comment" and len(res_ids) == 1:
            report = self.env["nolte.service.report"].browse(res_ids).exists()
            if report:
                report.check_access("read")
                action = self.env.ref("nolte_stundenbericht.action_nolte_service_report")
                # A composer opened by a standalone server-action URL has no
                # underlying form to restore when Odoo closes its dialog.
                return {"type": "ir.actions.act_url", "url": "/odoo/action-%s/%s" % (action.id, report.id), "target": "self"}
        return result

    def _prepare_signature_dispatch(self):
        self.ensure_one()
        record = self.nolte_signature_request_id.sudo()
        if not record:
            return record, ""
        record.report_id.with_user(self.env.user).check_access("write")
        record._lock()
        if self.model != "nolte.service.report" or self._evaluate_res_ids() != record.report_id.ids or self.composition_mode != "comment":
            raise AccessError(_("Diese Anfrage gehört nicht zum ausgewählten Bericht."))
        if record.state != "pending" or record.sent_at or record.expires_at <= fields.Datetime.now():
            raise UserError(_("Diese Anfrage wurde bereits versendet, ist abgelaufen oder wurde widerrufen. Bitte bei Bedarf eine neue Anfrage vorbereiten."))
        tokens = re.findall(r"/nolte_stundenbericht/sign/([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])", str(self.body))
        if not any(hashlib.sha256(token.encode()).hexdigest() == record.token_hash for token in tokens):
            raise UserError(_("Der persönliche Unterschriftslink fehlt im E-Mail-Text. Bitte den Link nicht entfernen."))
        customers = [email for email in self.partner_ids.mapped("email") if email and email.strip().casefold() != record.company_email.strip().casefold()]
        if not customers and record.customer_email.strip().casefold() != record.company_email.strip().casefold():
            raise UserError(_("Bitte mindestens eine Kundenadresse als Empfänger auswählen."))
        return record, ",".join(dict.fromkeys(customers)) or record.customer_email

    def _action_send_mail(self, auto_commit=False):
        requests = [wizard._prepare_signature_dispatch() for wizard in self if wizard.nolte_signature_request_id]
        result = super()._action_send_mail(auto_commit=auto_commit)
        for record, customer_email in requests:
            record.write({"sent_at": fields.Datetime.now(), "customer_email": customer_email})
        return result

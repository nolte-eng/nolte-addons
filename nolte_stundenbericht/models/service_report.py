import base64
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

from psycopg2 import IntegrityError
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class NolteServiceReport(models.Model):
    _name = "nolte.service.report"
    _description = "Nolte Einsatzbericht"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "service_date desc, id desc"

    name = fields.Char(default=lambda self: _("Neu"), required=True, copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    owner_user_id = fields.Many2one("res.users", string="Verantwortlicher Benutzer", required=True, default=lambda self: self.env.user, index=True, readonly=True)
    task_id = fields.Many2one("project.task", string="Aufgabe / Einsatzauftrag", index=True)
    project_id = fields.Many2one(related="task_id.project_id", store=True, index=True)
    sale_order_id = fields.Many2one("sale.order", string="Auftrag", index=True)
    partner_id = fields.Many2one("res.partner", string="Kunde", index=True)
    manual_customer_name = fields.Char(string="Firma (manuell)")
    manual_customer_street = fields.Char(string="Straße / Hausnummer (manuell)")
    manual_customer_zip = fields.Char(string="PLZ (manuell)")
    manual_customer_city = fields.Char(string="Ort (manuell)")
    manual_contact_name = fields.Char(string="Ansprechpartner (manuell)")
    manual_contact_phone = fields.Char(string="Telefon (manuell)")
    manual_contact_email = fields.Char(string="E-Mail (manuell)")
    service_date = fields.Date(string="Einsatzdatum", required=True, default=fields.Date.context_today, index=True, tracking=True)
    country_rate_key = fields.Char(string="BMF-Tarifschlüssel", default="DE", required=True)
    service_location = fields.Char(string="Einsatzort")
    service_location_name = fields.Char(string="Firma am Einsatzort")
    service_location_contact_name = fields.Char(string="Ansprechpartner am Einsatzort")
    service_location_contact_phone = fields.Char(string="Telefon am Einsatzort")
    machine_number = fields.Char(string="Maschinennummer")
    machine_type = fields.Char(string="Maschinentyp")
    overnight_count = fields.Integer(string="Anzahl Übernachtungen", default=0)
    state = fields.Selection([
        ("draft", "Entwurf"),
        ("customer_confirmed", "Kunde bestätigt"),
        ("internally_amended", "Intern ergänzt"),
        ("under_review", "In Prüfung"),
        ("ready_to_bill", "Abrechnungsbereit"),
        ("billed", "Abgerechnet"),
        ("returned", "Zur Korrektur"),
    ], default="draft", required=True, tracking=True, index=True)
    is_closed = fields.Boolean(string="Abgeschlossen", compute="_compute_is_closed", store=True, index=True)
    mobile_uuid = fields.Char(default=lambda self: str(uuid4()), required=True, copy=False, readonly=True, index=True)
    mobile_revision = fields.Integer(default=0, required=True, copy=False)
    server_revision = fields.Integer(default=0, required=True, copy=False)
    customer_snapshot_hash = fields.Char(copy=False, readonly=True)
    customer_snapshot_payload = fields.Text(copy=False, readonly=True)
    customer_signature = fields.Binary(string="Kundenunterschrift", attachment=True, copy=False, readonly=True)
    customer_pdf_attachment_id = fields.Many2one("ir.attachment", string="Bestätigter Kundenbericht", readonly=True, copy=False)
    customer_signed_at = fields.Datetime(copy=False, readonly=True)
    customer_signer_name = fields.Char(copy=False, readonly=True)
    public_note = fields.Text(string="Bemerkung für den Kunden")
    work_description = fields.Text(string="Ausgeführte Arbeiten")
    work_result = fields.Text(string="Fazit / Handlungsbedarf")
    internal_note = fields.Text(string="Interne Bemerkung")
    member_ids = fields.One2many("nolte.service.report.member", "report_id", string="Mitarbeiter")
    employee_assignment_ids = fields.One2many("nolte.service.report.employee", "report_id", string="Einsatzmitarbeiter")
    material_ids = fields.One2many("nolte.service.report.material", "report_id", string="Material")
    checklist_ids = fields.One2many("nolte.service.report.checklist", "report_id", string="Checkliste")
    customer_checklist_ids = fields.One2many("nolte.service.report.checklist", "report_id", string="Kundencheckliste", domain=[("visibility", "=", "customer")])
    internal_checklist_ids = fields.One2many("nolte.service.report.checklist", "report_id", string="Interne Checkliste", domain=[("visibility", "=", "internal")])
    photo_ids = fields.Many2many("ir.attachment", string="Einsatzfotos", copy=False)
    conflict_ids = fields.One2many("nolte.service.report.conflict", "report_id", string="Konflikte", readonly=True)
    work_report_id = fields.Many2one("nolte.work.report", string="Interner Stundenbericht", readonly=True, copy=False)
    spesen_sync_state = fields.Selection([
        ("pending", "Noch nicht übertragen"),
        ("synchronized", "An Spesenbericht übergeben"),
        ("conflict", "Prüfkonflikt"),
    ], default="pending", required=True, copy=False)
    spesen_sync_message = fields.Char(readonly=True, copy=False)
    attendance_sync_state = fields.Selection([
        ("pending", "Noch nicht übertragen"),
        ("synchronized", "An Anwesenheit übergeben"),
        ("conflict", "Anwesenheit prüfen"),
    ], default="pending", required=True, copy=False)
    attendance_sync_message = fields.Char(readonly=True, copy=False)

    _mobile_uuid_unique = models.Constraint(
        "UNIQUE(mobile_uuid)",
        "Die mobile Berichtskennung muss eindeutig sein.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Neu")) == _("Neu"):
                sequence_date = fields.Date.to_date(vals.get("service_date")) or fields.Date.context_today(self)
                sequence = self.env["ir.sequence"].search([
                    ("code", "=", "nolte.service.report"),
                    ("company_id", "in", [self.env.company.id, False]),
                ], order="company_id", limit=1)
                if sequence and sequence.use_date_range:
                    month_start = sequence_date.replace(day=1)
                    if month_start.month == 12:
                        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
                    else:
                        month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
                    ranges = self.env["ir.sequence.date_range"].sudo()
                    domain = [
                        ("sequence_id", "=", sequence.id),
                        ("date_from", "=", month_start),
                        ("date_to", "=", month_end),
                    ]
                    if not ranges.search(domain, limit=1):
                        try:
                            with self.env.cr.savepoint():
                                ranges.create({
                                    "sequence_id": sequence.id,
                                    "date_from": month_start,
                                    "date_to": month_end,
                                })
                        except IntegrityError:
                            # Another report may have initialized this month
                            # concurrently; the unique range constraint handles it.
                            pass
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "nolte.service.report", sequence_date=sequence_date
                ) or _("Neu")
        return super().create(vals_list)

    @api.depends("state", "task_id.state", "task_id.stage_id.name")
    def _compute_is_closed(self):
        for report in self:
            task = report.task_id
            stage_name = (task.stage_id.with_context(lang=None).name or "").strip().casefold()
            report.is_closed = bool(
                report.state == "billed"
                or task.state == "1_done"
                or stage_name in ("abgeschlossen", "abgerechnet")
            )

    def action_submit_review(self):
        self.filtered(lambda report: report.state in ("customer_confirmed", "internally_amended", "returned")).write({"state": "under_review"})

    def action_send_customer_pdf(self):
        self.ensure_one()
        self.check_access("read")
        service_contact = self.task_id.nolte_service_contact_id if self.task_id else self.env["res.partner"]
        recipient = self.manual_contact_email or service_contact.email or (self.partner_id.email if self.partner_id else False)
        if not recipient:
            raise UserError(_("Für den Kunden ist keine E-Mail-Adresse hinterlegt. Bitte zuerst eine E-Mail-Adresse am Kunden oder im Bericht eintragen."))
        company_email = self.company_id.email or self.company_id.partner_id.email
        if not company_email:
            raise UserError(_("Für Ihr Unternehmen ist keine Service-E-Mail-Adresse hinterlegt."))
        if not self.customer_pdf_attachment_id and not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_approver"):
            raise UserError(_("Der Kundenbericht kann erst nach der Kundenbestätigung versendet werden."))
        # The standard Odoo composer uses contact tags for editable recipients.
        # Resolve only these authorized report addresses; sending must not
        # require granting technicians general contact-creation privileges.
        recipients = self.env["res.partner"].sudo()
        for address in (recipient, company_email):
            recipients |= recipients.find_or_create(address, assert_valid_email=True)

        attachment = self.customer_pdf_attachment_id
        if not attachment:
            pdf, _report_format = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
                "nolte_stundenbericht.action_report_customer_service_report", self.ids
            )
            attachment = self.env["ir.attachment"].create({
                "name": "Kunden-Stundenbericht_%s.pdf" % self.name.replace("/", "-"),
                "datas": base64.b64encode(pdf),
                "mimetype": "application/pdf",
                "res_model": self._name,
                "res_id": self.id,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Stundenbericht per E-Mail senden"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": [self.id],
                "default_composition_mode": "comment",
                "default_subtype_xmlid": "mail.mt_comment",
                "default_partner_ids": [(6, 0, recipients.ids)],
                "default_email_from": company_email,
                "default_reply_to": company_email,
                "default_notify_author": True,
                "default_notify_skip_followers": True,
                "default_subject": _("Stundenbericht %s") % self.name,
                "default_body": Markup(_("Guten Tag,<br/><br/>anbei erhalten Sie den Stundenbericht %(report)s.<br/><br/>Freundliche Grüße<br/>%(company)s")) % {"report": self.name, "company": self.company_id.name},
                "default_attachment_ids": [(6, 0, [attachment.id])],
            },
        }

    def customer_snapshot_for_pdf(self):
        self.ensure_one()
        if not self.customer_snapshot_payload:
            raise UserError(_("Für diesen Einsatzbericht existiert noch keine bestätigte Kundenfassung."))
        return json.loads(self.customer_snapshot_payload)

    def pdf_text(self, value):
        """Return safe HTML text that wkhtmltopdf renders with German characters."""
        encoded = str(escape(value or "")).translate(str.maketrans({
            "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae",
            "Ö": "Oe", "Ü": "Ue", "ß": "ss",
        }))
        return Markup(encoded)

    def pdf_date(self, value):
        """Format ISO snapshot dates in German day-month-year notation."""
        if not value:
            return ""
        try:
            return fields.Date.to_date(value).strftime("%d.%m.%Y")
        except (TypeError, ValueError):
            return str(value)

    def preview_customer_snapshot(self):
        """Live snapshot used for the customer-PDF preview before signing."""
        self.ensure_one()
        partner = self.partner_id
        address = ", ".join(part for part in [
            partner.street,
            partner.street2,
            " ".join(part for part in [partner.zip, partner.city] if part),
            partner.country_id.name,
        ] if part) if partner else ", ".join(part for part in [
            self.manual_customer_street,
            " ".join(part for part in [self.manual_customer_zip, self.manual_customer_city] if part),
        ] if part)
        def time_text(segments):
            return ", ".join("%s-%s" % (item.start_time, item.end_time) for item in segments)

        def minutes(segments):
            total = 0
            for item in segments:
                try:
                    start_hour, start_minute = map(int, item.start_time.split(":"))
                    end_hour, end_minute = map(int, item.end_time.split(":"))
                except (AttributeError, ValueError):
                    continue
                value = (end_hour * 60 + end_minute) - (start_hour * 60 + start_minute)
                total += value if value >= 0 else value + 24 * 60
            return total

        def duration_text(value):
            return "%d:%02d h" % divmod(value, 60)

        time_rows = []
        total_work = total_outbound_travel = total_return_travel = total_breaks = 0
        total_outbound_km = total_return_km = total_overnights = 0.0
        for member in self.member_ids.sorted(lambda item: (item.service_date, item.employee_id.name)):
            segments = member.segment_ids.filtered(lambda item: not item.internal_only)
            outbound = segments.filtered(lambda item: item.segment_type == "outbound_travel")
            work = segments.filtered(lambda item: item.segment_type == "work")
            breaks = segments.filtered(lambda item: item.segment_type == "break")
            returned = segments.filtered(lambda item: item.segment_type == "return_travel")
            total_work += minutes(work)
            total_outbound_travel += minutes(outbound)
            total_return_travel += minutes(returned)
            total_breaks += minutes(breaks)
            outbound_km = sum(item.kilometers or 0.0 for item in outbound)
            return_km = sum(item.kilometers or 0.0 for item in returned)
            total_outbound_km += outbound_km
            total_return_km += return_km
            employee_assignment = self.employee_assignment_ids.filtered(lambda item: item.employee_id == member.employee_id)[:1]
            legacy_overnights = sum(self.member_ids.filtered(lambda item: item.employee_id == member.employee_id).mapped("overnight_count"))
            employee_overnights = employee_assignment.overnight_count if employee_assignment else legacy_overnights
            # Show the Einsatz-wide count only once per employee in the table.
            first_employee_day = not any(row["employeeId"] == member.employee_id.id for row in time_rows)
            shown_overnights = employee_overnights if first_employee_day else 0
            total_overnights += shown_overnights
            time_rows.append({
                "serviceDate": fields.Date.to_string(member.service_date),
                "employeeId": member.employee_id.id,
                "employeeName": member.employee_id.name,
                "outbound": time_text(outbound),
                "outboundDuration": duration_text(minutes(outbound)),
                "work": time_text(work),
                "workDuration": duration_text(minutes(work)),
                "breaks": time_text(breaks),
                "breakDuration": duration_text(minutes(breaks)),
                "return": time_text(returned),
                "returnDuration": duration_text(minutes(returned)),
                "outboundKilometers": outbound_km,
                "returnKilometers": return_km,
                "kilometers": outbound_km + return_km,
                "overnightCount": shown_overnights,
            })
        return {
            "version": 1,
            "report": {
                "number": self.name,
                "serviceDate": fields.Date.to_string(self.service_date),
                "customerId": partner.id or False,
                "customerName": partner.display_name or self.manual_customer_name or "",
                "customerAddress": address,
                "contactName": self.manual_contact_name or "",
                "contactPhone": self.manual_contact_phone or "",
                "contactEmail": self.manual_contact_email or "",
                "taskId": self.task_id.id or False,
                "taskName": self.task_id.display_name or "",
                "locationName": self.service_location_name or "",
                "location": self.service_location or "",
                "locationContactName": self.service_location_contact_name or "",
                "locationContactPhone": self.service_location_contact_phone or "",
                "machineNumber": self.machine_number or "",
                "machineType": self.machine_type or "",
                "overnightCount": sum(self.employee_assignment_ids.mapped("overnight_count")) or sum(self.member_ids.mapped("overnight_count")) or self.overnight_count,
                "note": self.public_note or "",
                "workDescription": self.work_description or "",
                "workResult": self.work_result or "",
            },
            "members": [{
                "employeeId": member.employee_id.id,
                "employeeName": member.employee_id.name,
                "overnightCount": member.overnight_count,
                "segments": [{
                    "type": segment.segment_type,
                    "start": segment.start_time,
                    "end": segment.end_time,
                    "kilometers": segment.kilometers,
                } for segment in member.segment_ids.filtered(lambda item: not item.internal_only)],
            } for member in self.member_ids],
            "employeeAssignments": [{
                "employeeId": assignment.employee_id.id,
                "employeeName": assignment.employee_id.name,
                "overnightCount": assignment.overnight_count,
            } for assignment in self.employee_assignment_ids],
            "memberNames": list(dict.fromkeys(self.member_ids.mapped("employee_id.name"))),
            "timeRows": time_rows,
            "timeTotals": {
                "work": duration_text(total_work),
                "outboundTravel": duration_text(total_outbound_travel),
                "returnTravel": duration_text(total_return_travel),
                "breaks": duration_text(total_breaks),
                "outboundKilometers": total_outbound_km,
                "returnKilometers": total_return_km,
                "kilometers": total_outbound_km + total_return_km,
                "overnightCount": total_overnights,
            },
            "materials": [{"name": item.name, "quantity": item.quantity, "unit": item.unit or "", "note": item.note or ""} for item in self.material_ids],
            "checklist": [{"name": item.name, "checked": item.checked, "note": item.note or ""} for item in self.checklist_ids.filtered(lambda item: item.visibility == "customer")],
        }

    def _create_sync_conflict(self, employee, conflict_type, description, conflict_date=None):
        self.ensure_one()
        conflict_date = conflict_date or self.service_date
        existing = self.conflict_ids.filtered(lambda item: item.employee_id == employee and item.conflict_date == conflict_date and item.conflict_type == conflict_type and item.state == "open")
        if not existing:
            self.env["nolte.service.report.conflict"].create({
                "report_id": self.id,
                "employee_id": employee.id,
                "conflict_date": conflict_date,
                "conflict_type": conflict_type,
                "description": description,
            })

    def _member_day_summary(self, member):
        active_segments = member.segment_ids.filtered(lambda item: item.segment_type != "break")
        if not active_segments:
            raise UserError(_("Für %s fehlen Arbeits- oder Fahrtzeitsegmente.") % member.employee_id.name)

        def to_minutes(value):
            hour, minute = map(int, value.split(":"))
            return hour * 60 + minute

        starts = [to_minutes(item.start_time) for item in active_segments]
        ends = [to_minutes(item.end_time) for item in active_segments]
        # A segment after midnight is treated as belonging to the same work day.
        if max(ends) < min(starts):
            ends = [value + 24 * 60 for value in ends]
        break_minutes = 0
        for segment in member.segment_ids.filtered(lambda item: item.segment_type == "break"):
            start, end = to_minutes(segment.start_time), to_minutes(segment.end_time)
            if end < start:
                end += 24 * 60
            break_minutes += max(0, end - start)

        def as_time(value):
            value %= 24 * 60
            return "%02d:%02d" % (value // 60, value % 60)

        return {"start_time": as_time(min(starts)), "end_time": as_time(max(ends)), "break_minutes": break_minutes}

    def _employee_day_members(self, employee, service_date=None):
        """Confirmed app report rows of one employee on the requested service day."""
        self.ensure_one()
        return self.env["nolte.service.report.member"].search([
            ("employee_id", "=", employee.id),
            ("service_date", "=", service_date or self.service_date),
            ("report_id.state", "in", ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill", "billed")),
        ])

    def _members_day_summary(self, members):
        """Produce one daily source line without counting gaps between jobs as work.

        The legacy expense module has one line per employee/day.  We preserve
        that contract and store the gaps between separate assignments as break
        minutes, so its existing work-hour calculation remains correct.
        """
        intervals = []
        for member in members:
            for segment in member.segment_ids.filtered(lambda item: item.segment_type != "break"):
                start_h, start_m = map(int, segment.start_time.split(":"))
                end_h, end_m = map(int, segment.end_time.split(":"))
                start, end = start_h * 60 + start_m, end_h * 60 + end_m
                if end <= start:
                    end += 24 * 60
                intervals.append((start, end))
        if not intervals:
            raise UserError(_("Für %s fehlen Arbeits- oder Fahrtzeitsegmente.") % members[:1].employee_id.name)
        intervals.sort()
        merged = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        first, last = merged[0][0], merged[-1][1]
        active_minutes = sum(end - start for start, end in merged)
        return {
            "start_time": "%02d:%02d" % ((first // 60) % 24, first % 60),
            "end_time": "%02d:%02d" % ((last // 60) % 24, last % 60),
            "break_minutes": max(0, last - first - active_minutes),
        }

    def _members_attendance_intervals(self, members):
        """Return merged active intervals for one employee/day in local minutes."""
        intervals = []
        for member in members:
            for segment in member.segment_ids.filtered(lambda item: item.segment_type != "break"):
                start_h, start_m = map(int, segment.start_time.split(":"))
                end_h, end_m = map(int, segment.end_time.split(":"))
                start, end = start_h * 60 + start_m, end_h * 60 + end_m
                if end <= start:
                    end += 24 * 60
                intervals.append((start, end))
        intervals.sort()
        merged = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        return merged

    def action_sync_attendance(self):
        """Create technical attendance entries while protecting manual/kiosk data."""
        Attendance = self.env["hr.attendance"].sudo()
        valid_states = ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill", "billed")
        for original_report in self:
            report = original_report.sudo()
            if report.state not in valid_states:
                raise UserError(_("Nur bestätigte Einsatzberichte können an die Anwesenheit übergeben werden."))
            for member in report.member_ids:
                day_members = report._employee_day_members(member.employee_id, member.service_date)
                intervals = report._members_attendance_intervals(day_members)
                if not intervals:
                    raise UserError(_("Für %s fehlen Arbeits- oder Fahrtzeitsegmente.") % member.employee_id.name)
                controlled = day_members.mapped("attendance_ids")
                timezone = ZoneInfo(member.employee_id._get_tz() or "UTC")
                values = []
                for start, end in intervals:
                    start_local = datetime.combine(member.service_date, datetime.min.time()) + timedelta(minutes=start)
                    end_local = datetime.combine(member.service_date, datetime.min.time()) + timedelta(minutes=end)
                    check_in = start_local.replace(tzinfo=timezone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                    check_out = end_local.replace(tzinfo=timezone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                    overlap = Attendance.search([
                        ("employee_id", "=", member.employee_id.id),
                        ("check_in", "<", check_out),
                        "|", ("check_out", "=", False), ("check_out", ">", check_in),
                    ]) - controlled
                    if overlap:
                        raise UserError(_(
                            "Für %s existiert im Zeitraum %s–%s bereits eine manuell oder per Kiosk erfasste Anwesenheit. Diese wird nicht überschrieben."
                        ) % (member.employee_id.name, start_local.strftime("%H:%M"), end_local.strftime("%H:%M")))
                    values.append({"employee_id": member.employee_id.id, "check_in": check_in, "check_out": check_out, "in_mode": "technical", "out_mode": "technical"})
                controlled.unlink()
                created = Attendance.create(values)
                day_members.write({"attendance_ids": [(6, 0, created.ids)]})
                day_members.mapped("report_id").write({
                    "attendance_sync_state": "synchronized",
                    "attendance_sync_message": _("Anwesenheitszeiten aus dem Stundenbericht synchronisiert."),
                })
            report.message_post(body=_("Zeiten an die Odoo-Anwesenheit übergeben."))
        return True

    def action_sync_spesenbericht(self):
        """Create/update the existing work report and distribute it safely.

        The method runs only after a customer confirmation. It deliberately
        checks the target monthly line before using the established
        ``action_distribute`` flow, so that neither manual data nor CSV data
        can be silently replaced.
        """
        for original_report in self:
            report = original_report.sudo()
            if report.state not in ("customer_confirmed", "internally_amended", "under_review"):
                raise UserError(_("Nur bestätigte Einsatzberichte können an den Spesenbericht übergeben werden."))
            report.conflict_ids.filtered(lambda item: item.state == "open").write({"state": "resolved"})
            report.write({"spesen_sync_state": "pending", "spesen_sync_message": False})
            conflicts = False
            day_groups = {}
            for member in report.member_ids:
                employee = member.employee_id
                # This workflow already runs with elevated report rights and
                # may inspect the employee's private rollout configuration.
                # Read only these two configuration fields in sudo mode;
                # normal employee access is intentionally more restrictive.
                employee_profile = employee.sudo()
                service_date = member.service_date
                key = (employee.id, service_date)
                if key in day_groups:
                    continue
                day_members = report._employee_day_members(employee, service_date)
                group = day_groups[key] = {
                    "employee": employee,
                    "service_date": service_date,
                    "members": day_members,
                }
                if employee_profile.stundenbericht_source == "csv":
                    report._create_sync_conflict(employee, "csv_duplicate", _("Der Mitarbeiter ist weiterhin auf CSV-Stundenberichte eingestellt."), service_date)
                    conflicts = True
                    continue
                if employee_profile.stundenbericht_app_active_from and service_date < employee_profile.stundenbericht_app_active_from:
                    report._create_sync_conflict(employee, "csv_duplicate", _("Der Einsatz liegt vor dem App-Umstellungsdatum des Mitarbeiters."), service_date)
                    conflicts = True
                    continue
                try:
                    group["summary"] = report._members_day_summary(day_members)
                except UserError as error:
                    report._create_sync_conflict(employee, "manual_entry", str(error), service_date)
                    conflicts = True
                    continue
                target_month = service_date.replace(day=1)
                monthly_report = report.env["nolte.expense.report"].search([
                    ("employee_id", "=", employee.id), ("month", "=", target_month),
                ], limit=1)
                if monthly_report and monthly_report.state not in ("draft", "rejected"):
                    report._create_sync_conflict(employee, "locked_month", _("Der Monatsbericht %s ist bereits gesperrt.") % monthly_report.display_name, service_date)
                    conflicts = True
                    continue
                if monthly_report:
                    daily_line = monthly_report.line_ids.filtered(lambda item: item.date == service_date)[:1]
                    if daily_line and daily_line.absence_hours:
                        report._create_sync_conflict(employee, "absence", _("Für diesen Tag ist eine Abwesenheit eingetragen."), service_date)
                        conflicts = True
                    elif daily_line and daily_line.work_report_line_id and daily_line.work_report_line_id not in day_members.mapped("work_report_line_id"):
                        report._create_sync_conflict(employee, "csv_duplicate", _("Für diesen Tag existiert bereits eine andere importierte Stundenquelle."), service_date)
                        conflicts = True
                    elif daily_line and not daily_line.work_report_line_id and (daily_line.customer or daily_line.start_time or daily_line.end_time or daily_line.break_minutes):
                        report._create_sync_conflict(employee, "manual_entry", _("Für diesen Tag existieren manuell gepflegte Monatsdaten."), service_date)
                        conflicts = True
            if conflicts:
                report.write({"spesen_sync_state": "conflict", "spesen_sync_message": _("Die Übergabe wurde wegen Prüfkonflikten nicht ausgeführt.")})
                continue

            customer = report.partner_id.display_name or report.task_id.display_name or report.name
            daily_work_reports = {}
            work_reports = self.env["nolte.work.report"]
            for group in day_groups.values():
                employee = group["employee"]
                service_date = group["service_date"]
                day_members = group["members"]
                work_line = day_members.mapped("work_report_line_id")[:1]
                if work_line and work_line.work_report_id.report_date != service_date:
                    # Older multiday syncs may have linked every day to the
                    # report's first date. Rebuild those links on the correct
                    # per-day source report rather than moving that old line.
                    work_line = self.env["nolte.work.report.line"]
                work_report = work_line.work_report_id if work_line else self.env["nolte.work.report"]
                if not work_report and report.work_report_id and report.work_report_id.report_date == service_date:
                    work_report = report.work_report_id
                if not work_report:
                    work_report = daily_work_reports.get(service_date)
                if not work_report:
                    work_report = report.env["nolte.work.report"].create({
                        "report_date": service_date,
                        "customer": customer,
                        "company_id": report.company_id.id,
                    })
                daily_work_reports.setdefault(service_date, work_report)
                work_reports |= work_report
                day_customers = ", ".join(dict.fromkeys(
                    (item.report_id.partner_id.display_name or item.report_id.task_id.display_name or item.report_id.name)
                    for item in day_members
                ))
                values = {
                    "employee_id": employee.id,
                    "description": day_customers,
                    **group["summary"],
                }
                if work_line:
                    work_line.write(values)
                else:
                    work_line = report.env["nolte.work.report.line"].create({"work_report_id": work_report.id, **values})
                day_members.write({"work_report_line_id": work_line.id})
                if service_date == report.service_date:
                    report.work_report_id = work_report
            work_reports.action_distribute()
            for group in day_groups.values():
                employee = group["employee"]
                service_date = group["service_date"]
                day_members = group["members"]
                monthly_report = report.env["nolte.expense.report"].search([
                    ("employee_id", "=", employee.id), ("month", "=", service_date.replace(day=1)),
                ], limit=1)
                work_line = day_members.mapped("work_report_line_id")[:1]
                expense_line = monthly_report.line_ids.filtered(lambda item: item.work_report_line_id == work_line)[:1]
                day_members.write({"expense_report_line_id": expense_line.id})
            report.write({"spesen_sync_state": "synchronized", "spesen_sync_message": _("An den Spesenbericht übergeben."), "server_revision": report.server_revision + 1})
            report.message_post(body=_("Zeiten an den bestehenden Spesenbericht übergeben."))
        return True

    def action_compute_billing_preview(self):
        """Calculate billable quantities without creating sales-order lines."""
        from odoo.addons.nolte_overtime_billing.services.time_allocation import allocate_with_pauses

        for original_report in self:
            report = original_report.sudo()
            if report.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill"):
                raise UserError(_("Eine Abrechnungsvorschau setzt eine Kundenbestätigung voraus."))
            for member in report.member_ids:
                intervals, pauses = [], []
                total_kilometers = 0.0
                for segment in member.segment_ids:
                    start = datetime.combine(member.service_date, datetime.strptime(segment.start_time, "%H:%M").time())
                    end = datetime.combine(member.service_date, datetime.strptime(segment.end_time, "%H:%M").time())
                    if end < start:
                        end += timedelta(days=1)
                    if segment.segment_type == "break":
                        pauses.append((start, end))
                    else:
                        kind = "work" if segment.segment_type == "work" else "travel"
                        intervals.append((start, end, kind))
                        if segment.segment_type in ("outbound_travel", "return_travel"):
                            total_kilometers += segment.kilometers
                if not intervals:
                    raise UserError(_("Für %s fehlen abrechenbare Zeitsegmente.") % member.employee_id.name)
                allocation = allocate_with_pauses(intervals, pauses)
                employee_members = report.member_ids.filtered(lambda item: item.employee_id == member.employee_id).sorted(lambda item: (item.service_date, item.id))
                assignment = report.employee_assignment_ids.filtered(lambda item: item.employee_id == member.employee_id)[:1]
                overnight_total = assignment.overnight_count if assignment else sum(employee_members.mapped("overnight_count"))
                overnight_quantity = float(overnight_total or 0) if member == employee_members[:1] else 0.0
                member.write({
                    "billing_preview": {**allocation, "kilometers": total_kilometers, "overnights": overnight_quantity, "allowance_days": 1.0},
                    "billing_state": "preview",
                })
            report.write({"server_revision": report.server_revision + 1})
            report.message_post(body=_("Abrechnungsvorschau aus Arbeits- und Fahrtsegmenten berechnet."))
        return True

    def _sale_order_service_note(self):
        """Compact customer-facing service details, without internal work text."""
        self.ensure_one()
        technicians = list(dict.fromkeys(self.member_ids.mapped("employee_id.name")))
        dates = sorted(date for date in self.member_ids.mapped("service_date") if date)
        if not dates and self.service_date:
            dates = [self.service_date]
        date_text = dates[0].strftime("%d.%m.%Y") if dates else "-"
        if dates and dates[-1] != dates[0]:
            date_text += "–%s" % dates[-1].strftime("%d.%m.%Y")
        return "\n".join([
            "Service Techniker: %s" % (", ".join(technicians) or "-"),
            "Maschinen Nr.: %s" % (self.machine_number or "-"),
            "Maschinen Typ: %s" % (self.machine_type or "-"),
            "Zeitraum: %s" % date_text,
        ])

    def _ensure_sale_order(self, partner=None):
        """Return the report's quotation, creating it at most once per report."""
        self.ensure_one()
        self.flush_recordset(["sale_order_id"])
        self.env.cr.execute(
            "SELECT id FROM nolte_service_report WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["sale_order_id"])
        if self.sale_order_id:
            return self.sale_order_id

        partner = (partner or self.partner_id).commercial_partner_id
        if not partner or not partner.active:
            raise UserError(_("Für die Verkaufsübergabe muss ein aktiver Odoo-Kunde hinterlegt sein."))
        if partner.company_id and partner.company_id != self.company_id:
            raise UserError(_("Der gewählte Kunde gehört zu einem anderen Unternehmen."))
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "company_id": self.company_id.id,
            "origin": self.name,
            "client_order_ref": self.name,
        })
        self.env["sale.order.line"].create({
            "order_id": order.id,
            "display_type": "line_note",
            "name": self._sale_order_service_note(),
            "sequence": 1,
        })
        self.write({"sale_order_id": order.id})
        self.message_post(body=_("Angebotsentwurf %(order)s für %(customer)s erstellt und verknüpft.") % {
            "order": order.name,
            "customer": partner.display_name,
        })
        return order

    def action_approve_billing(self, approved_quantities=None):
        """Create sale lines only after an explicit office approval.

        ``approved_quantities`` is keyed by member id (with legacy employee-id
        fallback). Missing values retain
        the calculated preview; a zero explicitly suppresses that billable
        quantity while keeping the raw internal time intact.
        """
        approved_quantities = approved_quantities or {}
        product_keys = {
            "work_normal": "nolte_overtime_billing.product_work_id",
            "work_ot30": "nolte_overtime_billing.product_work_ot30_id",
            "work_ot50": "nolte_overtime_billing.product_work_ot50_id",
            "travel_normal": "nolte_overtime_billing.product_travel_id",
            "travel_ot30": "nolte_overtime_billing.product_travel_ot30_id",
            "travel_ot50": "nolte_overtime_billing.product_travel_ot50_id",
            "kilometers": "nolte_overtime_billing.product_km_id",
            "overnights": "nolte_overtime_billing.product_overnight_id",
            "allowance_days": "nolte_overtime_billing.product_allowance_id",
        }
        labels = {
            "work_normal": _("Arbeitszeit"), "work_ot30": _("Arbeitszeit Überstunden 30 %"),
            "work_ot50": _("Arbeitszeit Überstunden 50 %"), "travel_normal": _("Fahrtzeit"),
            "travel_ot30": _("Fahrtzeit Überstunden 30 %"), "travel_ot50": _("Fahrtzeit Überstunden 50 %"),
            "kilometers": _("Kilometer"), "overnights": _("Übernachtung"),
            "allowance_days": _("Auslöse pro Tag"),
        }
        for original_report in self:
            report = original_report.sudo()
            report.flush_recordset(["state", "sale_order_id"])
            report.env.cr.execute(
                "SELECT id FROM nolte_service_report WHERE id = %s FOR UPDATE",
                [report.id],
            )
            report.invalidate_recordset(["state", "sale_order_id"])
            if report.state == "ready_to_bill" or (report.member_ids and all(member.billing_state == "transferred" for member in report.member_ids)):
                continue
            if report.state != "under_review":
                raise UserError(_("Die Abrechnung kann erst nach der Büroprüfung freigegeben werden."))
            if report.sale_order_id and report.sale_order_id.state not in ("draft", "sent"):
                raise UserError(_("Für die Abrechnung ist ein offener Auftrag erforderlich."))
            report._ensure_sale_order()
            existing_note_lines = report.sale_order_id.order_line.filtered(
                lambda line: line.display_type == "line_note"
            )
            service_note = report._sale_order_service_note()
            legacy_note = existing_note_lines.filtered(
                lambda line: (line.name or "").split("\n", 1)[0] == "Stundenbericht: %s" % report.name
            )[:1]
            if legacy_note:
                legacy_note.write({"name": service_note})
            if not any(line.name == service_note for line in existing_note_lines):
                report.env["sale.order.line"].create({
                    "order_id": report.sale_order_id.id,
                    "display_type": "line_note",
                    "name": service_note,
                    "sequence": 2,
                })
            if any(member.billing_state != "preview" for member in report.member_ids):
                raise UserError(_("Für alle Mitarbeiter muss zuerst eine Abrechnungsvorschau vorliegen."))
            parameters = report.env["ir.config_parameter"].sudo()
            products = {}
            for key, parameter in product_keys.items():
                value = parameters.get_param(parameter) or ""
                product = report.env["product.product"].browse(int(value)) if value.isdigit() else report.env["product.product"]
                if key not in ("kilometers", "overnights") and not product:
                    raise UserError(_("Für %s ist im Überstundenmodul kein Abrechnungsprodukt konfiguriert.") % labels[key])
                products[key] = product
            approved_by_employee = {}
            members_by_employee = {}
            for member in report.member_ids:
                preview = member.billing_preview or {}
                source = {
                    "work_normal": (preview.get("work") or {}).get("normal", 0.0),
                    "work_ot30": (preview.get("work") or {}).get("ot30", 0.0),
                    "work_ot50": (preview.get("work") or {}).get("ot50", 0.0),
                    "travel_normal": (preview.get("travel") or {}).get("normal", 0.0),
                    "travel_ot30": (preview.get("travel") or {}).get("ot30", 0.0),
                    "travel_ot50": (preview.get("travel") or {}).get("ot50", 0.0),
                    "kilometers": preview.get("kilometers", 0.0),
                    "overnights": preview.get("overnights", 0.0),
                    "allowance_days": preview.get("allowance_days", 1.0),
                }
                overrides = approved_quantities.get(str(member.id), approved_quantities.get(member.id))
                if overrides is None:
                    overrides = approved_quantities.get(str(member.employee_id.id), approved_quantities.get(member.employee_id.id, {}))
                approved = {}
                for key, calculated in source.items():
                    quantity = float(overrides[key]) if key in overrides else float(calculated)
                    if quantity < 0 or quantity > float(calculated) + 1e-6:
                        raise UserError(_("Die freigegebene Menge für %s ist ungültig.") % labels[key])
                    approved[key] = quantity
                employee_id = member.employee_id.id
                if employee_id not in approved_by_employee:
                    approved_by_employee[employee_id] = {key: 0.0 for key in product_keys}
                    members_by_employee[employee_id] = report.env["nolte.service.report.member"]
                members_by_employee[employee_id] |= member
                for key, quantity in approved.items():
                    approved_by_employee[employee_id][key] += quantity
                member.billing_approved = approved

            for employee_id, approved in approved_by_employee.items():
                employee_members = members_by_employee[employee_id].sorted("service_date")
                employee = employee_members[0].employee_id
                created_lines = report.env["sale.order.line"]
                for sequence, key in enumerate(product_keys, start=10):
                    product = products[key]
                    quantity = approved[key]
                    if not product or quantity <= 1e-6:
                        continue
                    line = report.env["sale.order.line"].new({
                        "order_id": report.sale_order_id.id,
                        "product_id": product.id,
                        "product_uom_qty": quantity,
                    })
                    if hasattr(line, "_onchange_product_id"):
                        line._onchange_product_id()
                    if hasattr(line, "_onchange_product_uom_qty"):
                        line._onchange_product_uom_qty()
                    line.product_uom_qty = quantity
                    detail = employee.name
                    if key == "allowance_days":
                        service_dates = sorted(set(employee_members.mapped("service_date")))
                        date_text = ", ".join(day.strftime("%d.%m.%Y") for day in service_dates)
                        if date_text:
                            detail += "\nAuslöse: %s" % date_text
                    product_description = line.name or product.display_name
                    line.name = "%s\n%s" % (product_description, detail)
                    line.sequence = sequence
                    created_lines |= report.env["sale.order.line"].create(line._convert_to_write(line._cache))
                employee_members.write({
                    "billing_sale_line_ids": [(6, 0, created_lines.ids)],
                    "billing_state": "transferred",
                })
            report.write({"state": "ready_to_bill", "server_revision": report.server_revision + 1})
            report.message_post(body=_("Abrechnung freigegeben und Auftragspositionen erstellt."))
        return True

    def action_open_billing_approval_wizard(self):
        self.ensure_one()
        if self.state != "under_review":
            raise UserError(_("Die Verkaufsübergabe ist nur nach der Büroprüfung möglich."))
        if self.sale_order_id and self.sale_order_id.state not in ("draft", "sent"):
            raise UserError(_("Für die Abrechnung ist kein offener Verkaufsauftrag verfügbar."))
        if any(member.billing_state == "transferred" for member in self.member_ids):
            raise UserError(_("Die Abrechnung wurde für diesen Bericht bereits an Verkauf übergeben."))
        if any(member.billing_state != "preview" for member in self.member_ids):
            self.action_compute_billing_preview()
        return {
            "type": "ir.actions.act_window",
            "name": _("Abrechnung freigeben"),
            "res_model": "nolte.service.report.billing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id},
        }

    def action_sync_after_customer_confirmation(self):
        """Transfer signed report hours to expenses and attendance automatically.

        Each integration is isolated so an existing manual attendance or an
        expense-month conflict does not roll back the customer's signature.
        Conflicts remain visible and can be retried from the report backend.
        """
        for report in self.sudo():
            try:
                with self.env.cr.savepoint():
                    report.action_sync_spesenbericht()
            except UserError as error:
                report.write({"spesen_sync_state": "conflict", "spesen_sync_message": str(error)})
            try:
                with self.env.cr.savepoint():
                    report.action_sync_attendance()
            except UserError as error:
                report.write({"attendance_sync_state": "conflict", "attendance_sync_message": str(error)})
        return True

    def action_open_sale_order_wizard(self):
        self.ensure_one()
        if self.sale_order_id:
            raise UserError(_("Für diesen Stundenbericht ist bereits ein Auftrag hinterlegt."))
        if self.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill"):
            raise UserError(_("Ein Angebotsentwurf kann erst nach der Kundenbestätigung erstellt werden."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Auftrag aus Bericht erstellen"),
            "res_model": "nolte.service.report.sale.order.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id},
        }


class NolteServiceReportMember(models.Model):
    _name = "nolte.service.report.member"
    _description = "Mitarbeiter im Nolte Einsatzbericht"
    _order = "id"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    service_date = fields.Date(string="Einsatztag", required=True, default=fields.Date.context_today, index=True)
    overnight_count = fields.Integer(string="Übernachtungen", default=0)
    segment_ids = fields.One2many("nolte.service.report.segment", "member_id", string="Zeitsegmente")
    work_report_line_id = fields.Many2one("nolte.work.report.line", string="Quelle Stundenbericht", readonly=True, copy=False)
    expense_report_line_id = fields.Many2one("nolte.expense.report.line", string="Monatszeile", readonly=True, copy=False)
    attendance_ids = fields.Many2many("hr.attendance", string="Erzeugte Anwesenheiten", readonly=True, copy=False)
    billing_state = fields.Selection([
        ("pending", "Noch nicht übertragen"),
        ("preview", "Abrechnungsvorschau"),
        ("transferred", "Übertragen"),
        ("conflict", "Konflikt"),
    ], default="pending", required=True, copy=False)
    billing_preview = fields.Json(string="Abrechnungsvorschau", readonly=True, copy=False)
    billing_approved = fields.Json(string="Freigegebene Abrechnung", readonly=True, copy=False)
    billing_sale_line_ids = fields.Many2many("sale.order.line", string="Erzeugte Auftragspositionen", readonly=True, copy=False)

    _report_employee_day_unique = models.Constraint(
        "UNIQUE(report_id, employee_id, service_date)",
        "Ein Mitarbeiter darf je Einsatztag nur einmal vorkommen.",
    )

    def init(self):
        self._cr.execute("ALTER TABLE nolte_service_report_member DROP CONSTRAINT IF EXISTS nolte_service_report_member_report_employee_unique")


class NolteServiceReportEmployee(models.Model):
    _name = "nolte.service.report.employee"
    _description = "Mitarbeiter im Einsatz"
    _order = "id"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    overnight_count = fields.Integer(string="Übernachtungen im gesamten Einsatz", default=0)

    _report_employee_unique = models.Constraint(
        "UNIQUE(report_id, employee_id)",
        "Ein Mitarbeiter darf je Einsatz nur einmal eingetragen werden.",
    )

class NolteServiceReportMaterial(models.Model):
    _name = "nolte.service.report.material"
    _description = "Material im Nolte Einsatzbericht"
    _order = "sequence, id"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    mobile_uuid = fields.Char(required=True, copy=False, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Artikel / Material", required=True)
    product_id = fields.Many2one("product.product", string="Odoo-Artikel")
    quantity = fields.Float(string="Menge", default=1.0)
    unit = fields.Char(string="Einheit", default="Stk.")
    note = fields.Char(string="Bemerkung")

    _material_uuid_unique = models.Constraint("UNIQUE(mobile_uuid)", "Die Materialkennung muss eindeutig sein.")


class NolteServiceReportChecklist(models.Model):
    _name = "nolte.service.report.checklist"
    _description = "Checklistenpunkt im Nolte Einsatzbericht"
    _order = "sequence, id"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    mobile_uuid = fields.Char(default=lambda self: str(uuid4()), required=True, copy=False, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Prüfpunkt", required=True)
    checked = fields.Boolean(string="Erledigt")
    note = fields.Char(string="Bemerkung")
    visibility = fields.Selection([
        ("internal", "Intern – nur Monteure und Prüfer"),
        ("customer", "Kundencheckliste – erscheint im PDF"),
    ], string="Sichtbarkeit", required=True, default="customer", index=True)

    _checklist_uuid_unique = models.Constraint("UNIQUE(mobile_uuid)", "Die Checklistenkennung muss eindeutig sein.")


class NolteServiceReportSegment(models.Model):
    _name = "nolte.service.report.segment"
    _description = "Zeitsegment eines Nolte Einsatzberichts"
    _order = "start_time, id"

    member_id = fields.Many2one("nolte.service.report.member", required=True, ondelete="cascade", index=True)
    report_id = fields.Many2one(related="member_id.report_id", store=True, index=True)
    segment_uuid = fields.Char(default=lambda self: str(uuid4()), required=True, copy=False, readonly=True, index=True)
    segment_type = fields.Selection([
        ("outbound_travel", "Hinfahrt"),
        ("work", "Arbeit"),
        ("return_travel", "Rückfahrt"),
        ("break", "Pause"),
    ], required=True)
    start_time = fields.Char(string="Beginn", required=True)
    end_time = fields.Char(string="Ende", required=True)
    kilometers = fields.Float(string="Kilometer")
    internal_only = fields.Boolean(string="Nur intern", default=False, copy=False)

    _segment_uuid_unique = models.Constraint(
        "UNIQUE(segment_uuid)",
        "Die mobile Segmentkennung muss eindeutig sein.",
    )

    @api.constrains("start_time", "end_time")
    def _check_quarter_hours(self):
        for segment in self:
            for value in (segment.start_time, segment.end_time):
                try:
                    hour, minute = map(int, value.split(":"))
                except (AttributeError, ValueError) as exc:
                    raise ValidationError(_("Zeitangaben müssen das Format HH:MM haben.")) from exc
                if hour not in range(24) or minute not in (0, 15, 30, 45):
                    raise ValidationError(_("Zeiten dürfen nur in 15-Minuten-Schritten erfasst werden."))


class NolteServiceReportConflict(models.Model):
    _name = "nolte.service.report.conflict"
    _description = "Konflikt im Nolte Einsatzbericht"
    _order = "create_date desc, id desc"

    report_id = fields.Many2one("nolte.service.report", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    conflict_date = fields.Date(required=True, index=True)
    conflict_type = fields.Selection([
        ("csv_duplicate", "CSV-Doppelquelle"),
        ("manual_entry", "Manueller Eintrag"),
        ("absence", "Abwesenheit"),
        ("locked_month", "Gesperrter Monatsbericht"),
        ("revision", "Versionskonflikt"),
    ], required=True)
    state = fields.Selection([("open", "Offen"), ("resolved", "Gelöst")], default="open", required=True)
    description = fields.Text(required=True)
    resolution_note = fields.Text()
    resolved_by_id = fields.Many2one("res.users", readonly=True)
    resolved_at = fields.Datetime(readonly=True)


class NolteProjectTask(models.Model):
    _inherit = "project.task"

    nolte_service_contact_id = fields.Many2one("res.partner", string="Ansprechpartner Einsatz")
    nolte_service_location = fields.Char(string="Standard-Einsatzort")
    nolte_service_location_name = fields.Char(string="Firma am Einsatzort")
    nolte_service_location_contact_name = fields.Char(string="Ansprechpartner am Einsatzort")
    nolte_service_location_contact_phone = fields.Char(string="Telefon am Einsatzort")
    nolte_machine_number = fields.Char(string="Standard-Maschinennummer")
    nolte_machine_type = fields.Char(string="Standard-Maschinentyp")
    nolte_overnight_count = fields.Integer(string="Standard-Übernachtungen", default=0)

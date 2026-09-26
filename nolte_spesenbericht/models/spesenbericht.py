from calendar import monthrange
from datetime import date, datetime, time, timedelta
import unicodedata
from zoneinfo import ZoneInfo
from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class NolteBmfRate(models.Model):
    _name = "nolte.bmf.rate"
    _description = "BMF Auslandsreisepauschale"
    _order = "year desc, country_name, location_name"
    _rec_name = "display_name"

    year = fields.Integer(string="Jahr", required=True, index=True)
    rate_key = fields.Char(string="Tarifschlüssel", required=True, index=True)
    country_name = fields.Char(string="Land", required=True, index=True)
    location_name = fields.Char(string="Ort / Gebiet")
    display_name = fields.Char(string="Bezeichnung", compute="_compute_display_name", store=True)
    full_day = fields.Monetary(string="Volltag (24 Std.)", required=True)
    partial_day = fields.Monetary(string="An-/Abreise (> 8 Std.)", required=True)
    overnight = fields.Monetary(string="Übernachtung", required=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.ref("base.EUR"))
    source_url = fields.Char(string="BMF-Quelle")
    show_in_report = fields.Boolean(
        string="Im Spesenbericht anzeigen",
        help="Zeigt diesen Tarif direkt in der kurzen Länderauswahl des Spesenberichts an.",
    )
    active = fields.Boolean(default=True)

    _year_key_unique = models.Constraint(
        "UNIQUE(year, rate_key)", "Tarifschlüssel und Jahr müssen eindeutig sein."
    )

    @api.depends("country_name", "location_name", "year")
    def _compute_display_name(self):
        for rate in self:
            location = " (%s)" % rate.location_name if rate.location_name and rate.location_name.strip().lower() != "im übrigen" else ""
            rate.display_name = "%s%s - %s" % (rate.country_name or "", location, rate.year or "")

    def action_recompute_reports(self):
        years = {rate.year for rate in self if rate.year}
        keys = {rate.rate_key for rate in self if rate.rate_key}
        lines = self.env["nolte.expense.report.line"].search([
            ("country", "in", list(keys)),
            ("date", ">=", date(min(years), 1, 1)),
            ("date", "<=", date(max(years), 12, 31)),
        ]) if years and keys else self.env["nolte.expense.report.line"]
        lines._compute_allowance()
        return True


class NolteExpenseConfig(models.Model):
    _name = "nolte.expense.config"
    _description = "Nolte Spesenbericht Konfiguration"
    _rec_name = "company_id"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
    travel_product_id = fields.Many2one("product.product", string="Produkt Verpflegung/Reise", required=True)
    hotel_product_id = fields.Many2one("product.product", string="Produkt Hotel", required=True)
    other_product_id = fields.Many2one("product.product", string="Produkt sonstige Auslagen", required=True)
    active = fields.Boolean(default=True)

    _company_unique = models.Constraint("UNIQUE(company_id)", "Für jedes Unternehmen darf es nur eine Konfiguration geben.")


class NolteWorkReport(models.Model):
    _name = "nolte.work.report"
    _description = "Gemeinsamer Stundenbericht"
    _order = "report_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Berichtsnummer", required=True, default=lambda self: _("Neu"), tracking=True)
    report_date = fields.Date(string="Datum", required=True, default=fields.Date.context_today, index=True, tracking=True)
    customer = fields.Char(string="Kunde / Projekt", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True, ondelete="cascade"
    )
    line_ids = fields.One2many("nolte.work.report.line", "work_report_id", string="Mitarbeiter", copy=True)
    original_file = fields.Binary(string="Original-Stundenbericht", attachment=True, copy=False)
    original_filename = fields.Char(string="Dateiname", copy=False)
    state = fields.Selection(
        [("draft", "In Bearbeitung"), ("distributed", "Verteilt")],
        default="draft", required=True, tracking=True,
    )
    distributed_at = fields.Datetime(string="Verteilt am", readonly=True, copy=False)
    distributed_by_id = fields.Many2one("res.users", string="Verteilt von", readonly=True, copy=False)
    employee_count = fields.Integer(string="Anzahl Mitarbeiter", compute="_compute_employee_count")

    @api.depends("line_ids.employee_id")
    def _compute_employee_count(self):
        for report in self:
            report.employee_count = len(report.line_ids.filtered("employee_id"))

    def action_set_draft(self):
        self.write({"state": "draft"})

    def action_distribute(self):
        """Create or update one personal monthly report for every employee line."""
        ExpenseReport = self.env["nolte.expense.report"]
        ExpenseLine = self.env["nolte.expense.report.line"]
        for work_report in self:
            if not work_report.line_ids:
                raise UserError(_("Bitte mindestens einen Mitarbeiter eintragen."))
            affected_reports = ExpenseReport
            for work_line in work_report.line_ids:
                if not work_line.employee_id:
                    raise UserError(_("In jeder Zeile muss ein Mitarbeiter ausgewählt sein."))
                month = work_report.report_date.replace(day=1)
                expense_report = ExpenseReport.search([
                    ("employee_id", "=", work_line.employee_id.id),
                    ("month", "=", month),
                ], limit=1)
                if not expense_report:
                    expense_report = ExpenseReport.create({
                        "employee_id": work_line.employee_id.id,
                        "month": month,
                    })
                if expense_report.state not in ("draft", "rejected"):
                    raise UserError(_(
                        "Der Monatsbericht von %s ist bereits gesperrt und kann nicht ergänzt werden."
                    ) % work_line.employee_id.name)

                day_line = expense_report.line_ids.filtered(
                    lambda item: item.date == work_report.report_date
                )[:1]
                if day_line and day_line.work_report_line_id != work_line:
                    has_manual_time = bool(
                        day_line.start_time or day_line.end_time or day_line.break_minutes or day_line.customer
                    )
                    if has_manual_time or day_line.absence_hours:
                        raise UserError(_(
                            "Für %s existieren am %s bereits manuelle Arbeits- oder Abwesenheitsdaten. "
                            "Diese wurden nicht überschrieben."
                        ) % (work_line.employee_id.name, fields.Date.to_string(work_report.report_date)))

                vals = {
                    "report_id": expense_report.id,
                    "date": work_report.report_date,
                    "customer": work_line.description or work_report.customer,
                    "start_time": work_line.start_time,
                    "end_time": work_line.end_time,
                    "break_minutes": work_line.break_minutes,
                    "work_report_line_id": work_line.id,
                }
                if day_line:
                    day_line.write(vals)
                else:
                    ExpenseLine.create(vals)
                affected_reports |= expense_report

            affected_reports.sync_automatic_travel_allowances()
            work_report.write({
                "state": "distributed",
                "distributed_at": fields.Datetime.now(),
                "distributed_by_id": self.env.user.id,
            })
        return True


class NolteWorkReportLine(models.Model):
    _name = "nolte.work.report.line"
    _description = "Mitarbeiterzeile eines Stundenberichts"
    _order = "id"

    work_report_id = fields.Many2one("nolte.work.report", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="work_report_id.company_id", store=True, index=True)
    employee_id = fields.Many2one(
        "hr.employee", string="Mitarbeiter", required=True, index=True,
        domain="[('company_id', '=', company_id)]",
    )
    description = fields.Char(string="Abweichende Tätigkeit / Projekt")
    start_time = fields.Char(string="Start", required=True, default="08:00")
    end_time = fields.Char(string="Ende", required=True, default="16:00")
    break_minutes = fields.Integer(string="Pause (Min.)", default=0)
    work_hours = fields.Float(string="Arbeitszeit", compute="_compute_work_hours", store=True)

    _employee_report_unique = models.Constraint(
        "UNIQUE(work_report_id, employee_id)",
        "Ein Mitarbeiter darf in einem Stundenbericht nur einmal vorkommen.",
    )

    @api.depends("start_time", "end_time", "break_minutes")
    def _compute_work_hours(self):
        for line in self:
            line.work_hours = self._duration(line.start_time, line.end_time, line.break_minutes)

    @api.model
    def _duration(self, start_value, end_value, break_minutes=0):
        try:
            start_h, start_m = map(int, (start_value or "").split(":"))
            end_h, end_m = map(int, (end_value or "").split(":"))
            minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
            if minutes < 0:
                minutes += 24 * 60
            return max(0, minutes - (break_minutes or 0)) / 60.0
        except (ValueError, AttributeError):
            return 0.0

    @api.constrains("start_time", "end_time")
    def _check_quarter_hours(self):
        for line in self:
            for value in (line.start_time, line.end_time):
                try:
                    hour, minute = map(int, (value or "").split(":"))
                except ValueError as exc:
                    raise ValidationError(_("Zeitangaben müssen das Format HH:MM haben.")) from exc
                if hour not in range(24) or minute not in (0, 15, 30, 45):
                    raise ValidationError(_("Zeiten dürfen nur in 15-Minuten-Schritten erfasst werden."))


class NolteExpenseReport(models.Model):
    _name = "nolte.expense.report"
    _description = "Monatlicher Spesenbericht"
    _order = "month desc, employee_id"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    month = fields.Date(required=True, index=True, tracking=True, help="Erster Tag des Berichtsmonats")
    state = fields.Selection([
        ("draft", "In Bearbeitung"), ("submitted", "Eingereicht"),
        ("approved", "Freigegeben"), ("exported", "An Odoo übergeben"),
        ("rejected", "Zur Korrektur"),
    ], default="draft", required=True, tracking=True)
    line_ids = fields.One2many("nolte.expense.report.line", "report_id", copy=True)
    expense_ids = fields.One2many("hr.expense", "nolte_report_id", string="Erzeugte Odoo-Spesen", readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    total_work_hours = fields.Float(compute="_compute_totals", store=True)
    total_overtime_hours = fields.Float(compute="_compute_totals", store=True)
    total_allowance = fields.Monetary(compute="_compute_totals", store=True)
    total_hotel = fields.Monetary(compute="_compute_totals", store=True)
    total_expenses = fields.Monetary(compute="_compute_totals", store=True)
    attachment_count = fields.Integer(string="Belege", compute="_compute_attachment_count")
    total_amount = fields.Monetary(
        string="Gesamtsumme",
        compute="_compute_totals",
        store=True,
        help="Summe aus Verpflegungspauschalen, Hotelkosten und sonstigen Auslagen.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    _employee_month_unique = models.Constraint("UNIQUE(employee_id, month)", "Für Mitarbeiter und Monat existiert bereits ein Bericht.")

    @api.depends("employee_id.name", "month")
    def _compute_name(self):
        for report in self:
            report.name = "%s · %s" % (report.employee_id.name or _("Mitarbeiter"), report.month.strftime("%m/%Y") if report.month else "")

    @api.depends(
        "line_ids.work_hours", "line_ids.allowance", "line_ids.hotel_amount", "line_ids.expense_amount",
        "employee_id.resource_calendar_id",
        "employee_id.resource_calendar_id.attendance_ids.hour_from",
        "employee_id.resource_calendar_id.attendance_ids.hour_to",
        "employee_id.resource_calendar_id.attendance_ids.dayofweek",
        "employee_id.resource_calendar_id.attendance_ids.day_period",
        "employee_id.resource_calendar_id.attendance_ids.duration_hours",
        "employee_id.resource_calendar_id.attendance_ids.duration_based",
        "employee_id.resource_calendar_id.attendance_ids.date",
        "employee_id.resource_calendar_id.attendance_ids.recurrency",
        "employee_id.resource_calendar_id.attendance_ids.recurrency_type",
        "employee_id.resource_calendar_id.attendance_ids.recurrency_interval",
        "employee_id.resource_calendar_id.attendance_ids.recurrency_until",
        "employee_id.resource_calendar_id.attendance_ids.recurrency_excluded_occurences",
        "employee_id.resource_calendar_id.global_leave_ids.date_from",
        "employee_id.resource_calendar_id.global_leave_ids.date_to",
        "company_id.resource_calendar_id", "month",
    )
    def _compute_totals(self):
        for report in self:
            report.total_work_hours = sum(report.line_ids.mapped("work_hours"))
            report.total_overtime_hours = report.total_work_hours - report._get_target_month_hours()
            report.total_allowance = sum(report.line_ids.mapped("allowance"))
            report.total_hotel = sum(report.line_ids.mapped("hotel_amount"))
            report.total_expenses = sum(report.line_ids.mapped("expense_amount"))
            report.total_amount = report.total_allowance + report.total_hotel + report.total_expenses

    def _get_target_month_hours(self):
        self.ensure_one()
        if not self.month:
            return 0.0
        calendar = self.employee_id.resource_calendar_id or self.company_id.resource_calendar_id
        if not calendar:
            days = monthrange(self.month.year, self.month.month)[1]
            return sum(8.0 for day in range(1, days + 1) if date(self.month.year, self.month.month, day).weekday() < 5)
        next_month = (self.month.replace(day=28) + timedelta(days=4)).replace(day=1)
        calendar_tz = ZoneInfo(self.company_id.tz or self.env.company.tz or "UTC")
        start_dt = datetime.combine(self.month, time.min, tzinfo=calendar_tz)
        end_dt = datetime.combine(next_month, time.min, tzinfo=calendar_tz)
        return calendar.get_work_hours_count(start_dt, end_dt, compute_leaves=True)

    @api.depends("line_ids.attachment_ids")
    def _compute_attachment_count(self):
        for report in self:
            report.attachment_count = len(report.line_ids.mapped("attachment_ids"))

    def _print_time(self, value):
        minutes = round((value or 0.0) * 60)
        sign = "-" if minutes < 0 else ""
        minutes = abs(minutes)
        return "%s%d:%02d" % (sign, minutes // 60, minutes % 60)

    def _print_money(self, value):
        return ("%0.2f" % (value or 0.0)).replace(".", ",")

    def _print_time_nonzero(self, value):
        """Keep empty PDF cells quiet while retaining signed non-zero times."""
        return self._print_time(value) if round((value or 0.0) * 60) else ""

    def _print_money_nonzero(self, value):
        """Do not fill the monthly PDF with visually redundant zero amounts."""
        return self._print_money(value) if round((value or 0.0) * 100) else ""

    def _print_ascii(self, value):
        text = value or ""
        for source, target in (
            ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"),
            ("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
            ("·", "-"), ("–", "-"),
        ):
            text = text.replace(source, target)
        return text

    def _print_state(self):
        self.ensure_one()
        return {
            "draft": "In Bearbeitung", "submitted": "Eingereicht",
            "approved": "Freigegeben", "exported": "An Odoo uebergeben",
            "rejected": "Zur Korrektur",
        }.get(self.state, self.state)

    def _print_rows(self):
        self.ensure_one()
        lines = {line.date.day: line for line in self.line_ids}
        rates = self.env["nolte.bmf.rate"].search([
            ("year", "=", self.month.year), ("active", "=", True),
        ])
        rate_labels = {
            rate.rate_key: "%s%s" % (
                rate.country_name,
                " (%s)" % rate.location_name
                if rate.location_name and rate.location_name.strip().lower() != "im übrigen"
                else "",
            )
            for rate in rates
        }
        travel_labels = {"single": "Über 8 Std.", "arrival": "Anreise", "full": "Volltag", "departure": "Abreise"}
        weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        rows = []
        for day in range(1, monthrange(self.month.year, self.month.month)[1] + 1):
            row_date = date(self.month.year, self.month.month, day)
            line = lines.get(day)
            travel = "-"
            if line and line.country:
                travel = rate_labels.get(line.country, line.country)
                if line.travel_type:
                    travel += " · " + travel_labels.get(line.travel_type, line.travel_type)
                deductions = "".join([
                    "F" if line.breakfast else "",
                    "M" if line.lunch else "",
                    "A" if line.dinner else "",
                ])
                if deductions:
                    travel += " · Abzug " + deductions
            allowance = line.allowance if line else 0.0
            hotel = line.hotel_amount if line else 0.0
            expenses = line.expense_amount if line else 0.0
            rows.append({
                "day": day,
                "date": row_date.strftime("%d.%m."),
                "weekday": weekdays[row_date.weekday()],
                "customer": self._print_ascii(line.customer or line.absence_name or "-") if line else "-",
                "start": (line.start_time or "-") if line else "-",
                "end": (line.end_time or "-") if line else "-",
                "break": (str(line.break_minutes) if line.break_minutes else "-") if line else "-",
                "work": self._print_time_nonzero(line.work_hours if line else 0.0),
                "travel": self._print_ascii(travel),
                "allowance": self._print_money_nonzero(allowance),
                "hotel": self._print_money_nonzero(hotel),
                "expenses": self._print_money_nonzero(expenses),
                "sum": self._print_money_nonzero(allowance + hotel + expenses),
            })
        return rows

    def action_view_attachments(self):
        self.ensure_one()
        attachments = self.line_ids.mapped("attachment_ids")
        attachment_view = self.env.ref("nolte_spesenbericht.view_nolte_receipt_attachment_list")
        return {
            "type": "ir.actions.act_window",
            "name": _("Belege · %s") % self.name,
            "res_model": "ir.attachment",
            "view_mode": "list",
            "views": [(attachment_view.id, "list")],
            "domain": [("id", "in", attachments.ids)],
            "context": {"create": False},
        }

    def action_submit(self):
        for report in self:
            if report.state not in ("draft", "rejected"):
                raise UserError(_("Nur bearbeitbare Berichte können eingereicht werden."))
            missing = report.line_ids.filtered("rate_missing")
            if missing:
                raise UserError(_(
                    "Für mindestens einen Reisetag fehlt ein BMF-Tarif für das betreffende Jahr."
                ))
            report.write({"state": "submitted", "submitted_at": fields.Datetime.now()})
            report._notify_approvers_submitted()

    def _notify_approvers_submitted(self):
        """Queue one notification per active approver with an email address."""
        approver_group = self.env.ref("nolte_spesenbericht.group_spesenbericht_approver")
        base_url = self.env["ir.config_parameter"].sudo().get_str("web.base.url", "")
        for report in self:
            recipients = approver_group.sudo().user_ids.filtered(
                lambda user: user.active
                and user.partner_id.email
                and report.company_id in user.company_ids
            )
            report_url = "%s/web#id=%s&model=nolte.expense.report&view_type=form" % (
                base_url.rstrip("/"), report.id,
            )
            month_label = report.month.strftime("%m/%Y")
            for user in recipients:
                body = """
                    <p>Hallo %s,</p>
                    <p><strong>%s</strong> hat den Spesenbericht für <strong>%s</strong> eingereicht.</p>
                    <p><a href="%s">Spesenbericht prüfen</a></p>
                """ % (
                    escape(user.name or ""),
                    escape(report.employee_id.name or ""),
                    escape(month_label),
                    escape(report_url),
                )
                self.env["mail.mail"].sudo().create({
                    "subject": "Spesenbericht eingereicht: %s · %s" % (
                        report.employee_id.name, month_label,
                    ),
                    "body_html": body,
                    "email_to": user.partner_id.email,
                    "email_from": report.company_id.email or self.env.user.email_formatted,
                    "auto_delete": True,
                })

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_approve(self):
        if not self.env.user.has_group("nolte_spesenbericht.group_spesenbericht_approver"):
            raise UserError(_("Sie besitzen keine Freigabeberechtigung."))
        for report in self:
            if report.state != "submitted":
                raise UserError(_("Nur eingereichte Berichte können freigegeben werden."))
            report.write({"state": "approved", "approved_at": fields.Datetime.now(), "approved_by_id": self.env.user.id})

    def action_create_expenses(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Der Bericht muss zuerst freigegeben werden."))
        config = self.env["nolte.expense.config"].search([("company_id", "=", self.company_id.id)], limit=1)
        if not config:
            raise UserError(_("Bitte zuerst die Spesenprodukte konfigurieren."))
        created_expenses = self.env["hr.expense"]
        for line in self.line_ids:
            line_expenses = {}
            for expense_kind, product, amount, label in [
                ("travel", config.travel_product_id, line.allowance, _("Verpflegung/Reise")),
                ("hotel", config.hotel_product_id, line.hotel_amount, _("Hotel")),
                ("other", config.other_product_id, line.expense_amount, _("Sonstige Auslagen")),
            ]:
                if not amount:
                    continue
                vals = {"name": "%s · %s" % (label, line.date.strftime("%d.%m.%Y")), "employee_id": self.employee_id.id, "date": line.date, "product_id": product.id}
                expense_fields = self.env["hr.expense"]._fields
                vals["nolte_report_id"] = self.id
                if "total_amount_currency" in expense_fields:
                    vals["total_amount_currency"] = amount
                elif "price_unit" in expense_fields:
                    vals.update({"price_unit": amount, "quantity": 1.0})
                expense = self.env["hr.expense"].create(vals)
                created_expenses |= expense
                line_expenses[expense_kind] = expense
            receipt_expense = line_expenses.get("hotel") or line_expenses.get("other") or line_expenses.get("travel")
            if receipt_expense:
                for attachment in line.attachment_ids:
                    attachment.copy({"res_model": "hr.expense", "res_id": receipt_expense.id})
        self.write({"state": "exported"})
        return {
            "type": "ir.actions.act_window",
            "name": _("Erzeugte Odoo-Spesen"),
            "res_model": "hr.expense",
            "view_mode": "list,form",
            "domain": [("id", "in", created_expenses.ids)],
            "context": {"search_default_group_nolte_month": 1},
        }

    def sync_approved_leaves(self):
        self.ensure_one()
        self.line_ids.filtered(lambda line: line.absence_source == "odoo").write({
            "absence_name": False, "absence_hours": 0.0, "absence_source": False,
        })
        month_start = self.month
        month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
        leaves = self.env["hr.leave"].sudo().search([
            ("employee_id", "=", self.employee_id.id), ("state", "=", "validate"),
            ("date_from", "<=", datetime.combine(month_end, time.max)),
            ("date_to", ">=", datetime.combine(month_start, time.min)),
        ])
        for leave in leaves:
            current = max(fields.Datetime.to_datetime(leave.date_from).date(), month_start)
            end = min(fields.Datetime.to_datetime(leave.date_to).date(), month_end)
            while current <= end:
                if current.weekday() < 5:
                    line = self.line_ids.filtered(lambda item: item.date == current)[:1]
                    if not line:
                        line = self.env["nolte.expense.report.line"].create({"report_id": self.id, "date": current})
                    half = bool(getattr(leave, "request_unit_half", False)) or getattr(leave, "number_of_days_display", 1.0) == 0.5
                    line.write({"absence_name": leave.holiday_status_id.name, "absence_hours": 4.0 if half else 8.0, "absence_source": "odoo"})
                current += timedelta(days=1)
        return len(leaves)

    def sync_automatic_travel_allowances(self):
        """Infer single-day or multi-day travel without overwriting manual data."""
        for report in self:
            lines = report.line_ids.sorted("date")
            travel_run_line_ids = set()
            runs = []

            # A CSV hours report describes one continuous customer assignment. Keep
            # that sequence intact even when no hotel type has been selected yet and
            # when a weekend lies between two imported working days.
            imported_runs = {}
            for line in lines.filtered("travel_sequence_key"):
                imported_runs.setdefault(line.travel_sequence_key, self.env["nolte.expense.report.line"])
                imported_runs[line.travel_sequence_key] |= line
            for imported_run in imported_runs.values():
                imported_run = imported_run.sorted("date")
                if len(imported_run) >= 2:
                    runs.append(imported_run)
                    travel_run_line_ids.update(imported_run.ids)

            current_run = []
            for line in lines:
                if line.id in travel_run_line_ids:
                    if len(current_run) >= 2 and any(item.hotel_mode for item in current_run):
                        runs.append(current_run)
                    current_run = []
                    continue
                is_work_line = bool(line.customer and (line.start_time or line.end_time) and not line.absence_hours)
                continues = bool(
                    current_run
                    and is_work_line
                    and line.customer == current_run[-1].customer
                    and (line.date - current_run[-1].date).days == 1
                )
                if continues:
                    current_run.append(line)
                else:
                    if len(current_run) >= 2 and any(item.hotel_mode for item in current_run):
                        runs.append(current_run)
                    current_run = [line] if is_work_line else []
            if len(current_run) >= 2 and any(item.hotel_mode for item in current_run):
                runs.append(current_run)

            for run in runs:
                for index, line in enumerate(run):
                    travel_run_line_ids.add(line.id)
                    desired_type = "arrival" if index == 0 else ("departure" if index == len(run) - 1 else "full")
                    if not line.travel_type or line.travel_type_automatic:
                        line.write({
                            "country": line.country or "DE",
                            "travel_type": desired_type,
                            "travel_type_automatic": True,
                        })

            for line in lines:
                if line.id in travel_run_line_ids:
                    continue
                eligible = line.work_hours > 8.0 and not line.absence_hours
                if eligible and (not line.travel_type or line.travel_type_automatic):
                    line.write({
                        "country": line.country or "DE",
                        "travel_type": "single",
                        "travel_type_automatic": True,
                    })
                elif not eligible and line.travel_type_automatic:
                    line.write({
                        "country": False,
                        "travel_type": False,
                        "travel_type_automatic": False,
                    })


class ResCompany(models.Model):
    _inherit = "res.company"

    nolte_overtime_export_employee_ids = fields.Many2many(
        "hr.employee",
        "nolte_overtime_export_company_employee_rel",
        "company_id",
        "employee_id",
        string="Mitarbeiter im Überstundenexport",
    )
    nolte_overtime_export_selection_configured = fields.Boolean(default=False)


class NolteOvertimeExportWizard(models.TransientModel):
    _name = "nolte.overtime.export.wizard"
    _description = "Überstunden-Jahresübersicht exportieren"

    year = fields.Integer(
        string="Jahr", required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    company_id = fields.Many2one(
        "res.company", string="Unternehmen", required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [("id", "in", self.env.companies.ids)],
    )
    include_drafts = fields.Boolean(
        string="Entwürfe einbeziehen",
        help="Bezieht auch noch nicht eingereichte Monatsberichte in die Übersicht ein.",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Mitarbeiter",
        required=False,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self._default_employee_ids(),
        help="Diese Auswahl wird beim PDF-Export gespeichert und beim nächsten Export wieder verwendet.",
    )

    @api.model
    def _default_employee_ids(self):
        company = self.env.company
        if company.nolte_overtime_export_selection_configured:
            return company.nolte_overtime_export_employee_ids
        return self.env["hr.employee"].search([("company_id", "=", company.id), ("active", "=", True)])

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if not self.company_id:
            self.employee_ids = [(5, 0, 0)]
        elif self.company_id.nolte_overtime_export_selection_configured:
            self.employee_ids = self.company_id.nolte_overtime_export_employee_ids
        else:
            self.employee_ids = self.env["hr.employee"].search([
                ("company_id", "=", self.company_id.id), ("active", "=", True),
            ])

    @api.constrains("year")
    def _check_year(self):
        for wizard in self:
            if wizard.year < 2000 or wizard.year > 2100:
                raise ValidationError(_("Bitte ein Jahr zwischen 2000 und 2100 eintragen."))

    def action_export_pdf(self):
        self.ensure_one()
        if not self.env.user.has_group("nolte_spesenbericht.group_spesenbericht_manager"):
            raise UserError(_("Sie besitzen keine Berechtigung für den Überstundenexport."))
        self.company_id.sudo().write({
            "nolte_overtime_export_employee_ids": [(6, 0, self.employee_ids.ids)],
            "nolte_overtime_export_selection_configured": True,
        })
        return self.env.ref("nolte_spesenbericht.action_report_overtime_year").report_action(self)

    def _overtime_report_data(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("employee_id", "in", self.employee_ids.ids),
            ("month", ">=", date(self.year, 1, 1)),
            ("month", "<=", date(self.year, 12, 31)),
        ]
        if not self.include_drafts:
            domain.append(("state", "in", ("submitted", "approved", "exported")))
        reports = self.env["nolte.expense.report"].search(domain, order="employee_id, month")
        employees = reports.mapped("employee_id").sorted(lambda employee: employee.name or "")
        report_by_key = {(report.employee_id.id, report.month.month): report for report in reports}
        rows = []
        for employee in employees:
            worked, target, balance = [], [], []
            for month in range(1, 13):
                report = report_by_key.get((employee.id, month))
                worked.append(report.total_work_hours if report else None)
                target.append(report._get_target_month_hours() if report else None)
                balance.append(report.total_overtime_hours if report else None)
            rows.append({
                "employee": employee.name,
                "worked": worked,
                "target": target,
                "balance": balance,
                "worked_total": sum(value for value in worked if value is not None),
                "target_total": sum(value for value in target if value is not None),
                "balance_total": sum(value for value in balance if value is not None),
            })
        return {
            "rows": rows,
            "months": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
            "include_drafts": self.include_drafts,
        }

    def _format_hours(self, value):
        if value is None:
            return "-"
        minutes = round(value * 60)
        sign = "-" if minutes < 0 else ""
        minutes = abs(minutes)
        return "%s%d:%02d" % (sign, minutes // 60, minutes % 60)

    def _ascii(self, value):
        text = (value or "").replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
        text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


class NolteExpenseReportLine(models.Model):
    _name = "nolte.expense.report.line"
    _description = "Spesenbericht Tageszeile"
    _order = "date"

    report_id = fields.Many2one("nolte.expense.report", required=True, ondelete="cascade", index=True)
    date = fields.Date(required=True, index=True)
    customer = fields.Char(string="Kunde / Projekt")
    start_time = fields.Char()
    end_time = fields.Char()
    break_minutes = fields.Integer()
    work_hours = fields.Float(compute="_compute_work", store=True)
    overtime_hours = fields.Float(compute="_compute_work", store=True)
    country = fields.Char(string="BMF-Tarifschlüssel", index=True)
    travel_type = fields.Selection([
        ("single", "Über 8 Std."),
        ("arrival", "Anreise"),
        ("full", "Volltag"),
        ("departure", "Abreise"),
    ])
    travel_type_automatic = fields.Boolean(
        string="Reisetag automatisch",
        default=False,
        copy=False,
        help="Land und Reisetag wurden automatisch aus einer Arbeitszeit von mehr als acht Stunden gesetzt.",
    )
    travel_sequence_key = fields.Char(
        string="Importierte Reisefolge",
        index=True,
        copy=False,
        readonly=True,
        help="Verbindet die Tage eines gemeinsam importierten mehrtägigen Stundenberichts.",
    )
    breakfast = fields.Boolean()
    lunch = fields.Boolean()
    dinner = fields.Boolean()
    allowance = fields.Monetary(compute="_compute_allowance", store=True)
    rate_missing = fields.Boolean(string="BMF-Tarif fehlt", compute="_compute_rate_missing")
    hotel_mode = fields.Selection([("flat", "Pauschale"), ("receipt", "Beleg")])
    hotel_input = fields.Monetary(string="Hotelbetrag")
    hotel_amount = fields.Monetary(compute="_compute_allowance", store=True)
    expense_amount = fields.Monetary(string="Sonstige Auslagen")
    currency_id = fields.Many2one(related="report_id.currency_id")
    absence_name = fields.Char()
    absence_hours = fields.Float()
    absence_source = fields.Selection([("odoo", "Odoo"), ("manual", "Manuell")])
    attachment_ids = fields.Many2many("ir.attachment", "nolte_expense_line_attachment_rel", "line_id", "attachment_id", string="Belege")
    work_report_line_id = fields.Many2one(
        "nolte.work.report.line", string="Quelle Stundenbericht", index=True,
        ondelete="set null", copy=False, readonly=True,
    )

    _report_date_unique = models.Constraint("UNIQUE(report_id, date)", "Für diesen Tag existiert bereits eine Zeile.")

    @api.depends("start_time", "end_time", "break_minutes", "absence_hours")
    def _compute_work(self):
        for line in self:
            if line.absence_hours:
                line.work_hours, line.overtime_hours = line.absence_hours, 0.0
                continue
            try:
                start_h, start_m = map(int, (line.start_time or "").split(":"))
                end_h, end_m = map(int, (line.end_time or "").split(":"))
                minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
                if minutes < 0:
                    minutes += 24 * 60
                minutes = max(0, minutes - (line.break_minutes or 0))
            except (ValueError, AttributeError):
                minutes = 0
            line.work_hours = minutes / 60.0
            line.overtime_hours = 0.0

    def _bmf_rate(self):
        self.ensure_one()
        if not self.country or not self.date:
            return self.env["nolte.bmf.rate"]
        return self.env["nolte.bmf.rate"].search([
            ("year", "=", self.date.year),
            ("rate_key", "=", self.country),
            ("active", "=", True),
        ], limit=1)

    @api.depends("country", "travel_type", "hotel_mode", "date")
    def _compute_rate_missing(self):
        for line in self:
            needs_rate = bool(line.country and (line.travel_type or line.hotel_mode == "flat"))
            line.rate_missing = needs_rate and not bool(line._bmf_rate())

    @api.depends("country", "travel_type", "breakfast", "lunch", "dinner", "hotel_mode", "hotel_input", "date")
    def _compute_allowance(self):
        for line in self:
            rate = line._bmf_rate()
            full = rate.full_day if rate else 0.0
            gross = full if line.travel_type == "full" else (rate.partial_day if rate and line.travel_type else 0.0)
            deduction = full * ((0.2 if line.breakfast else 0.0) + (0.4 if line.lunch else 0.0) + (0.4 if line.dinner else 0.0))
            line.allowance = max(0.0, gross - min(gross, deduction))
            line.hotel_amount = (rate.overnight if rate else 0.0) if line.hotel_mode == "flat" else line.hotel_input

    @api.constrains("start_time", "end_time")
    def _check_quarter_hours(self):
        for line in self:
            for value in (line.start_time, line.end_time):
                if value:
                    try:
                        hour, minute = map(int, value.split(":"))
                    except ValueError as exc:
                        raise ValidationError(_("Zeitangaben müssen das Format HH:MM haben.")) from exc
                    if hour not in range(24) or minute not in (0, 15, 30, 45):
                        raise ValidationError(_("Zeiten dürfen nur in 15-Minuten-Schritten erfasst werden."))


class HrExpense(models.Model):
    _inherit = "hr.expense"

    nolte_report_id = fields.Many2one("nolte.expense.report", string="Nolte Spesenbericht", index=True, ondelete="set null", copy=False)
    nolte_month_reference = fields.Char(
        string="Monatsreferenz",
        related="nolte_report_id.name",
        store=True,
        index=True,
        readonly=True,
        help="Gemeinsame Referenz für alle Einzelpositionen eines Mitarbeiters und Monats.",
    )


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def action_open_nolte_receipt(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=0" % self.id,
            "target": "new",
        }

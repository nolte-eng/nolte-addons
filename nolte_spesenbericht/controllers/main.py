from base64 import b64encode
from calendar import monthrange
from datetime import date

from odoo import fields, http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.http.stream import content_disposition


class NolteSpesenberichtController(http.Controller):

    def _is_manager(self):
        return request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_manager")

    def _employee(self, employee_id=None):
        own_employee = request.env["hr.employee"].search([("user_id", "=", request.env.user.id)], limit=1)
        if employee_id:
            employee = request.env["hr.employee"].browse(int(employee_id)).exists()
            if not employee or employee.company_id not in request.env.companies:
                raise AccessError(_("Kein Zugriff auf diesen Mitarbeiter."))
            if not self._is_manager():
                if not own_employee or employee.id != own_employee.id:
                    raise AccessError(_("Sie dürfen keine anderen Mitarbeiter auswählen."))
                return own_employee
            return employee
        employee = own_employee
        if not employee and self._is_manager():
            employee = request.env["hr.employee"].search([("company_id", "in", request.env.companies.ids)], order="name", limit=1)
        if not employee:
            raise UserError(_("Für den angemeldeten Benutzer ist kein Mitarbeiter hinterlegt."))
        return employee

    def _report(self, month_value, create=True, employee_id=None):
        employee = self._employee(employee_id)
        month = fields.Date.to_date(month_value).replace(day=1)
        report = request.env["nolte.expense.report"].search([("employee_id", "=", employee.id), ("month", "=", month)], limit=1)
        if not report and create:
            report = request.env["nolte.expense.report"].create({"employee_id": employee.id, "month": month})
        return report

    def _serialize(self, report):
        rates = request.env["nolte.bmf.rate"].search([
            ("year", "=", report.month.year), ("active", "=", True),
        ], order="country_name, location_name")
        rate_labels = {
            rate.rate_key: "%s%s" % (
                rate.country_name,
                " (%s)" % rate.location_name if rate.location_name and rate.location_name.strip().lower() != "im übrigen" else "",
            )
            for rate in rates
        }
        rows = {line.date.day: line for line in report.line_ids}
        days = monthrange(report.month.year, report.month.month)[1]
        result = []
        for day in range(1, days + 1):
            line = rows.get(day)
            result.append({
                "id": line.id if line else False, "day": day,
                "date": date(report.month.year, report.month.month, day).isoformat(),
                "weekday": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][date(report.month.year, report.month.month, day).weekday()],
                "customer": line.customer if line else "", "start": line.start_time if line else "",
                "end": line.end_time if line else "", "breakMinutes": line.break_minutes if line else 0,
                "workHours": line.work_hours if line else 0, "overtimeHours": line.overtime_hours if line else 0,
                "country": line.country if line else False, "travelType": line.travel_type if line else False,
                "countryLabel": rate_labels.get(line.country, line.country or "") if line else "",
                "rateMissing": line.rate_missing if line else False,
                "travelTypeAutomatic": line.travel_type_automatic if line else False,
                "breakfast": line.breakfast if line else False, "lunch": line.lunch if line else False,
                "dinner": line.dinner if line else False, "allowance": line.allowance if line else 0,
                "hotelMode": line.hotel_mode if line else False, "hotel": line.hotel_input if line else 0,
                "hotelAmount": line.hotel_amount if line else 0, "expenses": line.expense_amount if line else 0,
                "absenceName": line.absence_name if line else False, "absenceHours": line.absence_hours if line else 0,
                "attachmentCount": len(line.attachment_ids) if line else 0,
                "attachments": [{
                    "id": attachment.id,
                    "name": attachment.name,
                    "url": "/web/content/%s?download=0" % attachment.id,
                } for attachment in line.attachment_ids] if line else [],
            })
        employees = []
        if self._is_manager():
            employees = request.env["hr.employee"].search_read(
                [("company_id", "in", request.env.companies.ids)], ["name"], order="name"
            )
        return {
            "id": report.id, "name": report.name, "month": report.month.isoformat(), "state": report.state,
            "employee": {"id": report.employee_id.id, "name": report.employee_id.name},
            "totals": {"work": report.total_work_hours, "target": report._get_target_month_hours(), "overtime": report.total_overtime_hours, "allowance": report.total_allowance, "hotel": report.total_hotel, "expenses": report.total_expenses},
            "rows": result,
            "canApprove": request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_approver"),
            "canExport": request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_manager"),
            "canSelectEmployee": self._is_manager(),
            "employees": [{"id": item["id"], "name": item["name"]} for item in employees],
            "rateOptions": [{
                "value": rate.rate_key,
                "label": rate_labels[rate.rate_key],
                "common": rate.show_in_report,
            } for rate in rates],
            "rateYear": report.month.year,
        }

    @http.route("/my/spesenbericht", type="http", auth="user", website=True, sitemap=False)
    def spesenbericht_page(self, **kwargs):
        if not request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_user"):
            raise AccessError(_("Sie sind nicht für den Spesenbericht freigeschaltet."))
        self._employee()
        return request.render("nolte_spesenbericht.page_spesenbericht")

    @http.route("/nolte_spesenbericht/data", type="jsonrpc", auth="user", methods=["POST"])
    def data(self, month, employee_id=None):
        report = self._report(month, employee_id=employee_id)
        if report.state in ("draft", "rejected"):
            report.sync_approved_leaves()
            report.sync_automatic_travel_allowances()
        return self._serialize(report)

    @http.route("/my/spesenbericht/print", type="http", auth="user", website=True, sitemap=False)
    def spesenbericht_print(self, month=None, employee_id=None, **kwargs):
        report = self._report(month or fields.Date.today().replace(day=1), employee_id=employee_id)
        if report.state in ("draft", "rejected"):
            report.sync_approved_leaves()
            report.sync_automatic_travel_allowances()
        month_names = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        def money(value):
            text = "%0.2f" % (value or 0.0)
            return text.replace(".", ",") + " €"

        def time_value(value):
            minutes = round((value or 0.0) * 60)
            return "%d:%02d" % (minutes // 60, minutes % 60)

        return request.render("nolte_spesenbericht.page_spesenbericht_print", {
            "data": self._serialize(report),
            "company": report.company_id,
            "month_label": "%s %s" % (month_names[report.month.month - 1], report.month.year),
            "country_labels": {item["value"]: item["label"] for item in self._serialize(report)["rateOptions"]},
            "travel_labels": {"": "–", "single": "Über 8 Std.", "arrival": "Anreise", "full": "Volltag", "departure": "Abreise"},
            "state_labels": {"draft": "In Bearbeitung", "rejected": "Zur Korrektur", "submitted": "Eingereicht", "approved": "Freigegeben", "exported": "An Odoo übergeben"},
            "money": money,
            "time_value": time_value,
        })

    @http.route("/my/spesenbericht/pdf", type="http", auth="user", website=True, sitemap=False)
    def spesenbericht_pdf(self, month=None, employee_id=None, **kwargs):
        """Return a real landscape PDF instead of relying on browser print CSS."""
        report = self._report(month or fields.Date.today().replace(day=1), employee_id=employee_id)
        if report.state in ("draft", "rejected"):
            report.sync_approved_leaves()
            report.sync_automatic_travel_allowances()
        pdf, _ = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "nolte_spesenbericht.action_report_spesenbericht_pdf", report.ids
        )
        filename = "Spesenbericht_%s_%s.pdf" % (
            report.employee_id.name.replace(" ", "_"),
            report.month.strftime("%Y-%m"),
        )
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", str(len(pdf))),
            ("Content-Disposition", content_disposition(filename, disposition_type="inline")),
        ])

    @http.route("/nolte_spesenbericht/save", type="jsonrpc", auth="user", methods=["POST"])
    def save(self, month, rows, employee_id=None):
        report = self._report(month, employee_id=employee_id)
        if report.state not in ("draft", "rejected"):
            raise UserError(_("Dieser Bericht ist gesperrt und kann nicht bearbeitet werden."))
        allowed = {"customer", "start_time", "end_time", "break_minutes", "country", "travel_type", "breakfast", "lunch", "dinner", "hotel_mode", "hotel_input", "expense_amount"}
        for payload in rows:
            row_date = fields.Date.to_date(payload.get("date"))
            if not row_date or row_date.replace(day=1) != report.month:
                continue
            line = report.line_ids.filtered(lambda item: item.date == row_date)[:1]
            vals = {key: value for key, value in payload.items() if key in allowed}
            if vals.get("country") and vals.get("travel_type"):
                rate = request.env["nolte.bmf.rate"].search([
                    ("year", "=", row_date.year),
                    ("rate_key", "=", vals["country"]),
                    ("active", "=", True),
                ], limit=1)
                if not rate:
                    raise UserError(_(
                        "Für den gewählten Reisetag ist kein BMF-Tarif für %s hinterlegt."
                    ) % row_date.year)
            if line and line.travel_type_automatic and (
                vals.get("country") != line.country or vals.get("travel_type") != line.travel_type
            ):
                vals["travel_type_automatic"] = False
            vals.update({"report_id": report.id, "date": row_date})
            meaningful = any(value not in (False, None, "", 0, 0.0) for key, value in vals.items() if key not in ("report_id", "date"))
            if line and meaningful:
                line.write(vals)
            elif line and not meaningful and not line.absence_source and not line.attachment_ids:
                line.unlink()
            elif not line and meaningful:
                request.env["nolte.expense.report.line"].create(vals)
        report.sync_automatic_travel_allowances()
        return self._serialize(report)

    @http.route("/nolte_spesenbericht/upload", type="http", auth="user", methods=["POST"], csrf=True)
    def upload(self, report_id=None, line_date=None, receipt=None, **kwargs):
        report = request.env["nolte.expense.report"].browse(int(report_id or 0)).exists()
        owns_report = report and report.employee_id.user_id == request.env.user
        manages_report = report and self._is_manager() and report.company_id in request.env.companies
        if not report or not (owns_report or manages_report) or report.state not in ("draft", "rejected"):
            raise AccessError(_("Kein Zugriff auf diesen Bericht."))
        row_date = fields.Date.to_date(line_date)
        line = report.line_ids.filtered(lambda item: item.date == row_date)[:1]
        if not line:
            line = request.env["nolte.expense.report.line"].create({"report_id": report.id, "date": row_date})
        if receipt and receipt.filename:
            attachment = request.env["ir.attachment"].create({"name": receipt.filename, "datas": b64encode(receipt.read()), "res_model": line._name, "res_id": line.id})
            line.attachment_ids = [(4, attachment.id)]
        return request.redirect("/my/spesenbericht")

    @http.route("/nolte_spesenbericht/delete_attachment", type="jsonrpc", auth="user", methods=["POST"])
    def delete_attachment(self, report_id, attachment_id):
        report = request.env["nolte.expense.report"].browse(int(report_id or 0)).exists()
        owns_report = report and report.employee_id.user_id == request.env.user
        manages_report = report and self._is_manager() and report.company_id in request.env.companies
        if not report or not (owns_report or manages_report) or report.state not in ("draft", "rejected"):
            raise AccessError(_("Belege können nur in einem bearbeitbaren Bericht gelöscht werden."))
        attachment = request.env["ir.attachment"].browse(int(attachment_id or 0)).exists()
        report_attachments = report.line_ids.mapped("attachment_ids")
        if not attachment or attachment not in report_attachments:
            raise AccessError(_("Dieser Beleg gehört nicht zu dem gewählten Bericht."))
        attachment.unlink()
        return {"deleted": True}

    @http.route("/nolte_spesenbericht/sync_leaves", type="jsonrpc", auth="user", methods=["POST"])
    def sync_leaves(self, month, employee_id=None):
        report = self._report(month, employee_id=employee_id)
        count = report.sync_approved_leaves()
        return {"count": count, "report": self._serialize(report)}

    @http.route("/nolte_spesenbericht/submit", type="jsonrpc", auth="user", methods=["POST"])
    def submit(self, month, employee_id=None):
        report = self._report(month, employee_id=employee_id)
        report.action_submit()
        return self._serialize(report)

    @http.route("/nolte_spesenbericht/approve", type="jsonrpc", auth="user", methods=["POST"])
    def approve(self, report_id, decision):
        report = request.env["nolte.expense.report"].browse(int(report_id)).exists()
        if decision == "approve":
            report.action_approve()
        elif decision == "reject":
            if not request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_approver"):
                raise AccessError(_("Keine Freigabeberechtigung."))
            report.action_reject()
        return self._serialize(report)

    @http.route("/nolte_spesenbericht/create_expenses", type="jsonrpc", auth="user", methods=["POST"])
    def create_expenses(self, report_id):
        if not request.env.user.has_group("nolte_spesenbericht.group_spesenbericht_manager"):
            raise AccessError(_("Keine Berechtigung zur Odoo-Übergabe."))
        report = request.env["nolte.expense.report"].browse(int(report_id)).exists()
        action = report.action_create_expenses()
        return {"expenseIds": report.expense_ids.ids, "action": action}

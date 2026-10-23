import json

from odoo import _, fields, http
from odoo.exceptions import AccessError
from odoo.http import content_disposition, request


class NolteCustomerHistory(http.Controller):
    _customer_visible_states = (
        "customer_confirmed",
        "internally_amended",
        "under_review",
        "ready_to_bill",
        "billed",
        "returned",
    )

    def _authorized_task(self, task_id):
        user = request.env.user
        if not user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(_("Sie sind nicht für die Kundenhistorie freigeschaltet."))
        task = request.env["project.task"].sudo().browse(task_id).exists()
        if not task or user not in task.user_ids:
            # Do not reveal whether an unassigned task exists.
            raise AccessError(_("Diese Kundenhistorie ist nicht verfügbar."))
        return task

    def _history_reports(self, task):
        partner = task.partner_id
        if not partner:
            return request.env["nolte.service.report"].sudo().browse()
        commercial_partner = partner.commercial_partner_id
        return request.env["nolte.service.report"].sudo().search([
            ("company_id", "in", request.env.user.company_ids.ids),
            ("state", "in", self._customer_visible_states),
            ("customer_pdf_attachment_id", "!=", False),
            ("customer_snapshot_payload", "!=", False),
            ("partner_id", "child_of", commercial_partner.id),
        ], order="service_date desc, id desc", limit=100)

    @http.route("/my/stundenbericht/history/<int:task_id>", type="http", auth="user", website=True, sitemap=False)
    def customer_history(self, task_id, **kwargs):
        task = self._authorized_task(task_id)
        reports = self._history_reports(task)
        rows = []
        for report in reports:
            try:
                snapshot = json.loads(report.customer_snapshot_payload or "{}")
                data = snapshot.get("report") or {}
            except (TypeError, ValueError):
                continue
            service_date = data.get("serviceDate") or ""
            try:
                service_date = fields.Date.to_date(service_date).strftime("%d.%m.%Y") if service_date else ""
            except (TypeError, ValueError):
                pass
            rows.append({
                "id": report.id,
                "number": data.get("number") or report.name,
                "date": service_date,
                "machine_number": data.get("machineNumber") or "",
                "machine_type": data.get("machineType") or "",
                "location": data.get("locationName") or data.get("location") or "",
                "work_description": data.get("workDescription") or "",
                "work_result": data.get("workResult") or "",
            })
        response = request.render("nolte_stundenbericht.customer_history_page", {
            "task": task,
            "history": rows,
        })
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    @http.route("/my/stundenbericht/history/<int:task_id>/<int:report_id>.pdf", type="http", auth="user", methods=["GET"], sitemap=False)
    def customer_history_pdf(self, task_id, report_id, **kwargs):
        task = self._authorized_task(task_id)
        report = self._history_reports(task).filtered(lambda item: item.id == report_id)[:1]
        if not report:
            raise AccessError(_("Dieser bestätigte Kundenbericht ist nicht verfügbar."))
        pdf, _report_format = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "nolte_stundenbericht.action_report_customer_service_report", report.ids
        )
        response = request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", content_disposition("%s.pdf" % report.name.replace("/", "-"))),
            ("Cache-Control", "private, no-store"),
        ])
        return response

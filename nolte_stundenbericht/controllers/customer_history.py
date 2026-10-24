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

    def _history_legacy_documents(self, task):
        partner = task.partner_id
        if not partner:
            return request.env["nolte.service.report.legacy.archive"].sudo().browse()
        commercial_partner = partner.commercial_partner_id
        return request.env["nolte.service.report.legacy.archive"].sudo().search([
            ("company_id", "in", request.env.user.company_ids.ids),
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
                "kind": "report",
                "id": report.id,
                "number": data.get("number") or report.name,
                "date": service_date,
                "machine_number": data.get("machineNumber") or "",
                "machine_type": data.get("machineType") or "",
                "location": data.get("locationName") or data.get("location") or "",
                "work_description": data.get("workDescription") or "",
                "work_result": data.get("workResult") or "",
            })
        for document in self._history_legacy_documents(task):
            service_date = document.service_date.strftime("%d.%m.%Y") if document.service_date else ""
            rows.append({
                "kind": "legacy",
                "id": document.id,
                "number": document.name,
                "date": document.period_text or service_date,
                "machine_number": document.machine_number or "",
                "machine_type": document.machine_type or "",
                "location": document.service_location or "",
                "work_description": "",
                "work_result": "",
            })
        rows.sort(key=lambda item: item["date"] or "", reverse=True)
        response = request.render("nolte_stundenbericht.customer_history_page", {
            "task": task,
            "history": rows,
        })
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    @http.route("/my/stundenbericht/history/<int:task_id>/legacy/<int:document_id>.pdf", type="http", auth="user", methods=["GET"], sitemap=False)
    def customer_history_legacy_pdf(self, task_id, document_id, **kwargs):
        task = self._authorized_task(task_id)
        document = self._history_legacy_documents(task).filtered(lambda item: item.id == document_id)[:1]
        if not document:
            raise AccessError(_("Dieser archivierte Stundenbericht ist nicht verfügbar."))
        attachment = document.attachment_id.sudo().exists()
        if not attachment:
            raise AccessError(_("Das verknüpfte PDF wurde nicht gefunden."))
        pdf = attachment.raw
        if not pdf:
            raise AccessError(_("Die Originaldatei dieses archivierten Berichts ist nicht verfügbar."))
        return request.make_response(pdf, headers=[
            ("Content-Type", attachment.mimetype or "application/pdf"),
            ("Content-Disposition", content_disposition(attachment.name or "%s.pdf" % document.name).replace("attachment;", "inline;", 1)),
            ("Cache-Control", "private, no-store"),
        ])

    @http.route("/nolte_stundenbericht/legacy-archive/<int:document_id>/pdf", type="http", auth="user", methods=["GET"], sitemap=False)
    def legacy_archive_pdf(self, document_id, **kwargs):
        """Open an indexed invoice attachment from the backend archive."""
        document = request.env["nolte.service.report.legacy.archive"].browse(document_id).exists()
        if not document:
            raise AccessError(_("Dieser archivierte Stundenbericht ist nicht verfügbar."))
        document.check_access("read")
        document.check_access_rule("read")
        attachment = document.attachment_id.sudo().exists()
        if not attachment:
            raise AccessError(_("Das verknüpfte PDF wurde nicht gefunden."))
        pdf = attachment.raw
        if not pdf:
            raise AccessError(_("Die Originaldatei dieses archivierten Berichts ist nicht verfügbar."))
        return request.make_response(pdf, headers=[
            ("Content-Type", attachment.mimetype or "application/pdf"),
            ("Content-Disposition", content_disposition(attachment.name or "%s.pdf" % document.name).replace("attachment;", "inline;", 1)),
            ("Cache-Control", "private, no-store"),
        ])

    @http.route("/nolte_stundenbericht/legacy-archive/<int:document_id>/preview", type="http", auth="user", methods=["GET"], sitemap=False)
    def legacy_archive_preview(self, document_id, **kwargs):
        document = request.env["nolte.service.report.legacy.archive"].browse(document_id).exists()
        if not document:
            raise AccessError(_("Dieser archivierte Stundenbericht ist nicht verfügbar."))
        document.check_access("read")
        document.check_access_rule("read")
        return request.render("nolte_stundenbericht.legacy_archive_preview", {
            "document": document,
            "archive_action_id": request.env.ref("nolte_stundenbericht.action_nolte_service_legacy_archive").id,
        })

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

import re
from uuid import uuid4
from markupsafe import Markup, escape

from odoo import fields, http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import content_disposition, request
from odoo.tools import html2plaintext


class NolteStundenberichtApiV1(http.Controller):
    """Initial private API for the mobile app.

    All write requests are session-authenticated Odoo JSON-RPC calls. A future
    device-token layer may sit in front of these routes; it must not bypass the
    model-level access rules.
    """

    def _available_tasks(self):
        user = request.env.user
        if not user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(request.env._("Sie dürfen keine Serviceeinsätze übernehmen."))
        company_domain = [("company_id", "in", [False, request.env.company.id]), ("project_id.name", "=", "Aussendienst")]
        model = request.env["project.task"]
        domain = company_domain if user.has_group("nolte_stundenbericht.group_stundenbericht_manager") else company_domain + [("user_ids", "in", user.id)]
        assigned = model.search(domain, order="write_date desc")
        # Only unassigned service orders are exposed beyond native project
        # rules, with the same company boundary and a restricted response.
        open_pool = model.sudo().search(company_domain + [
            ("user_ids", "=", False), ("project_id.name", "=", "Aussendienst"),
        ], order="write_date desc")
        candidates = assigned.sudo() | open_pool
        reports = request.env["nolte.service.report"].sudo().search([("task_id", "in", candidates.ids)])
        by_task = reports.grouped("task_id")
        tasks = candidates.filtered(lambda task: not task._nolte_closed_for_mobile(by_task.get(task, reports.browse())))
        return tasks.sorted(lambda task: (task.write_date, task.id), reverse=True)

    def _claim_task(self, task_id):
        employee = self._employee_for_request()
        user = request.env.user
        if not user.has_group("nolte_stundenbericht.group_stundenbericht_user") or not employee.active or employee.company_id != request.env.company:
            raise AccessError(request.env._("Für die Übernahme ist ein aktiver Monteur im ausgewählten Unternehmen erforderlich."))
        task = request.env["project.task"].sudo().search([
            ("id", "=", int(task_id)), ("company_id", "in", [False, request.env.company.id]),
        ], limit=1)
        if not task:
            raise AccessError(request.env._("Dieser Einsatzauftrag ist nicht verfügbar."))
        if task.project_id.with_context(lang=None).name != "Aussendienst":
            raise AccessError(request.env._("Diese Aufgabe gehört nicht zur Serviceplanung Aussendienst."))
        request.env.cr.execute("SELECT id FROM project_task WHERE id = %s FOR UPDATE", [task.id])
        task.invalidate_recordset()
        if task._nolte_closed_for_mobile():
            raise UserError(request.env._("Dieser Einsatz ist bereits abgeschlossen oder archiviert."))
        if not task.user_ids:
            if task.project_id.with_context(lang=None).name != "Aussendienst":
                raise AccessError(request.env._("Nur unbesetzte Serviceeinsätze können übernommen werden."))
            task.with_context(mail_auto_subscribe_no_notify=True).write({"user_ids": [(4, user.id)]})
        elif user not in task.user_ids:
            if not user.has_group("nolte_stundenbericht.group_stundenbericht_manager"):
                raise UserError(request.env._("Dieser Einsatz wurde inzwischen von einem anderen Monteur übernommen. Bitte die Auftragsliste neu laden."))
            request.env["project.task"].browse(task.id).check_access("read")
        prepared = request.env["nolte.service.report"].search([
            ("task_id", "=", task.id), ("owner_user_id", "=", user.id),
            ("planning_draft", "=", True), ("state", "=", "draft"), ("is_closed", "=", False),
        ], limit=1)
        return task, prepared

    @http.route("/nolte_stundenbericht/api/v1/tasks/claim", type="jsonrpc", auth="user", methods=["POST"])
    def claim_task(self, task_id):
        task, prepared = self._claim_task(task_id)
        return {"taskId": task.id, "reportId": prepared.id or False}

    @http.route("/nolte_stundenbericht/api/v1/reports/archive", type="jsonrpc", auth="user", methods=["POST"])
    def archive_report(self, report_id):
        self._employee_for_request()
        report = request.env["nolte.service.report"].browse(int(report_id)).exists()
        if not report:
            raise AccessError(request.env._("Dieser Bericht ist nicht verfügbar."))
        report.action_archive_completed()
        return {"archived": True, "taskId": report.task_id.id if report.task_id and report.task_id._nolte_closed_for_mobile() else False}

    def _employee_for_request(self, requested_employee_id=None):
        employee_model = request.env["hr.employee"]
        own_employee = employee_model.search([("user_id", "=", request.env.user.id)], limit=1)
        is_manager = request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager")
        if requested_employee_id:
            employee = employee_model.browse(int(requested_employee_id)).exists()
            if not employee:
                raise UserError(request.env._("Der angegebene Mitarbeiter existiert nicht."))
            if not is_manager and employee != own_employee:
                raise AccessError(request.env._("Sie dürfen nur eigene Einsatzzeiten synchronisieren."))
            return employee
        if not own_employee:
            raise UserError(request.env._("Für den angemeldeten Benutzer ist kein Mitarbeiter hinterlegt."))
        return own_employee

    def _move_task_to_stage(self, task, stage_name):
        """Move a linked service task to the requested stage in its project."""
        if not task or not task.project_id:
            return
        stage = request.env["project.task.type"].search([
            ("name", "ilike", stage_name),
            ("project_ids", "in", task.project_id.id),
        ], order="sequence, id", limit=1)
        if stage and task.stage_id != stage and task.has_access("write"):
            task.write({"stage_id": stage.id})

    def _ensure_manual_service_task(self, report, employees):
        """Create one task for an authorized, customer-filled mobile draft.

        Called inside the UUID upsert lock. Old offline payloads may still have
        no taskId, so the persisted report link is authoritative on retries.
        """
        report.ensure_one()
        report.check_access("write")
        if report.task_id or not (report.partner_id or (report.manual_customer_name or "").strip()):
            return
        if report.company_id != request.env.company:
            raise AccessError(request.env._("Der Bericht gehört nicht zum aktiven Unternehmen."))
        # Narrow elevation: technicians need no general project creation rights.
        # Never accept a project, assignee or task values directly from the client.
        projects = request.env["project.project"].sudo()
        project = projects.search([
            ("name", "=", "Aussendienst"), ("company_id", "=", report.company_id.id),
        ], order="sequence, id", limit=1) or projects.search([
            ("name", "=", "Aussendienst"), ("company_id", "=", False),
        ], order="sequence, id", limit=1)
        if not project:
            raise UserError(request.env._("Für dieses Unternehmen fehlt das Projekt Aussendienst. Bitte die Administration kontaktieren."))
        customer = report.partner_id.display_name or report.manual_customer_name.strip()
        details = [
            report.name, customer, report.manual_customer_street,
            " ".join(filter(None, [report.manual_customer_zip, report.manual_customer_city])),
            report.manual_contact_name, report.manual_contact_phone, report.manual_contact_email,
            report.work_description,
        ]
        values = {
            "name": "%s – %s" % (customer, report.name),
            "project_id": project.id, "company_id": report.company_id.id,
            "partner_id": report.partner_id.id or False,
            "user_ids": [(6, 0, employees.mapped("user_id").ids)],
            "date_deadline": report.service_date,
            "description": Markup("<br/>").join(escape(value) for value in details if value),
            "nolte_machine_number": report.machine_number,
            "nolte_machine_type": report.machine_type,
            "nolte_service_location": report.service_location,
            "nolte_service_location_name": report.service_location_name,
            "nolte_service_location_contact_name": report.service_location_contact_name,
            "nolte_service_location_contact_phone": report.service_location_contact_phone,
        }
        tasks = request.env["project.task"].sudo().with_context(
            tracking_disable=True, mail_create_nosubscribe=True)
        if "x_customer_id" in tasks._fields:
            values["x_customer_id"] = report.partner_id.id or False
        stage = request.env["project.task.type"].sudo().search([
            ("name", "=", "In Durchführung"), ("project_ids", "in", project.id),
        ], order="sequence, id", limit=1)
        if stage:
            values["stage_id"] = stage.id
        report.task_id = tasks.create(values)

    def _serialize(self, report):
        task_contact = report.task_id.nolte_service_contact_id if report.task_id else request.env["res.partner"]
        customer_email = (
            report.manual_contact_email
            or (task_contact.email if task_contact and "email" in task_contact._fields else False)
            or (report.partner_id.email if report.partner_id else False)
            or ""
        )
        company_email = report.company_id.email or report.company_id.partner_id.email or ""
        return {
            "id": report.id,
            "mobileUuid": report.mobile_uuid,
            "mobileRevision": report.mobile_revision,
            "serverRevision": report.server_revision,
            "state": report.state,
            "requestSignatureUrl": "/odoo/action-%s?active_id=%s" % (request.env.ref("nolte_stundenbericht.action_nolte_service_request_signature").id, report.id),
            "signatureManageUrl": "/odoo/action-%s/%s" % (request.env.ref("nolte_stundenbericht.action_nolte_service_report").id, report.id),
            "serviceDate": fields.Date.to_string(report.service_date),
            "taskId": report.task_id.id or False,
            "taskName": report.task_id.display_name or "",
            "customerName": report.partner_id.display_name or report.manual_customer_name or "",
            "previewPdfUrl": "/nolte_stundenbericht/reports/preview/%s/pdf?v=%s" % (report.mobile_uuid, report.server_revision),
            "previewHtmlUrl": "/nolte_stundenbericht/reports/preview/%s/html?v=%s" % (report.mobile_uuid, report.server_revision),
            "countryRateKey": report.country_rate_key,
            "serviceLocation": report.service_location or "",
            "serviceLocationName": report.service_location_name or "",
            "serviceLocationContactName": report.service_location_contact_name or "",
            "serviceLocationContactPhone": report.service_location_contact_phone or "",
            "manualCustomerName": report.manual_customer_name or "",
            "manualCustomerStreet": report.manual_customer_street or "",
            "manualCustomerZip": report.manual_customer_zip or "",
            "manualCustomerCity": report.manual_customer_city or "",
            "manualContactName": report.manual_contact_name or "",
            "manualContactPhone": report.manual_contact_phone or "",
            "manualContactEmail": report.manual_contact_email or "",
            "machineNumber": report.machine_number or "",
            "machineType": report.machine_type or "",
            "overnightCount": sum(report.employee_assignment_ids.mapped("overnight_count")) or sum(report.member_ids.mapped("overnight_count")) or report.overnight_count,
            "workDescription": report.work_description or "",
            "workResult": report.work_result or "",
            "expenseSyncState": report.spesen_sync_state,
            "expenseSyncMessage": report.spesen_sync_message or "",
            "customerPdfUrl": "/web/content/%s?download=false" % report.customer_pdf_attachment_id.id if report.customer_pdf_attachment_id else False,
            "customerEmail": customer_email,
            "companyServiceEmail": company_email,
            "composeEmailUrl": "/odoo/action-%s?active_id=%s" % (request.env.ref("nolte_stundenbericht.action_nolte_service_report_compose").id, report.id),
            "canSendCustomerEmail": bool(report.customer_pdf_attachment_id and report.state in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill", "billed")),
            "flatRates": [{"id": line.flat_rate_id.id, "name": line.name} for line in report.flat_rate_line_ids],
            "materials": [{
                "materialUuid": material.mobile_uuid,
                "productId": material.product_id.id or False,
                "name": material.name,
                "quantity": material.quantity,
                "unit": material.unit or "",
                "note": material.note or "",
            } for material in report.material_ids],
            "checklist": [{
                "checklistUuid": item.mobile_uuid,
                "name": item.name,
                "checked": item.checked,
                "note": item.note or "",
                "visibility": item.visibility,
            } for item in report.checklist_ids],
            "photos": [{"id": photo.id, "name": photo.name} for photo in report.photo_ids],
            "members": [
                {
                    "employeeId": member.employee_id.id,
                    "employeeName": member.employee_id.name,
                    "serviceDate": fields.Date.to_string(member.service_date),
                    "overnightCount": member.overnight_count,
                    "billingState": member.billing_state,
                    "billingPreview": member.billing_preview or {},
                    "billingApproved": member.billing_approved or {},
                    "saleLineIds": member.billing_sale_line_ids.ids,
                    "segments": [
                        {
                            "segmentUuid": segment.segment_uuid,
                            "type": segment.segment_type,
                            "start": segment.start_time,
                            "end": segment.end_time,
                            "kilometers": segment.kilometers,
                            "internalOnly": segment.internal_only,
                        }
                        for segment in member.segment_ids
                    ],
                }
                for member in report.member_ids
            ],
            "employeeAssignments": [
                {
                    "employeeId": assignment.employee_id.id,
                    "employeeName": assignment.employee_id.name,
                    "overnightCount": assignment.overnight_count,
                }
                for assignment in report.employee_assignment_ids
            ] or [
                {
                    "employeeId": employee_id,
                    "employeeName": report.member_ids.filtered(lambda item: item.employee_id.id == employee_id)[:1].employee_id.name,
                    "overnightCount": sum(report.member_ids.filtered(lambda item: item.employee_id.id == employee_id).mapped("overnight_count")),
                }
                for employee_id in set(report.member_ids.mapped("employee_id").ids)
            ],
        }

    def _report_for_update(self, mobile_uuid, expected_server_revision=None):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report:
            raise UserError(request.env._("Der Einsatzbericht wurde nicht gefunden."))
        if expected_server_revision is not None and int(expected_server_revision) != report.server_revision:
            raise UserError(request.env._("Der Bericht wurde auf dem Server geändert. Bitte zuerst die aktuelle Fassung laden."))
        return report

    def _customer_snapshot(self, report):
        return report.preview_customer_snapshot()

    def _work_templates(self):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(request.env._("Sie sind nicht für den Stundenbericht freigeschaltet."))
        templates = request.env["nolte.service.work.template"].search([
            ("company_id", "in", [False, request.env.company.id]),
        ])
        return [{"id": template.id, "name": template.name, "body": template.body} for template in templates]

    @http.route("/nolte_stundenbericht/api/v1/flat-rates", type="jsonrpc", auth="user", methods=["POST"])
    def flat_rates(self):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(request.env._("Kein Zugriff auf Einsatzpauschalen."))
        rates = request.env["nolte.service.flat.rate"].search([("company_id", "=", request.env.company.id)])
        return [{"id": rate.id, "name": rate.name} for rate in rates if rate.sudo().product_id.active and rate.sudo().product_id.sale_ok]

    @http.route("/nolte_stundenbericht/api/v1/work-templates", type="jsonrpc", auth="user", methods=["POST"])
    def work_templates(self):
        return self._work_templates()

    @http.route("/nolte_stundenbericht/api/v1/checklist-templates", type="jsonrpc", auth="user", methods=["POST"])
    def checklist_templates(self):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(request.env._("Sie sind nicht für den Stundenbericht freigeschaltet."))
        templates = request.env["nolte.service.checklist.template"]._default_for_current_company()
        return [{"id": template.id, "name": template.name, "visibility": template.visibility,
                 "items": [{"name": line.name, "note": line.note or ""} for line in template.line_ids]}
                for template in templates]

    @http.route("/nolte_stundenbericht/api/v1/bootstrap", type="jsonrpc", auth="user", methods=["POST"])
    def bootstrap(self, task_id=None):
        employee = self._employee_for_request()
        available = self._available_tasks()
        tasks = available[:100]
        if task_id:
            # A direct link must also work for older/folded tasks beyond the
            # 100 recent assignments, without bypassing project access rules.
            direct_task = available.filtered(lambda task: task.id == int(task_id))
            if not direct_task:
                raise AccessError(request.env._("Dieser Einsatzauftrag ist für Sie nicht verfügbar."))
            tasks |= direct_task

        def task_values(task):
            sale_order = task.sale_order_id if "sale_order_id" in task._fields else request.env["sale.order"]
            task_partner = task.partner_id
            customer = task_partner.commercial_partner_id if task_partner else request.env["res.partner"]
            contact = task.nolte_service_contact_id or (task_partner if task_partner and task_partner != customer else request.env["res.partner"])
            address_parts = [customer.street, customer.street2, " ".join(part for part in [customer.zip, customer.city] if part), customer.country_id.name]
            customer_address = ", ".join(part for part in address_parts if part)
            service_location = task.nolte_service_location or ""
            service_location_name = task.nolte_service_location_name or ""
            return {
                "id": task.id,
                "name": task.display_name,
                "customerId": customer.id or False,
                "customerName": customer.display_name or "",
                "customerAddress": customer_address,
                "contactName": contact.name or "",
                "contactPhone": (contact.mobile if "mobile" in contact._fields else "") or (contact.phone if "phone" in contact._fields else ""),
                "contactEmail": contact.email if "email" in contact._fields else "",
                "saleOrderId": sale_order.id or False,
                "serviceLocation": service_location,
                "serviceLocationName": service_location_name,
                "serviceLocationContactName": task.nolte_service_location_contact_name or "",
                "serviceLocationContactPhone": task.nolte_service_location_contact_phone or "",
                "serviceLocationDiffers": bool(
                    (service_location and service_location.strip().casefold() != customer_address.strip().casefold())
                    or (service_location_name and service_location_name.strip().casefold() != (customer.display_name or "").strip().casefold())
                    or task.nolte_service_location_contact_name
                    or task.nolte_service_location_contact_phone
                ),
                "machineNumber": task.nolte_machine_number or "",
                "machineType": task.nolte_machine_type or "",
                "overnightCount": task.nolte_overnight_count,
                # Technician instructions are stored in the task description;
                # never substitute the task title here.
                "workOrderDescription": html2plaintext(task.description or "").strip(),
            }
        technician_group = request.env.ref("nolte_stundenbericht.group_stundenbericht_user")
        employees = request.env["hr.employee"].sudo().search([
            ("active", "=", True),
            ("user_id.group_ids", "in", technician_group.id),
            "|", ("company_id", "=", False), ("company_id", "=", request.env.company.id),
        ], order="name, id")
        employee_options = [{"id": item.id, "name": item.name} for item in employees]
        if employee.id not in employees.ids:
            employee_options.insert(0, {"id": employee.id, "name": employee.name})
        # These rollout controls belong to the private employee profile. The
        # mobile user has already been matched to their own employee above;
        # use a narrow sudo read only for these two fields so the public
        # employee profile ACL does not block app bootstrap for portal-like
        # users.
        private_employee = request.env["hr.employee"].sudo().browse(employee.id)
        rates = request.env["nolte.bmf.rate"].sudo().search([("active", "=", True)], order="year desc, country_name, location_name, id")
        country_options = {}
        for rate in rates:
            label = rate.country_name
            if rate.location_name and rate.location_name.strip().casefold() != "im übrigen":
                label += " (%s)" % rate.location_name
            country_options.setdefault(rate.rate_key, {"code": rate.rate_key, "name": label})
        return {
            "employee": {"id": employee.id, "name": employee.name},
            "employees": employee_options,
            "source": private_employee.stundenbericht_source,
            "appActiveFrom": fields.Date.to_string(private_employee.stundenbericht_app_active_from) if private_employee.stundenbericht_app_active_from else False,
            "countries": sorted(country_options.values(), key=lambda item: item["name"].casefold()),
            "serverTime": fields.Datetime.to_string(fields.Datetime.now()),
            "assignments": [task_values(task) for task in tasks],
            "workTemplates": self._work_templates(),
        }

    @http.route("/nolte_stundenbericht/api/v1/reports/recent", type="jsonrpc", auth="user", methods=["POST"])
    def recent_reports(self):
        employee = self._employee_for_request()
        reports = request.env["nolte.service.report"].search(
            [("member_ids.employee_id", "=", employee.id), ("is_closed", "=", False)], order="service_date desc, id desc", limit=100
        )
        return [{
            "id": report.id,
            "number": report.name,
            "date": fields.Date.to_string(report.display_service_date) or "Termin offen",
            "customer": report.partner_id.display_name or report.manual_customer_name or report.task_id.display_name or "–",
            "state": dict(report._fields["state"].selection).get(report.state, report.state),
            "canLoadData": report.state in ("draft", "returned"),
            "canArchive": report.state not in ("draft", "returned", "awaiting_signature"),
            "signatureManageUrl": "/odoo/action-%s/%s" % (request.env.ref("nolte_stundenbericht.action_nolte_service_report").id, report.id) if report.state == "awaiting_signature" else False,
            "url": "/report/pdf/nolte_stundenbericht.action_report_customer_service_report/%s" % report.id,
        } for report in reports]

    @http.route("/nolte_stundenbericht/api/v1/reports/load", type="jsonrpc", auth="user", methods=["POST"])
    def load_report(self, report_id):
        employee = self._employee_for_request()
        report = request.env["nolte.service.report"].search([
            ("id", "=", int(report_id)),
            ("member_ids.employee_id", "=", employee.id),
        ], limit=1)
        if not report:
            raise AccessError(request.env._("Dieser Bericht ist für Sie nicht verfügbar."))
        if report.is_closed:
            raise UserError(request.env._("Dieser Bericht liegt bereits im Archiv."))
        if report.state not in ("draft", "returned"):
            raise UserError(request.env._("Nur Entwürfe und zur Korrektur zurückgegebene Berichte können in die Eingabemaske geladen werden. Für diesen Bericht bitte die PDF-Vorschau öffnen."))
        data = self._serialize(report)
        task = report.task_id
        customer = (task.partner_id.commercial_partner_id if task and task.partner_id else report.partner_id)
        contact = (task.nolte_service_contact_id or (task.partner_id if task and task.partner_id and task.partner_id != customer else request.env["res.partner"])) if task else request.env["res.partner"]
        address_parts = [customer.street, customer.street2, " ".join(part for part in [customer.zip, customer.city] if part), customer.country_id.name] if customer else []
        data.update({
            "employeeId": employee.id,
            "taskId": task.id or False,
            "partnerId": report.partner_id.id or False,
            "publicNote": report.public_note or "",
            "taskDefaults": {
                "name": task.display_name,
                "customerId": customer.id,
                "customerName": customer.display_name or "",
                "customerAddress": ", ".join(part for part in address_parts if part),
                "contactName": contact.name or "",
                "contactPhone": (contact.mobile if "mobile" in contact._fields else "") or (contact.phone if "phone" in contact._fields else ""),
                "contactEmail": contact.email if "email" in contact._fields else "",
                "serviceLocation": task.nolte_service_location or report.service_location or "",
                "serviceLocationName": task.nolte_service_location_name or report.service_location_name or "",
                "serviceLocationContactName": task.nolte_service_location_contact_name or report.service_location_contact_name or "",
                "serviceLocationContactPhone": task.nolte_service_location_contact_phone or report.service_location_contact_phone or "",
                "serviceLocationDiffers": bool(task.nolte_service_location or task.nolte_service_location_name or task.nolte_service_location_contact_name or task.nolte_service_location_contact_phone),
                "machineNumber": task.nolte_machine_number or report.machine_number or "",
                "machineType": task.nolte_machine_type or report.machine_type or "",
                "overnightCount": task.nolte_overnight_count if task else report.overnight_count,
                "workOrderDescription": html2plaintext(task.description or "").strip(),
            } if task else {},
            "days": [{
                "date": item["serviceDate"],
                "segments": item["segments"],
            } for item in data["members"] if item["employeeId"] == employee.id],
            "employeeDays": [{
                "employeeId": item["employeeId"],
                "employeeName": item["employeeName"],
                "date": item["serviceDate"],
                "segments": item["segments"],
            } for item in data["members"]],
        })
        return data

    @http.route("/nolte_stundenbericht/api/v1/companies/search", type="jsonrpc", auth="user", methods=["POST"])
    def search_companies(self, query=""):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(request.env._("Sie sind nicht für den Stundenbericht freigeschaltet."))
        self._employee_for_request()
        term = str(query or "").strip()[:120]
        if len(term) < 2:
            return []
        # Respect normal contact access and active company boundaries. No sudo,
        # private persons or child/contact addresses in the company catalogue.
        companies = request.env["res.partner"].search([
            ("active", "=", True), ("is_company", "=", True), ("parent_id", "=", False),
            "|", ("company_id", "=", False), ("company_id", "=", request.env.company.id),
            "|", "|", ("name", "ilike", term), ("city", "ilike", term), ("zip", "ilike", term),
        ], order="name, id", limit=10)
        return [{"id": company.id, "name": company.name,
                 "street": ", ".join(filter(None, [company.street, company.street2])),
                 "zip": company.zip or "", "city": company.city or "",
                 "phone": company.phone or "", "email": company.email or ""}
                for company in companies]

    @http.route("/nolte_stundenbericht/api/v1/products/search", type="jsonrpc", auth="user", methods=["POST"])
    def search_products(self, query=""):
        # Field staff normally do not receive full product-menu access.  They
        # still need a small, company-limited catalogue lookup for material.
        self._employee_for_request()
        term = (query or "").strip()
        if len(term) < 2:
            return []
        products = request.env["product.product"].sudo().with_company(request.env.company).search([
            ("sale_ok", "=", True),
            "|", ("company_id", "=", False), ("company_id", "=", request.env.company.id),
            "|", ("name", "ilike", term), ("default_code", "ilike", term),
        ], limit=12)
        return [{
            "id": product.id,
            "name": "%s · %s" % (product.default_code, product.display_name) if product.default_code else product.display_name,
            "unit": product.uom_id.name or "Stk.",
        } for product in products]

    @http.route("/nolte_stundenbericht/api/v1/reports/previous-template", type="jsonrpc", auth="user", methods=["POST"])
    def previous_template(self, service_date, task_id=None):
        employee = self._employee_for_request()
        date_value = fields.Date.to_date(service_date)
        domain = [
            ("member_ids.employee_id", "=", employee.id),
            ("service_date", "<", date_value),
            ("state", "in", ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill", "billed")),
        ]
        if task_id:
            domain.append(("task_id", "=", int(task_id)))
        report = request.env["nolte.service.report"].search(domain, order="service_date desc, id desc", limit=1)
        if not report:
            return False
        member = report.member_ids.filtered(lambda item: item.employee_id == employee)[:1]
        return {
            "sourceDate": fields.Date.to_string(report.service_date),
            "serviceLocation": report.service_location or "",
            "machineNumber": report.machine_number or "",
            "machineType": report.machine_type or "",
            "overnightCount": member.overnight_count if member else report.overnight_count,
            "segments": [{
                "type": segment.segment_type, "start": segment.start_time, "end": segment.end_time,
                "kilometers": segment.kilometers,
            } for segment in member.segment_ids.filtered(lambda item: not item.internal_only)],
        }

    @http.route("/nolte_stundenbericht/api/v1/reports/get", type="jsonrpc", auth="user", methods=["POST"])
    def get_report(self, mobile_uuid):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report:
            raise UserError(request.env._("Der Einsatzbericht wurde nicht gefunden."))
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/photo-upload", type="jsonrpc", auth="user", methods=["POST"])
    def photo_upload(self, mobile_uuid, filename, data):
        report = self._report_for_update(mobile_uuid)
        employee = self._employee_for_request()
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager") and employee not in report.member_ids.employee_id:
            raise AccessError(request.env._("Sie dürfen diesem Einsatzbericht keine Fotos hinzufügen."))
        if report.state not in ("draft", "returned"):
            raise UserError(request.env._("Fotos können nach der Kundenbestätigung nicht mehr geändert werden."))
        if not isinstance(data, str) or not data.startswith("data:image/") or "," not in data:
            raise UserError(request.env._("Das Foto hat kein unterstütztes Bildformat."))
        encoded = data.split(",", 1)[1]
        if len(encoded) > 12 * 1024 * 1024:
            raise UserError(request.env._("Ein Foto darf höchstens 9 MB groß sein."))
        attachment = request.env["ir.attachment"].create({
            "name": (filename or "Einsatzfoto.jpg")[:255],
            "datas": encoded,
            "mimetype": data.split(";", 1)[0].split(":", 1)[1],
            "res_model": report._name,
            "res_id": report.id,
        })
        report.write({"photo_ids": [(4, attachment.id)]})
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/upsert", type="jsonrpc", auth="user", methods=["POST"])
    def upsert_report(self, payload):
        if not isinstance(payload, dict):
            raise UserError(request.env._("Ungültige Synchronisationsdaten."))
        mobile_uuid = (payload.get("mobileUuid") or "").strip()
        if not mobile_uuid:
            raise UserError(request.env._("Die mobile Berichtskennung fehlt."))
        employee = self._employee_for_request(payload.get("employeeId"))
        requested_employee_ids = payload.get("employeeIds") or [employee.id]
        try:
            requested_employee_ids = {int(item) for item in requested_employee_ids} | {employee.id}
        except (TypeError, ValueError):
            raise UserError(request.env._("Die Mitarbeiterauswahl ist ungültig."))
        technician_group = request.env.ref("nolte_stundenbericht.group_stundenbericht_user")
        allowed_employees = request.env["hr.employee"].sudo().search([
            ("id", "in", list(requested_employee_ids)),
            ("active", "=", True),
            ("user_id.group_ids", "in", technician_group.id),
            "|", ("company_id", "=", False), ("company_id", "=", request.env.company.id),
        ])
        if set(allowed_employees.ids) != requested_employee_ids:
            raise AccessError(request.env._("Mindestens ein ausgewählter Mitarbeiter gehört nicht zur Gruppe Stundenbericht Monteur oder ist für dieses Unternehmen nicht verfügbar."))
        report_model = request.env["nolte.service.report"]
        client_revision = int(payload.get("mobileRevision") or 0)
        # Serialize concurrent taps/retries for the same offline report UUID.
        # The UNIQUE constraint remains the final integrity safeguard.
        request.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
            ["nolte.service.report.upsert", mobile_uuid],
        )
        report = report_model.search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if report and report.is_closed:
            raise UserError(request.env._("Dieser Bericht ist abgeschlossen oder archiviert und kann nicht mehr synchronisiert werden."))
        if report and report.state not in ("draft", "returned"):
            if client_revision <= report.mobile_revision:
                return self._serialize(report)
            raise UserError(request.env._("Dieser Bericht ist nicht mehr über den Entwurfsabgleich änderbar."))
        expected_server_revision = payload.get("serverRevision")
        if report and expected_server_revision is not None and int(expected_server_revision) != report.server_revision:
            raise UserError(request.env._("Der Bericht wurde auf dem Server geändert. Bitte zuerst die aktuelle Fassung laden."))

        allowed = {
            "planning_draft": False,
            "service_date": payload.get("serviceDate"),
            "country_rate_key": payload.get("countryRateKey") or "DE",
            "service_location": payload.get("serviceLocation") or False,
            "service_location_name": payload.get("serviceLocationName") or False,
            "service_location_contact_name": payload.get("serviceLocationContactName") or False,
            "service_location_contact_phone": payload.get("serviceLocationContactPhone") or False,
            "machine_number": payload.get("machineNumber") or False,
            "machine_type": payload.get("machineType") or False,
            "overnight_count": int(payload.get("overnightCount") or 0),
            "public_note": payload.get("publicNote") or False,
            "work_description": payload.get("workDescription") or False,
            "work_result": payload.get("workResult") or False,
            "manual_customer_name": payload.get("manualCustomerName") or False,
            "manual_customer_street": payload.get("manualCustomerStreet") or False,
            "manual_customer_zip": payload.get("manualCustomerZip") or False,
            "manual_customer_city": payload.get("manualCustomerCity") or False,
            "manual_contact_name": payload.get("manualContactName") or False,
            "manual_contact_phone": payload.get("manualContactPhone") or False,
            "manual_contact_email": payload.get("manualContactEmail") or False,
        }
        task_id = int(payload["taskId"]) if payload.get("taskId") else False
        task = request.env["project.task"].browse(task_id).exists() if task_id else (report.task_id if report else request.env["project.task"])
        if task_id and not task:
            raise UserError(request.env._("Der ausgewählte Einsatzauftrag existiert nicht mehr."))
        if task:
            task, prepared = self._claim_task(task.id)
            if not report and prepared and prepared.mobile_uuid != mobile_uuid:
                raise UserError(request.env._("Für diesen Einsatz ist bereits ein Entwurf vorbereitet. Bitte den Auftrag erneut auswählen, um diesen Bericht zu öffnen."))
            task_values = {
                "nolte_service_location": payload.get("serviceLocation") or task.nolte_service_location,
                "nolte_service_location_name": payload.get("serviceLocationName") or task.nolte_service_location_name,
                "nolte_service_location_contact_name": payload.get("serviceLocationContactName") or task.nolte_service_location_contact_name,
                "nolte_service_location_contact_phone": payload.get("serviceLocationContactPhone") or task.nolte_service_location_contact_phone,
                "nolte_machine_number": payload.get("machineNumber") or task.nolte_machine_number,
                "nolte_machine_type": payload.get("machineType") or task.nolte_machine_type,
            }
            # Read-only project access must not prevent technicians from
            # updating their own report; do not broaden task write rights.
            if task.has_access("write") and (payload.get("machineNumber") or payload.get("machineType") or payload.get("serviceLocation") or payload.get("serviceLocationName") or payload.get("serviceLocationContactName") or payload.get("serviceLocationContactPhone")):
                task.write(task_values)
            allowed.update({
                "service_location": allowed["service_location"] or task.nolte_service_location or False,
                "service_location_name": allowed["service_location_name"] or task.nolte_service_location_name or False,
                "service_location_contact_name": allowed["service_location_contact_name"] or task.nolte_service_location_contact_name or False,
                "service_location_contact_phone": allowed["service_location_contact_phone"] or task.nolte_service_location_contact_phone or False,
                "machine_number": allowed["machine_number"] or task.nolte_machine_number or False,
                "machine_type": allowed["machine_type"] or task.nolte_machine_type or False,
                "overnight_count": allowed["overnight_count"] or task.nolte_overnight_count or 0,
            })
        partner_id = int(payload["partnerId"]) if payload.get("partnerId") else False
        partner = request.env["res.partner"].browse(partner_id).exists() if partner_id else request.env["res.partner"]
        if partner_id and not partner:
            raise UserError(request.env._("Der ausgewählte Kunde existiert nicht mehr."))
        if partner:
            partner.check_access("read")
            if partner.company_id and partner.company_id != request.env.company:
                raise AccessError(request.env._("Der ausgewählte Kunde gehört zu einem anderen Unternehmen."))
        sale_order = task.sale_order_id if task and "sale_order_id" in task._fields else request.env["sale.order"]
        task_partner = task.partner_id
        allowed.update({
            "task_id": task.id or False,
            "partner_id": task_partner.id or partner.id or False,
            "sale_order_id": sale_order.id or False,
        })
        if allowed["service_date"]:
            allowed["service_date"] = fields.Date.to_date(allowed["service_date"])
        else:
            raise UserError(request.env._("Das Einsatzdatum fehlt."))
        if not report:
            report = report_model.create({
                **allowed,
                "mobile_uuid": mobile_uuid,
                "mobile_revision": client_revision,
                "owner_user_id": request.env.user.id,
            })
        else:
            if report.state not in ("draft", "returned"):
                raise UserError(request.env._("Dieser Bericht ist nicht mehr über den Entwurfsabgleich änderbar."))
            report.write({**allowed, "mobile_revision": client_revision, "server_revision": report.server_revision + 1})

        employee_days = payload.get("employeeDays")
        if employee_days is not None:
            if not isinstance(employee_days, list):
                raise UserError(request.env._("Die Mitarbeiter-Zeiterfassung ist ungültig."))
            days_by_employee = {employee_id: [] for employee_id in requested_employee_ids}
            for item in employee_days:
                if not isinstance(item, dict) or not item.get("employeeId"):
                    raise UserError(request.env._("Ein Mitarbeiter-Zeiteintrag ist ungültig."))
                employee_id = int(item["employeeId"])
                if employee_id not in requested_employee_ids:
                    raise AccessError(request.env._("Zeiten wurden für einen nicht ausgewählten Mitarbeiter übermittelt."))
                days_by_employee[employee_id].append(item)
        else:
            days = payload.get("days")
            # Older mobile drafts used one schedule, assigned to the logged-in worker.
            if not days:
                days = [{"date": payload.get("serviceDate"), "segments": payload.get("segments") or []}]
            days_by_employee = {employee.id: days}
        segment_model = request.env["nolte.service.report.segment"]
        for employee_id, days in days_by_employee.items():
            if not isinstance(days, list):
                raise UserError(request.env._("Die Zeiterfassung eines Mitarbeiters ist ungültig."))
            target_employee = allowed_employees.filtered(lambda item: item.id == employee_id)[:1]
            received_days = set()
            for day in days:
                if not isinstance(day, dict) or not day.get("date") or not isinstance(day.get("segments") or [], list):
                    raise UserError(request.env._("Ein Einsatztag ist ungültig."))
                service_date = fields.Date.to_date(day["date"])
                received_days.add(service_date)
                member = report.member_ids.filtered(lambda item: item.employee_id == target_employee and item.service_date == service_date)[:1]
                if not member:
                    member = request.env["nolte.service.report.member"].create({"report_id": report.id, "employee_id": target_employee.id, "service_date": service_date})
                # Old clients attached counts to each date. Preserve those by
                # collecting them for the assignment below, then clear the
                # deprecated per-day field.
                member.overnight_count = 0
                existing = {segment.segment_uuid: segment for segment in member.segment_ids}
                received_uuids = set()
                for item in day.get("segments") or []:
                    if not isinstance(item, dict):
                        raise UserError(request.env._("Ein Zeitsegment ist ungültig."))
                    segment_uuid = (item.get("segmentUuid") or "").strip()
                    if not segment_uuid:
                        raise UserError(request.env._("Die Segmentkennung fehlt."))
                    values = {"segment_type": item.get("type"), "start_time": item.get("start"), "end_time": item.get("end"), "kilometers": float(item.get("kilometers") or 0.0), "internal_only": bool(item.get("internalOnly"))}
                    if values["segment_type"] not in {"outbound_travel", "work", "return_travel", "break"}:
                        raise UserError(request.env._("Ein Zeitsegment hat einen unbekannten Typ."))
                    if segment_uuid in existing:
                        existing[segment_uuid].write(values)
                    else:
                        # Drafts made by an older offline version can reuse an ID after a day was copied.
                        collision = segment_model.search([("segment_uuid", "=", segment_uuid)], limit=1)
                        if collision and collision.report_id == report:
                            collision.write({"member_id": member.id, **values})
                        else:
                            if collision:
                                segment_uuid = str(uuid4())
                            segment_model.create({"member_id": member.id, "segment_uuid": segment_uuid, **values})
                    received_uuids.add(segment_uuid)
                member.segment_ids.filtered(lambda segment: segment.segment_uuid not in received_uuids).unlink()
            report.member_ids.filtered(lambda item: item.employee_id.id == employee_id and item.service_date not in received_days).unlink()
        if employee_days is not None:
            submitted_overnights = payload.get("employeeOvernights") or {}
            legacy_day_totals = {}
            for item in employee_days:
                if isinstance(item, dict) and item.get("employeeId") and item.get("overnightCount"):
                    key = str(int(item["employeeId"]))
                    legacy_day_totals[key] = legacy_day_totals.get(key, 0) + max(0, int(item.get("overnightCount") or 0))
            assignment_model = request.env["nolte.service.report.employee"]
            for employee_id in requested_employee_ids:
                count_value = submitted_overnights.get(str(employee_id), submitted_overnights.get(employee_id))
                if count_value is None:
                    count_value = legacy_day_totals.get(str(employee_id), 0)
                assignment = report.employee_assignment_ids.filtered(lambda item: item.employee_id.id == employee_id)[:1]
                assignment_values = {"overnight_count": max(0, int(count_value or 0))}
                if assignment:
                    assignment.write(assignment_values)
                elif count_value or any(item.get("employeeId") == employee_id for item in employee_days if isinstance(item, dict)):
                    assignment_model.create({"report_id": report.id, "employee_id": employee_id, **assignment_values})
            report.write({"overnight_count": sum(report.employee_assignment_ids.mapped("overnight_count"))})
        materials = payload.get("materials") or []
        if not isinstance(materials, list):
            raise UserError(request.env._("Die Materialliste ist ungültig."))
        existing_materials = {material.mobile_uuid: material for material in report.material_ids}
        received_material_uuids = set()
        for sequence, item in enumerate(materials, start=1):
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise UserError(request.env._("Jede Materialzeile benötigt eine Bezeichnung."))
            material_uuid = str(item.get("materialUuid") or "").strip()
            if not material_uuid:
                raise UserError(request.env._("Die Materialkennung fehlt."))
            received_material_uuids.add(material_uuid)
            values = {
                "name": str(item["name"]).strip(),
                "product_id": int(item["productId"]) if item.get("productId") else False,
                "quantity": float(item.get("quantity") or 0.0),
                "unit": str(item.get("unit") or "Stk.").strip(),
                "note": str(item.get("note") or "").strip() or False,
                "sequence": sequence,
            }
            if material_uuid in existing_materials:
                existing_materials[material_uuid].write(values)
            else:
                request.env["nolte.service.report.material"].create({"report_id": report.id, "mobile_uuid": material_uuid, **values})
        report.material_ids.filtered(lambda material: material.mobile_uuid not in received_material_uuids).unlink()
        self._sync_checklist(report, payload.get("checklist") or [])
        if "flatRateIds" in payload:
            report._sync_flat_rates(payload["flatRateIds"])
        self._ensure_manual_service_task(report, allowed_employees)
        # A synced draft means the technician has started the field work.
        self._move_task_to_stage(report.task_id, "In Durchführung")
        return self._serialize(report)

    def _sync_checklist(self, report, checklist):
        """Synchronize checklist IDs within the already authorized report."""
        if not isinstance(checklist, list):
            raise UserError(request.env._("Die Checkliste ist ungültig."))
        existing_checklist = {item.mobile_uuid: item for item in report.checklist_ids}
        received_checklist_uuids = set()
        for sequence, item in enumerate(checklist, start=1):
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise UserError(request.env._("Jeder Checklistenpunkt benötigt eine Bezeichnung."))
            checklist_uuid = str(item.get("checklistUuid") or "").strip()
            if not checklist_uuid:
                raise UserError(request.env._("Die Checklistenkennung fehlt."))
            received_checklist_uuids.add(checklist_uuid)
            existing_item = existing_checklist.get(checklist_uuid)
            visibility = item.get("visibility") or (existing_item.visibility if existing_item else "customer")
            if visibility not in ("internal", "customer"):
                raise UserError(request.env._("Die Sichtbarkeit des Checklistenpunkts ist ungültig."))
            values = {
                "name": str(item["name"]).strip(),
                "checked": bool(item.get("checked")),
                "note": str(item.get("note") or "").strip() or False,
                "sequence": sequence,
                "visibility": visibility,
            }
            if checklist_uuid in existing_checklist:
                existing_checklist[checklist_uuid].write(values)
            else:
                existing_checklist[checklist_uuid] = report.env["nolte.service.report.checklist"].create({"report_id": report.id, "mobile_uuid": checklist_uuid, **values})
        # Only remove children of the report already authorized above. Mobile
        # technicians need no unrestricted delete permission on this model.
        report.checklist_ids.filtered(lambda item: item.mobile_uuid not in received_checklist_uuids).sudo().unlink()

    @http.route("/nolte_stundenbericht/api/v1/reports/customer-confirm", type="jsonrpc", auth="user", methods=["POST"])
    def customer_confirm(self, mobile_uuid, signer_name, signature, expected_server_revision=None):
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        if report.state not in ("draft", "returned"):
            raise UserError(request.env._("Der Bericht kann in seinem aktuellen Status nicht vom Kunden bestätigt werden."))
        if not signer_name or not str(signer_name).strip():
            raise UserError(request.env._("Der Name des Unterzeichners fehlt."))
        if not signature:
            raise UserError(request.env._("Die Kundenunterschrift fehlt."))
        # Canvas.toDataURL() includes a ``data:image/png;base64,`` prefix;
        # Odoo Binary fields expect only the base64 payload.
        if isinstance(signature, str) and signature.startswith("data:"):
            signature = signature.split(",", 1)[-1]
        report._finalize_customer_confirmation(str(signer_name).strip(), signature)
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/send-customer-email", type="jsonrpc", auth="user", methods=["POST"])
    def send_customer_email(self, mobile_uuid, email_to):
        employee = self._employee_for_request()
        report = request.env["nolte.service.report"].search([
            ("mobile_uuid", "=", (mobile_uuid or "").strip()),
            ("member_ids.employee_id", "=", employee.id),
        ], limit=1)
        if not report:
            raise AccessError(request.env._("Dieser Bericht ist für Sie nicht verfügbar."))
        if report.state not in ("customer_confirmed", "internally_amended", "under_review", "ready_to_bill", "billed") or not report.customer_pdf_attachment_id:
            raise UserError(request.env._("Der Kundenbericht kann erst nach der Kundenbestätigung versendet werden."))

        recipient = (email_to or "").strip()
        if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", recipient):
            raise UserError(request.env._("Bitte geben Sie eine gültige einzelne Kunden-E-Mail-Adresse ein."))
        company_email = (report.company_id.email or report.company_id.partner_id.email or "").strip()
        if not company_email:
            raise UserError(request.env._("Für Ihr Unternehmen ist keine Service-E-Mail-Adresse hinterlegt."))
        copy_recipient = company_email if company_email.casefold() != recipient.casefold() else False

        mail = request.env["mail.mail"].sudo().create({
            "subject": request.env._("Stundenbericht %s") % report.name,
            "body_html": request.env._("Guten Tag,<br/><br/>anbei erhalten Sie den Stundenbericht %(report)s.<br/><br/>Freundliche Grüße<br/>%(company)s") % {
                "report": report.name,
                "company": report.company_id.name,
            },
            "email_from": company_email,
            "reply_to": company_email,
            "email_to": recipient,
            "email_cc": copy_recipient,
            "attachment_ids": [(4, report.customer_pdf_attachment_id.id)],
            "model": report._name,
            "res_id": report.id,
            "auto_delete": False,
        })
        mail.send()
        return {
            "sent": mail.state == "sent",
            "queued": mail.state == "outgoing",
            "recipient": recipient,
            "copyRecipient": copy_recipient or "",
            "error": request.env._("Der Mailserver hat die Nachricht nicht angenommen. Bitte den Prüfer oder Administrator informieren.") if mail.state not in ("sent", "outgoing") else "",
        }

    @http.route("/nolte_stundenbericht/api/v1/reports/internal-amendment", type="jsonrpc", auth="user", methods=["POST"])
    def internal_amendment(self, mobile_uuid, payload, expected_server_revision=None):
        if not isinstance(payload, dict):
            raise UserError(request.env._("Ungültige Nachtragsdaten."))
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        if report.state not in ("customer_confirmed", "internally_amended"):
            raise UserError(request.env._("Interne Nachträge sind erst nach der Kundenbestätigung zulässig."))
        employee = self._employee_for_request(payload.get("employeeId"))
        member = report.member_ids.filtered(lambda item: item.employee_id == employee)[:1]
        if not member:
            raise AccessError(request.env._("Dieser Mitarbeiter gehört nicht zum Einsatzbericht."))
        segments = payload.get("segments") or []
        if not isinstance(segments, list):
            raise UserError(request.env._("Die Rückfahrtsegmente müssen als Liste übermittelt werden."))
        # Only subsequent, internal return trips may be edited here.  A return
        # trip captured before customer confirmation remains part of the
        # customer-approved report and must never be replaced by this process.
        existing = {
            segment.segment_uuid: segment
            for segment in member.segment_ids.filtered(
                lambda item: item.segment_type == "return_travel" and item.internal_only
            )
        }
        received_uuids = set()
        for item in segments:
            if not isinstance(item, dict) or item.get("type") != "return_travel":
                raise UserError(request.env._("Ein interner Nachtrag darf ausschließlich Rückfahrten enthalten."))
            segment_uuid = (item.get("segmentUuid") or "").strip()
            if not segment_uuid:
                raise UserError(request.env._("Die Segmentkennung fehlt."))
            received_uuids.add(segment_uuid)
            values = {
                "segment_type": "return_travel",
                "start_time": item.get("start"),
                "end_time": item.get("end"),
                "kilometers": float(item.get("kilometers") or 0.0),
                "internal_only": True,
            }
            if segment_uuid in existing:
                existing[segment_uuid].write(values)
            else:
                request.env["nolte.service.report.segment"].create({"member_id": member.id, "segment_uuid": segment_uuid, **values})
        member.segment_ids.filtered(
            lambda item: item.segment_type == "return_travel"
            and item.internal_only
            and item.segment_uuid not in received_uuids
        ).unlink()
        internal_note = payload.get("internalNote")
        values = {"state": "internally_amended", "server_revision": report.server_revision + 1}
        if internal_note is not None:
            values["internal_note"] = internal_note
        report.write(values)
        report.message_post(body=request.env._("Interner Rückfahrtnachtrag erfasst."))
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/sync-expenses", type="jsonrpc", auth="user", methods=["POST"])
    def sync_expenses(self, mobile_uuid, expected_server_revision=None):
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        report.action_sync_spesenbericht()
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/billing-preview", type="jsonrpc", auth="user", methods=["POST"])
    def billing_preview(self, mobile_uuid, expected_server_revision=None):
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        report.action_compute_billing_preview()
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/approve-billing", type="jsonrpc", auth="user", methods=["POST"])
    def approve_billing(self, mobile_uuid, approved_quantities=None, expected_server_revision=None):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager"):
            raise AccessError(request.env._("Nur Stundenbericht-Administratoren dürfen Auftragspositionen erzeugen."))
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        report.action_approve_billing(approved_quantities)
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/reports/preview/<string:mobile_uuid>/<string:preview_format>", type="http", auth="user", methods=["GET"])
    def customer_preview(self, mobile_uuid, preview_format, **kwargs):
        if preview_format not in ("pdf", "html"):
            return request.not_found()
        # Apply the caller's record rules before rendering with elevated rights.
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report:
            return request.not_found()
        report.check_access("read")
        renderer = request.env["ir.actions.report"].sudo()
        report_ref = "nolte_stundenbericht.action_report_customer_service_report"
        if preview_format == "pdf":
            if report.customer_pdf_attachment_id:
                content = report.customer_pdf_attachment_id.raw
            else:
                content, _format = renderer._render_qweb_pdf(report_ref, report.ids)
            content_type = "application/pdf"
        else:
            # Reuse the customer template: internal checklist items stay private.
            content, _format = renderer._render_qweb_html(report_ref, report.ids)
            preview_style = b"<style>html,body,#wrapwrap{width:100%!important;max-width:none!important;margin:0!important;padding:0!important;background:#fff}body{overflow-x:auto!important}main{min-width:740px}.ns-footer{position:static!important;margin-top:20px}.ns-service-report{overflow:visible}</style>"
            content = content.replace(b"</head>", preview_style + b"</head>", 1)
            content_type = "text/html; charset=utf-8"
        return request.make_response(content, headers=[
            ("Content-Type", content_type),
            ("Content-Disposition", content_disposition("Stundenbericht.%s" % preview_format, disposition_type="inline")),
            ("Cache-Control", "private, no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])

    @http.route("/nolte_stundenbericht/reports/customer-pdf/<string:mobile_uuid>", type="http", auth="user", methods=["GET"])
    def customer_pdf(self, mobile_uuid):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report or not report.customer_pdf_attachment_id:
            raise UserError(request.env._("Der bestätigte Kundenbericht wurde nicht gefunden."))
        attachment = report.customer_pdf_attachment_id
        return request.make_response(attachment.raw, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", content_disposition(attachment.name, disposition_type="inline")),
        ])

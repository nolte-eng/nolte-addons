import hashlib
import json
from uuid import uuid4

from odoo import fields, http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.http.stream import content_disposition


class NolteStundenberichtApiV1(http.Controller):
    """Initial private API for the mobile app.

    All write requests are session-authenticated Odoo JSON-RPC calls. A future
    device-token layer may sit in front of these routes; it must not bypass the
    model-level access rules.
    """

    def _employee_for_request(self, requested_employee_id=None):
        employee_model = request.env["hr.employee"]
        own_employee = employee_model.search([("user_id", "=", request.env.user.id)], limit=1)
        is_manager = request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager")
        if requested_employee_id:
            employee = employee_model.browse(int(requested_employee_id)).exists()
            if not employee:
                raise UserError(_("Der angegebene Mitarbeiter existiert nicht."))
            if not is_manager and employee != own_employee:
                raise AccessError(_("Sie dürfen nur eigene Einsatzzeiten synchronisieren."))
            return employee
        if not own_employee:
            raise UserError(_("Für den angemeldeten Benutzer ist kein Mitarbeiter hinterlegt."))
        return own_employee

    def _serialize(self, report):
        return {
            "id": report.id,
            "mobileUuid": report.mobile_uuid,
            "mobileRevision": report.mobile_revision,
            "serverRevision": report.server_revision,
            "state": report.state,
            "serviceDate": fields.Date.to_string(report.service_date),
            "taskName": report.task_id.display_name or "",
            "customerName": report.partner_id.display_name or report.manual_customer_name or "",
            "previewPdfUrl": "/report/pdf/nolte_stundenbericht.action_report_customer_service_report/%s" % report.id,
            "countryRateKey": report.country_rate_key,
            "serviceLocation": report.service_location or "",
            "manualCustomerName": report.manual_customer_name or "",
            "manualCustomerStreet": report.manual_customer_street or "",
            "manualCustomerZip": report.manual_customer_zip or "",
            "manualCustomerCity": report.manual_customer_city or "",
            "manualContactName": report.manual_contact_name or "",
            "manualContactPhone": report.manual_contact_phone or "",
            "manualContactEmail": report.manual_contact_email or "",
            "machineNumber": report.machine_number or "",
            "machineType": report.machine_type or "",
            "overnightCount": report.overnight_count,
            "workDescription": report.work_description or "",
            "workResult": report.work_result or "",
            "expenseSyncState": report.spesen_sync_state,
            "expenseSyncMessage": report.spesen_sync_message or "",
            "customerPdfUrl": "/web/content/%s?download=false" % report.customer_pdf_attachment_id.id if report.customer_pdf_attachment_id else False,
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
            } for item in report.checklist_ids],
            "photos": [{"id": photo.id, "name": photo.name} for photo in report.photo_ids],
            "members": [
                {
                    "employeeId": member.employee_id.id,
                    "serviceDate": fields.Date.to_string(member.service_date),
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
        }

    def _report_for_update(self, mobile_uuid, expected_server_revision=None):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report:
            raise UserError(_("Der Einsatzbericht wurde nicht gefunden."))
        if expected_server_revision is not None and int(expected_server_revision) != report.server_revision:
            raise UserError(_("Der Bericht wurde auf dem Server geändert. Bitte zuerst die aktuelle Fassung laden."))
        return report

    def _customer_snapshot(self, report):
        return report.preview_customer_snapshot()

    @http.route("/nolte_stundenbericht/api/v1/bootstrap", type="jsonrpc", auth="user", methods=["POST"])
    def bootstrap(self):
        employee = self._employee_for_request()
        task_model = request.env["project.task"]
        # Some existing project stages store ``fold`` as NULL rather than False.
        # Treat only explicit terminal/folded stages as closed.
        domain = [("company_id", "in", [False, request.env.company.id]), ("stage_id.fold", "!=", True)]
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager"):
            domain.insert(0, ("user_ids", "in", [request.env.user.id]))
        tasks = task_model.search(domain, limit=100, order="write_date desc")

        def task_values(task):
            sale_order = task.sale_order_id if "sale_order_id" in task._fields else request.env["sale.order"]
            task_partner = task.partner_id
            customer = task_partner.commercial_partner_id if task_partner else request.env["res.partner"]
            contact = task_partner if task_partner and task_partner != customer else request.env["res.partner"]
            address_parts = [customer.street, customer.street2, " ".join(part for part in [customer.zip, customer.city] if part), customer.country_id.name]
            customer_address = ", ".join(part for part in address_parts if part)
            service_location = task.nolte_service_location or ""
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
                "serviceLocationDiffers": bool(service_location and service_location.strip().casefold() != customer_address.strip().casefold()),
                "machineNumber": task.nolte_machine_number or "",
                "machineType": task.nolte_machine_type or "",
                "overnightCount": task.nolte_overnight_count,
            }
        return {
            "employee": {"id": employee.id, "name": employee.name},
            "source": employee.stundenbericht_source,
            "appActiveFrom": fields.Date.to_string(employee.stundenbericht_app_active_from) if employee.stundenbericht_app_active_from else False,
            "serverTime": fields.Datetime.to_string(fields.Datetime.now()),
            "assignments": [task_values(task) for task in tasks],
        }

    @http.route("/nolte_stundenbericht/api/v1/reports/recent", type="jsonrpc", auth="user", methods=["POST"])
    def recent_reports(self):
        employee = self._employee_for_request()
        reports = request.env["nolte.service.report"].search(
            [("member_ids.employee_id", "=", employee.id)], order="service_date desc, id desc", limit=8
        )
        return [{
            "number": report.name,
            "date": fields.Date.to_string(report.service_date),
            "customer": report.partner_id.display_name or report.manual_customer_name or report.task_id.display_name or "–",
            "state": dict(report._fields["state"].selection).get(report.state, report.state),
        } for report in reports]

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
            "overnightCount": report.overnight_count,
            "segments": [{
                "type": segment.segment_type, "start": segment.start_time, "end": segment.end_time,
                "kilometers": segment.kilometers,
            } for segment in member.segment_ids.filtered(lambda item: not item.internal_only)],
        }

    @http.route("/nolte_stundenbericht/api/v1/reports/get", type="jsonrpc", auth="user", methods=["POST"])
    def get_report(self, mobile_uuid):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report:
            raise UserError(_("Der Einsatzbericht wurde nicht gefunden."))
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/photo-upload", type="jsonrpc", auth="user", methods=["POST"])
    def photo_upload(self, mobile_uuid, filename, data):
        report = self._report_for_update(mobile_uuid)
        employee = self._employee_for_request()
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_manager") and employee not in report.member_ids.employee_id:
            raise AccessError(_("Sie dürfen diesem Einsatzbericht keine Fotos hinzufügen."))
        if report.state not in ("draft", "returned"):
            raise UserError(_("Fotos können nach der Kundenbestätigung nicht mehr geändert werden."))
        if not isinstance(data, str) or not data.startswith("data:image/") or "," not in data:
            raise UserError(_("Das Foto hat kein unterstütztes Bildformat."))
        encoded = data.split(",", 1)[1]
        if len(encoded) > 12 * 1024 * 1024:
            raise UserError(_("Ein Foto darf höchstens 9 MB groß sein."))
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
            raise UserError(_("Ungültige Synchronisationsdaten."))
        mobile_uuid = (payload.get("mobileUuid") or "").strip()
        if not mobile_uuid:
            raise UserError(_("Die mobile Berichtskennung fehlt."))
        employee = self._employee_for_request(payload.get("employeeId"))
        report_model = request.env["nolte.service.report"]
        report = report_model.search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        client_revision = int(payload.get("mobileRevision") or 0)
        expected_server_revision = payload.get("serverRevision")
        if report and expected_server_revision is not None and int(expected_server_revision) != report.server_revision:
            raise UserError(_("Der Bericht wurde auf dem Server geändert. Bitte zuerst die aktuelle Fassung laden."))

        allowed = {
            "service_date": payload.get("serviceDate"),
            "country_rate_key": payload.get("countryRateKey") or "DE",
            "service_location": payload.get("serviceLocation") or False,
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
        task = request.env["project.task"].browse(task_id).exists() if task_id else request.env["project.task"]
        if task_id and not task:
            raise UserError(_("Der ausgewählte Einsatzauftrag existiert nicht mehr."))
        if task:
            task_values = {
                "nolte_service_location": payload.get("serviceLocation") or task.nolte_service_location,
                "nolte_machine_number": payload.get("machineNumber") or task.nolte_machine_number,
                "nolte_machine_type": payload.get("machineType") or task.nolte_machine_type,
            }
            if payload.get("machineNumber") or payload.get("machineType") or payload.get("serviceLocation"):
                task_values["nolte_overnight_count"] = int(payload.get("overnightCount") or 0)
                task.write(task_values)
            allowed.update({
                "service_location": allowed["service_location"] or task.nolte_service_location or False,
                "machine_number": allowed["machine_number"] or task.nolte_machine_number or False,
                "machine_type": allowed["machine_type"] or task.nolte_machine_type or False,
                "overnight_count": allowed["overnight_count"] or task.nolte_overnight_count or 0,
            })
        partner_id = int(payload["partnerId"]) if payload.get("partnerId") else False
        partner = request.env["res.partner"].browse(partner_id).exists() if partner_id else request.env["res.partner"]
        if partner_id and not partner:
            raise UserError(_("Der ausgewählte Kunde existiert nicht mehr."))
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
            raise UserError(_("Das Einsatzdatum fehlt."))
        if not report:
            report = report_model.create({
                **allowed,
                "mobile_uuid": mobile_uuid,
                "mobile_revision": client_revision,
                "owner_user_id": request.env.user.id,
            })
        else:
            if report.state not in ("draft", "returned"):
                raise UserError(_("Dieser Bericht ist nicht mehr über den Entwurfsabgleich änderbar."))
            report.write({**allowed, "mobile_revision": client_revision, "server_revision": report.server_revision + 1})

        days = payload.get("days")
        # Older local drafts created before multi-day support can contain an
        # empty ``days`` list.  Preserve their report date as a valid service
        # day instead of blocking every pending local draft during sync.
        if not days:
            days = [{"date": payload.get("serviceDate"), "segments": payload.get("segments") or []}]
        if not isinstance(days, list) or not days:
            raise UserError(_("Mindestens ein Einsatztag muss übermittelt werden."))
        segment_model = request.env["nolte.service.report.segment"]
        received_days = set()
        for day in days:
            if not isinstance(day, dict) or not day.get("date") or not isinstance(day.get("segments") or [], list):
                raise UserError(_("Ein Einsatztag ist ungültig."))
            service_date = fields.Date.to_date(day["date"])
            received_days.add(service_date)
            member = report.member_ids.filtered(lambda item: item.employee_id == employee and item.service_date == service_date)[:1]
            if not member:
                member = request.env["nolte.service.report.member"].create({"report_id": report.id, "employee_id": employee.id, "service_date": service_date})
            existing = {segment.segment_uuid: segment for segment in member.segment_ids}
            received_uuids = set()
            for item in day.get("segments") or []:
                if not isinstance(item, dict):
                    raise UserError(_("Ein Zeitsegment ist ungültig."))
                segment_uuid = (item.get("segmentUuid") or "").strip()
                if not segment_uuid:
                    raise UserError(_("Die Segmentkennung fehlt."))
                values = {"segment_type": item.get("type"), "start_time": item.get("start"), "end_time": item.get("end"), "kilometers": float(item.get("kilometers") or 0.0), "internal_only": bool(item.get("internalOnly"))}
                if values["segment_type"] not in {"outbound_travel", "work", "return_travel", "break"}:
                    raise UserError(_("Ein Zeitsegment hat einen unbekannten Typ."))
                if segment_uuid in existing:
                    existing[segment_uuid].write(values)
                else:
                    # Drafts made by an older offline version can reuse an ID
                    # after a day was copied.  Reuse it inside this report;
                    # for an ID belonging to another report, mint a new one so
                    # the technician can still complete the synchronization.
                    collision = segment_model.search([("segment_uuid", "=", segment_uuid)], limit=1)
                    if collision and collision.report_id == report:
                        collision.write({"member_id": member.id, **values})
                    else:
                        if collision:
                            segment_uuid = str(uuid4())
                        segment_model.create({"member_id": member.id, "segment_uuid": segment_uuid, **values})
                received_uuids.add(segment_uuid)
            member.segment_ids.filtered(lambda segment: segment.segment_uuid not in received_uuids).unlink()
        report.member_ids.filtered(lambda item: item.employee_id == employee and item.service_date not in received_days).unlink()
        materials = payload.get("materials") or []
        if not isinstance(materials, list):
            raise UserError(_("Die Materialliste ist ungültig."))
        existing_materials = {material.mobile_uuid: material for material in report.material_ids}
        received_material_uuids = set()
        for sequence, item in enumerate(materials, start=1):
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise UserError(_("Jede Materialzeile benötigt eine Bezeichnung."))
            material_uuid = str(item.get("materialUuid") or "").strip()
            if not material_uuid:
                raise UserError(_("Die Materialkennung fehlt."))
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
        checklist = payload.get("checklist") or []
        if not isinstance(checklist, list):
            raise UserError(_("Die Checkliste ist ungültig."))
        existing_checklist = {item.mobile_uuid: item for item in report.checklist_ids}
        received_checklist_uuids = set()
        for sequence, item in enumerate(checklist, start=1):
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise UserError(_("Jeder Checklistenpunkt benötigt eine Bezeichnung."))
            checklist_uuid = str(item.get("checklistUuid") or "").strip()
            if not checklist_uuid:
                raise UserError(_("Die Checklistenkennung fehlt."))
            received_checklist_uuids.add(checklist_uuid)
            values = {
                "name": str(item["name"]).strip(),
                "checked": bool(item.get("checked")),
                "note": str(item.get("note") or "").strip() or False,
                "sequence": sequence,
            }
            if checklist_uuid in existing_checklist:
                existing_checklist[checklist_uuid].write(values)
            else:
                request.env["nolte.service.report.checklist"].create({"report_id": report.id, "mobile_uuid": checklist_uuid, **values})
        report.checklist_ids.filtered(lambda item: item.mobile_uuid not in received_checklist_uuids).unlink()
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/customer-confirm", type="jsonrpc", auth="user", methods=["POST"])
    def customer_confirm(self, mobile_uuid, signer_name, signature, expected_server_revision=None):
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        if report.state not in ("draft", "returned"):
            raise UserError(_("Der Bericht kann in seinem aktuellen Status nicht vom Kunden bestätigt werden."))
        if not signer_name or not str(signer_name).strip():
            raise UserError(_("Der Name des Unterzeichners fehlt."))
        if not signature:
            raise UserError(_("Die Kundenunterschrift fehlt."))
        # Canvas.toDataURL() includes a ``data:image/png;base64,`` prefix;
        # Odoo Binary fields expect only the base64 payload.
        if isinstance(signature, str) and signature.startswith("data:"):
            signature = signature.split(",", 1)[-1]
        snapshot = self._customer_snapshot(report)
        snapshot_payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        snapshot_hash = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        report.write({
            "state": "customer_confirmed",
            "customer_signer_name": str(signer_name).strip(),
            "customer_signed_at": fields.Datetime.now(),
            "customer_signature": signature,
            "customer_snapshot_payload": snapshot_payload,
            "customer_snapshot_hash": snapshot_hash,
            "server_revision": report.server_revision + 1,
        })
        pdf, report_format = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "nolte_stundenbericht.action_report_customer_service_report", report.ids
        )
        attachment = request.env["ir.attachment"].create({
            "name": "Kunden-Stundenbericht_%s.pdf" % report.name.replace("/", "-"),
            "datas": __import__("base64").b64encode(pdf),
            "mimetype": "application/pdf",
            "res_model": report._name,
            "res_id": report.id,
        })
        report.write({"customer_pdf_attachment_id": attachment.id})
        report.message_post(body=_("Kundenfassung bestätigt von %s.") % report.customer_signer_name)
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/api/v1/reports/internal-amendment", type="jsonrpc", auth="user", methods=["POST"])
    def internal_amendment(self, mobile_uuid, payload, expected_server_revision=None):
        if not isinstance(payload, dict):
            raise UserError(_("Ungültige Nachtragsdaten."))
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        if report.state not in ("customer_confirmed", "internally_amended"):
            raise UserError(_("Interne Nachträge sind erst nach der Kundenbestätigung zulässig."))
        employee = self._employee_for_request(payload.get("employeeId"))
        member = report.member_ids.filtered(lambda item: item.employee_id == employee)[:1]
        if not member:
            raise AccessError(_("Dieser Mitarbeiter gehört nicht zum Einsatzbericht."))
        segments = payload.get("segments") or []
        if not isinstance(segments, list):
            raise UserError(_("Die Rückfahrtsegmente müssen als Liste übermittelt werden."))
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
                raise UserError(_("Ein interner Nachtrag darf ausschließlich Rückfahrten enthalten."))
            segment_uuid = (item.get("segmentUuid") or "").strip()
            if not segment_uuid:
                raise UserError(_("Die Segmentkennung fehlt."))
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
        report.message_post(body=_("Interner Rückfahrtnachtrag erfasst."))
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
            raise AccessError(_("Nur Stundenbericht-Administratoren dürfen Auftragspositionen erzeugen."))
        report = self._report_for_update(mobile_uuid, expected_server_revision)
        report.action_approve_billing(approved_quantities)
        return self._serialize(report)

    @http.route("/nolte_stundenbericht/reports/customer-pdf/<string:mobile_uuid>", type="http", auth="user", methods=["GET"])
    def customer_pdf(self, mobile_uuid):
        report = request.env["nolte.service.report"].search([("mobile_uuid", "=", mobile_uuid)], limit=1)
        if not report or not report.customer_pdf_attachment_id:
            raise UserError(_("Der bestätigte Kundenbericht wurde nicht gefunden."))
        attachment = report.customer_pdf_attachment_id
        return request.make_response(attachment.raw, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", content_disposition(attachment.name, disposition_type="inline")),
        ])

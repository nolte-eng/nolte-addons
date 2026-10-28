from odoo import _, api, models, fields, Command
from odoo.exceptions import AccessError


class ProjectTask(models.Model):
    _inherit = "project.task"

    nolte_service_planning = fields.Boolean(compute="_compute_nolte_service_planning")

    @api.depends("project_id.name")
    def _compute_nolte_service_planning(self):
        for task in self:
            task.nolte_service_planning = task.project_id.with_context(lang=None).name == "Aussendienst"

    def _check_nolte_planning_archive_access(self):
        self.ensure_one()
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_approver"):
            raise AccessError(_("Nur Prüfer und Administratoren dürfen Serviceeinsätze in der Planung archivieren."))
        self.check_access("write")
        if not self.nolte_service_planning:
            raise AccessError(_("Diese Aktion ist nur für die Serviceplanung Aussendienst verfügbar."))

    def action_nolte_archive_service(self):
        self._check_nolte_planning_archive_access()
        self.action_archive()
        return {"type": "ir.actions.act_url", "url": "/odoo/project/%s/tasks" % self.project_id.id, "target": "self"}

    def action_nolte_restore_service(self):
        self._check_nolte_planning_archive_access()
        self.action_unarchive()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _nolte_closed_for_mobile(self, reports=None):
        self.ensure_one()
        stage = (self.stage_id.with_context(lang=None).name or "").strip().casefold()
        if not self.active or self.state in ("1_done", "1_canceled") or self.stage_id.fold or stage in ("abgeschlossen", "abgerechnet"):
            return True
        if reports is None:
            reports = self.env["nolte.service.report"].sudo().search([("task_id", "=", self.id)])
        return bool(reports) and all(reports.mapped("is_closed"))

    def write(self, values):
        result = super().write(values)
        if not self.env.context.get("install_mode") and not self.env.context.get("nolte_skip_planning_sync") and {"date_deadline", "user_ids"}.intersection(values):
            self._sync_nolte_planning_drafts()
        return result

    def _sync_nolte_planning_drafts(self):
        """Update only untouched planning placeholders after an authorized task edit.

        Once field work starts, signatures, times, report ownership and existing
        expense/billing data are never moved by a later planning change.
        """
        group = self.env.ref("nolte_stundenbericht.group_stundenbericht_user", raise_if_not_found=False)
        if not group:
            return
        for task in self:
            if task.project_id.with_context(lang=None).name != "Aussendienst":
                continue
            stage_name = (task.stage_id.with_context(lang=None).name or "").strip().casefold()
            if task.state == "1_done" or stage_name in ("abgeschlossen", "abgerechnet"):
                continue
            # The originating write already enforced task access. Elevation is
            # limited to its own pristine, company-matching prepared reports.
            reports = self.env["nolte.service.report"].sudo().search([
                ("task_id", "=", task.id), ("company_id", "=", task.company_id.id or self.env.company.id),
                ("planning_draft", "=", True), ("state", "=", "draft"),
            ])
            for report in reports:
                if (report.mobile_revision or report.member_ids.segment_ids or report.work_description or report.work_result
                        or report.public_note or report.photo_ids or report.material_ids or report.flat_rate_line_ids
                        or report.customer_pdf_attachment_id or report.sale_order_id
                        or report.member_ids.work_report_line_id or report.member_ids.expense_report_line_id
                        or report.member_ids.attendance_ids or report.member_ids.billing_sale_line_ids
                        or len(report.member_ids) != len(report.member_ids.mapped("employee_id"))
                        or report.checklist_ids.filtered("checked")
                        or any(report.employee_assignment_ids.mapped("overnight_count"))):
                    report.planning_draft = False
                    continue
                employees = self.env["hr.employee"].sudo().search([
                    ("user_id", "in", task.user_ids.ids), ("active", "=", True),
                    ("user_id.group_ids", "in", group.id),
                    "|", ("company_id", "=", False), ("company_id", "=", report.company_id.id),
                ], order="name, id")
                users = employees.mapped("user_id")
                owner = (report.owner_user_id if report.owner_user_id in users else
                         (self.env.user if self.env.user in users else users[:1])) or report.create_uid
                service_date = fields.Date.to_date(task.date_deadline) or report.service_date
                existing = report.member_ids.mapped("employee_id")
                removed_members = report.member_ids.filtered(lambda member: member.employee_id not in employees)
                removed_members.unlink()
                report.member_ids.write({"service_date": service_date})
                report.employee_assignment_ids.filtered(lambda assignment: assignment.employee_id not in employees).unlink()
                assigned = report.employee_assignment_ids.mapped("employee_id")
                report.write({"owner_user_id": owner.id, "service_date": service_date,
                    "member_ids": [Command.create({"employee_id": employee.id, "service_date": service_date}) for employee in employees - existing],
                    "employee_assignment_ids": [Command.create({"employee_id": employee.id}) for employee in employees - assigned],
                })
            # A date alone is sufficient for 'Einsatz geplant'. Do not move
            # in-progress or completed work back into a planning column.
            if stage_name in ("ungeplant", "einsatz geplant") and task.state != "1_done":
                stage = self.env["project.task.type"].search([
                    ("name", "=", "Einsatz geplant" if task.date_deadline else "Ungeplant"),
                    "|", ("project_ids", "=", False), ("project_ids", "in", task.project_id.id),
                ], order="sequence, id", limit=1)
                if stage and stage != task.stage_id:
                    task.with_context(nolte_skip_planning_sync=True).write({"stage_id": stage.id})

    def action_open_nolte_customer_history(self):
        self.ensure_one()
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(_("Sie dürfen keine Kundenhistorie öffnen."))
        if self.env.user not in self.user_ids:
            raise AccessError(_("Die Kundenhistorie ist nur für Ihnen zugewiesene Einsätze verfügbar."))
        return {
            "type": "ir.actions.act_url",
            "url": "/my/stundenbericht/history/%s" % self.id,
            "target": "new",
        }

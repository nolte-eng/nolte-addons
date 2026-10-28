from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError


class NolteServiceIntakeWizard(models.TransientModel):
    _name = "nolte.service.intake.wizard"
    _description = "Neuen Serviceeinsatz anlegen"

    name = fields.Char(string="Auftrag / Einsatz", required=True)
    project_id = fields.Many2one(
        "project.project", string="Projekt", required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        default=lambda self: self._default_project_id(),
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    partner_id = fields.Many2one(
        "res.partner", string="Kunde", required=True,
        domain="[('customer_rank', '>', 0), ('parent_id', '=', False)]",
    )
    service_contact_id = fields.Many2one(
        "res.partner", string="Ansprechpartner", domain="[('parent_id', '=', partner_id)]",
    )
    service_location_contact_id = fields.Many2one(
        "res.partner", string="Einsatzort aus Kontakten",
        domain="[('active', '=', True)]",
    )
    technician_ids = fields.Many2many(
        "hr.employee", string="Servicetechniker",
        domain=lambda self: [("active", "=", True), ("user_id.group_ids", "in", self.env.ref("nolte_stundenbericht.group_stundenbericht_user").id),
                             "|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)],
    )
    report_owner_employee_id = fields.Many2one("hr.employee", string="Berichtverantwortlich",
        domain="[('id', 'in', technician_ids)]",
        help="Dieser Monteur führt den gemeinsamen Stundenbericht in der App weiter.")
    created_report_id = fields.Many2one("nolte.service.report", readonly=True, copy=False)
    planned_date = fields.Date(string="Geplanter Termin")
    service_location = fields.Text(
        string="Abweichender Einsatzort",
        help="Leer lassen, wenn der Einsatz beim Kunden stattfindet. Sonst vollständige Adresse eintragen.",
    )
    service_location_name = fields.Char(string="Firma am Einsatzort")
    service_location_contact_name = fields.Char(string="Ansprechpartner am Einsatzort")
    service_location_contact_phone = fields.Char(string="Telefon am Einsatzort")
    machine_number = fields.Char(string="Maschinen-Nr.")
    machine_type_id = fields.Many2one("nolte.machine.type", string="Maschinentyp")
    work_description = fields.Text(string="Arbeitsauftrag / Fehlerbild")

    @api.model
    def _default_project_id(self):
        context_project = self.env.context.get("default_project_id")
        if context_project:
            return context_project
        if self.env.context.get("active_model") == "project.project":
            return self.env.context.get("active_id")
        Project = self.env["project.project"]
        company_domain = [
            "|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)
        ]
        # Use the service project as the default even when another project
        # happens to sort first. Keep a generic fallback for other databases.
        service_project = Project.search(
            [("name", "=", "Aussendienst"), *company_domain],
            order="company_id, sequence, id", limit=1,
        )
        if service_project:
            return service_project.id
        return Project.search(company_domain, order="sequence, id", limit=1).id

    @api.model
    def default_get(self, field_list):
        self._sync_machine_type_catalog()
        return super().default_get(field_list)

    @api.model
    def _sync_machine_type_catalog(self):
        """Make machine types already used on tasks selectable in the wizard."""
        grouped_types = self.env["project.task"].sudo()._read_group(
            [("nolte_machine_type", "!=", False)],
            groupby=["nolte_machine_type"],
            aggregates=[],
        )
        names = {
            value.strip() for (value,) in grouped_types if value and value.strip()
        }
        if not names:
            return
        catalog = self.env["nolte.machine.type"].sudo()
        existing = set(catalog.search([("name", "in", list(names))]).mapped("name"))
        missing = sorted(names - existing)
        if missing:
            catalog.create([{"name": name} for name in missing])

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.service_contact_id = False

    @api.onchange("technician_ids")
    def _onchange_technician_ids(self):
        if self.report_owner_employee_id not in self.technician_ids:
            self.report_owner_employee_id = self.technician_ids.filtered(lambda employee: employee.user_id == self.env.user)[:1] or self.technician_ids[:1]

    @api.onchange("service_location_contact_id")
    def _onchange_service_location_contact_id(self):
        for wizard in self:
            contact = wizard.service_location_contact_id
            if not contact:
                continue
            wizard.service_location_name = contact.parent_id.name or contact.name
            wizard.service_location_contact_name = contact.name or ""
            wizard.service_location_contact_phone = (
                (contact.mobile if "mobile" in contact._fields else False)
                or (contact.phone if "phone" in contact._fields else False)
                or ""
            )
            address = [contact.street, contact.street2]
            locality = " ".join(part for part in (contact.zip, contact.city) if part)
            if locality:
                address.append(locality)
            if contact.state_id:
                address.append(contact.state_id.name)
            if contact.country_id:
                address.append(contact.country_id.name)
            wizard.service_location = ", ".join(part.strip() for part in address if part and part.strip())

    def action_create_service_task(self):
        self.ensure_one()
        self.check_access("write")
        # Serialize retries/double clicks on the same saved planning wizard.
        self.flush_recordset()
        self.env.cr.execute("SELECT id FROM nolte_service_intake_wizard WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["created_report_id"])
        if self.created_report_id:
            self.created_report_id.check_access("read")
            return self._created_report_action()
        name = (self.name or "").strip()
        if not name:
            raise UserError(_("Bitte eine Bezeichnung für den Einsatz eingeben."))
        technicians = self.technician_ids.filtered(lambda employee: employee.user_id)
        group = self.env.ref("nolte_stundenbericht.group_stundenbericht_user")
        allowed = self.env["hr.employee"].sudo().search([
            ("id", "in", technicians.ids), ("active", "=", True), ("user_id.group_ids", "in", group.id),
            "|", ("company_id", "=", False), ("company_id", "=", self.company_id.id),
        ])
        if set(allowed.ids) != set(self.technician_ids.ids):
            raise UserError(_("Alle ausgewählten Servicetechniker müssen für Stundenbericht Monteur im gewählten Unternehmen freigeschaltet sein."))
        owner = self.report_owner_employee_id or technicians.filtered(lambda employee: employee.user_id == self.env.user)[:1] or technicians[:1]
        if owner and owner not in technicians:
            raise UserError(_("Der Berichtverantwortliche muss ein ausgewählter Servicetechniker sein."))
        if self.project_id.company_id and self.project_id.company_id != self.company_id:
            raise UserError(_("Projekt und Serviceeinsatz müssen zum selben Unternehmen gehören."))
        planned_stage = self.env["project.task.type"].search([
            ("name", "=", "Einsatz geplant" if self.planned_date else "Ungeplant"),
            "|", ("project_ids", "=", False), ("project_ids", "in", [self.project_id.id]),
        ], order="sequence, id", limit=1)
        values = {
            "name": name,
            "project_id": self.project_id.id,
            "company_id": self.project_id.company_id.id or self.company_id.id,
            "partner_id": self.partner_id.id,
            "nolte_service_contact_id": self.service_contact_id.id or False,
            "user_ids": [(6, 0, technicians.mapped("user_id").ids)],
            "date_deadline": self.planned_date or False,
            "nolte_service_location": (self.service_location or "").strip() or False,
            "nolte_service_location_name": (self.service_location_name or "").strip() or False,
            "nolte_service_location_contact_name": (self.service_location_contact_name or "").strip() or False,
            "nolte_service_location_contact_phone": (self.service_location_contact_phone or "").strip() or False,
            "nolte_machine_number": (self.machine_number or "").strip() or False,
            "nolte_machine_type": self.machine_type_id.name or False,
            "description": (self.work_description or "").strip() or False,
        }
        if planned_stage:
            values["stage_id"] = planned_stage.id
        if "x_customer_id" in self.env["project.task"]._fields:
            values["x_customer_id"] = self.partner_id.id
        task = self.env["project.task"].create(values)
        service_date = self.planned_date or fields.Date.context_today(self)
        template = self.env["nolte.service.checklist.template"].with_company(self.company_id)._default_for_current_company()
        report = self.env["nolte.service.report"].create({
            "task_id": task.id, "partner_id": self.partner_id.id, "company_id": self.company_id.id,
            "owner_user_id": owner.user_id.id if owner else self.env.user.id, "service_date": service_date,
            "planning_draft": True,
            "service_location": values["nolte_service_location"],
            "service_location_name": values["nolte_service_location_name"],
            "service_location_contact_name": values["nolte_service_location_contact_name"],
            "service_location_contact_phone": values["nolte_service_location_contact_phone"],
            "machine_number": values["nolte_machine_number"], "machine_type": values["nolte_machine_type"],
            "employee_assignment_ids": [Command.create({"employee_id": employee.id}) for employee in technicians],
            "member_ids": [Command.create({"employee_id": employee.id, "service_date": service_date}) for employee in technicians],
            "checklist_ids": [Command.create({"name": line.name, "note": line.note or False,
                "visibility": "customer", "checked": False, "sequence": line.sequence}) for line in template.line_ids],
        })
        self.created_report_id = report
        return self._created_report_action()

    def _created_report_action(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Einsatzbericht"),
            "res_model": "nolte.service.report",
            "res_id": self.created_report_id.id,
            "views": [(False, "form")],
            "target": "current",
        }

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NolteBillingApprovalWizard(models.TransientModel):
    _name = "nolte.service.report.billing.wizard"
    _description = "Freigabe der Einsatzabrechnung"

    report_id = fields.Many2one("nolte.service.report", readonly=True)
    report_ids = fields.Many2many("nolte.service.report", string="Maschinenberichte", readonly=True)
    combined_preview = fields.Json(readonly=True)
    line_ids = fields.One2many("nolte.service.report.billing.wizard.line", "wizard_id", string="Freigaben")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        report = self.env["nolte.service.report"].browse(self.env.context.get("active_id")).exists()
        if not report:
            return values
        if report.state != "under_review" or any(member.billing_state != "preview" for member in report.member_ids):
            raise UserError(_("Der Bericht benötigt zuerst eine vollständige Abrechnungsvorschau und Büroprüfung."))
        values.update({"report_id": report.id, "line_ids": self._preview_lines(report.member_ids)})
        return values

    def _preview_lines(self, members, previews=None):
        lines = []
        for member in members:
            preview = previews[str(member.id)] if previews is not None else member.billing_preview or {}
            work, travel = preview.get("work") or {}, preview.get("travel") or {}
            lines.append((0, 0, {
                "member_id": member.id,
                "employee_id": member.employee_id.id,
                "work_normal": work.get("normal", 0.0), "work_ot30": work.get("ot30", 0.0), "work_ot50": work.get("ot50", 0.0),
                "travel_normal": travel.get("normal", 0.0), "travel_ot30": travel.get("ot30", 0.0), "travel_ot50": travel.get("ot50", 0.0),
                "kilometers": preview.get("kilometers", 0.0), "overnights": preview.get("overnights", 0.0),
                "allowance_days": preview.get("allowance_days", 1.0),
                "calculated_work_normal": work.get("normal", 0.0), "calculated_work_ot30": work.get("ot30", 0.0), "calculated_work_ot50": work.get("ot50", 0.0),
                "calculated_travel_normal": travel.get("normal", 0.0), "calculated_travel_ot30": travel.get("ot30", 0.0), "calculated_travel_ot50": travel.get("ot50", 0.0),
                "calculated_kilometers": preview.get("kilometers", 0.0), "calculated_overnights": preview.get("overnights", 0.0),
                "calculated_allowance_days": preview.get("allowance_days", 1.0),
            }))
        return lines

    def action_approve(self):
        self.ensure_one()
        if self.report_ids:
            return self._approve_combined()
        quantities = {}
        keys = ("work_normal", "work_ot30", "work_ot50", "travel_normal", "travel_ot30", "travel_ot50", "kilometers", "overnights", "allowance_days")
        for line in self.line_ids:
            member = line.member_id or self.report_id.member_ids.filtered(lambda item: item.employee_id == line.employee_id)[:1]
            if not member:
                continue
            quantities[str(member.id)] = {key: getattr(line, key) for key in keys}
        if not quantities:
            # Some Odoo web clients do not submit untouched transient
            # one2many defaults. Fall back to the immutable server preview.
            for member in self.report_id.member_ids:
                preview = member.billing_preview or {}
                work, travel = preview.get("work") or {}, preview.get("travel") or {}
                quantities[str(member.id)] = {
                    "work_normal": work.get("normal", 0.0), "work_ot30": work.get("ot30", 0.0), "work_ot50": work.get("ot50", 0.0),
                    "travel_normal": travel.get("normal", 0.0), "travel_ot30": travel.get("ot30", 0.0), "travel_ot50": travel.get("ot50", 0.0),
                    "kilometers": preview.get("kilometers", 0.0), "overnights": preview.get("overnights", 0.0),
                    "allowance_days": preview.get("allowance_days", 1.0),
                }
        self.report_id.action_approve_billing(quantities)
        return {"type": "ir.actions.act_window", "res_model": "nolte.service.report", "res_id": self.report_id.id, "view_mode": "form"}

    def _approve_combined(self):
        reports = self.report_ids
        reports.check_access("write")
        reports.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM nolte_service_report WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(reports.ids)],
        )
        reports.invalidate_recordset()
        reports._check_combined_billing_reports()
        previews = reports._combined_billing_previews()
        if previews != self.combined_preview:
            raise UserError(_("Die Abrechnungsdaten wurden geändert. Bitte die gemeinsame Vorschau erneut öffnen."))
        members = reports.member_ids
        if sorted(self.line_ids.member_id.ids) != sorted(members.ids) or len(self.line_ids) != len(members):
            raise UserError(_("Die Vorschau enthält unvollständige oder ungültige Freigabezeilen."))
        allowances = set()
        quantities = {}
        keys = ("work_normal", "work_ot30", "work_ot50", "travel_normal", "travel_ot30", "travel_ot50", "kilometers", "overnights", "allowance_days")
        for line in self.line_ids:
            member = line.member_id
            key = (member.employee_id.id, member.service_date)
            if line.allowance_days not in (0, 1) or (line.allowance_days and key in allowances):
                raise UserError(_("Pro Mitarbeiter und Tag darf die Auslöse höchstens einmal freigegeben werden."))
            if line.allowance_days:
                allowances.add(key)
            quantities[str(member.id)] = {field: line[field] for field in keys}
            preview = previews[str(member.id)]
            preview["allowance_days"] = line.allowance_days
            member.sudo().write({"billing_preview": preview, "billing_state": "preview"})
        reports.sorted("id").action_approve_billing(quantities)
        return {"type": "ir.actions.act_window_close"}


class NolteBillingApprovalWizardLine(models.TransientModel):
    _name = "nolte.service.report.billing.wizard.line"
    _description = "Freigabezeile Einsatzabrechnung"

    wizard_id = fields.Many2one("nolte.service.report.billing.wizard", required=True, ondelete="cascade")
    # A transient client-side draft row may briefly exist while the editable
    # list is rendered. It is ignored by action_approve and must not block
    # the actual approval rows.
    member_id = fields.Many2one("nolte.service.report.member", readonly=True)
    report_id = fields.Many2one(related="member_id.report_id", string="Bericht", readonly=True)
    machine_number = fields.Char(related="member_id.report_id.machine_number", string="Maschinen-Nr.", readonly=True)
    service_date = fields.Date(related="member_id.service_date", string="Einsatztag", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Mitarbeiter", readonly=True)
    calculated_work_normal = fields.Float(string="Berechnet Arbeit normal", readonly=True)
    calculated_work_ot30 = fields.Float(string="Berechnet Arbeit 30 %", readonly=True)
    calculated_work_ot50 = fields.Float(string="Berechnet Arbeit 50 %", readonly=True)
    calculated_travel_normal = fields.Float(string="Berechnet Fahrt normal", readonly=True)
    calculated_travel_ot30 = fields.Float(string="Berechnet Fahrt 30 %", readonly=True)
    calculated_travel_ot50 = fields.Float(string="Berechnet Fahrt 50 %", readonly=True)
    calculated_kilometers = fields.Float(string="Berechnete Kilometer", readonly=True)
    calculated_overnights = fields.Float(string="Berechnete Übernachtungen", readonly=True)
    calculated_allowance_days = fields.Float(string="Berechnete Auslöse-Tage", readonly=True)
    work_normal = fields.Float(string="Arbeit normal")
    work_ot30 = fields.Float(string="Arbeit 30 %")
    work_ot50 = fields.Float(string="Arbeit 50 %")
    travel_normal = fields.Float(string="Fahrt normal")
    travel_ot30 = fields.Float(string="Fahrt 30 %")
    travel_ot50 = fields.Float(string="Fahrt 50 %")
    kilometers = fields.Float(string="Kilometer")
    overnights = fields.Float(string="Übernachtungen")
    allowance_days = fields.Float(string="Auslöse-Tage")

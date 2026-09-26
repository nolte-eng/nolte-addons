from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NolteBillingApprovalWizard(models.TransientModel):
    _name = "nolte.service.report.billing.wizard"
    _description = "Freigabe der Einsatzabrechnung"

    report_id = fields.Many2one("nolte.service.report", required=True, readonly=True)
    line_ids = fields.One2many("nolte.service.report.billing.wizard.line", "wizard_id", string="Freigaben")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        report = self.env["nolte.service.report"].browse(self.env.context.get("active_id")).exists()
        if not report:
            return values
        if report.state not in ("under_review", "ready_to_bill") or any(member.billing_state != "preview" for member in report.member_ids):
            raise UserError(_("Der Bericht benötigt zuerst eine vollständige Abrechnungsvorschau und Büroprüfung."))
        lines = []
        for member in report.member_ids:
            preview = member.billing_preview or {}
            work, travel = preview.get("work") or {}, preview.get("travel") or {}
            lines.append((0, 0, {
                "member_id": member.id,
                "employee_id": member.employee_id.id,
                "work_normal": work.get("normal", 0.0), "work_ot30": work.get("ot30", 0.0), "work_ot50": work.get("ot50", 0.0),
                "travel_normal": travel.get("normal", 0.0), "travel_ot30": travel.get("ot30", 0.0), "travel_ot50": travel.get("ot50", 0.0),
                "kilometers": preview.get("kilometers", 0.0), "overnights": preview.get("overnights", 0.0),
                "calculated_work_normal": work.get("normal", 0.0), "calculated_work_ot30": work.get("ot30", 0.0), "calculated_work_ot50": work.get("ot50", 0.0),
                "calculated_travel_normal": travel.get("normal", 0.0), "calculated_travel_ot30": travel.get("ot30", 0.0), "calculated_travel_ot50": travel.get("ot50", 0.0),
                "calculated_kilometers": preview.get("kilometers", 0.0), "calculated_overnights": preview.get("overnights", 0.0),
            }))
        values.update({"report_id": report.id, "line_ids": lines})
        return values

    def action_approve(self):
        self.ensure_one()
        quantities = {}
        keys = ("work_normal", "work_ot30", "work_ot50", "travel_normal", "travel_ot30", "travel_ot50", "kilometers", "overnights")
        for line in self.line_ids:
            member = line.member_id or self.report_id.member_ids.filtered(lambda item: item.employee_id == line.employee_id)[:1]
            if not member:
                continue
            quantities[str(member.employee_id.id)] = {key: getattr(line, key) for key in keys}
        if not quantities:
            # Some Odoo web clients do not submit untouched transient
            # one2many defaults. Fall back to the immutable server preview.
            for member in self.report_id.member_ids:
                preview = member.billing_preview or {}
                work, travel = preview.get("work") or {}, preview.get("travel") or {}
                quantities[str(member.employee_id.id)] = {
                    "work_normal": work.get("normal", 0.0), "work_ot30": work.get("ot30", 0.0), "work_ot50": work.get("ot50", 0.0),
                    "travel_normal": travel.get("normal", 0.0), "travel_ot30": travel.get("ot30", 0.0), "travel_ot50": travel.get("ot50", 0.0),
                    "kilometers": preview.get("kilometers", 0.0), "overnights": preview.get("overnights", 0.0),
                }
        self.report_id.action_approve_billing(quantities)
        return {"type": "ir.actions.act_window", "res_model": "nolte.service.report", "res_id": self.report_id.id, "view_mode": "form"}


class NolteBillingApprovalWizardLine(models.TransientModel):
    _name = "nolte.service.report.billing.wizard.line"
    _description = "Freigabezeile Einsatzabrechnung"

    wizard_id = fields.Many2one("nolte.service.report.billing.wizard", required=True, ondelete="cascade")
    # A transient client-side draft row may briefly exist while the editable
    # list is rendered. It is ignored by action_approve and must not block
    # the actual approval rows.
    member_id = fields.Many2one("nolte.service.report.member", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Mitarbeiter", readonly=True)
    calculated_work_normal = fields.Float(string="Berechnet Arbeit normal", readonly=True)
    calculated_work_ot30 = fields.Float(string="Berechnet Arbeit 30 %", readonly=True)
    calculated_work_ot50 = fields.Float(string="Berechnet Arbeit 50 %", readonly=True)
    calculated_travel_normal = fields.Float(string="Berechnet Fahrt normal", readonly=True)
    calculated_travel_ot30 = fields.Float(string="Berechnet Fahrt 30 %", readonly=True)
    calculated_travel_ot50 = fields.Float(string="Berechnet Fahrt 50 %", readonly=True)
    calculated_kilometers = fields.Float(string="Berechnete Kilometer", readonly=True)
    calculated_overnights = fields.Float(string="Berechnete Übernachtungen", readonly=True)
    work_normal = fields.Float(string="Arbeit normal")
    work_ot30 = fields.Float(string="Arbeit 30 %")
    work_ot50 = fields.Float(string="Arbeit 50 %")
    travel_normal = fields.Float(string="Fahrt normal")
    travel_ot30 = fields.Float(string="Fahrt 30 %")
    travel_ot50 = fields.Float(string="Fahrt 50 %")
    kilometers = fields.Float(string="Kilometer")
    overnights = fields.Float(string="Übernachtungen")

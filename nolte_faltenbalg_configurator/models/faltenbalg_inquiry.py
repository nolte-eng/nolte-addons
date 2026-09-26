from odoo import _, api, fields, models


class FaltenbalgInquiry(models.Model):
    _name = "faltenbalg.inquiry"
    _description = "Faltenbalg Anfrage"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Referenz", required=True, copy=False, readonly=True, default=lambda self: _("Neue Anfrage"))
    state = fields.Selection([(
        "new", "Neu"),
        ("in_progress", "In Bearbeitung"),
        ("quoted", "Angebot erstellt"),
        ("done", "Erledigt"),
        ("cancel", "Abgebrochen"),
    ], string="Status", default="new", tracking=True)

    product_tmpl_id = fields.Many2one("product.template", string="Produkt", tracking=True)
    partner_id = fields.Many2one("res.partner", string="Kontakt", tracking=True)
    lead_id = fields.Many2one("crm.lead", string="Lead", readonly=True)

    company_name = fields.Char(string="Firma")
    contact_name = fields.Char(string="Ansprechpartner", required=True, tracking=True)
    email = fields.Char(string="E-Mail", required=True, tracking=True)
    phone = fields.Char(string="Telefon")

    shape = fields.Selection([
        ("straight", "Gerade"),
        ("u", "U-Form"),
        ("l", "L-Form"),
        ("c", "C-Form"),
        ("g", "G-Form"),
        ("box", "Kastenform"),
        ("pult", "Pultform"),
        ("roof", "Dachform"),
        ("kastenbalg", "Kastenform"),
        ("special", "Sonderform"),
    ], string="Bauform", required=True, default="straight", tracking=True)
    axis = fields.Selection([
        ("x", "X-Achse"),
        ("y", "Y-Achse"),
        ("z", "Z-Achse"),
        ("table", "Tisch / Führung"),
        ("other", "Sonstiges"),
    ], string="Achse / Einsatzbereich", default="other", tracking=True)
    installation_position = fields.Selection([
        ("horizontal", "Horizontal"),
        ("vertical", "Vertikal"),
        ("overhead", "Überkopf"),
        ("other", "Sonstige Lage"),
    ], string="Einbaulage", default="horizontal", tracking=True)
    width_mm = fields.Float(string="Maß A / Breite (mm)", required=True, digits=(16, 2), tracking=True)
    depth_mm = fields.Float(string="Maß B / Tiefe (mm)", required=True, digits=(16, 2), tracking=True)
    length_mm = fields.Float(string="Gesamtlänge (mm)", required=True, digits=(16, 2), tracking=True)
    lmin_mm = fields.Float(string="Lmin (mm)", digits=(16, 2), tracking=True)
    hub_mm = fields.Float(string="Hub (mm)", digits=(16, 2), tracking=True)
    fold_pitch_mm = fields.Float(string="Faltenabstand (mm)", digits=(16, 2), tracking=True)
    fold_count = fields.Integer(string="Faltenanzahl", tracking=True)
    height_mm = fields.Float(string="Maß D (mm)", digits=(16, 2), tracking=True)
    extra_e_mm = fields.Float(string="Maß E (mm)", digits=(16, 2), tracking=True)
    extra_f_mm = fields.Float(string="Maß F (mm)", digits=(16, 2), tracking=True)
    extra_g_mm = fields.Float(string="Maß G (mm)", digits=(16, 2), tracking=True)
    quantity = fields.Integer(string="Stückzahl", default=1, required=True, tracking=True)
    material = fields.Selection([
        ("standard", "Standard"),
        ("pu", "PU-beschichtet"),
        ("alu", "Mit Alulamellen"),
        ("heat", "Hitzebeständig"),
        ("special", "Sondermaterial"),
    ], string="Material", default="standard", tracking=True)
    application = fields.Char(string="Maschine / Einsatz")
    note = fields.Text(string="Bemerkung")
    source_url = fields.Char(string="Quelle / URL")
    attachment_ids = fields.Many2many("ir.attachment", string="Anhänge")

    description = fields.Text(string="Zusammenfassung", compute="_compute_description", store=True)

    @api.depends("shape", "axis", "installation_position", "width_mm", "depth_mm", "length_mm", "lmin_mm", "hub_mm", "fold_pitch_mm", "fold_count", "height_mm", "extra_e_mm", "extra_f_mm", "extra_g_mm", "quantity", "material", "application")
    def _compute_description(self):
        shape_map = dict(self._fields["shape"].selection)
        material_map = dict(self._fields["material"].selection)
        axis_map = dict(self._fields["axis"].selection)
        position_map = dict(self._fields["installation_position"].selection)
        for record in self:
            dims = f"A:{record.width_mm:g} | B:{record.depth_mm:g} | C/Lmax:{record.length_mm:g} mm"
            if record.lmin_mm:
                dims += f" | Lmin:{record.lmin_mm:g} mm"
            if record.hub_mm:
                dims += f" | Hub:{record.hub_mm:g} mm"
            if record.fold_pitch_mm:
                dims += f" | Faltenabstand:{record.fold_pitch_mm:g} mm"
            if record.fold_count:
                dims += f" | Falten:{record.fold_count:d}"
            if record.height_mm:
                dims += f" | D:{record.height_mm:g} mm"
            if record.extra_e_mm:
                dims += f" | E:{record.extra_e_mm:g} mm"
            if record.extra_f_mm:
                dims += f" | F:{record.extra_f_mm:g} mm"
            if record.extra_g_mm:
                dims += f" | G:{record.extra_g_mm:g} mm"
            parts = [shape_map.get(record.shape, ""), dims, f"{record.quantity} Stk.", material_map.get(record.material, "")]
            if record.axis:
                parts.append(axis_map.get(record.axis, ""))
            if record.installation_position:
                parts.append(position_map.get(record.installation_position, ""))
            if record.application:
                parts.append(record.application)
            record.description = " | ".join([p for p in parts if p])

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _("Neue Anfrage"):
                record.name = self.env["ir.sequence"].next_by_code("faltenbalg.inquiry") or _("Neue Anfrage")
            record._link_partner()
            record._create_optional_lead()
        return records

    def _link_partner(self):
        for record in self.filtered(lambda r: r.email and not r.partner_id):
            partner = self.env["res.partner"].sudo().search([("email", "=", record.email)], limit=1)
            if not partner:
                partner_vals = {"name": record.contact_name, "email": record.email, "phone": record.phone, "company_type": "company" if record.company_name else "person"}
                if record.company_name:
                    company_partner = self.env["res.partner"].sudo().search([("name", "=", record.company_name), ("is_company", "=", True)], limit=1)
                    if company_partner:
                        partner_vals["parent_id"] = company_partner.id
                    else:
                        company_partner = self.env["res.partner"].sudo().create({"name": record.company_name, "is_company": True})
                        partner_vals["parent_id"] = company_partner.id
                partner = self.env["res.partner"].sudo().create(partner_vals)
            record.partner_id = partner

    def _create_optional_lead(self):
        if "crm.lead" not in self.env:
            return
        shape_map = dict(self._fields["shape"].selection)
        material_map = dict(self._fields["material"].selection)
        axis_map = dict(self._fields["axis"].selection)
        position_map = dict(self._fields["installation_position"].selection)
        for record in self.filtered(lambda r: not r.lead_id):
            dims = f"A: {record.width_mm:g} mm\nB: {record.depth_mm:g} mm\nC: {record.length_mm:g} mm"
            if record.fold_pitch_mm:
                dims += f" | Faltenabstand:{record.fold_pitch_mm:g} mm"
            if record.fold_count:
                dims += f" | Falten:{record.fold_count:d}"
            if record.fold_pitch_mm:
                dims += f"\nFaltenabstand: {record.fold_pitch_mm:g} mm"
            if record.fold_count:
                dims += f"\nFaltenanzahl: {record.fold_count:d}"
            if record.height_mm:
                dims += f"\nD: {record.height_mm:g} mm"
            lead = self.env["crm.lead"].sudo().create({
                "name": f"Faltenbalg-Anfrage {record.contact_name}",
                "partner_id": record.partner_id.id,
                "contact_name": record.contact_name,
                "email_from": record.email,
                "phone": record.phone,
                "description": (
                    f"Bauform: {shape_map.get(record.shape)}\n"
                    f"Achse / Einsatzbereich: {axis_map.get(record.axis)}\n"
                    f"Einbaulage: {position_map.get(record.installation_position)}\n"
                    f"Maße:\n{dims}\n"
                    f"Menge: {record.quantity}\n"
                    f"Material: {material_map.get(record.material)}\n"
                    f"Maschine / Einsatz: {record.application or '-'}\n\n"
                    f"Bemerkung:\n{record.note or '-'}"
                ),
            })
            record.lead_id = lead

    def action_mark_in_progress(self):
        self.write({"state": "in_progress"})

    def action_mark_quoted(self):
        self.write({"state": "quoted"})

    def action_mark_done(self):
        self.write({"state": "done"})

    def action_mark_cancel(self):
        self.write({"state": "cancel"})

import base64
import csv
import io
import logging
import re
from datetime import datetime, timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError


def _parse_hours(val: str) -> float:
    if not val:
        return 0.0
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)", str(val))
    return float(m.group(1).replace(",", ".")) if m else 0.0


def _parse_number(val: str) -> float:
    if val is None:
        return 0.0
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)", str(val))
    return float(m.group(1).replace(",", ".")) if m else 0.0


def _parse_hhmm(val: str):
    if not val:
        return None
    val = str(val).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", val)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_date(val: str):
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _dt(date_val: str, hhmm: str):
    p = _parse_hhmm(hhmm)
    d = _parse_date(date_val)
    if not (d and p):
        return None
    return datetime.combine(d, datetime.min.time()).replace(hour=p[0], minute=p[1])


def _clip(seg_start, seg_end, clip_start, clip_end):
    s = max(seg_start, clip_start)
    e = min(seg_end, clip_end)
    return (s, e) if e > s else None


def _subtract_pauses(work_start, work_end, pauses):
    segments = [(work_start, work_end)]
    for ps, pe in pauses:
        new = []
        for s, e in segments:
            ov = _clip(s, e, ps, pe)
            if not ov:
                new.append((s, e))
                continue
            os, oe = ov
            if os > s:
                new.append((s, os))
            if oe < e:
                new.append((oe, e))
        segments = new
    return segments


def _alloc_overtime_by_timeline(segments):
    out = {"work": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0},
           "travel": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0}}
    segments = sorted(segments, key=lambda x: x[0])
    consumed = 0.0
    for s, e, kind in segments:
        h = (e - s).total_seconds() / 3600.0
        if h <= 0:
            continue
        remaining = h
        while remaining > 1e-9:
            if consumed < 8.0:
                bucket_end = 8.0; bucket = "normal"
            elif consumed < 10.0:
                bucket_end = 10.0; bucket = "ot30"
            else:
                bucket_end = float("inf"); bucket = "ot50"
            take = remaining if bucket_end == float("inf") else min(remaining, max(bucket_end - consumed, 0.0))
            if take <= 0:
                take = remaining
            out[kind][bucket] += take
            consumed += take
            remaining -= take
    return out


def _alloc_overtime_fallback(work_h, travel_h):
    total = work_h + travel_h
    ot = max(total - 8.0, 0.0)
    ot30 = min(ot, 2.0)
    ot50 = max(ot - 2.0, 0.0)
    if total <= 0:
        return {"work": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0},
                "travel": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0}}
    w_share = work_h / total
    t_share = travel_h / total
    normal = total - ot
    return {"work": {"normal": normal * w_share, "ot30": ot30 * w_share, "ot50": ot50 * w_share},
            "travel": {"normal": normal * t_share, "ot30": ot30 * t_share, "ot50": ot50 * t_share}}


class NolteOvertimeImportWizard(models.TransientModel):
    _name = "nolte.overtime.import.wizard"
    _description = "Import Überstunden CSV und erstelle Verkaufsauftrag"

    csv_file = fields.Binary(string="CSV-Datei", required=True)
    csv_filename = fields.Char(string="Dateiname")

    import_target = fields.Selection([
        ("new", "Neuen Verkaufsauftrag erstellen"),
        ("existing", "In bestehenden Verkaufsauftrag importieren"),
    ], string="Importziel", default="new", required=True)
    order_id = fields.Many2one(
        "sale.order",
        string="Bestehender Verkaufsauftrag",
        domain="[('state', 'in', ['draft', 'sent'])]",
    )
    partner_id = fields.Many2one("res.partner", string="Kunde")
    detected_partner_name = fields.Char(string="Erkannter Kunde", readonly=True)
    create_partner_if_missing = fields.Boolean(string="Partner automatisch neu anlegen, wenn nicht gefunden", default=False)
    new_partner_name = fields.Char(string="Neuer Partnername")
    new_partner_street = fields.Char(string="Straße")
    new_partner_zip = fields.Char(string="PLZ")
    new_partner_city = fields.Char(string="Ort")
    new_partner_country_id = fields.Many2one("res.country", string="Land")


    @api.onchange("order_id")
    def _onchange_order_id(self):
        for wizard in self:
            if wizard.order_id:
                wizard.partner_id = wizard.order_id.partner_id



    def _extract_partner_data_from_meta(self, meta):
        addr = (meta.get("rechnungsadresse") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [line.strip() for line in addr.split("\n") if line.strip()]
        vals = {
            "name": lines[0] if lines else "",
            "street": False,
            "zip": False,
            "city": False,
            "country_id": False,
        }
        if len(lines) >= 2:
            vals["street"] = lines[1]
        if len(lines) >= 3:
            m = re.match(r"^(?P<zip>[A-Za-z0-9\- ]{3,12})\s+(?P<city>.+)$", lines[2])
            if m:
                vals["zip"] = m.group("zip").strip()
                vals["city"] = m.group("city").strip()
            else:
                vals["city"] = lines[2]
        if len(lines) >= 4:
            country_line = lines[3]
            country = self.env["res.country"].search(["|", ("name", "=ilike", country_line), ("code", "=ilike", country_line)], limit=1)
            if country:
                vals["country_id"] = country.id
        return vals

    @api.onchange("csv_file")
    def _onchange_csv_file_partner_preview(self):
        for wizard in self:
            wizard.detected_partner_name = False
            wizard.new_partner_name = False
            wizard.new_partner_street = False
            wizard.new_partner_zip = False
            wizard.new_partner_city = False
            wizard.new_partner_country_id = False
            if not wizard.csv_file:
                continue
            try:
                raw = base64.b64decode(wizard.csv_file)
                text = raw.decode("utf-8-sig", errors="replace")
                meta, _activities = wizard._read_kv_csv(text)
                vals = wizard._extract_partner_data_from_meta(meta)
                wizard.detected_partner_name = vals.get("name") or False
                wizard.new_partner_name = vals.get("name") or False
                wizard.new_partner_street = vals.get("street") or False
                wizard.new_partner_zip = vals.get("zip") or False
                wizard.new_partner_city = vals.get("city") or False
                wizard.new_partner_country_id = vals.get("country_id") or False
                if vals.get("name") and not wizard.partner_id:
                    partner = wizard.env["res.partner"].search([("name", "ilike", vals["name"])], limit=1)
                    if partner:
                        wizard.partner_id = partner
            except Exception:
                _logger.exception("Partner-Vorschau aus CSV konnte nicht gelesen werden.")

    def _cfg_pid(self, key: str):
        v = self.env["ir.config_parameter"].sudo().get_param(key)
        if not v:
            return False
        try:
            return int(v)
        except (TypeError, ValueError):
            return False

    def _get_products(self):
        keys = {
            "work": "nolte_overtime_billing.product_work_id",
            "travel": "nolte_overtime_billing.product_travel_id",
            "work_ot30": "nolte_overtime_billing.product_work_ot30_id",
            "work_ot50": "nolte_overtime_billing.product_work_ot50_id",
            "travel_ot30": "nolte_overtime_billing.product_travel_ot30_id",
            "travel_ot50": "nolte_overtime_billing.product_travel_ot50_id",
        }
        pids = {k: self._cfg_pid(v) for k, v in keys.items()}
        if not all(pids.values()):
            raise UserError(_(
                "Bitte in Einstellungen alle 6 Produkte zuordnen: Arbeitszeit/Fahrzeit normal sowie OT30/OT50 jeweils."
            ))
        km_pid = self._cfg_pid("nolte_overtime_billing.product_km_id")
        overnight_pid = self._cfg_pid("nolte_overtime_billing.product_overnight_id")
        allowance_pid = self._cfg_pid("nolte_overtime_billing.product_allowance_id")

        prods = {k: self.env["product.product"].browse(pid) for k, pid in pids.items()}
        prods["km"] = self.env["product.product"].browse(km_pid) if km_pid else False
        prods["overnight"] = self.env["product.product"].browse(overnight_pid) if overnight_pid else False
        prods["allowance"] = self.env["product.product"].browse(allowance_pid) if allowance_pid else False
        return prods

    def _read_kv_csv(self, text: str):
        reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"')
        meta = {}
        activities = {}
        for row in reader:
            if not row or len(row) < 2:
                continue
            key = (row[0] or "").strip()
            val = (row[1] or "").strip()
            if not key:
                continue
            m = re.match(r"taetigkeit(\d+)\.(.+)", key)
            if m:
                idx = int(m.group(1))
                field = m.group(2)
                activities.setdefault(idx, {})[field] = val
            else:
                meta[key] = val
        return meta, activities

    def _partner_from_meta(self, meta):
        vals = self._extract_partner_data_from_meta(meta)
        name = (vals.get("name") or "").strip()
        if not name:
            raise UserError(_("Kunde konnte nicht ermittelt werden (rechnungsadresse fehlt)."))
        partner = self.env["res.partner"].search([("name", "ilike", name)], limit=1)
        if not partner:
            raise UserError(_("Kunde '%s' nicht gefunden. Bitte Partner in Odoo anlegen oder Name anpassen.") % name)
        return partner

    def _resolve_partner(self, meta):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id

        vals = self._extract_partner_data_from_meta(meta)
        name = (vals.get("name") or self.new_partner_name or "").strip()
        if not name:
            raise UserError(_("Kunde konnte nicht ermittelt werden (rechnungsadresse fehlt)."))

        partner = self.env["res.partner"].search([("name", "ilike", name)], limit=1)
        if partner:
            return partner

        if not self.create_partner_if_missing:
            raise UserError(_("Kunde '%s' nicht gefunden. Bitte Partner in Odoo anlegen, im Assistenten auswählen oder automatische Neuanlage aktivieren.") % name)

        create_vals = {
            "name": name,
            "street": self.new_partner_street or vals.get("street") or False,
            "zip": self.new_partner_zip or vals.get("zip") or False,
            "city": self.new_partner_city or vals.get("city") or False,
            "country_id": self.new_partner_country_id.id or vals.get("country_id") or False,
            "customer_rank": 1,
        }
        partner = self.env["res.partner"].create(create_vals)
        self.partner_id = partner
        return partner

    def _build_segments(self, a):
        date_str = a.get("datum")
        segments = []

        to_s = _dt(date_str, a.get("fahrzeitAbfahrt"))
        to_e = _dt(date_str, a.get("fahrzeitAnkunft"))
        if to_s and to_e and to_e < to_s:
            to_e += timedelta(days=1)
        if to_s and to_e and to_e > to_s:
            segments.append((to_s, to_e, "travel"))

        w_s = _dt(date_str, a.get("arbeitszeitBeginn"))
        w_e = _dt(date_str, a.get("arbeitszeitEnde"))
        if w_s and w_e and w_e < w_s:
            w_e += timedelta(days=1)

        pauses = []
        p1s = _dt(date_str, a.get("pausenzeitBeginn"))
        p1e = _dt(date_str, a.get("pausenzeitEnde"))
        if p1s and p1e and p1e < p1s:
            p1e += timedelta(days=1)
        if p1s and p1e and p1e > p1s:
            pauses.append((p1s, p1e))

        p2s = _dt(date_str, a.get("pausenzeit2Beginn"))
        p2e = _dt(date_str, a.get("pausenzeit2Ende"))
        if p2s and p2e and p2e < p2s:
            p2e += timedelta(days=1)
        if p2s and p2e and p2e > p2s:
            pauses.append((p2s, p2e))

        if w_s and w_e and w_e > w_s:
            for ws, we in _subtract_pauses(w_s, w_e, pauses):
                segments.append((ws, we, "work"))

        tb_s = _dt(date_str, a.get("fahrzeitAbAbfahrt"))
        tb_e = _dt(date_str, a.get("fahrzeitAbAnkunft"))
        if tb_s and tb_e and tb_e < tb_s:
            tb_e += timedelta(days=1)
        if tb_s and tb_e and tb_e > tb_s:
            segments.append((tb_s, tb_e, "travel"))

        return segments

    def _extract_km(self, a):
        return _parse_number(a.get("fahrstrecke")) + _parse_number(a.get("fahrstreckeAb"))

    def _extract_overnights_from_meta(self, meta):
        if (meta.get("auswahllisteBezeichnung3") or "").lower().find("übernacht") >= 0:
            for k in ("auswahleintrag3", "auswahleintrag_3"):
                n = _parse_number(meta.get(k))
                if n:
                    return n
        for k in ("auswahleintrag3", "auswahleintrag_3", "overnights", "uebernachtungen"):
            n = _parse_number(meta.get(k))
            if n:
                return n
        return 0.0

    def _add_note_line(self, order, meta, activities):
        note_lines = []

        # Zeitraum
        dates = []
        for a in activities.values():
            d = _parse_date(a.get("datum"))
            if d:
                dates.append(d)
        zeitraum = f"{min(dates).strftime('%d.%m.%Y')} – {max(dates).strftime('%d.%m.%Y')}" if dates else ""

        # Meta
        ausfuehrungsort = meta.get("ausfuehrungsort")
        maschinennr = meta.get("auswahleintrag1") or meta.get("auswahleintrag_1")
        maschinentyp = meta.get("auswahleintrag2") or meta.get("auswahleintrag_2")

        # Servicetechniker aus erster Tätigkeit
        first = activities[min(activities.keys())] if activities else {}
        servicetechniker = first.get("name")

        # Reihenfolge: Auführungsort, servicetechniker, Machinentyp, Maschinennr, Zeitraum
        if ausfuehrungsort:
            note_lines.append(f"Ausführungsort: {ausfuehrungsort}")
        if servicetechniker:
            note_lines.append(f"Servicetechniker: {servicetechniker}")
        if maschinentyp:
            note_lines.append(f"Maschinentyp: {maschinentyp}")
        if maschinennr:
            note_lines.append(f"Maschinen Nr.: {maschinennr}")
        if zeitraum:
            note_lines.append(f"Zeitraum: {zeitraum}")

        if not note_lines:
            return

        self.env["sale.order.line"].create({
            "order_id": order.id,
            "display_type": "line_note",
            "name": "\n".join(note_lines),
            "sequence": 1,
        })

    def action_import_create_sale_order(self):
        self.ensure_one()
        prods = self._get_products()

        raw = base64.b64decode(self.csv_file)
        text = raw.decode("utf-8-sig", errors="replace")
        meta, activities = self._read_kv_csv(text)
        if not activities:
            raise UserError(_("Keine 'taetigkeitN.*' Einträge in der CSV gefunden."))

        partner = self._resolve_partner(meta)
        origin = meta.get("berichtNr") or self.csv_filename or _("Überstunden-Import")
        order = False

        if self.import_target == "existing":
            if not self.order_id:
                raise UserError(_("Bitte einen bestehenden Verkaufsauftrag auswählen."))
            order = self.order_id
            if order.state not in ("draft", "sent"):
                raise UserError(_("Es kann nur in einen Verkaufsauftrag im Status Angebot oder Angebot gesendet importiert werden."))
            if order.partner_id and order.partner_id != partner:
                raise UserError(_("Der ausgewählte Verkaufsauftrag gehört zu '%s', die CSV jedoch zu '%s'. Bitte passenden Auftrag wählen oder Kunden-Auswahl anpassen.") % (order.partner_id.display_name, partner.display_name))
            if not order.partner_id:
                order.partner_id = partner.id
            if not order.origin:
                order.origin = origin
        else:
            if self.env.context.get('active_model') == 'sale.order' and self.env.context.get('active_id'):
                order = self.env['sale.order'].browse(self.env.context['active_id'])
            if order:
                if not order.partner_id:
                    order.partner_id = partner.id
                if not order.origin:
                    order.origin = origin
            else:
                order = self.env['sale.order'].create({'partner_id': partner.id, 'origin': origin})

        # Ensure pricelist is set so sales prices follow the customer's pricing rules
        if not order.pricelist_id and order.partner_id and order.partner_id.property_product_pricelist:
            order.pricelist_id = order.partner_id.property_product_pricelist.id
        self._add_note_line(order, meta, activities)

        totals = {"work": 0.0, "work_ot30": 0.0, "work_ot50": 0.0,
                  "travel": 0.0, "travel_ot30": 0.0, "travel_ot50": 0.0,
                  "km": 0.0, "overnight": 0.0}
        detail_lines = []
        allowance_days = {}  # person -> set(day)


        for idx in sorted(activities.keys()):
            a = activities[idx]
            date_str = a.get("datum") or ""
            d = _parse_date(date_str)
            day = d.isoformat() if d else str(date_str).strip()
            person = a.get("name") or ""
            note = (f"{day} {person}").strip()
            # Auslöse: je Mitarbeiter & Einsatztag genau 1× zählen (auch bei nicht zusammenhängenden Tagen / Wochenende)
            person_key = (person or "").strip() or "_gesamt_"
            allowance_days.setdefault(person_key, set()).add(day)


            segments = self._build_segments(a)
            if segments:
                alloc = _alloc_overtime_by_timeline(segments)
            else:
                work_h = _parse_hours(a.get("arbeitszeit", ""))
                travel_h = _parse_hours(a.get("fahrzeit", "")) + _parse_hours(a.get("fahrzeitAb", ""))
                alloc = _alloc_overtime_fallback(work_h, travel_h)

            work_normal = alloc["work"]["normal"]
            work_ot30 = alloc["work"]["ot30"]
            work_ot50 = alloc["work"]["ot50"]
            trav_normal = alloc["travel"]["normal"]
            trav_ot30 = alloc["travel"]["ot30"]
            trav_ot50 = alloc["travel"]["ot50"]

            km = self._extract_km(a)

            totals["work"] += work_normal
            totals["work_ot30"] += work_ot30
            totals["work_ot50"] += work_ot50
            totals["travel"] += trav_normal
            totals["travel_ot30"] += trav_ot30
            totals["travel_ot50"] += trav_ot50
            totals["km"] += km

            detail_lines.append(
                f"{note}: Arbeit {work_normal:.2f}h (OT30 {work_ot30:.2f} / OT50 {work_ot50:.2f}), "
                f"Fahrt {trav_normal:.2f}h (OT30 {trav_ot30:.2f} / OT50 {trav_ot50:.2f}), km {km:.0f}"
            )

        totals["overnight"] = self._extract_overnights_from_meta(meta)

        if detail_lines:
            extra = f"\nÜbernachtungen (gesamt): {totals['overnight']:.0f}" if totals["overnight"] else ""
            order.note = f"CSV Import: {origin}\n" + "\n".join(detail_lines) + extra

        def add_line(product, qty, label, seq):
            qty = float(qty or 0.0)
            if qty <= 1e-6:
                return

            def _pricelist_price(prod, q):
                """Pricelist price getter.
                - Uses the order's pricelist
                - Tries multiple API signatures (Odoo version differences)
                - Never crashes the import: falls back to product list price if pricelist/currency setup is incomplete
                """
                pl = order.pricelist_id
                partner = order.partner_id
                date = order.date_order or fields.Date.context_today(self)
                uom = getattr(prod, "uom_id", False)

                try:
                    # Newer APIs (signature differs between versions)
                    if hasattr(pl, "_get_product_price"):
                        try:
                            return pl._get_product_price(prod, q, partner, date=date, uom_id=uom.id if uom else False)
                        except TypeError:
                            # older signature without keywords
                            return pl._get_product_price(prod, q, partner)

                    if hasattr(pl, "get_product_price"):
                        try:
                            return pl.get_product_price(prod, q, partner, date=date, uom_id=uom.id if uom else False)
                        except TypeError:
                            return pl.get_product_price(prod, q, partner)

                    # Older APIs
                    if hasattr(pl, "_get_product_price_rule"):
                        try:
                            res = pl._get_product_price_rule(prod, q, partner, date=date, uom_id=uom.id if uom else False)
                        except TypeError:
                            res = pl._get_product_price_rule(prod, q, partner)
                        # usually returns (price, rule_id)
                        if isinstance(res, (list, tuple)) and res:
                            return res[0]

                except Exception as e:
                    _logger.exception("Pricelist price computation failed (pricelist=%s, product=%s, qty=%s). Falling back to list price. Error: %s",
                                      pl.display_name if pl else pl, prod.display_name if prod else prod, q, e)

                # Safe fallback: product list price (company-aware)
                try:
                    return prod.with_company(order.company_id).lst_price
                except Exception:
                    return prod.lst_price

            # Create the line via onchange so Odoo applies the customer's pricelist (and taxes, UoM logic, etc.)
            line = self.env["sale.order.line"].new({
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
            })

            # Odoo version compatibility: the onchange helper name differs across versions/installations.
            if hasattr(line, "_onchange_product_id"):
                line._onchange_product_id()
            elif hasattr(line, "product_id_change"):
                line.product_id_change()
            else:
                # Fallback: at least apply pricelist price
                line.price_unit = _pricelist_price(product, qty)

            line.product_uom_qty = qty
            # qty can affect pricelist rules (quantity breaks)
            if hasattr(line, "_onchange_product_uom_qty"):
                line._onchange_product_uom_qty()
            elif hasattr(line, "product_uom_qty_change"):
                line.product_uom_qty_change()
            elif not getattr(line, "price_unit", None):
                # If no qty onchange exists, ensure price respects quantity breaks
                line.price_unit = _pricelist_price(product, qty)

            line.name = label
            line.sequence = seq
            self.env["sale.order.line"].create(line._convert_to_write(line._cache))

        add_line(prods["work"], totals["work"], "Arbeitszeit", 10)
        add_line(prods["work_ot30"], totals["work_ot30"], "Arbeitszeit Überstunden 30%", 11)
        add_line(prods["work_ot50"], totals["work_ot50"], "Arbeitszeit Überstunden 50%", 12)

        add_line(prods["travel"], totals["travel"], "Fahrzeit", 20)
        add_line(prods["travel_ot30"], totals["travel_ot30"], "Fahrzeit Überstunden 30%", 21)
        add_line(prods["travel_ot50"], totals["travel_ot50"], "Fahrzeit Überstunden 50%", 22)

        if prods.get("km") and totals["km"] > 1e-6:
            add_line(prods["km"], totals["km"], "Kilometer", 30)
        elif totals["km"] > 1e-6:
            order.note = (order.note or "") + "\n\nHinweis: Kilometer vorhanden, aber kein Produkt konfiguriert."

        if prods.get("overnight") and totals["overnight"] > 1e-6:
            add_line(prods["overnight"], totals["overnight"], "Übernachtungspauschale", 40)
        elif totals["overnight"] > 1e-6:
            order.note = (order.note or "") + "\n\nHinweis: Übernachtungen vorhanden, aber kein Produkt konfiguriert."
        
        # Auslöse je Mitarbeiter & Einsatztag
        if allowance_days:
            if prods.get("allowance"):
                seq = 50
                for person_key in sorted(allowance_days.keys()):
                    qty = float(len(allowance_days[person_key]))
                    if qty <= 0:
                        continue
                    label = "Auslöse" if person_key == "_gesamt_" else f"Auslöse ({person_key})"
                    add_line(prods["allowance"], qty, label, seq)
                    seq += 1
            else:
                total_days = sum(len(s) for s in allowance_days.values())
                if total_days:
                    order.note = (order.note or "") + f"\n\nHinweis: Auslöse-Tage ({total_days}) vorhanden, aber kein Produkt konfiguriert."


        return {"type": "ir.actions.act_window", "res_model": "sale.order", "view_mode": "form", "res_id": order.id}

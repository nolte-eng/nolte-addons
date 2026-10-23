/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const DAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const TRAVEL = [["", "–"], ["single", "Über 8 Std."], ["arrival", "Anreise"], ["full", "Volltag"], ["departure", "Abreise"]];

function euro(value) { return new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0)); }
function hours(value) { const rawMinutes = Math.round(Number(value || 0) * 60); const sign = rawMinutes < 0 ? "-" : ""; const minutes = Math.abs(rawMinutes); return `${sign}${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`; }
function optionList(items, selected) { return items.map(([value, label]) => `<option value="${value}" ${value === (selected || "") ? "selected" : ""}>${label}</option>`).join(""); }
function monthKey(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`; }
function timeInput(field, value, disabled) {
  return `<button type="button" class="ns-time-input" data-time-button="${field}" ${disabled}>${value || "--:--"}</button><input type="hidden" data-field="${field}" value="${value || ""}"/>`;
}

class NolteSpesenbericht {
  constructor(root) {
    this.root = root;
    this.date = new Date();
    this.date.setDate(1);
    this.report = null;
    this.employeeId = Number(new URLSearchParams(window.location.search).get("employee_id")) || null;
    this.saveTimer = null;
  }

  async start() {
    this.bind();
    await this.load();
  }

  bind() {
    this.root.querySelector(".js_ns_prev").addEventListener("click", () => this.changeMonth(-1));
    this.root.querySelector(".js_ns_next").addEventListener("click", () => this.changeMonth(1));
    this.root.querySelector(".js_ns_employee").addEventListener("change", (ev) => this.changeEmployee(ev.target.value));
    this.root.querySelector(".js_ns_rows").addEventListener("change", (ev) => this.onChange(ev));
    this.root.querySelector(".js_ns_rows").addEventListener("click", (ev) => {
      const deleteButton = ev.target.closest("[data-delete-attachment]");
      if (deleteButton) {
        ev.preventDefault();
        this.deleteAttachment(Number(deleteButton.dataset.deleteAttachment), deleteButton.dataset.attachmentName);
        return;
      }
      const button = ev.target.closest("[data-time-button]");
      if (button) this.openTimePicker(button);
    });
    document.addEventListener("pointerdown", (ev) => {
      if (this.timePicker && !this.timePicker.contains(ev.target) && !ev.target.closest("[data-time-button]")) this.closeTimePicker();
    });
    this.root.querySelector(".js_ns_submit").addEventListener("click", () => this.submit());
    this.root.querySelector(".js_ns_approve").addEventListener("click", () => this.approve());
    this.root.querySelector(".js_ns_export").addEventListener("click", () => this.exportExpenses());
    this.root.querySelector(".js_ns_print").addEventListener("click", () => window.open(`/my/spesenbericht/pdf?month=${monthKey(this.date)}${this.employeeId ? `&employee_id=${this.employeeId}` : ""}`, "_blank", "noopener"));
    this.root.querySelector(".js_ns_csv").addEventListener("click", () => this.downloadCsv());
  }

  async load() {
    this.setSaving("Odoo-Daten werden geladen …");
    try {
      this.report = await rpc("/nolte_spesenbericht/data", { month: monthKey(this.date), employee_id: this.employeeId });
      this.employeeId = this.report.canSelectEmployee ? this.report.employee.id : null;
      if (!this.report.canSelectEmployee) {
        const url = new URL(window.location.href);
        if (url.searchParams.has("employee_id")) {
          url.searchParams.delete("employee_id");
          window.history.replaceState({}, "", url);
        }
      }
      this.render();
      this.setSaving("● In Odoo gespeichert");
    } catch (error) { this.message(error.message || "Bericht konnte nicht geladen werden.", true); }
  }

  async changeMonth(offset) { this.date = new Date(this.date.getFullYear(), this.date.getMonth() + offset, 1); await this.load(); }

  async changeEmployee(value) {
    this.employeeId = Number(value) || null;
    const url = new URL(window.location.href);
    if (this.employeeId) url.searchParams.set("employee_id", this.employeeId); else url.searchParams.delete("employee_id");
    window.history.replaceState({}, "", url);
    await this.load();
  }

  render() {
    this.root.querySelector(".js_ns_month").textContent = `${MONTHS[this.date.getMonth()]} ${this.date.getFullYear()}`;
    const employeeWrap = this.root.querySelector(".js_ns_employee_wrap");
    const employeeSelect = this.root.querySelector(".js_ns_employee");
    employeeWrap.classList.toggle("d-none", !this.report.canSelectEmployee);
    if (this.report.canSelectEmployee) {
      employeeSelect.innerHTML = this.report.employees.map((item) => `<option value="${item.id}" ${item.id === this.report.employee.id ? "selected" : ""}>${this.escape(item.name)}</option>`).join("");
    }
    this.root.querySelector(".js_ns_work").textContent = `${hours(this.report.totals.work)} Std.`;
    this.root.querySelector(".js_ns_overtime").textContent = `${hours(this.report.totals.overtime)} Std.`;
    this.root.querySelector(".js_ns_overtime_basis").textContent = `Soll ${hours(this.report.totals.target)} Std.`;
    this.root.querySelector(".js_ns_allowance").textContent = `${euro(this.report.totals.allowance)} €`;
    this.root.querySelector(".js_ns_expenses").textContent = `${euro(this.report.totals.hotel + this.report.totals.expenses)} €`;
    const labels = { draft: "In Bearbeitung", rejected: "Zur Korrektur", submitted: "Eingereicht", approved: "Freigegeben", exported: "An Odoo übergeben" };
    const editable = ["draft", "rejected"].includes(this.report.state);
    const status = this.root.querySelector(".js_ns_status");
    status.textContent = labels[this.report.state]; status.dataset.state = this.report.state;
    this.root.querySelector(".js_ns_rows").innerHTML = this.report.rows.map((row) => this.rowHtml(row, editable)).join("");
    this.root.querySelector(".js_ns_submit").classList.toggle("d-none", !editable);
    this.root.querySelector(".js_ns_approve").classList.toggle("d-none", !(this.report.state === "submitted" && this.report.canApprove));
    this.root.querySelector(".js_ns_export").classList.toggle("d-none", !(this.report.state === "approved" && this.report.canExport));
  }

  rowHtml(row, editable) {
    const date = new Date(`${row.date}T12:00:00`);
    const disabled = editable ? "" : "disabled";
    const absence = row.absenceName ? `<span class="ns-absence">${row.absenceName} · ${hours(row.absenceHours)}</span>` : "";
    const dailyTotal = Number(row.allowance || 0) + Number(row.hotelAmount || 0) + Number(row.expenses || 0);
    const commonCountries = this.report.rateOptions.filter((item) => item.common);
    const commonKeys = new Set(commonCountries.map((item) => item.value));
    const otherCountries = this.report.rateOptions.filter((item) => !item.common);
    const isOtherCountry = Boolean(row.country && !commonKeys.has(row.country));
    const countries = [["", "–"], ...commonCountries.map((item) => [item.value, item.label]), ["__more__", "Weiteres Land …"]];
    const selectedCountry = isOtherCountry ? "__more__" : row.country;
    const moreCountries = [["", "Land / Ort auswählen …"], ...otherCountries.map((item) => [item.value, item.label])];
    const rateWarning = row.rateMissing ? `<span class="ns-rate-warning" title="BMF-Tarif ${this.report.rateYear} fehlt">Tarif fehlt</span>` : "";
    const attachmentLinks = (row.attachments || []).map((file) => `<span class="ns-attachment-item"><a href="${file.url}" target="_blank" rel="noopener" title="${this.escape(file.name)}">${this.escape(file.name)}</a>${editable ? `<button type="button" data-delete-attachment="${file.id}" data-attachment-name="${this.escape(file.name)}" title="Falschen Beleg löschen">×</button>` : ""}</span>`).join("");
    const attachmentList = row.attachmentCount ? `<details class="ns-attachment-list"><summary title="Belege anzeigen">✓ ${row.attachmentCount}</summary><div>${attachmentLinks}</div></details>` : "";
    const upload = editable ? `<label class="ns-upload ${row.attachmentCount ? "ready" : ""}">${row.attachmentCount ? "+" : "+ Beleg"}<input type="file" data-upload="1" accept="image/*,.pdf"/></label>` : "";
    return `<tr data-date="${row.date}" class="${date.getDay() % 6 === 0 ? "weekend" : ""}">
      <td><b>${String(row.day).padStart(2, "0")}</b><small>${DAYS[date.getDay()]}</small></td>
      <td>${absence}<input data-field="customer" value="${this.escape(row.customer)}" placeholder="Kunde / Baustelle" ${disabled}/></td>
      <td>${timeInput("start_time", row.start, disabled)}</td>
      <td>${timeInput("end_time", row.end, disabled)}</td>
      <td><input type="number" min="0" step="15" data-field="break_minutes" value="${row.breakMinutes || ""}" placeholder="Min." ${disabled}/></td>
      <td class="calculated"><strong>${hours(row.workHours)}</strong></td>
      <td><div class="ns-expense-controls"><div><select data-field="country" title="Häufig verwendetes BMF-Land" ${disabled}>${optionList(countries, selectedCountry)}</select><select data-country-more title="Weitere BMF-Länder und Sonderorte" class="ns-country-more ${isOtherCountry ? "" : "d-none"}" ${disabled}>${optionList(moreCountries, row.country)}</select><select data-field="travel_type" title="Reisetag" ${disabled}>${optionList(TRAVEL, row.travelType)}</select></div><div class="meals" title="Gestellte Mahlzeiten">${rateWarning}${row.travelTypeAutomatic ? '<span title="Automatisch aus der Reiseabfolge">Auto</span>' : ''}<label>F<input type="checkbox" data-field="breakfast" ${row.breakfast ? "checked" : ""} ${disabled}/></label><label>M<input type="checkbox" data-field="lunch" ${row.lunch ? "checked" : ""} ${disabled}/></label><label>A<input type="checkbox" data-field="dinner" ${row.dinner ? "checked" : ""} ${disabled}/></label></div></div></td>
      <td class="money">${euro(row.allowance)} €</td>
      <td><div class="hotel"><select data-field="hotel_mode" ${disabled}>${optionList([["", "–"], ["flat", "Pauschale"], ["receipt", "Beleg"]], row.hotelMode)}</select><input type="number" min="0" step="0.01" data-field="hotel_input" value="${row.hotelMode === "flat" ? Number(row.hotelAmount || 0).toFixed(2) : (row.hotel || "")}" ${row.hotelMode === "receipt" ? "" : "disabled"}/></div></td>
      <td><input type="number" min="0" step="0.01" data-field="expense_amount" value="${row.expenses || ""}" ${disabled}/></td>
      <td class="ns-daily-total">${euro(dailyTotal)} €</td>
      <td><div class="ns-receipts">${attachmentList}${upload}</div></td>
    </tr>`;
  }

  openTimePicker(button) {
    this.closeTimePicker();
    const field = button.dataset.timeButton;
    const input = button.parentElement.querySelector(`[data-field="${field}"]`);
    const initial = input.value || (field === "start_time" ? "08:00" : "16:00");
    let [hour, minute] = initial.split(":");
    const picker = document.createElement("div");
    picker.className = "ns-time-picker";
    const hoursHtml = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0")).map((h) => `<button type="button" data-hour="${h}" class="${h === hour ? "selected" : ""}">${h}</button>`).join("");
    const minutesHtml = ["00", "15", "30", "45"].map((m) => `<button type="button" data-minute="${m}" class="${m === minute ? "selected" : ""}">${m}</button>`).join("");
    picker.innerHTML = `<header><strong>${field === "start_time" ? "Startzeit" : "Endzeit"}</strong><button type="button" data-time-clear>Leeren</button></header><div class="ns-time-columns"><div>${hoursHtml}</div><span>:</span><div>${minutesHtml}</div></div>`;
    document.body.appendChild(picker);
    const rect = button.getBoundingClientRect();
    picker.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - picker.offsetWidth - 12))}px`;
    picker.style.top = `${Math.max(12, Math.min(rect.bottom + 5, window.innerHeight - picker.offsetHeight - 12))}px`;
    picker.querySelector('[data-hour].selected')?.scrollIntoView({ block: "center" });
    picker.addEventListener("click", (ev) => {
      const hourButton = ev.target.closest("[data-hour]");
      const minuteButton = ev.target.closest("[data-minute]");
      if (ev.target.closest("[data-time-clear]")) { input.value = ""; button.textContent = "--:--"; input.dispatchEvent(new Event("change", { bubbles: true })); this.closeTimePicker(); return; }
      if (hourButton) { hour = hourButton.dataset.hour; picker.querySelectorAll("[data-hour]").forEach((item) => item.classList.toggle("selected", item === hourButton)); }
      if (minuteButton) { minute = minuteButton.dataset.minute; input.value = `${hour}:${minute}`; button.textContent = input.value; input.dispatchEvent(new Event("change", { bubbles: true })); this.closeTimePicker(); }
    });
    this.timePicker = picker;
  }

  closeTimePicker() { this.timePicker?.remove(); this.timePicker = null; }

  onChange(ev) {
    const row = ev.target.closest("tr[data-date]");
    if (!row) return;
    if (ev.target.dataset.upload) { if (ev.target.files[0]) this.upload(row.dataset.date, ev.target.files[0]); return; }
    if (ev.target.dataset.field === "country") {
      const more = row.querySelector("[data-country-more]");
      more.classList.toggle("d-none", ev.target.value !== "__more__");
      if (ev.target.value !== "__more__") more.value = "";
      if (ev.target.value === "__more__") return;
    }
    if (ev.target.dataset.field === "travel_type" && ev.target.value && !row.querySelector('[data-field="country"]').value) {
      const country = row.querySelector('[data-field="country"]');
      if ([...country.options].some((option) => option.value === "DE")) country.value = "DE";
    }
    if (ev.target.dataset.field === "hotel_mode") {
      const hotelInput = row.querySelector('[data-field="hotel_input"]');
      hotelInput.disabled = ev.target.value !== "receipt";
      if (ev.target.value !== "receipt") hotelInput.value = "";
    }
    clearTimeout(this.saveTimer); this.saveTimer = setTimeout(() => this.save(), 450);
  }

  collectRows() {
    return [...this.root.querySelectorAll("tr[data-date]")].map((row) => {
      const value = (field) => row.querySelector(`[data-field="${field}"]`);
      const country = value("country").value === "__more__" ? row.querySelector("[data-country-more]").value : value("country").value;
      const hotelMode = value("hotel_mode").value || false;
      return { date: row.dataset.date, customer: value("customer").value, start_time: value("start_time").value, end_time: value("end_time").value, break_minutes: Number(value("break_minutes").value || 0), country: country || false, travel_type: value("travel_type").value || false, breakfast: value("breakfast").checked, lunch: value("lunch").checked, dinner: value("dinner").checked, hotel_mode: hotelMode, hotel_input: hotelMode === "receipt" ? Number(value("hotel_input").value || 0) : 0, expense_amount: Number(value("expense_amount").value || 0) };
    });
  }

  async save() { this.setSaving("Speichert …"); try { this.report = await rpc("/nolte_spesenbericht/save", { month: monthKey(this.date), rows: this.collectRows(), employee_id: this.employeeId }); this.render(); this.setSaving("● In Odoo gespeichert"); } catch (error) { this.message(error.message, true); } }
  async submit() { await this.save(); this.report = await rpc("/nolte_spesenbericht/submit", { month: monthKey(this.date), employee_id: this.employeeId }); this.render(); this.message("Monat wurde zur Freigabe eingereicht."); }
  async approve() { this.report = await rpc("/nolte_spesenbericht/approve", { report_id: this.report.id, decision: "approve" }); this.render(); this.message("Spesenbericht wurde freigegeben."); }
  async exportExpenses() { const result = await rpc("/nolte_spesenbericht/create_expenses", { report_id: this.report.id }); this.message(`${result.expenseIds.length} Odoo-Spesen wurden erstellt.`); await this.load(); }

  async upload(lineDate, file) { const form = new FormData(); form.append("csrf_token", window.odoo.csrf_token); form.append("report_id", this.report.id); form.append("line_date", lineDate); form.append("receipt", file); await fetch("/nolte_spesenbericht/upload", { method: "POST", body: form }); this.message("Beleg wurde in Odoo gespeichert."); await this.load(); }

  async deleteAttachment(attachmentId, attachmentName) {
    if (!window.confirm(`Beleg „${attachmentName || "Datei"}“ wirklich löschen?`)) return;
    try {
      await rpc("/nolte_spesenbericht/delete_attachment", { report_id: this.report.id, attachment_id: attachmentId });
      this.message("Beleg wurde gelöscht.");
      await this.load();
    } catch (error) {
      this.message(error.message || "Beleg konnte nicht gelöscht werden.", true);
    }
  }

  downloadCsv() { const lines = [["Datum", "Kunde", "Start", "Ende", "Pause", "Arbeit", "Land / Ort", "Reisetag", "Pauschale", "Hotel", "Auslagen"], ...this.report.rows.map((row) => [row.date, row.customer, row.start, row.end, row.breakMinutes, hours(row.workHours), row.countryLabel || "", row.travelType || "", euro(row.allowance), euro(row.hotelAmount), euro(row.expenses)])]; const csv = "\uFEFF" + lines.map((line) => line.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(";")).join("\r\n"); const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })); link.download = `spesenbericht-${monthKey(this.date).slice(0, 7)}.csv`; link.click(); }
  setSaving(text) { this.root.querySelector(".js_ns_save_state").textContent = text; }
  message(text, error = false) { const box = this.root.querySelector(".js_ns_message"); box.textContent = text; box.classList.remove("d-none"); box.classList.toggle("error", error); clearTimeout(this.messageTimer); this.messageTimer = setTimeout(() => box.classList.add("d-none"), 5000); }
  escape(value) { const node = document.createElement("span"); node.textContent = value || ""; return node.innerHTML; }
}

function startNolteSpesenbericht() {
  const root = document.getElementById("nolte-spesenbericht-app");
  if (root && !root.dataset.started) {
    root.dataset.started = "1";
    new NolteSpesenbericht(root).start();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startNolteSpesenbericht, { once: true });
} else {
  startNolteSpesenbericht();
}

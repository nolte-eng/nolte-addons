/** @odoo-module **/
const DRAFT_KEY = "nolte-stundenbericht-drafts-v1";
const SYNCED_STATE_KEY = "nolte-stundenbericht-sync-complete-v1";
const uuid = () => window.nolteUuid();
const drafts = () => { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "[]"); } catch { return []; } };
const storeDrafts = value => localStorage.setItem(DRAFT_KEY, JSON.stringify(value));
const rpc = (url, params) => fetch(url, {
    method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({jsonrpc: "2.0", method: "call", params, id: Date.now()}),
}).then(response => response.json()).then(response => {
    if (response.error) throw Error(response.error.data?.message || response.error.message);
    return response.result;
});

document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const form = app.querySelector("[data-report-form]");
    const message = app.querySelector("[data-message]");
    const customerEmailPanel = app.querySelector("[data-customer-email-panel]");
    const companyServiceEmail = app.querySelector("[data-company-service-email]");
    const customerEmailCompose = app.querySelector("[data-customer-email-compose]");
    const status = app.querySelector("[data-status]");
    const draftState = app.querySelector("[data-draft-state]");
    const confirmation = app.querySelector("[data-confirmation]");
    const canvas = app.querySelector("[data-signature]");
    const context = canvas.getContext("2d");
    const field = name => form.elements.namedItem(name);
    const workDescription = field("workDescription");
    const growWorkDescription = () => {
        if (workDescription.clientWidth && workDescription.scrollHeight > workDescription.clientHeight) {
            const borderHeight = workDescription.offsetHeight - workDescription.clientHeight;
            workDescription.style.height = `${workDescription.scrollHeight + borderHeight}px`;
        }
    };
    workDescription.addEventListener("input", growWorkDescription);
    if ("ResizeObserver" in window) {
        new ResizeObserver(() => requestAnimationFrame(growWorkDescription)).observe(workDescription);
    }
    const customerName = app.querySelector("[data-customer-name]");
    const customerCard = app.querySelector("[data-customer-card]");
    const manualCustomer = app.querySelector("[data-manual-customer]");
    const workTemplateSelect = app.querySelector("[data-work-template-select]");
    const workTemplateInsert = app.querySelector("[data-work-template-insert]");
    const workTemplateRefresh = app.querySelector("[data-work-template-refresh]");
    const workTemplatePreview = app.querySelector("[data-work-template-preview]");
    const workTemplateStatus = app.querySelector("[data-work-template-status]");
    const workTemplatesById = new Map();
    const showWorkTemplate = () => {
        const template = workTemplatesById.get(workTemplateSelect.value);
        workTemplateInsert.disabled = !template;
        workTemplatePreview.textContent = template?.body || "";
        workTemplatePreview.classList.toggle("d-none", !template);
    };
    const renderWorkTemplates = templates => {
        const selected = workTemplateSelect.value;
        workTemplatesById.clear();
        workTemplateSelect.replaceChildren();
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Frei schreiben – ohne Vorlage";
        workTemplateSelect.append(empty);
        for (const template of templates) {
            workTemplatesById.set(String(template.id), template);
            const option = document.createElement("option");
            option.value = String(template.id);
            option.textContent = template.name;
            workTemplateSelect.append(option);
        }
        workTemplateSelect.value = workTemplatesById.has(selected) ? selected : "";
        workTemplateStatus.textContent = templates.length
            ? "Vorlage auswählen oder direkt frei schreiben. Vorhandener Text bleibt beim Einfügen erhalten."
            : "Noch keine zentralen Vorlagen hinterlegt. Du kannst weiterhin frei schreiben.";
        showWorkTemplate();
    };
    workTemplateSelect.addEventListener("change", showWorkTemplate);
    workTemplateRefresh.addEventListener("click", async () => {
        workTemplateRefresh.disabled = true;
        try {
            renderWorkTemplates(await rpc("/nolte_stundenbericht/api/v1/work-templates", {}));
        } catch {
            workTemplateStatus.textContent = "Vorlagen konnten nicht aktualisiert werden. Freies Schreiben bleibt möglich.";
        } finally {
            workTemplateRefresh.disabled = false;
        }
    });
    workTemplateInsert.addEventListener("click", () => {
        const template = workTemplatesById.get(workTemplateSelect.value);
        if (!template) return;
        const description = field("workDescription");
        const existing = description.value.trimEnd();
        description.value = existing ? `${existing}\n\n${template.body}` : template.body;
        description.dispatchEvent(new Event("input", {bubbles: true}));
        description.focus();
        workTemplateStatus.textContent = `Vorlage „${template.name}“ eingefügt. Du kannst den Text frei bearbeiten.`;
    });
    const dayDate = app.querySelector("[data-day-date]");
    const dayList = app.querySelector("[data-day-list]");
    const timeEmployee = app.querySelector("[data-time-employee]");
    let report = null;
    let currentDraft = null;
    let syncCompleted = localStorage.getItem(SYNCED_STATE_KEY) === "1";
    const syncButton = app.querySelector("[data-sync]");
    if (syncCompleted) {
        syncButton.disabled = true;
        syncButton.textContent = "Bericht synchronisiert";
    }
    let drawing = false;
    let lastPoint = null;
    let hasSignature = false;
    let days = {};
    let employeeSchedules = {};
    // Einsatzweite Übernachtungssumme pro Mitarbeiter (nicht pro Tag).
    let employeeOvernights = {};
    let activeEmployeeId = "self";
    let ownEmployeeId = null;
    let employeeOptions = [];
    const assignmentsById = new Map();
    const say = (text, error = false) => { message.textContent = text; message.className = `alert ${error ? "alert-danger" : "alert-info"}`; };
    const updateCustomerEmailPanel = () => {
        if (!customerEmailPanel) return;
        const canSend = Boolean(report?.canSendCustomerEmail);
        customerEmailPanel.classList.toggle("d-none", !canSend);
        if (canSend) {
            companyServiceEmail.textContent = report.companyServiceEmail || "E-Mail-Adresse beim Unternehmen fehlt";
            customerEmailCompose.href = report.composeEmailUrl;
            if (report.customerPdfUrl) app.querySelector("[data-pdf-link]").href = report.customerPdfUrl;
        }
    };
    const online = () => { status.textContent = navigator.onLine ? "Online" : "Offline"; status.className = `badge ${navigator.onLine ? "text-bg-success" : "text-bg-secondary"}`; };
    const isQuarterHour = value => /^(?:[01]\d|2[0-3]):(?:00|15|30|45)$/.test(value || "");
    const validateTimeBlocks = () => {
        const allSchedules = {...employeeSchedules, [String(activeEmployeeId)]: days};
        for (const [employeeId, employeeDays] of Object.entries(allSchedules)) for (const [date, segments] of Object.entries(employeeDays || {})) {
            for (const segment of segments) {
                if (Boolean(segment.start) !== Boolean(segment.end)) {
                    say(`${date}: Bitte bei ${segmentLabel(segment.type)} Anfang und Ende vollständig auswählen.`, true);
                    return false;
                }
                if (segment.start && (!isQuarterHour(segment.start) || !isQuarterHour(segment.end))) {
                    say(`${date}: ${segmentLabel(segment.type)} muss im 15-Minuten-Raster erfasst werden.`, true);
                    return false;
                }
            }
        }
        return true;
    };
    const segmentLabel = type => ({outbound_travel: "Hinfahrt", return_travel: "Rückfahrt", work: "Arbeitszeit", break: "Pause"}[type] || type);
    const duration = segment => {
        if (!segment?.start || !segment?.end) return 0;
        const [sh, sm] = segment.start.split(":").map(Number), [eh, em] = segment.end.split(":").map(Number);
        let minutes = eh * 60 + em - sh * 60 - sm;
        return minutes < 0 ? minutes + 1440 : minutes;
    };
    const showDuration = value => `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")} h`;
    const addClockMinutes = (value, minutes) => {
        if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value || "")) return "";
        const [hour, minute] = value.split(":").map(Number);
        const total = (hour * 60 + minute + minutes) % 1440;
        return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
    };
    const newSegment = type => ({segmentUuid: uuid(), type, start: "", end: "", kilometers: 0, internalOnly: false});
    const saveActiveSchedule = () => { employeeSchedules[String(activeEmployeeId)] = days; };
    const switchEmployee = employeeId => {
        saveActiveSchedule();
        activeEmployeeId = String(employeeId);
        days = employeeSchedules[activeEmployeeId] || {};
        employeeSchedules[activeEmployeeId] = days;
        employeeOvernights[activeEmployeeId] ??= 0;
        if (!Object.keys(days).length) days[dayDate.value || field("serviceDate").value] = [];
        dayDate.value = Object.keys(days).sort()[0] || field("serviceDate").value;
        renderDays();
        renderEmployeeOvernight();
        scheduleAutoSave();
    };
    let timePicker = null;
    const closeTimePicker = () => { timePicker?.remove(); timePicker = null; };
    const timeButton = (date, segment, key, label, defaultTime = "") => {
        const button = document.createElement("button");
        button.type = "button"; button.className = "ns-time-input form-control text-start"; button.textContent = segment[key] || "--:--";
        button.setAttribute("aria-label", label);
        button.onclick = () => {
            closeTimePicker();
            let [hour, minute] = (segment[key] || defaultTime || (key === "start" ? "08:00" : "16:00")).split(":");
            const picker = document.createElement("div"); picker.className = "ns-time-picker";
            picker.innerHTML = `<header><strong>${label}</strong><button type="button" data-clear="">Leeren</button></header><div class="ns-time-columns"><div>${Array.from({length:24}, (_, i) => String(i).padStart(2, "0")).map(value => `<button type="button" data-hour="${value}" class="${value === hour ? "selected" : ""}">${value}</button>`).join("")}</div><span>:</span><div>${["00", "15", "30", "45"].map(value => `<button type="button" data-minute="${value}" class="${value === minute ? "selected" : ""}">${value}</button>`).join("")}</div></div>`;
            document.body.append(picker);
            const rect = button.getBoundingClientRect();
            picker.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - picker.offsetWidth - 12))}px`;
            picker.style.top = `${Math.max(12, Math.min(rect.bottom + 5, window.innerHeight - picker.offsetHeight - 12))}px`;
            picker.querySelector("[data-hour].selected")?.scrollIntoView({block:"center"});
            picker.onclick = event => {
                const hourButton = event.target.closest("[data-hour]"); const minuteButton = event.target.closest("[data-minute]");
                if (event.target.closest("[data-clear]")) { segment[key] = ""; closeTimePicker(); renderDays(); scheduleAutoSave(); return; }
                if (hourButton) { hour = hourButton.dataset.hour; picker.querySelectorAll("[data-hour]").forEach(item => item.classList.toggle("selected", item === hourButton)); }
                if (minuteButton) {
                    segment[key] = `${hour}:${minuteButton.dataset.minute}`;
                    closeTimePicker(); renderDays(); scheduleAutoSave();
                }
            };
            timePicker = picker;
        };
        return button;
    };
    document.addEventListener("pointerdown", event => { if (timePicker && !timePicker.contains(event.target) && !event.target.closest(".ns-time-input")) closeTimePicker(); });
    const segmentRow = (date, segment) => {
        const row = document.createElement("div"); row.className = "ns-segment-row border rounded p-2 mb-2 bg-light";
        const header = document.createElement("div"); header.className = "d-flex justify-content-between align-items-center mb-2";
        const title = document.createElement("strong"); title.textContent = segmentLabel(segment.type); header.append(title);
        const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-outline-danger"; remove.textContent = "Entfernen";
        remove.onclick = () => { days[date] = days[date].filter(item => item.segmentUuid !== segment.segmentUuid); renderDays(); scheduleAutoSave(); };
        header.append(remove); row.append(header);
        const grid = document.createElement("div"); grid.className = "row g-2 align-items-end";
        const workEnd = [...(days[date] || [])].reverse().find(item => item.type === "work" && item.end)?.end || "";
        const startDefault = segment.type === "return_travel" ? workEnd : "";
        const start = document.createElement("div"); start.className = "col-6 col-md-3"; start.innerHTML = "<label class=\"form-label small mb-1\">von</label>"; start.append(timeButton(date, segment, "start", `${segmentLabel(segment.type)} – Startzeit`, startDefault));
        const endDefault = segment.type.includes("travel") ? (addClockMinutes(segment.start, 120) || "10:00") : "";
        const end = document.createElement("div"); end.className = "col-6 col-md-3"; end.innerHTML = "<label class=\"form-label small mb-1\">bis</label>"; end.append(timeButton(date, segment, "end", `${segmentLabel(segment.type)} – Endzeit`, endDefault));
        grid.append(start, end);
        if (segment.type.includes("travel")) {
            const km = document.createElement("div"); km.className = "col-12 col-md-3"; km.innerHTML = "<label class=\"form-label small mb-1\">Kilometer</label>";
            const input = document.createElement("input"); input.className = "form-control"; input.type = "number"; input.min = "0"; input.step = "0.1"; input.value = segment.kilometers || ""; input.oninput = () => { segment.kilometers = Number(input.value || 0); renderTimeTable(); scheduleAutoSave(); }; km.append(input); grid.append(km);
        }
        const total = document.createElement("div"); total.className = "col-12 col-md-3 small text-muted"; total.textContent = segment.start && segment.end ? `Dauer: ${showDuration(duration(segment))}` : "Zeit auswählen"; grid.append(total);
        row.append(grid); return row;
    };
    const renderTimeTable = () => {
        const body = app.querySelector("[data-time-table-body]");
        if (!body) return;
        body.replaceChildren();
        const footer = app.querySelector("[data-time-table-totals]");
        footer.replaceChildren();
        const allSchedules = {...employeeSchedules, [String(activeEmployeeId)]: days};
        const employeeName = employeeId => employeeOptions.find(item => String(item.id) === String(employeeId))?.name || "–";
        const entries = Object.entries(allSchedules).flatMap(([employeeId, employeeDays]) => Object.keys(employeeDays || {}).map(date => ({employeeId, date, segments: employeeDays[date] || []})))
            .sort((a, b) => a.date.localeCompare(b.date) || employeeName(a.employeeId).localeCompare(employeeName(b.employeeId), "de"));
        if (!entries.length) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 10;
            cell.className = "text-muted";
            cell.textContent = "Noch keine Zeiten erfasst.";
            row.append(cell);
            body.append(row);
            return;
        }
        const types = ["outbound_travel", "work", "break", "return_travel"];
        const totals = {minutes: [0, 0, 0, 0], outboundKm: 0, returnKm: 0, overnights: 0};
        const seenEmployees = new Set();
        const kilometersText = value => Number(value).toLocaleString("de-DE", {maximumFractionDigits: 1});
        const appendCell = (row, text, className = "") => {
            const cell = document.createElement("td");
            cell.textContent = text;
            cell.className = className;
            row.append(cell);
            return cell;
        };
        entries.forEach(({employeeId, date, segments}) => {
            const row = document.createElement("tr");
            appendCell(row, new Date(`${date}T00:00:00`).toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric"}));
            appendCell(row, employeeName(employeeId));
            const grouped = types.map(type => segments.filter(segment => segment.type === type));
            grouped.forEach((items, index) => {
                const minutes = items.reduce((sum, item) => sum + duration(item), 0);
                totals.minutes[index] += minutes;
                const cell = appendCell(row, "");
                const ranges = items.filter(item => item.start || item.end);
                if (!ranges.length) { cell.textContent = "–"; return; }
                ranges.forEach(item => {
                    const range = document.createElement("div");
                    range.textContent = `${item.start || "–"}–${item.end || "–"}`;
                    cell.append(range);
                });
                const subtotal = document.createElement("small");
                subtotal.className = "d-block text-muted";
                subtotal.textContent = showDuration(minutes);
                cell.append(subtotal);
            });
            const outboundKm = grouped[0].reduce((sum, item) => sum + Number(item.kilometers || 0), 0);
            const returnKm = grouped[3].reduce((sum, item) => sum + Number(item.kilometers || 0), 0);
            // Overnight counts belong to the whole assignment, so show each
            // employee's count only on their first day, as in the PDF.
            const overnights = seenEmployees.has(employeeId) ? 0 : Number(employeeOvernights[employeeId] || 0);
            seenEmployees.add(employeeId);
            totals.outboundKm += outboundKm;
            totals.returnKm += returnKm;
            totals.overnights += overnights;
            [outboundKm, returnKm, outboundKm + returnKm].forEach(value => appendCell(row, value ? kilometersText(value) : "–", "text-end"));
            appendCell(row, String(overnights), "text-end");
            body.append(row);
        });
        const totalRow = document.createElement("tr");
        appendCell(totalRow, "Gesamtsumme").colSpan = 2;
        totals.minutes.forEach(value => appendCell(totalRow, showDuration(value)));
        [totals.outboundKm, totals.returnKm, totals.outboundKm + totals.returnKm, totals.overnights].forEach(value => appendCell(totalRow, kilometersText(value), "text-end"));
        footer.append(totalRow);
    };
    if (!field("serviceDate").value) field("serviceDate").value = new Date().toISOString().slice(0, 10);
    if (!dayDate.value) dayDate.value = field("serviceDate").value;
    online();
    window.addEventListener("online", online);
    window.addEventListener("offline", online);
    document.head.insertAdjacentHTML("beforeend", '<link rel="manifest" href="/nolte_stundenbericht/manifest.webmanifest">');
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/nolte_stundenbericht/service-worker.js?v=35", {scope: "/"}).catch(() => null);
    const boot = rpc("/nolte_stundenbericht/api/v1/bootstrap", {}).then(data => {
        renderWorkTemplates(data.workTemplates || []);
        const countryField = field("countryRateKey");
        const selectedCountry = countryField.value || "DE";
        if (data.countries?.length) {
            countryField.replaceChildren(...data.countries.map(country => {
                const option = document.createElement("option");
                option.value = country.code;
                option.textContent = country.name;
                return option;
            }));
        }
        countryField.value = data.countries?.some(country => country.code === selectedCountry) ? selectedCountry : "DE";
        const initialOvernights = employeeOvernights[activeEmployeeId] || 0;
        ownEmployeeId = String(data.employee.id);
        activeEmployeeId = ownEmployeeId;
        employeeOvernights[activeEmployeeId] ??= initialOvernights;
        delete employeeOvernights.self;
        employeeOptions = data.employees?.length ? data.employees : [data.employee];
        employeeSchedules[activeEmployeeId] = days;
        timeEmployee.replaceChildren();
        employeeOptions.forEach(employee => {
            const option = document.createElement("option"); option.value = employee.id; option.textContent = employee.name;
            timeEmployee.append(option);
        });
        timeEmployee.value = activeEmployeeId;
        timeEmployee.closest("[data-time-employee-wrap]").classList.toggle("d-none", employeeOptions.length < 2);
        timeEmployee.addEventListener("change", () => switchEmployee(timeEmployee.value));
        renderEmployeeOvernight();
        for (const assignment of data.assignments || []) {
            assignmentsById.set(String(assignment.id), assignment);
            const option = document.createElement("option");
            option.value = assignment.id;
            // The user needs to recognize the customer when choosing an
            // assignment. Technician instructions are shown separately below.
            option.textContent = assignment.customerName || "Einsatzauftrag";
            option.dataset.customerId = assignment.customerId || "";
            option.dataset.customerName = assignment.customerName || "";
            option.dataset.customerAddress = assignment.customerAddress || "";
            option.dataset.contactName = assignment.contactName || "";
            option.dataset.contactPhone = assignment.contactPhone || "";
            option.dataset.contactEmail = assignment.contactEmail || "";
            option.dataset.serviceLocation = assignment.serviceLocation || "";
            option.dataset.serviceLocationName = assignment.serviceLocationName || "";
            option.dataset.serviceLocationContactName = assignment.serviceLocationContactName || "";
            option.dataset.serviceLocationContactPhone = assignment.serviceLocationContactPhone || "";
            option.dataset.serviceLocationDiffers = assignment.serviceLocationDiffers ? "1" : "";
            option.dataset.machineNumber = assignment.machineNumber || "";
            option.dataset.machineType = assignment.machineType || "";
            option.dataset.overnightCount = assignment.overnightCount || 0;
            option.dataset.taskWorkOrderDescription = assignment.workOrderDescription || "";
            field("taskId").append(option);
        }
        renderDays();
        return data;
    });
    const applyTaskDefaults = () => {
        const taskId = String(field("taskId").value || "");
        const task = field("taskId").selectedOptions[0];
        const assignment = assignmentsById.get(taskId);
        const historyWrap = app.querySelector("[data-customer-history-wrap]");
        const historyLink = app.querySelector("[data-customer-history-link]");
        historyWrap.classList.toggle("d-none", !taskId);
        historyLink.href = taskId ? `/my/stundenbericht/history/${encodeURIComponent(taskId)}` : "#";
        // Technician instructions live only in the task description. Never
        // display the task title as a substitute for these instructions.
        const workOrder = String(
            assignment?.workOrderDescription || task?.dataset.taskWorkOrderDescription || ""
        )
            .replace(/\u00a0/g, " ").trim();
        app.querySelector("[data-work-order-card]").classList.toggle("d-none", !taskId);
        app.querySelector("[data-work-order-card] [data-work-order-description]").textContent = workOrder;
        customerName.value = task?.dataset.customerName || "";
        customerCard.classList.toggle("d-none", !task?.value);
        manualCustomer.classList.toggle("d-none", Boolean(task?.value));
        customerCard.querySelector("[data-customer-display]").textContent = task?.dataset.customerName || "";
        customerCard.querySelector("[data-customer-address]").textContent = task?.dataset.customerAddress || "";
        const contact = customerCard.querySelector("[data-contact-display]");
        const contactParts = [task?.dataset.contactPhone, task?.dataset.contactEmail].filter(Boolean).join(" · ");
        contact.classList.toggle("d-none", !(task?.dataset.contactName || contactParts));
        customerCard.querySelector("[data-contact-name]").textContent = task?.dataset.contactName || "";
        customerCard.querySelector("[data-contact-phone]").textContent = contactParts ? (task?.dataset.contactName ? " · " : "") + contactParts : "";
        customerCard.querySelector("[data-contact-email]").textContent = "";
        const locationWrap = app.querySelector("[data-service-location-wrap]");
        const locationDiffers = task?.dataset.serviceLocationDiffers === "1";
        locationWrap.classList.toggle("d-none", Boolean(task?.value) && !locationDiffers);
        app.querySelector("[data-service-location-label]").textContent = locationDiffers ? "Einsatzort (abweichend vom Kunden)" : "Einsatzort";
        app.querySelector("[data-service-location-name-label]").textContent = locationDiffers ? "Firma am Einsatzort (abweichend vom Auftraggeber)" : "Firma am Einsatzort";
        if (!task?.value) return;
        field("serviceLocation").value = task.dataset.serviceLocation || "";
        field("serviceLocationName").value = task.dataset.serviceLocationName || "";
        field("serviceLocationContactName").value = task.dataset.serviceLocationContactName || "";
        field("serviceLocationContactPhone").value = task.dataset.serviceLocationContactPhone || "";
        field("machineNumber").value = task.dataset.machineNumber || "";
        field("machineType").value = task.dataset.machineType || "";
    };
    field("taskId").addEventListener("change", applyTaskDefaults);
    const renderDays = () => {
        dayList.replaceChildren();
        const activeEmployee = employeeOptions.find(item => String(item.id) === String(activeEmployeeId));
        const employeeHeading = document.createElement("p"); employeeHeading.className = "small text-muted mb-2";
        employeeHeading.textContent = `Zeiterfassung für: ${activeEmployee?.name || "Mitarbeiter"}. Über die Auswahl kannst du weitere Mitarbeiter mit jeweils eigenen Zeiten erfassen.`;
        dayList.append(employeeHeading);
        let totalWork = 0, totalTravel = 0, totalBreak = 0;
        Object.keys(days).sort().forEach(date => {
            const segments = days[date] || [];
            const work = segments.filter(item => item.type === "work").reduce((sum, item) => sum + duration(item), 0);
            const travel = segments.filter(item => item.type.includes("travel")).reduce((sum, item) => sum + duration(item), 0);
            const breaks = segments.filter(item => item.type === "break").reduce((sum, item) => sum + duration(item), 0);
            totalWork += work; totalTravel += travel; totalBreak += breaks;
            const details = document.createElement("details");
            details.className = "ns-day-card border rounded bg-white mb-2";
            details.open = date === dayDate.value;
            const label = new Date(`${date}T00:00:00`).toLocaleDateString("de-DE", {weekday:"short", day:"2-digit", month:"2-digit", year:"numeric"});
            const summary = document.createElement("summary");
            summary.className = "ns-day-summary p-2";
            summary.innerHTML = `<strong>${label}</strong><span class="ns-day-metrics ms-2 text-muted">Arbeit ${showDuration(work)} · Fahrt ${showDuration(travel)} · Pause ${showDuration(breaks)} · Einsatz ${showDuration(Math.max(0, work + travel - breaks))}</span>`;
            details.append(summary);
            const body = document.createElement("div");
            body.className = "ns-day-body border-top p-2";
            if (!segments.length) {
                const hint = document.createElement("p"); hint.className = "text-muted small mb-2";
                hint.textContent = "Noch keine Zeiten erfasst."; body.append(hint);
            }
            segments.forEach(segment => body.append(segmentRow(date, segment)));
            const buttons = document.createElement("div"); buttons.className = "ns-day-actions d-flex flex-wrap gap-1 mt-2";
            [["outbound_travel", "＋ Hinfahrt"], ["work", "＋ Arbeitszeit"], ["break", "＋ Pause"], ["return_travel", "＋ Rückfahrt"]].forEach(([type, text]) => {
                const button = document.createElement("button"); button.type = "button";
                button.className = type === "break" ? "btn btn-outline-secondary" : "btn btn-outline-primary";
                button.textContent = text; buttons.append(button);
                button.onclick = () => {
                    const segment = newSegment(type);
                    if (type === "break") {
                        segment.start = "12:00";
                        segment.end = "12:30";
                    }
                    if (type === "work") segment.start = [...days[date]].reverse().find(item => item.type === "outbound_travel" && item.end)?.end || "";
                    // Return travel stays empty until the technician chooses a value;
                    // its start-time picker is preselected to the work end.
                    days[date].push(segment); dayDate.value = date; renderDays(); scheduleAutoSave();
                };
            });
            const deleteDay = document.createElement("button"); deleteDay.type = "button";
            deleteDay.className = "btn btn-outline-danger ms-auto"; deleteDay.textContent = "Einsatztag löschen";
            deleteDay.onclick = () => { delete days[date]; const remaining = Object.keys(days).sort(); dayDate.value = remaining[0] || field("serviceDate").value; renderDays(); scheduleAutoSave(); };
            if (segments.length) {
                const copyDay = document.createElement("button"); copyDay.type = "button";
                copyDay.className = "btn btn-outline-secondary"; copyDay.textContent = "Tag auf Folgetag kopieren";
                copyDay.onclick = () => {
                    const next = new Date(`${date}T00:00:00Z`);
                    next.setUTCDate(next.getUTCDate() + 1);
                    const nextDate = next.toISOString().slice(0, 10);
                    if ((days[nextDate] || []).length) {
                        say(`Am ${new Date(`${nextDate}T00:00:00`).toLocaleDateString("de-DE")} sind bereits Zeiten erfasst. Es wurde nichts überschrieben.`, true);
                        dayDate.value = nextDate;
                        renderDays();
                        return;
                    }
                    days[nextDate] = segments.map(item => ({
                        ...item,
                        segmentUuid: uuid(),
                        start: item.start || "",
                        end: item.end || "",
                        kilometers: Number(item.kilometers || 0),
                        internalOnly: Boolean(item.internalOnly),
                    }));
                    dayDate.value = nextDate;
                    renderDays();
                    scheduleAutoSave();
                    say(`Alle Zeitsegmente von ${new Date(`${date}T00:00:00`).toLocaleDateString("de-DE")} wurden auf ${new Date(`${nextDate}T00:00:00`).toLocaleDateString("de-DE")} kopiert. Bitte bei Bedarf anpassen.`);
                };
                buttons.append(copyDay);

                // Copy this employee's complete day to another employee on the
                // same date. Never overwrite time blocks already entered there.
                if (employeeOptions.length > 1) {
                    const copyToEmployee = document.createElement("select");
                    copyToEmployee.className = "form-select form-select-sm w-auto";
                    copyToEmployee.setAttribute("aria-label", `Mitarbeiter für Kopie des Tages ${label} auswählen`);
                    const placeholder = document.createElement("option");
                    placeholder.value = "";
                    placeholder.textContent = "Mitarbeiter wählen …";
                    copyToEmployee.append(placeholder);
                    employeeOptions.filter(item => String(item.id) !== String(activeEmployeeId)).forEach(employee => {
                        const option = document.createElement("option");
                        option.value = String(employee.id);
                        option.textContent = employee.name;
                        copyToEmployee.append(option);
                    });
                    const copyToButton = document.createElement("button");
                    copyToButton.type = "button";
                    copyToButton.className = "btn btn-outline-secondary";
                    copyToButton.textContent = "Tag an Mitarbeiter kopieren";
                    copyToButton.onclick = () => {
                        const targetEmployeeId = copyToEmployee.value;
                        if (!targetEmployeeId) {
                            say("Bitte zuerst den Ziel-Mitarbeiter auswählen.", true);
                            return;
                        }
                        const targetSchedule = employeeSchedules[targetEmployeeId] ||= {};
                        if ((targetSchedule[date] || []).length) {
                            const targetName = employeeOptions.find(item => String(item.id) === targetEmployeeId)?.name || "Der Ziel-Mitarbeiter";
                            say(`${targetName} hat am ${new Date(`${date}T00:00:00`).toLocaleDateString("de-DE")} bereits Zeiten. Es wurde nichts überschrieben.`, true);
                            return;
                        }
                        targetSchedule[date] = segments.map(item => ({
                            ...item,
                            segmentUuid: uuid(),
                            start: item.start || "",
                            end: item.end || "",
                            kilometers: Number(item.kilometers || 0),
                            internalOnly: Boolean(item.internalOnly),
                        }));
                        renderDays();
                        scheduleAutoSave();
                        const targetName = employeeOptions.find(item => String(item.id) === targetEmployeeId)?.name || "Mitarbeiter";
                        say(`Der komplette Tag von ${activeEmployee?.name || "Mitarbeiter"} wurde für ${targetName} am ${new Date(`${date}T00:00:00`).toLocaleDateString("de-DE")} kopiert. Bitte Ziel-Mitarbeiter und Zeiten kontrollieren.`);
                    };
                    buttons.append(copyToEmployee, copyToButton);
                }
            }
            buttons.append(deleteDay); body.append(buttons); details.append(body); dayList.append(details);
        });
        const summarySegments = Object.values({...employeeSchedules, [String(activeEmployeeId)]: days}).flatMap(employeeDays => Object.values(employeeDays || {}).flat());
        totalWork = summarySegments.filter(item => item.type === "work").reduce((sum, item) => sum + duration(item), 0);
        totalTravel = summarySegments.filter(item => item.type.includes("travel")).reduce((sum, item) => sum + duration(item), 0);
        totalBreak = summarySegments.filter(item => item.type === "break").reduce((sum, item) => sum + duration(item), 0);
        app.querySelector("[data-summary-work]").textContent = showDuration(totalWork);
        app.querySelector("[data-summary-travel]").textContent = showDuration(totalTravel);
        app.querySelector("[data-summary-break]").textContent = showDuration(totalBreak);
        app.querySelector("[data-summary-total]").textContent = showDuration(Math.max(0, totalWork + totalTravel - totalBreak));
        renderTimeTable();
    };
    const employeeOvernightInput = app.querySelector("[data-employee-overnights]");
    const renderEmployeeOvernight = () => {
        employeeOvernightInput.value = Number(employeeOvernights[activeEmployeeId] || 0);
        const employeeName = employeeOptions.find(item => String(item.id) === String(activeEmployeeId))?.name || "Mitarbeiter";
        employeeOvernightInput.closest("[data-employee-overnights-wrap]").querySelector("[data-employee-overnights-label]").textContent = `Übernachtungen für ${employeeName} im gesamten Einsatz`;
    };
    employeeOvernightInput.addEventListener("input", () => { employeeOvernights[activeEmployeeId] = Math.max(0, Math.floor(Number(employeeOvernightInput.value || 0))); renderTimeTable(); scheduleAutoSave(); });
    dayDate.addEventListener("change", () => { if (!days[dayDate.value]) days[dayDate.value] = []; renderDays(); scheduleAutoSave(); });
    app.querySelector("[data-day-add]").onclick = () => { const next = new Date(`${dayDate.value || field("serviceDate").value}T12:00:00`); if (Number.isNaN(next.valueOf())) return; do { next.setDate(next.getDate() + 1); } while (days[next.toISOString().slice(0, 10)]); dayDate.value = next.toISOString().slice(0, 10); days[dayDate.value] = []; renderDays(); scheduleAutoSave(); };
    days[dayDate.value] = days[dayDate.value] || []; renderDays();
    const buildDraft = async () => {
        const bootstrap = await boot;
        const task = field("taskId").selectedOptions[0];
        saveActiveSchedule();
        const employeeDays = Object.entries(employeeSchedules).flatMap(([employeeId, employeeDates]) => Object.keys(employeeDates || {}).sort().map(date => ({employeeId: Number(employeeId), date, segments: (employeeDates[date] || []).filter(segment => isQuarterHour(segment.start) && isQuarterHour(segment.end))})));
        const serviceDays = Object.keys(days).sort().map(date => ({date, segments: (days[date] || []).filter(segment => isQuarterHour(segment.start) && isQuarterHour(segment.end))}));
        return {
            mobileUuid: currentDraft?.mobileUuid || uuid(),
            mobileRevision: (currentDraft?.mobileRevision || 0) + 1,
            serverRevision: currentDraft?.serverRevision,
            employeeId: bootstrap.employee.id,
            employeeIds: [...new Set([Number(bootstrap.employee.id), ...Object.keys(employeeSchedules).filter(id => id !== "self").map(Number)])],
            employeeDays,
            employeeSchedules,
            activeEmployeeId: Number(activeEmployeeId),
            taskId: field("taskId").value || null,
            partnerId: task?.dataset.customerId || null,
            manualCustomerName: field("manualCustomerName").value,
            manualCustomerStreet: field("manualCustomerStreet").value,
            manualCustomerZip: field("manualCustomerZip").value,
            manualCustomerCity: field("manualCustomerCity").value,
            manualContactName: field("manualContactName").value,
            manualContactPhone: field("manualContactPhone").value,
            manualContactEmail: field("manualContactEmail").value,
            serviceDate: employeeDays.map(item => item.date).sort()[0] || field("serviceDate").value,
            countryRateKey: field("countryRateKey").value,
            serviceLocation: field("serviceLocation").value,
            serviceLocationName: field("serviceLocationName").value,
            serviceLocationContactName: field("serviceLocationContactName").value,
            serviceLocationContactPhone: field("serviceLocationContactPhone").value,
            machineNumber: field("machineNumber").value,
            machineType: field("machineType").value,
            overnightCount: Object.values(employeeOvernights).reduce((sum, count) => sum + Number(count || 0), 0),
            employeeOvernights,
            publicNote: field("publicNote").value,
            workDescription: field("workDescription").value,
            workResult: field("workResult").value,
            materials: window.nolteStundenbericht?.materials?.export?.() || [],
            checklist: window.nolteStundenbericht?.checklist?.export?.() || [],
            days: serviceDays,
            segments: serviceDays[0]?.segments || [],
        };
    };
    const saveDraftLocally = async (automatic = false) => {
        currentDraft = await buildDraft();
        storeDrafts([...drafts().filter(item => item.mobileUuid !== currentDraft.mobileUuid), currentDraft]);
        window.dispatchEvent(new Event("nolte:drafts-changed"));
        const timestamp = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
        draftState.textContent = `Auf diesem Gerät gespeichert · ${timestamp}`;
        if (!automatic) say("Entwurf ist auf diesem Gerät gespeichert.");
    };
    let autoSaveTimer;
    const scheduleAutoSave = () => {
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveDraftLocally(true).catch(() => {
                draftState.textContent = "Lokale Sicherung wird erneut versucht.";
            });
        }, 800);
    };
    const loadDraft = async draft => {
        await boot;
        workTemplateSelect.value = "";
        showWorkTemplate();
        syncCompleted = false;
        localStorage.removeItem(SYNCED_STATE_KEY);
        syncButton.disabled = false;
        syncButton.textContent = "Jetzt synchronisieren";
        currentDraft = draft;
        const ownId = String(draft.employeeId || activeEmployeeId);
        employeeSchedules = {};
        employeeOvernights = draft.employeeOvernights || {};
        if (draft.employeeDays?.length) {
            draft.employeeDays.forEach(item => {
                const key = String(item.employeeId);
                employeeSchedules[key] ||= {};
                employeeSchedules[key][item.date] = item.segments || [];
                if (item.overnightCount && employeeOvernights[key] === undefined) employeeOvernights[key] = Number(item.overnightCount || 0);
            });
        } else if (draft.employeeSchedules) {
            employeeSchedules = draft.employeeSchedules;
        } else {
            employeeSchedules[ownId] = Object.fromEntries((draft.days || [{date: draft.serviceDate, segments: draft.segments || []}]).filter(item => item.date).map(item => [item.date, item.segments || []]));
        }
        activeEmployeeId = String(draft.activeEmployeeId || ownId);
        employeeSchedules[activeEmployeeId] ||= {};
        employeeOvernights[activeEmployeeId] ??= 0;
        days = employeeSchedules[activeEmployeeId];
        field("serviceDate").value = draft.serviceDate || "";
        dayDate.value = Object.keys(days).sort()[0] || draft.serviceDate || "";
        if (timeEmployee.querySelector(`option[value="${activeEmployeeId}"]`)) timeEmployee.value = activeEmployeeId;
        field("taskId").value = draft.taskId || "";
        applyTaskDefaults();
        field("manualCustomerName").value = draft.manualCustomerName || "";
        field("manualCustomerStreet").value = draft.manualCustomerStreet || "";
        field("manualCustomerZip").value = draft.manualCustomerZip || "";
        field("manualCustomerCity").value = draft.manualCustomerCity || "";
        field("manualContactName").value = draft.manualContactName || "";
        field("manualContactPhone").value = draft.manualContactPhone || "";
        field("manualContactEmail").value = draft.manualContactEmail || "";
        field("countryRateKey").value = draft.countryRateKey || "DE";
        field("serviceLocation").value = draft.serviceLocation || "";
        field("serviceLocationName").value = draft.serviceLocationName || "";
        field("serviceLocationContactName").value = draft.serviceLocationContactName || "";
        field("serviceLocationContactPhone").value = draft.serviceLocationContactPhone || "";
        field("machineNumber").value = draft.machineNumber || "";
        field("machineType").value = draft.machineType || "";
        // Migrate legacy drafts that stored one report-wide count.
        // Migrate drafts whose counts were stored by date to one value per employee.
        for (const [employeeId, counts] of Object.entries(employeeOvernights)) {
            if (counts && typeof counts === "object") employeeOvernights[employeeId] = Object.values(counts).reduce((sum, count) => sum + Number(count || 0), 0);
        }
        if (!Object.values(employeeOvernights).some(count => Number(count) > 0) && Number(draft.overnightCount || 0)) employeeOvernights[activeEmployeeId] = Number(draft.overnightCount);
        field("publicNote").value = draft.publicNote || "";
        field("workDescription").value = draft.workDescription || "";
        field("workResult").value = draft.workResult || "";
        renderDays();
        renderEmployeeOvernight();
        window.nolteStundenbericht?.materials?.import?.(draft.materials || []);
        window.nolteStundenbericht?.checklist?.import?.(draft.checklist || []);
        window.dispatchEvent(new Event("nolte:draft-loaded"));
        window.dispatchEvent(new CustomEvent("nolte:show-view", {detail: "general"}));
        window.nolteStundenbericht?.refreshTimePickers?.();
        say("Entwurf wurde geladen. Änderungen bitte erneut auf diesem Gerät speichern.");
        form.scrollIntoView({behavior: "smooth"});
    };
    const newReport = () => {
        if (!confirm("Einen neuen Bericht beginnen? Nicht gespeicherte Eingaben gehen verloren.")) return;
        syncCompleted = false;
        localStorage.removeItem(SYNCED_STATE_KEY);
        syncButton.disabled = false;
        syncButton.textContent = "Jetzt synchronisieren";
        form.reset();
        showWorkTemplate();
        window.nolteStundenbericht?.refreshTimePickers?.();
        field("serviceDate").value = new Date().toISOString().slice(0, 10);
        if (ownEmployeeId && employeeOptions.some(item => String(item.id) === ownEmployeeId)) {
            activeEmployeeId = ownEmployeeId;
            timeEmployee.value = ownEmployeeId;
        }
        days = {[field("serviceDate").value]: []}; employeeSchedules = {[String(activeEmployeeId)]: days}; employeeOvernights = {[String(activeEmployeeId)]: 0}; dayDate.value = field("serviceDate").value; renderDays(); renderEmployeeOvernight();
        field("countryRateKey").value = "DE";
        customerName.value = "";
        applyTaskDefaults();
        currentDraft = null; report = null; hasSignature = false;
        draftState.textContent = "";
        context.clearRect(0, 0, canvas.width, canvas.height);
        confirmation.classList.add("d-none");
        window.dispatchEvent(new Event("nolte:new-report"));
        window.dispatchEvent(new CustomEvent("nolte:show-view", {detail: "general"}));
        say("Neuer Bericht gestartet.");
        window.scrollTo({top: 0, behavior: "smooth"});
    };
    const deleteDraft = draft => {
        storeDrafts(drafts().filter(item => item.mobileUuid !== draft.mobileUuid));
        if (currentDraft?.mobileUuid === draft.mobileUuid) {
            form.reset();
            window.nolteStundenbericht?.refreshTimePickers?.();
            field("serviceDate").value = new Date().toISOString().slice(0, 10);
            if (ownEmployeeId && employeeOptions.some(item => String(item.id) === ownEmployeeId)) {
                activeEmployeeId = ownEmployeeId;
                timeEmployee.value = ownEmployeeId;
            }
            days = {[field("serviceDate").value]: []}; employeeSchedules = {[String(activeEmployeeId)]: days}; employeeOvernights = {[String(activeEmployeeId)]: 0}; dayDate.value = field("serviceDate").value; renderDays(); renderEmployeeOvernight();
            field("countryRateKey").value = "DE";
            currentDraft = null; report = null; hasSignature = false;
            context.clearRect(0, 0, canvas.width, canvas.height);
            confirmation.classList.add("d-none"); draftState.textContent = "";
            window.dispatchEvent(new Event("nolte:new-report"));
        }
        window.dispatchEvent(new CustomEvent("nolte:draft-deleted", {detail: {mobileUuid: draft.mobileUuid}}));
        window.dispatchEvent(new Event("nolte:drafts-changed"));
    };
    const ensureDraft = async () => {
        if (!currentDraft) await saveDraftLocally(true);
        return currentDraft?.mobileUuid || null;
    };
    const loadServerReport = async data => {
        await boot;
        const taskId = data.taskId ? String(data.taskId) : "";
        if (taskId) {
            const task = data.taskDefaults || {};
            assignmentsById.set(taskId, task);
            let option = [...field("taskId").options].find(item => item.value === taskId);
            if (!option) {
                option = document.createElement("option");
                option.value = taskId;
                field("taskId").append(option);
            }
            option.textContent = task.customerName || "Einsatzauftrag";
            const values = {
                customerId: task.customerId ?? data.partnerId,
                customerName: task.customerName ?? data.customerName,
                customerAddress: task.customerAddress,
                contactName: task.contactName,
                contactPhone: task.contactPhone,
                contactEmail: task.contactEmail,
                serviceLocation: task.serviceLocation ?? data.serviceLocation,
                serviceLocationName: task.serviceLocationName ?? data.serviceLocationName,
                serviceLocationContactName: task.serviceLocationContactName ?? data.serviceLocationContactName,
                serviceLocationContactPhone: task.serviceLocationContactPhone ?? data.serviceLocationContactPhone,
                serviceLocationDiffers: task.serviceLocationDiffers ? "1" : "",
                machineNumber: task.machineNumber ?? data.machineNumber,
                machineType: task.machineType ?? data.machineType,
                overnightCount: task.overnightCount ?? data.overnightCount,
                taskWorkOrderDescription: task.workOrderDescription,
            };
            for (const [key, value] of Object.entries(values)) {
                if (value !== undefined && value !== null) option.dataset[key] = String(value);
            }
        }
        const ownDays = data.days || (data.members || []).filter(member => member.employeeId === data.employeeId).map(member => ({date: member.serviceDate, segments: member.segments || []}));
        const employeeOvernightValues = Object.fromEntries((data.employeeAssignments || []).map(item => [String(item.employeeId), Number(item.overnightCount || 0)]));
        if (!Object.keys(employeeOvernightValues).length) {
            for (const member of data.members || []) employeeOvernightValues[String(member.employeeId)] = (employeeOvernightValues[String(member.employeeId)] || 0) + Number(member.overnightCount || 0);
        }
        const draft = {
            ...data,
            employeeOvernights: employeeOvernightValues,
            mobileRevision: data.mobileRevision || 0,
            employeeId: data.employeeId,
            taskId,
            days: ownDays,
            segments: ownDays[0]?.segments || [],
            partnerId: data.partnerId || null,
            countryRateKey: data.countryRateKey || "DE",
            serviceLocationContactName: data.serviceLocationContactName || data.taskDefaults?.serviceLocationContactName || "",
            serviceLocationContactPhone: data.serviceLocationContactPhone || data.taskDefaults?.serviceLocationContactPhone || "",
            publicNote: data.publicNote || "",
            materials: data.materials || [],
            checklist: data.checklist || [],
        };
        await loadDraft(draft);
        currentDraft.serverRevision = data.serverRevision;
        await saveDraftLocally(true);
        say("Gespeicherte Berichtsdaten wurden geladen. Änderungen kannst du bearbeiten und erneut synchronisieren.");
    };
    window.nolteStundenbericht = {drafts, loadDraft, loadServerReport, newReport, deleteDraft, ensureDraft, getCurrentDraftUuid: () => currentDraft?.mobileUuid || null, getCurrentReport: () => report};
    app.querySelectorAll("[data-new-report]").forEach(button => { button.onclick = newReport; });
    form.addEventListener("input", scheduleAutoSave);
    form.addEventListener("change", scheduleAutoSave);
    window.addEventListener("nolte:report-content-changed", scheduleAutoSave);
    app.querySelector("[data-save]").onclick = async () => {
        try { await saveDraftLocally(); } catch (error) { say(error.message, true); }
    };
    syncButton.onclick = async () => {
        if (syncCompleted || syncButton.disabled) return;
        try {
            if (!validateTimeBlocks()) return;
            if (!form.reportValidity()) { form.reportValidity(); return; }
            syncButton.disabled = true;
            let all = drafts();
            const active = await buildDraft();
            all = [...all.filter(item => item.mobileUuid !== active.mobileUuid), active];
            for (const draft of all) report = await rpc("/nolte_stundenbericht/api/v1/reports/upsert", {payload: draft});
            storeDrafts([]); currentDraft = null; draftState.textContent = "";
            const previewPanel = app.querySelector("[data-pdf-preview]");
            const previewLink = app.querySelector("[data-pdf-link]");
            if (report?.previewPdfUrl && previewPanel && previewLink) {
                previewLink.href = report.previewPdfUrl;
                previewPanel.querySelector("[data-pdf-title]").textContent = "PDF-Vorschau";
                previewPanel.querySelector("[data-pdf-description]").textContent = "So sieht der Bericht für den Kunden aus. Die finale Fassung enthält zusätzlich die Kundenunterschrift.";
                previewPanel.classList.remove("d-none");
            }
            updateCustomerEmailPanel();
            syncCompleted = true;
            localStorage.setItem(SYNCED_STATE_KEY, "1");
            syncButton.textContent = "Bericht synchronisiert";
            window.dispatchEvent(new Event("nolte:sync-complete"));
            window.dispatchEvent(new Event("nolte:drafts-changed"));
            say("Stundenbericht wurde synchronisiert. Bitte jetzt vom Kunden bestätigen lassen.");
            confirmation.classList.remove("d-none");
            window.dispatchEvent(new CustomEvent("nolte:show-view", {detail: "signature"}));
            confirmation.scrollIntoView({behavior: "smooth"});
        } catch (error) {
            syncButton.disabled = false;
            say(`Synchronisation fehlgeschlagen: ${error.message}`, true);
        }
    };
    const point = event => { const rect = canvas.getBoundingClientRect(); return {x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height}; };
    canvas.onpointerdown = event => { event.preventDefault(); drawing = true; canvas.setPointerCapture?.(event.pointerId); lastPoint = point(event); };
    canvas.onpointermove = event => {
        if (!drawing) return;
        event.preventDefault();
        const next = point(event); context.lineWidth = 2.5; context.lineCap = "round";
        context.beginPath(); context.moveTo(lastPoint.x, lastPoint.y); context.lineTo(next.x, next.y); context.stroke();
        lastPoint = next; hasSignature = true;
    };
    const stopDrawing = event => { drawing = false; if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture?.(event.pointerId); };
    canvas.onpointerup = canvas.onpointercancel = stopDrawing;
    app.querySelector("[data-signature-clear]").onclick = () => { context.clearRect(0, 0, canvas.width, canvas.height); hasSignature = false; };
    app.querySelector("[data-confirm]").onclick = async () => {
        const signer = app.querySelector("[data-signer-name]").value.trim();
        if (!report || !signer || !hasSignature) return say("Bericht, Name oder Unterschrift fehlt.", true);
        try {
            report = await rpc("/nolte_stundenbericht/api/v1/reports/customer-confirm", {mobile_uuid: report.mobileUuid, signer_name: signer, signature: canvas.toDataURL("image/png"), expected_server_revision: report.serverRevision});
            updateCustomerEmailPanel();
            confirmation.classList.add("d-none"); say("Kundenbestätigung gespeichert.");
        } catch (error) { say(`Kundenbestätigung fehlgeschlagen: ${error.message}`, true); }
    };
});

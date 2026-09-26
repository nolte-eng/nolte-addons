/** @odoo-module **/
const DRAFT_KEY = "nolte-stundenbericht-drafts-v1";
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
    const status = app.querySelector("[data-status]");
    const draftState = app.querySelector("[data-draft-state]");
    const confirmation = app.querySelector("[data-confirmation]");
    const canvas = app.querySelector("[data-signature]");
    const context = canvas.getContext("2d");
    const field = name => form.elements.namedItem(name);
    const customerName = app.querySelector("[data-customer-name]");
    const customerCard = app.querySelector("[data-customer-card]");
    const manualCustomer = app.querySelector("[data-manual-customer]");
    const dayDate = app.querySelector("[data-day-date]");
    const dayList = app.querySelector("[data-day-list]");
    let report = null;
    let currentDraft = null;
    let drawing = false;
    let lastPoint = null;
    let hasSignature = false;
    let days = {};
    const say = (text, error = false) => { message.textContent = text; message.className = `alert ${error ? "alert-danger" : "alert-info"}`; };
    const online = () => { status.textContent = navigator.onLine ? "Online" : "Offline"; status.className = `badge ${navigator.onLine ? "text-bg-success" : "text-bg-secondary"}`; };
    const isQuarterHour = value => /^(?:[01]\d|2[0-3]):(?:00|15|30|45)$/.test(value || "");
    const validateTimeBlocks = () => {
        for (const [date, segments] of Object.entries(days)) {
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
    const newSegment = type => ({segmentUuid: uuid(), type, start: "", end: "", kilometers: 0, internalOnly: false});
    let timePicker = null;
    const closeTimePicker = () => { timePicker?.remove(); timePicker = null; };
    const timeButton = (segment, key, label) => {
        const button = document.createElement("button");
        button.type = "button"; button.className = "ns-time-input form-control text-start"; button.textContent = segment[key] || "--:--";
        button.setAttribute("aria-label", label);
        button.onclick = () => {
            closeTimePicker();
            let [hour, minute] = (segment[key] || (key === "start" ? "08:00" : "16:00")).split(":");
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
                if (minuteButton) { segment[key] = `${hour}:${minuteButton.dataset.minute}`; closeTimePicker(); renderDays(); scheduleAutoSave(); }
            };
            timePicker = picker;
        };
        return button;
    };
    document.addEventListener("pointerdown", event => { if (timePicker && !timePicker.contains(event.target) && !event.target.closest(".ns-time-input")) closeTimePicker(); });
    const segmentRow = (date, segment) => {
        const row = document.createElement("div"); row.className = "border rounded p-2 mb-2 bg-light";
        const header = document.createElement("div"); header.className = "d-flex justify-content-between align-items-center mb-2";
        const title = document.createElement("strong"); title.textContent = segmentLabel(segment.type); header.append(title);
        const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-outline-danger"; remove.textContent = "Entfernen";
        remove.onclick = () => { days[date] = days[date].filter(item => item.segmentUuid !== segment.segmentUuid); renderDays(); scheduleAutoSave(); };
        header.append(remove); row.append(header);
        const grid = document.createElement("div"); grid.className = "row g-2 align-items-end";
        const start = document.createElement("div"); start.className = "col-6 col-md-3"; start.innerHTML = "<label class=\"form-label small mb-1\">von</label>"; start.append(timeButton(segment, "start", `${segmentLabel(segment.type)} – Startzeit`));
        const end = document.createElement("div"); end.className = "col-6 col-md-3"; end.innerHTML = "<label class=\"form-label small mb-1\">bis</label>"; end.append(timeButton(segment, "end", `${segmentLabel(segment.type)} – Endzeit`));
        grid.append(start, end);
        if (segment.type.includes("travel")) {
            const km = document.createElement("div"); km.className = "col-12 col-md-3"; km.innerHTML = "<label class=\"form-label small mb-1\">Kilometer</label>";
            const input = document.createElement("input"); input.className = "form-control"; input.type = "number"; input.min = "0"; input.step = "0.1"; input.value = segment.kilometers || ""; input.oninput = () => { segment.kilometers = Number(input.value || 0); scheduleAutoSave(); }; km.append(input); grid.append(km);
        }
        const total = document.createElement("div"); total.className = "col-12 col-md-3 small text-muted"; total.textContent = segment.start && segment.end ? `Dauer: ${showDuration(duration(segment))}` : "Zeit auswählen"; grid.append(total);
        row.append(grid); return row;
    };
    if (!field("serviceDate").value) field("serviceDate").value = new Date().toISOString().slice(0, 10);
    if (!dayDate.value) dayDate.value = field("serviceDate").value;
    online();
    window.addEventListener("online", online);
    window.addEventListener("offline", online);
    document.head.insertAdjacentHTML("beforeend", '<link rel="manifest" href="/nolte_stundenbericht/manifest.webmanifest">');
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/nolte_stundenbericht/service-worker.js", {scope: "/"}).catch(() => null);
    const boot = rpc("/nolte_stundenbericht/api/v1/bootstrap", {}).then(data => {
        for (const assignment of data.assignments || []) {
            const option = document.createElement("option");
            option.value = assignment.id;
            option.textContent = assignment.customerName ? `${assignment.customerName} · ${assignment.name}` : assignment.name;
            option.dataset.customerId = assignment.customerId || "";
            option.dataset.customerName = assignment.customerName || "";
            option.dataset.customerAddress = assignment.customerAddress || "";
            option.dataset.contactName = assignment.contactName || "";
            option.dataset.contactPhone = assignment.contactPhone || "";
            option.dataset.contactEmail = assignment.contactEmail || "";
            option.dataset.serviceLocation = assignment.serviceLocation || "";
            option.dataset.serviceLocationDiffers = assignment.serviceLocationDiffers ? "1" : "";
            option.dataset.machineNumber = assignment.machineNumber || "";
            option.dataset.machineType = assignment.machineType || "";
            option.dataset.overnightCount = assignment.overnightCount || 0;
            field("taskId").append(option);
        }
        return data;
    });
    const applyTaskDefaults = () => {
        const task = field("taskId").selectedOptions[0];
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
        if (!task?.value) return;
        field("serviceLocation").value = task.dataset.serviceLocation || "";
        field("machineNumber").value = task.dataset.machineNumber || "";
        field("machineType").value = task.dataset.machineType || "";
        field("overnightCount").value = task.dataset.overnightCount || 0;
    };
    field("taskId").addEventListener("change", applyTaskDefaults);
    const renderDays = () => { dayList.replaceChildren(); let totalWork = 0, totalTravel = 0, totalBreak = 0; Object.keys(days).sort().forEach(date => { const segments = days[date] || []; const work = segments.filter(item => item.type === "work").reduce((sum, item) => sum + duration(item), 0); const travel = segments.filter(item => item.type.includes("travel")).reduce((sum, item) => sum + duration(item), 0); const breaks = segments.filter(item => item.type === "break").reduce((sum, item) => sum + duration(item), 0); totalWork += work; totalTravel += travel; totalBreak += breaks; const details = document.createElement("details"); details.className = "border rounded bg-white mb-3"; details.open = date === dayDate.value; const label = new Date(`${date}T00:00:00`).toLocaleDateString("de-DE", {weekday:"short", day:"2-digit", month:"2-digit", year:"numeric"}); const summary = document.createElement("summary"); summary.className = "p-3"; summary.innerHTML = `<strong>${label}</strong><span class="ms-2 text-muted">Arbeit ${showDuration(work)} · Fahrt ${showDuration(travel)} · Pause ${showDuration(breaks)} · Einsatz ${showDuration(Math.max(0, work + travel - breaks))}</span>`; details.append(summary); const body = document.createElement("div"); body.className = "border-top p-3"; if (!segments.length) { const hint = document.createElement("p"); hint.className = "text-muted small"; hint.textContent = "Noch keine Zeiten erfasst."; body.append(hint); } segments.forEach(segment => body.append(segmentRow(date, segment))); const buttons = document.createElement("div"); buttons.className = "d-flex flex-wrap gap-2 mt-2"; [["outbound_travel", "＋ Hinfahrt"], ["work", "＋ Arbeitszeit"], ["break", "＋ Pause"], ["return_travel", "＋ Rückfahrt"]].forEach(([type, text]) => { const button = document.createElement("button"); button.type = "button"; button.className = type === "break" ? "btn btn-outline-secondary" : "btn btn-outline-primary"; button.textContent = text; button.onclick = () => { const segment = newSegment(type); if (type === "work") segment.start = [...days[date]].reverse().find(item => item.type === "outbound_travel" && item.end)?.end || ""; if (type === "return_travel") segment.start = [...days[date]].reverse().find(item => item.type === "work" && item.end)?.end || ""; days[date].push(segment); dayDate.value = date; renderDays(); scheduleAutoSave(); }; buttons.append(button); }); const deleteDay = document.createElement("button"); deleteDay.type = "button"; deleteDay.className = "btn btn-outline-danger ms-auto"; deleteDay.textContent = "Einsatztag löschen"; deleteDay.onclick = () => { delete days[date]; const remaining = Object.keys(days).sort(); dayDate.value = remaining[0] || field("serviceDate").value; renderDays(); scheduleAutoSave(); }; buttons.append(deleteDay); body.append(buttons); details.append(body); dayList.append(details); }); app.querySelector("[data-summary-work]").textContent = showDuration(totalWork); app.querySelector("[data-summary-travel]").textContent = showDuration(totalTravel); app.querySelector("[data-summary-break]").textContent = showDuration(totalBreak); app.querySelector("[data-summary-total]").textContent = showDuration(Math.max(0, totalWork + totalTravel - totalBreak)); };
    dayDate.addEventListener("change", () => { if (!days[dayDate.value]) days[dayDate.value] = []; renderDays(); });
    app.querySelector("[data-day-add]").onclick = () => { const next = new Date(`${dayDate.value || field("serviceDate").value}T12:00:00`); if (Number.isNaN(next.valueOf())) return; do { next.setDate(next.getDate() + 1); } while (days[next.toISOString().slice(0, 10)]); dayDate.value = next.toISOString().slice(0, 10); days[dayDate.value] = []; renderDays(); scheduleAutoSave(); };
    days[dayDate.value] = days[dayDate.value] || []; renderDays();
    const buildDraft = async () => {
        const bootstrap = await boot;
        const task = field("taskId").selectedOptions[0];
        const serviceDays = Object.keys(days).sort().map(date => ({date, segments: (days[date] || []).filter(segment => isQuarterHour(segment.start) && isQuarterHour(segment.end))}));
        return {
            mobileUuid: currentDraft?.mobileUuid || uuid(),
            mobileRevision: (currentDraft?.mobileRevision || 0) + 1,
            employeeId: bootstrap.employee.id,
            taskId: field("taskId").value || null,
            partnerId: task?.dataset.customerId || null,
            manualCustomerName: field("manualCustomerName").value,
            manualCustomerStreet: field("manualCustomerStreet").value,
            manualCustomerZip: field("manualCustomerZip").value,
            manualCustomerCity: field("manualCustomerCity").value,
            manualContactName: field("manualContactName").value,
            manualContactPhone: field("manualContactPhone").value,
            manualContactEmail: field("manualContactEmail").value,
            serviceDate: serviceDays[0]?.date || field("serviceDate").value,
            countryRateKey: field("countryRateKey").value,
            serviceLocation: field("serviceLocation").value,
            machineNumber: field("machineNumber").value,
            machineType: field("machineType").value,
            overnightCount: Number(field("overnightCount").value || 0),
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
        currentDraft = draft;
        days = Object.fromEntries((draft.days || [{date: draft.serviceDate, segments: draft.segments || []}]).filter(item => item.date).map(item => [item.date, item.segments || []]));
        field("serviceDate").value = draft.serviceDate || "";
        dayDate.value = Object.keys(days).sort()[0] || draft.serviceDate || "";
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
        field("machineNumber").value = draft.machineNumber || "";
        field("machineType").value = draft.machineType || "";
        field("overnightCount").value = draft.overnightCount || 0;
        field("publicNote").value = draft.publicNote || "";
        field("workDescription").value = draft.workDescription || "";
        field("workResult").value = draft.workResult || "";
        renderDays();
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
        form.reset();
        window.nolteStundenbericht?.refreshTimePickers?.();
        field("serviceDate").value = new Date().toISOString().slice(0, 10);
        days = {}; dayDate.value = field("serviceDate").value; renderDays();
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
            days = {}; dayDate.value = field("serviceDate").value; renderDays();
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
    window.nolteStundenbericht = {drafts, loadDraft, newReport, deleteDraft, ensureDraft, getCurrentDraftUuid: () => currentDraft?.mobileUuid || null, getCurrentReport: () => report};
    app.querySelectorAll("[data-new-report]").forEach(button => { button.onclick = newReport; });
    form.addEventListener("input", scheduleAutoSave);
    form.addEventListener("change", scheduleAutoSave);
    window.addEventListener("nolte:report-content-changed", scheduleAutoSave);
    app.querySelector("[data-save]").onclick = async () => {
        try { await saveDraftLocally(); } catch (error) { say(error.message, true); }
    };
    app.querySelector("[data-sync]").onclick = async () => {
        try {
            if (!validateTimeBlocks()) return;
            if (!form.reportValidity()) { form.reportValidity(); return; }
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
            window.dispatchEvent(new Event("nolte:sync-complete"));
            window.dispatchEvent(new Event("nolte:drafts-changed"));
            say("Stundenbericht wurde synchronisiert. Bitte jetzt vom Kunden bestätigen lassen.");
            confirmation.classList.remove("d-none");
            window.dispatchEvent(new CustomEvent("nolte:show-view", {detail: "signature"}));
            confirmation.scrollIntoView({behavior: "smooth"});
        } catch (error) { say(`Synchronisation fehlgeschlagen: ${error.message}`, true); }
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
            confirmation.classList.add("d-none"); say("Kundenbestätigung gespeichert.");
        } catch (error) { say(`Kundenbestätigung fehlgeschlagen: ${error.message}`, true); }
    };
});

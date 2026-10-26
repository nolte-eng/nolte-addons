document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const storageKey = "nolte_stundenbericht_checklist_v1";
    const normalize = items => (Array.isArray(items) ? items : []).map(item => ({...item, checklistUuid: item.checklistUuid || window.nolteUuid(), visibility: item.visibility === "internal" ? "internal" : "customer"}));
    const load = () => { try { return normalize(JSON.parse(localStorage.getItem(storageKey) || "[]")); } catch { return []; } };
    let checklist = load();
    const sections = [...app.querySelectorAll("[data-checklist-kind]")];
    let defaultTemplate = null;
    let importedReport = checklist.length > 0;
    let reportStarted = false;
    let defaultApplied = false;
    const save = () => {
        localStorage.setItem(storageKey, JSON.stringify(checklist));
        window.dispatchEvent(new Event("nolte:report-content-changed"));
    };
    const render = () => {
        for (const section of sections) {
            const list = section.querySelector("[data-checklist-list]");
            list.replaceChildren();
            checklist.filter(item => item.visibility === section.dataset.checklistKind).forEach(item => {
            const row = document.createElement("div");
            row.className = "border-top py-2";
            const header = document.createElement("div"); header.className = "d-flex gap-2 align-items-center";
            const done = document.createElement("input");
            done.type = "checkbox"; done.className = "form-check-input m-0 flex-shrink-0"; done.checked = Boolean(item.checked);
            done.setAttribute("aria-label", `${item.name} erledigt`);
            done.onchange = () => { item.checked = done.checked; save(); };
            const label = document.createElement("input"); label.type = "text"; label.className = "form-control flex-grow-1"; label.value = item.name;
            label.setAttribute("aria-label", "Prüfpunkt bearbeiten");
            label.oninput = () => { item.name = label.value; save(); };
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-link text-danger"; remove.textContent = "Entfernen";
            remove.onclick = () => { checklist = checklist.filter(entry => entry !== item); save(); render(); };
            const note = document.createElement("input"); note.type = "text"; note.className = "form-control mt-2"; note.value = item.note || ""; note.placeholder = "Bemerkung (optional)";
            note.setAttribute("aria-label", `Bemerkung zu ${item.name}`);
            note.oninput = () => { item.note = note.value; save(); };
            header.append(done, label, remove); row.append(header, note); list.append(row);
        });
        }
    };
    const applyDefault = () => {
        if (!reportStarted || importedReport || defaultApplied || !defaultTemplate) return;
        defaultApplied = true;
        const previousCount = checklist.length;
        const names = new Set(checklist.filter(item => item.visibility === "customer").map(item => item.name.trim().toLocaleLowerCase("de")));
        for (const item of defaultTemplate.items) {
            const key = item.name.trim().toLocaleLowerCase("de");
            if (names.has(key)) continue;
            names.add(key);
            checklist.push({checklistUuid: window.nolteUuid(), name: item.name, checked: false, note: item.note || "", visibility: "customer"});
        }
        if (checklist.length !== previousCount) save();
        render();
    };
    for (const section of sections) {
        section.querySelector("[data-checklist-add]").onclick = () => {
        const input = section.querySelector("[data-checklist-name]");
        const name = input.value.trim(); if (!name) return;
        checklist.push({checklistUuid: window.nolteUuid(), name, checked: false, note: "", visibility: section.dataset.checklistKind});
        input.value = ""; save(); render();
        };
    }
    const loadDefault = async () => {
        try {
            const response = await fetch("/nolte_stundenbericht/api/v1/checklist-templates", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {}, id: Date.now()})});
            const data = await response.json();
            if (data.error) throw Error(data.error.message);
            defaultTemplate = (data.result || []).find(template => template.visibility === "customer") || null;
            applyDefault();
            for (const section of sections) {
                section.querySelector("[data-checklist-status]").textContent = defaultTemplate
                    ? "Neue Berichte erhalten die zentrale Vorgabe automatisch. Eigene Prüfpunkte kannst du ergänzen."
                    : "Noch keine zentrale Vorgabe hinterlegt. Eigene Prüfpunkte kannst du ergänzen.";
            }
        } catch {
            for (const section of sections) section.querySelector("[data-checklist-status]").textContent = "Die zentrale Vorgabe konnte nicht geladen werden. Vorhandene und eigene Prüfpunkte bleiben erhalten.";
        }
    };
    let defaultReady = loadDefault();
    const previousFetch = window.fetch;
    window.fetch = async (...args) => {
        if (String(args[0]).includes("/reports/upsert") && args[1]?.body) {
            const request = JSON.parse(args[1].body);
            if (!request.params.payload.checklist) request.params.payload.checklist = checklist;
            args[1] = {...args[1], body: JSON.stringify(request)};
        }
        return previousFetch(...args);
    };
    const clear = () => {
        checklist = []; localStorage.removeItem(storageKey);
        importedReport = false; reportStarted = true; defaultApplied = false;
        sections.forEach(section => {
            section.querySelector("[data-checklist-name]").value = "";
        });
        render();
        // Re-fetch for each new report so centrally changed defaults apply.
        defaultTemplate = null;
        defaultReady = loadDefault();
    };
    window.addEventListener("nolte:new-report", clear);
    window.addEventListener("nolte:view-selected", event => {
        if (event.detail === "home" || importedReport) return;
        reportStarted = true;
        applyDefault();
    });
    // Keep the current report visible after synchronization, but do not carry
    // its checklist into a new form after a page reload.
    window.addEventListener("nolte:sync-complete", () => { importedReport = true; localStorage.removeItem(storageKey); });
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.checklist = {
        // Retain legacy internal entries on round-trip, without displaying or
        // reclassifying them as customer-visible checklist points.
        export: () => checklist.map(item => ({...item})),
        import: items => { importedReport = true; checklist = normalize(items); save(); render(); },
        ready: async () => { await defaultReady; applyDefault(); },
    };
    render();
});

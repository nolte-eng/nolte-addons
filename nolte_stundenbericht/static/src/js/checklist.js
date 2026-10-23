document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const storageKey = "nolte_stundenbericht_checklist_v1";
    const normalize = items => (Array.isArray(items) ? items : []).map(item => ({...item, checklistUuid: item.checklistUuid || window.nolteUuid(), visibility: item.visibility === "internal" ? "internal" : "customer"}));
    const load = () => { try { return normalize(JSON.parse(localStorage.getItem(storageKey) || "[]")); } catch { return []; } };
    let checklist = load();
    const sections = [...app.querySelectorAll("[data-checklist-kind]")];
    const templatesById = new Map();
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
    for (const section of sections) {
        const select = section.querySelector("[data-checklist-template-select]");
        const apply = section.querySelector("[data-checklist-template-apply]");
        select.addEventListener("change", () => { apply.disabled = !select.value; });
        apply.onclick = () => {
            const template = templatesById.get(select.value);
            const visibility = section.dataset.checklistKind;
            if (!template || template.visibility !== visibility) return;
            const names = new Set(checklist.filter(item => item.visibility === visibility).map(item => item.name.trim().toLocaleLowerCase("de")));
            let added = 0;
            for (const item of template.items) {
                const key = item.name.trim().toLocaleLowerCase("de");
                if (names.has(key)) continue;
                names.add(key);
                checklist.push({checklistUuid: window.nolteUuid(), name: item.name, checked: false, note: item.note || "", visibility});
                added += 1;
            }
            save(); render();
            section.querySelector("[data-checklist-status]").textContent = added ? `${added} Prüfpunkte übernommen. Du kannst sie frei bearbeiten.` : "Die Prüfpunkte dieser Vorlage sind bereits enthalten.";
        };
        section.querySelector("[data-checklist-add]").onclick = () => {
        const input = section.querySelector("[data-checklist-name]");
        const name = input.value.trim(); if (!name) return;
        checklist.push({checklistUuid: window.nolteUuid(), name, checked: false, note: "", visibility: section.dataset.checklistKind});
        input.value = ""; save(); render();
        };
    }
    const refreshButton = app.querySelector("[data-checklist-template-refresh]");
    const refreshTemplates = async () => {
        refreshButton.disabled = true;
        try {
            const response = await fetch("/nolte_stundenbericht/api/v1/checklist-templates", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {}, id: Date.now()})});
            const data = await response.json();
            if (data.error) throw Error(data.error.message);
            templatesById.clear();
            for (const template of data.result || []) templatesById.set(String(template.id), template);
            for (const section of sections) {
                const select = section.querySelector("[data-checklist-template-select]");
                const selected = select.value;
                select.replaceChildren();
                const empty = document.createElement("option"); empty.value = ""; empty.textContent = "Ohne Vorlage"; select.append(empty);
                for (const template of templatesById.values()) {
                    if (template.visibility !== section.dataset.checklistKind) continue;
                    const option = document.createElement("option"); option.value = String(template.id); option.textContent = template.name; select.append(option);
                }
                select.value = [...select.options].some(option => option.value === selected) ? selected : "";
                section.querySelector("[data-checklist-template-apply]").disabled = !select.value;
                section.querySelector("[data-checklist-status]").textContent = select.options.length > 1 ? "Optional eine zentrale Vorlage übernehmen oder eigene Prüfpunkte hinzufügen." : "Noch keine zentrale Vorlage für diesen Bereich vorhanden. Eigene Prüfpunkte sind möglich.";
            }
        } catch {
            for (const section of sections) section.querySelector("[data-checklist-status]").textContent = "Vorlagen konnten nicht geladen werden. Eigene Prüfpunkte bleiben möglich.";
        } finally { refreshButton.disabled = false; }
    };
    refreshButton.onclick = refreshTemplates;
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
        sections.forEach(section => {
            section.querySelector("[data-checklist-template-select]").value = "";
            section.querySelector("[data-checklist-template-apply]").disabled = true;
            section.querySelector("[data-checklist-name]").value = "";
        });
        render();
    };
    window.addEventListener("nolte:new-report", clear);
    // Keep the current report visible after synchronization, but do not carry
    // its checklist into a new form after a page reload.
    window.addEventListener("nolte:sync-complete", () => localStorage.removeItem(storageKey));
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.checklist = {
        export: () => checklist.map(item => ({...item})),
        import: items => { checklist = normalize(items); save(); render(); },
    };
    render();
    refreshTemplates();
});

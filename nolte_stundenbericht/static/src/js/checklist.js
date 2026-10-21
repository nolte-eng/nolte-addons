document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const storageKey = "nolte_stundenbericht_checklist_v1";
    const load = () => { try { return JSON.parse(localStorage.getItem(storageKey) || "[]"); } catch { return []; } };
    let checklist = load();
    const save = () => localStorage.setItem(storageKey, JSON.stringify(checklist));
    const list = app.querySelector("[data-checklist-list]");
    const render = () => {
        list.replaceChildren();
        checklist.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "d-flex gap-2 align-items-center border-top py-2";
            const done = document.createElement("input");
            done.type = "checkbox"; done.className = "form-check-input m-0"; done.checked = item.checked;
            done.onchange = () => { item.checked = done.checked; save(); window.dispatchEvent(new Event("nolte:report-content-changed")); };
            const label = document.createElement("span"); label.className = "flex-grow-1"; label.textContent = item.name;
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-link text-danger"; remove.textContent = "Entfernen";
            remove.onclick = () => { checklist.splice(index, 1); save(); render(); window.dispatchEvent(new Event("nolte:report-content-changed")); };
            row.append(done, label, remove); list.append(row);
        });
    };
    app.querySelector("[data-checklist-add]").onclick = () => {
        const input = app.querySelector("[data-checklist-name]");
        const name = input.value.trim(); if (!name) return;
        checklist.push({checklistUuid: window.nolteUuid(), name, checked: false, note: ""});
        input.value = ""; save(); render(); window.dispatchEvent(new Event("nolte:report-content-changed"));
    };
    const previousFetch = window.fetch;
    window.fetch = async (...args) => {
        if (String(args[0]).includes("/reports/upsert") && args[1]?.body) {
            const request = JSON.parse(args[1].body);
            if (!request.params.payload.checklist) request.params.payload.checklist = checklist;
            args[1] = {...args[1], body: JSON.stringify(request)};
        }
        return previousFetch(...args);
    };
    window.addEventListener("nolte:new-report", () => { checklist = []; localStorage.removeItem(storageKey); render(); });
    window.addEventListener("nolte:sync-complete", () => { checklist = []; localStorage.removeItem(storageKey); render(); });
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.checklist = {
        export: () => checklist.map(item => ({...item})),
        import: items => { checklist = (items || []).map(item => ({...item, checklistUuid: item.checklistUuid || window.nolteUuid()})); save(); render(); },
    };
    render();
});

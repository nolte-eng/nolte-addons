document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const target = app?.querySelector("[data-local-drafts]");
    if (!target) return;
    const render = () => {
        const body = target.querySelector(".card-body");
        body.replaceChildren();
        const title = document.createElement("h2"); title.className = "h5 mb-2"; title.textContent = "Entwürfe auf diesem Gerät"; body.append(title);
        const entries = window.nolteStundenbericht?.drafts?.() || [];
        if (!entries.length) { const empty = document.createElement("p"); empty.className = "small text-muted mb-0"; empty.textContent = "Keine lokalen Entwürfe."; body.append(empty); return; }
        entries.forEach(draft => {
            const row = document.createElement("div"); row.className = "d-flex justify-content-between align-items-center border-top py-2";
            const label = document.createElement("span"); label.className = "small"; label.textContent = `${draft.serviceDate || "ohne Datum"} · ${draft.serviceLocation || "Einsatzbericht"}`;
            const actions = document.createElement("div"); actions.className = "d-flex gap-1";
            const button = document.createElement("button"); button.type = "button"; button.className = "btn btn-sm btn-outline-primary"; button.textContent = "Fortsetzen";
            button.onclick = () => window.nolteStundenbericht.loadDraft(draft);
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-outline-danger"; remove.textContent = "Löschen";
            remove.onclick = () => { if (confirm("Diesen lokalen Entwurf mit seinen vorgemerkten Fotos löschen?")) window.nolteStundenbericht.deleteDraft(draft); };
            actions.append(button, remove); row.append(label, actions); body.append(row);
        });
    };
    window.addEventListener("nolte:drafts-changed", render);
    render();
});

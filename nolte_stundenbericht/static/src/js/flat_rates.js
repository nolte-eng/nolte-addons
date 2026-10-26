document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const list = app.querySelector("[data-flat-rate-list]");
    const status = app.querySelector("[data-flat-rate-status]");
    const refresh = app.querySelector("[data-flat-rate-refresh]");
    let catalog = [];
    let selected = new Map();
    const changed = () => window.dispatchEvent(new Event("nolte:report-content-changed"));
    const render = () => {
        list.replaceChildren();
        const options = new Map(catalog.map(item => [item.id, item]));
        for (const [id, item] of selected) if (!options.has(id)) options.set(id, item);
        for (const item of options.values()) {
            const label = document.createElement("label"); label.className = "d-flex gap-3 align-items-center border-top py-3";
            const input = document.createElement("input"); input.type = "checkbox"; input.className = "form-check-input m-0"; input.checked = selected.has(item.id);
            input.onchange = () => { if (input.checked) selected.set(item.id, {id: item.id, name: item.name}); else selected.delete(item.id); changed(); };
            const text = document.createElement("span"); text.textContent = item.name;
            label.append(input, text); list.append(label);
        }
    };
    const load = async () => {
        if (refresh.disabled) return;
        refresh.disabled = true;
        try {
            const response = await fetch("/nolte_stundenbericht/api/v1/flat-rates", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {}})});
            const data = await response.json();
            if (!response.ok || data.error || !Array.isArray(data.result)) throw Error("catalog");
            catalog = data.result;
            status.textContent = catalog.length ? "Gewählte Pauschalen werden einmal pro Einsatzbericht übernommen." : "Noch keine Pauschalen eingerichtet. Verwaltung unter Stundenbericht → Konfiguration → Pauschalen.";
            render();
        } catch {
            status.textContent = "Pauschalen konnten nicht geladen werden. Bereits gespeicherte Auswahlen bleiben erhalten; bitte später aktualisieren.";
        } finally { refresh.disabled = false; }
    };
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.flatRates = {
        export: () => [...selected.values()].map(item => ({...item})),
        import: items => { selected = new Map((Array.isArray(items) ? items : []).filter(item => Number.isInteger(item.id)).map(item => [item.id, {...item}])); render(); },
    };
    window.addEventListener("nolte:new-report", () => { selected.clear(); render(); });
    // Configuration may change while this app remains open in another tab.
    app.querySelectorAll('[data-view-target="flat-rates"]').forEach(link => link.addEventListener("click", load));
    window.addEventListener("nolte:show-view", event => { if (event.detail === "flat-rates") load(); });
    window.addEventListener("focus", load);
    window.addEventListener("online", load);
    refresh.onclick = load;
    load();
});

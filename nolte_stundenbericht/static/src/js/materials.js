document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const storageKey = "nolte_stundenbericht_materials_v1";
    const load = () => { try { return JSON.parse(localStorage.getItem(storageKey) || "[]"); } catch { return []; } };
    let materials = load();
    let selectedProductId = null;
    const save = () => localStorage.setItem(storageKey, JSON.stringify(materials));
    const list = app.querySelector("[data-material-list]");
    const render = () => {
        list.replaceChildren();
        materials.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "d-flex justify-content-between align-items-center border-top py-2";
            const label = document.createElement("span");
            label.textContent = `${item.quantity} ${item.unit} · ${item.name}${item.note ? ` (${item.note})` : ""}`;
            const remove = document.createElement("button");
            remove.className = "btn btn-sm btn-link text-danger";
            remove.type = "button";
            remove.textContent = "Entfernen";
            remove.onclick = () => { materials.splice(index, 1); save(); render(); window.dispatchEvent(new Event("nolte:report-content-changed")); };
            row.append(label, remove);
            list.append(row);
        });
    };
    app.querySelector("[data-material-add]").onclick = () => {
        const name = app.querySelector("[data-material-name]").value.trim();
        if (!name) return;
        materials.push({materialUuid: window.nolteUuid(), productId: selectedProductId, name, quantity: Number(app.querySelector("[data-material-quantity]").value || 0), unit: app.querySelector("[data-material-unit]").value.trim() || "Stk.", note: app.querySelector("[data-material-note]").value.trim()});
        app.querySelector("[data-material-name]").value = "";
        app.querySelector("[data-material-quantity]").value = "1";
        app.querySelector("[data-material-note]").value = "";
        selectedProductId = null;
        save(); render(); window.dispatchEvent(new Event("nolte:report-content-changed"));
    };
    const searchInput = app.querySelector("[data-product-search]");
    const results = app.querySelector("[data-product-results]");
    const search = async () => {
        const query = searchInput.value.trim();
        results.replaceChildren();
        if (query.length < 2) {
            const hint = document.createElement("div");
            hint.className = "list-group-item text-muted";
            hint.textContent = "Bitte mindestens zwei Zeichen eingeben.";
            results.append(hint); results.classList.remove("d-none");
            return;
        }
        const response = await fetch("/nolte_stundenbericht/api/v1/products/search", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {query}})});
        const body = await response.json();
        if (body.error) throw Error(body.error.data?.message || body.error.message);
        results.replaceChildren();
        for (const product of body.result || []) {
            const item = document.createElement("button"); item.type = "button"; item.className = "list-group-item list-group-item-action"; item.textContent = product.name;
            item.onclick = () => { selectedProductId = product.id; app.querySelector("[data-material-name]").value = product.name; searchInput.value = ""; results.classList.add("d-none"); };
            results.append(item);
        }
        if (!results.childElementCount) {
            const empty = document.createElement("div");
            empty.className = "list-group-item text-muted";
            empty.textContent = "Keine passenden Odoo-Artikel gefunden.";
            results.append(empty);
        }
        results.classList.remove("d-none");
    };
    const showSearchError = error => {
        results.replaceChildren();
        const item = document.createElement("div");
        item.className = "list-group-item text-danger";
        item.textContent = `Artikelsuche nicht möglich: ${error.message}`;
        results.append(item); results.classList.remove("d-none");
    };
    app.querySelector("[data-product-search-button]").onclick = () => search().catch(showSearchError);
    searchInput.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); search().catch(() => null); } });
    let searchDelay;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchDelay);
        if (searchInput.value.trim().length < 2) { results.classList.add("d-none"); return; }
        searchDelay = setTimeout(() => search().catch(showSearchError), 350);
    });
    const previousFetch = window.fetch;
    window.fetch = async (...args) => {
        if (String(args[0]).includes("/reports/upsert") && args[1]?.body) {
            const request = JSON.parse(args[1].body);
            if (!request.params.payload.materials) request.params.payload.materials = materials;
            args[1] = {...args[1], body: JSON.stringify(request)};
        }
        return previousFetch(...args);
    };
    window.addEventListener("nolte:new-report", () => { materials = []; localStorage.removeItem(storageKey); render(); });
    window.addEventListener("nolte:sync-complete", () => { materials = []; localStorage.removeItem(storageKey); render(); });
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.materials = {
        export: () => materials.map(item => ({...item})),
        import: items => { materials = (items || []).map(item => ({...item, materialUuid: item.materialUuid || window.nolteUuid()})); selectedProductId = null; save(); render(); },
    };
    render();
});

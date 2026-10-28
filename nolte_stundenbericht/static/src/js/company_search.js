/** @odoo-module **/
document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const input = app?.querySelector("[data-company-search]");
    if (!input) return;
    const results = app.querySelector("[data-company-results]");
    const status = app.querySelector("[data-company-search-status]");
    const clear = app.querySelector("[data-company-clear]");
    const field = name => app.querySelector(`[name="${name}"]`);
    let timer, revision = 0;
    const hideResults = () => { results.replaceChildren(); results.classList.add("d-none"); };
    const refreshSelection = () => {
        clear.classList.toggle("d-none", !field("manualPartnerId").value);
        status.textContent = field("manualPartnerId").value ? "Vorhandene Firma ausgewählt. Ansprechpartner bei Bedarf ergänzen." : "";
    };
    const deselect = () => {
        field("manualPartnerId").value = "";
        refreshSelection();
        window.dispatchEvent(new Event("nolte:report-content-changed"));
    };
    clear.onclick = () => { deselect(); input.value = ""; hideResults(); };
    // Editing copied address data switches to a free-text report instead of
    // silently writing changes to the centrally managed contact.
    for (const name of ["manualCustomerName", "manualCustomerStreet", "manualCustomerZip", "manualCustomerCity"]) {
        field(name).addEventListener("input", () => { if (field("manualPartnerId").value) deselect(); });
    }
    const choose = company => {
        revision++;
        const values = {manualPartnerId: company.id, manualCustomerName: company.name,
            manualCustomerStreet: company.street, manualCustomerZip: company.zip,
            manualCustomerCity: company.city, manualContactName: "",
            manualContactPhone: company.phone, manualContactEmail: company.email};
        for (const [name, value] of Object.entries(values)) field(name).value = value || "";
        input.value = company.name;
        hideResults(); refreshSelection();
        window.dispatchEvent(new Event("nolte:report-content-changed"));
    };
    const search = async () => {
        const query = input.value.trim();
        const requestRevision = ++revision;
        hideResults();
        if (query.length < 2) { status.textContent = "Bitte mindestens zwei Zeichen eingeben."; return; }
        status.textContent = "Firmen werden gesucht …";
        try {
            const response = await fetch("/nolte_stundenbericht/api/v1/companies/search", {
                method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {query}}),
            });
            const data = await response.json();
            if (requestRevision !== revision) return;
            if (data.error) throw Error(data.error.data?.message || data.error.message);
            const companies = data.result || [];
            for (const company of companies) {
                const button = document.createElement("button");
                button.type = "button"; button.className = "list-group-item list-group-item-action";
                button.textContent = [company.name, company.street, [company.zip, company.city].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
                button.onclick = () => choose(company);
                results.append(button);
            }
            results.classList.toggle("d-none", !companies.length);
            status.textContent = companies.length ? "Firma auswählen, um die hinterlegten Daten zu übernehmen." : "Keine Firma gefunden. Du kannst die Daten unten frei eingeben.";
        } catch (error) {
            if (requestRevision !== revision) return;
            status.textContent = `Firmensuche nicht verfügbar: ${error.message}. Freie Eingabe bleibt möglich.`;
        }
    };
    input.addEventListener("input", event => {
        // Searching alone is not a report edit and must not create an empty draft.
        event.stopPropagation();
        revision++; hideResults(); clearTimeout(timer); timer = setTimeout(search, 300);
    });
    input.addEventListener("change", event => event.stopPropagation());
    input.addEventListener("keydown", event => {
        if (event.key === "Enter") { event.preventDefault(); clearTimeout(timer); search(); }
        if (event.key === "Escape") { revision++; clearTimeout(timer); hideResults(); }
    });
    for (const event of ["nolte:new-report", "nolte:draft-loaded"]) window.addEventListener(event, () => {
        revision++; clearTimeout(timer); input.value = ""; hideResults(); refreshSelection();
    });
    refreshSelection();
});

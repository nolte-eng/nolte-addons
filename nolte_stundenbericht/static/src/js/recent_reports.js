document.addEventListener("DOMContentLoaded", async () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const target = app?.querySelector("[data-recent-reports]");
    if (!target) return;
    try {
        const response = await fetch("/nolte_stundenbericht/api/v1/reports/recent", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {}}),
        });
        const reports = (await response.json()).result || [];
        const body = target.querySelector(".card-body");
        body.replaceChildren();
        const title = document.createElement("h2"); title.className = "h5 mb-2"; title.textContent = "Letzte Berichte"; body.append(title);
        if (!reports.length) { const empty = document.createElement("p"); empty.className = "small text-muted mb-0"; empty.textContent = "Noch keine synchronisierten Berichte."; body.append(empty); return; }
        reports.forEach(report => {
            const row = document.createElement("div"); row.className = "border-top py-2 d-flex justify-content-between gap-2 small";
            const left = document.createElement("span"); left.textContent = `${report.date} · ${report.customer}`;
            const right = document.createElement("span"); right.className = "text-muted text-end"; right.textContent = `${report.number} · ${report.state}`;
            row.append(left, right); body.append(row);
        });
    } catch {
        target.querySelector(".card-body").lastElementChild.textContent = "Im Offline-Modus werden die letzten Berichte nicht geladen.";
    }
});

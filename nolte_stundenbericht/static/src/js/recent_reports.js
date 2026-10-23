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
            const row = document.createElement("div");
            row.className = "border-top py-2 d-flex align-items-center justify-content-between gap-2 small";
            const left = document.createElement("span"); left.textContent = `${report.date} · ${report.customer}`;
            const actions = document.createElement("div"); actions.className = "d-flex align-items-center gap-2";
            const details = document.createElement("span"); details.className = "text-muted text-end"; details.textContent = `${report.number} · ${report.state}`;
            if (report.signatureManageUrl) {
                const manage = document.createElement("a"); manage.className = "btn btn-sm btn-outline-primary";
                manage.href = report.signatureManageUrl; manage.target = "_blank"; manage.rel = "noopener"; manage.textContent = "Unterschriftsanfrage";
                actions.append(manage);
            }
            if (report.canLoadData) {
                const load = document.createElement("button"); load.type = "button"; load.className = "btn btn-sm btn-outline-primary"; load.textContent = "Daten laden";
                load.onclick = async () => {
                    load.disabled = true;
                    try {
                        const response = await fetch("/nolte_stundenbericht/api/v1/reports/load", {
                            method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {report_id: report.id}}),
                        });
                        const result = await response.json();
                        if (result.error) throw Error(result.error.data?.message || result.error.message);
                        await window.nolteStundenbericht.loadServerReport(result.result);
                    } catch (error) {
                        const message = app.querySelector("[data-message]");
                        message.textContent = `Berichtsdaten konnten nicht geladen werden: ${error.message}`;
                        message.className = "alert alert-danger";
                    } finally { load.disabled = false; }
                };
                actions.append(load);
            }
            const pdf = document.createElement("a"); pdf.className = "btn btn-sm btn-outline-secondary"; pdf.href = report.url; pdf.target = "_blank"; pdf.rel = "noopener"; pdf.textContent = "PDF";
            actions.append(details, pdf); row.append(left, actions); body.append(row);
        });
    } catch {
        target.querySelector(".card-body").lastElementChild.textContent = "Im Offline-Modus werden die letzten Berichte nicht geladen.";
    }
});

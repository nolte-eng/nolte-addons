document.addEventListener("DOMContentLoaded", () => {
    const link = document.querySelector("[data-request-online-signature]");
    if (!link) return;
    const pending = document.querySelector("[data-online-signature-pending]");
    const manage = document.querySelector("[data-online-signature-manage]");
    const localSignature = document.querySelector("[data-local-customer-signature]");
    let requestedUuid = null;
    let updatedReport = null;
    const refresh = () => {
        const original = window.nolteStundenbericht?.getCurrentReport?.();
        const report = updatedReport?.mobileUuid === original?.mobileUuid ? updatedReport : original;
        const available = report?.requestSignatureUrl && ["draft", "returned"].includes(report.state);
        link.classList.toggle("d-none", !available);
        if (available) link.href = report.requestSignatureUrl;
        const remote = report && !["draft", "returned"].includes(report.state);
        localSignature.classList.toggle("d-none", Boolean(remote));
        pending.classList.toggle("d-none", !remote);
        pending.textContent = report?.state === "awaiting_signature"
            ? "Kundenbestätigung ausstehend. Bitte die vorbereitete E-Mail senden. Die Fassung ist gesperrt; für Änderungen oder eine neue Anfrage die alte Anfrage im Backend widerrufen."
            : "Die Kundenbestätigung wurde gespeichert. Den aktuellen Bericht kannst du im Backend öffnen.";
        manage.classList.toggle("d-none", !remote);
        if (remote) manage.href = report.signatureManageUrl;
    };
    link.addEventListener("click", () => { requestedUuid = window.nolteStundenbericht?.getCurrentReport?.()?.mobileUuid; });
    window.addEventListener("focus", async () => {
        if (!requestedUuid || requestedUuid !== window.nolteStundenbericht?.getCurrentReport?.()?.mobileUuid) return;
        try {
            const response = await fetch("/nolte_stundenbericht/api/v1/reports/get", {
                method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {mobile_uuid: requestedUuid}}),
            });
            const data = await response.json();
            if (data.result) { updatedReport = data.result; refresh(); }
        } catch { /* Offline: retain the last known state, never claim success. */ }
    });
    window.addEventListener("nolte:sync-complete", refresh);
    window.addEventListener("nolte:new-report", () => { requestedUuid = null; updatedReport = null; refresh(); });
    refresh();
});

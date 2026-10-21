document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const button = app?.querySelector("[data-copy-previous]");
    if (!button) return;
    const input = selector => app.querySelector(selector);
    const rpc = (url, params) => fetch(url, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params})}).then(response => response.json()).then(response => { if (response.error) throw Error(response.error.data?.message || response.error.message); return response.result; });
    const set = (segment, start, end, kilometers) => {
        const item = segment;
        if (input(start)) input(start).value = item?.start || "";
        if (input(end)) input(end).value = item?.end || "";
        if (kilometers && input(kilometers)) input(kilometers).value = item?.kilometers ?? "";
    };
    button.onclick = async () => {
        const date = input('[name="serviceDate"]').value;
        if (!date) return;
        try {
            const report = await rpc("/nolte_stundenbericht/api/v1/reports/previous-template", {service_date: date, task_id: input('[name="taskId"]').value || null});
            if (!report) { alert("Für diesen Auftrag gibt es keinen früheren bestätigten Bericht."); return; }
            const segment = type => report.segments.find(item => item.type === type);
            input('[name="serviceLocation"]').value = report.serviceLocation || "";
            input('[name="machineNumber"]').value = report.machineNumber || "";
            input('[name="machineType"]').value = report.machineType || "";
            input('[name="overnightCount"]').value = report.overnightCount || 0;
            set(segment("outbound_travel"), '[name="outboundStart"]', '[name="outboundEnd"]', '[name="outboundKm"]');
            set(segment("work"), '[name="workStart"]', '[name="workEnd"]');
            set(segment("break"), '[name="breakStart"]', '[name="breakEnd"]');
            set(segment("return_travel"), "[data-return-early-start]", "[data-return-early-end]", "[data-return-early-km]");
            window.nolteStundenbericht?.refreshTimePickers?.();
            app.querySelector("[data-message]").textContent = `Zeiten aus dem Bericht vom ${report.sourceDate} übernommen. Bitte prüfen.`;
        } catch (error) { app.querySelector("[data-message]").textContent = `Übernahme fehlgeschlagen: ${error.message}`; }
    };
});

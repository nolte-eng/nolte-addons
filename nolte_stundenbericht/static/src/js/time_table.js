document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const body = app?.querySelector("[data-time-table-body]");
    if (!body) return;
    const value = selector => app.querySelector(selector)?.value || "";
    const duration = (start, end) => {
        if (!start || !end) return "";
        const [sh, sm] = start.split(":").map(Number), [eh, em] = end.split(":").map(Number);
        let minutes = eh * 60 + em - sh * 60 - sm; if (minutes < 0) minutes += 24 * 60;
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")} h`;
    };
    const render = () => {
        const entries = [
            ["Hinfahrt", value('[name="outboundStart"]'), value('[name="outboundEnd"]'), value('[name="outboundKm"]')],
            ["Arbeit", value('[name="workStart"]'), value('[name="workEnd"]'), ""],
            ["Pause", value('[name="breakStart"]'), value('[name="breakEnd"]'), ""],
            ["Rückfahrt", value("[data-return-early-start]"), value("[data-return-early-end]"), value("[data-return-early-km]")],
        ].filter(([, start, end]) => start && end);
        body.replaceChildren();
        if (!entries.length) { const row = document.createElement("tr"), cell = document.createElement("td"); cell.colSpan = 5; cell.className = "text-muted"; cell.textContent = "Noch keine vollständigen Zeitblöcke erfasst."; row.append(cell); body.append(row); return; }
        entries.forEach(([type, start, end, kilometers]) => {
            const row = document.createElement("tr");
            [type, start, end, duration(start, end), kilometers ? `${kilometers}` : ""].forEach((item, index) => { const cell = document.createElement("td"); cell.textContent = item; if (index === 4) cell.className = "text-end"; row.append(cell); });
            body.append(row);
        });
    };
    app.addEventListener("input", render);
    render();
});

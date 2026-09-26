document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const box = app?.querySelector("[data-confirmation-preview]");
    const confirmation = app?.querySelector("[data-confirmation]");
    if (!box || !confirmation) return;
    const value = selector => app.querySelector(selector)?.value || "–";
    const add = (label, content) => {
        const row = document.createElement("div");
        const strong = document.createElement("strong"); strong.textContent = `${label}: `;
        const text = document.createElement("span"); text.textContent = content;
        row.append(strong, text); box.append(row);
    };
    const render = () => {
        box.replaceChildren();
        const report = window.nolteStundenbericht?.getCurrentReport?.();
        const task = report?.taskName || report?.customerName || app.querySelector('[name="taskId"]')?.selectedOptions[0]?.textContent || "Ohne Zuordnung";
        add("Einsatz", task);
        add("Datum", report?.serviceDate || value('[name="serviceDate"]'));
        add("Einsatzort", report?.serviceLocation || value('[name="serviceLocation"]'));
        const labels = {outbound_travel: "Hinfahrt", work: "Arbeit", return_travel: "Rückfahrt", break: "Pause"};
        const segments = (report?.members || []).flatMap(member => member.segments || []);
        if (segments.length) {
            for (const segment of segments) add(labels[segment.type] || segment.type, `${segment.start} – ${segment.end}${segment.type.includes("travel") && segment.kilometers ? ` · ${segment.kilometers} km` : ""}`);
        } else {
            add("Zeiten", "Noch keine Zeiten erfasst.");
        }
    };
    new MutationObserver(() => { if (!confirmation.classList.contains("d-none")) render(); }).observe(confirmation, {attributes: true, attributeFilter: ["class"]});
});

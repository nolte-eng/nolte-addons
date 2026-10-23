document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const box = app?.querySelector("[data-confirmation-preview]");
    const confirmation = app?.querySelector("[data-confirmation]");
    if (!box || !confirmation) return;
    const frame = box.querySelector("[data-confirmation-preview-frame]");
    const status = box.querySelector("[data-confirmation-preview-status]");
    const openPdf = box.querySelector("[data-confirmation-pdf-open]");
    const buttons = [...box.querySelectorAll("[data-confirmation-format]")];
    // Mobile PDF viewers may show only page one inside an iframe. The same
    // template as scrollable HTML is more reliable; the PDF remains available.
    const mobileViewer = /iPad|iPhone|iPod|Android/i.test(navigator.userAgent)
        || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    let format = mobileViewer || navigator.pdfViewerEnabled === false ? "html" : "pdf";
    let source = "";
    const render = () => {
        const report = window.nolteStundenbericht?.getCurrentReport?.();
        const pdfUrl = report?.previewPdfUrl;
        const htmlUrl = report?.previewHtmlUrl;
        const url = format === "html" ? htmlUrl || pdfUrl : pdfUrl;
        buttons.forEach(button => {
            const active = button.dataset.confirmationFormat === format;
            button.setAttribute("aria-pressed", String(active));
            button.classList.toggle("active", active);
            button.disabled = !report || (button.dataset.confirmationFormat === "html" && !htmlUrl);
        });
        openPdf.classList.toggle("d-none", !pdfUrl);
        if (pdfUrl) openPdf.href = pdfUrl;
        frame.classList.toggle("d-none", !url);
        if (!url) {
            frame.removeAttribute("src");
            source = "";
            status.textContent = "Die Vorschau erscheint nach der Synchronisation.";
            return;
        }
        if (source !== url) {
            source = url;
            frame.src = url;
        }
        status.textContent = format === "html"
            ? "Gleicher Aufbau und Inhalt wie im Kunden-PDF. Bitte den gesamten Bericht vor der Unterschrift prüfen."
            : "Bitte den gesamten Bericht vor der Unterschrift prüfen. Falls die PDF-Anzeige leer bleibt, wähle „Ansicht wie PDF“.";
    };
    buttons.forEach(button => button.addEventListener("click", () => {
        format = button.dataset.confirmationFormat;
        render();
    }));
    new MutationObserver(() => { if (!confirmation.classList.contains("d-none")) render(); }).observe(confirmation, {attributes: true, attributeFilter: ["class"]});
    window.addEventListener("nolte:sync-complete", render);
    if (!confirmation.classList.contains("d-none")) render();
});

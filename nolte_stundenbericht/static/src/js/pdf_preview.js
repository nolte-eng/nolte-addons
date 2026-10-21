document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    const panel = app?.querySelector("[data-pdf-preview]");
    const link = app?.querySelector("[data-pdf-link]");
    if (!panel || !link) return;
    const previousFetch = window.fetch;
    window.fetch = async (...args) => {
        const confirming = String(args[0]).includes("/reports/customer-confirm");
        const response = await previousFetch(...args);
        if (!confirming || !response.ok) return response;
        const body = await response.clone().json().catch(() => null);
        const url = body?.result?.customerPdfUrl;
        if (url) {
            link.href = url;
            panel.querySelector("[data-pdf-title]").textContent = "Kundenbericht bestätigt";
            panel.querySelector("[data-pdf-description]").textContent = "Die PDF-Fassung ist festgeschrieben.";
            panel.classList.remove("d-none");
            panel.scrollIntoView({behavior: "smooth"});
        }
        return response;
    };
});

/** @odoo-module **/
document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const select = name => {
        app.querySelectorAll("[data-report-view]").forEach(section => section.classList.toggle("ns-view-hidden", section.dataset.reportView !== name));
        app.querySelectorAll("[data-view-target]").forEach(link => link.classList.toggle("ns-nav-active", link.dataset.viewTarget === name));
        sessionStorage.setItem("nolte-stundenbericht-view", name);
        app.querySelector(".ns-main")?.scrollTo({top: 0, behavior: "smooth"});
        window.dispatchEvent(new CustomEvent("nolte:view-selected", {detail: name}));
    };
    app.querySelectorAll("[data-view-target]").forEach(link => link.addEventListener("click", event => { event.preventDefault(); select(link.dataset.viewTarget); }));
    window.addEventListener("nolte:show-view", event => select(event.detail));
    const previousView = sessionStorage.getItem("nolte-stundenbericht-view") || "home";
    // A reload has no loaded report yet. Never transfer an empty form merely
    // because Unterschrift was the last tab in the previous page instance.
    select(previousView === "signature" ? "home" : previousView);
});

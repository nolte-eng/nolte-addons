document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const minutes = value => {
        if (!value) return null;
        const [hour, minute] = value.split(":").map(Number);
        return hour * 60 + minute;
    };
    const duration = (start, end) => {
        const from = minutes(start), to = minutes(end);
        if (from === null || to === null) return 0;
        return (to >= from ? to : to + 24 * 60) - from;
    };
    const text = value => {
        const hours = Math.floor(value / 60), mins = value % 60;
        return `${hours}:${String(mins).padStart(2, "0")} h`;
    };
    const value = selector => app.querySelector(selector)?.value || "";
    const update = () => {
        const work = duration(value('[name="workStart"]'), value('[name="workEnd"]'));
        const travel = duration(value('[name="outboundStart"]'), value('[name="outboundEnd"]'))
            + duration(value('[data-return-early-start]'), value('[data-return-early-end]'));
        const pause = duration(value('[name="breakStart"]'), value('[name="breakEnd"]'));
        app.querySelector("[data-summary-work]").textContent = text(work);
        app.querySelector("[data-summary-travel]").textContent = text(travel);
        app.querySelector("[data-summary-break]").textContent = text(pause);
        app.querySelector("[data-summary-total]").textContent = text(Math.max(0, work + travel - pause));
    };
    app.addEventListener("input", update);
    update();
});

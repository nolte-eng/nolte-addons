/** @odoo-module **/
// Native iOS time fields always offer every minute.  The report is billed in
// quarter hours, so use two compact select boxes with only valid values.
document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;

    const pickers = [];
    const option = (value, label = value) => {
        const node = document.createElement("option");
        node.value = value;
        node.textContent = label;
        return node;
    };
    const setPickerValue = picker => {
        const value = picker.input.value || "";
        const [hour = "", minute = ""] = value.split(":");
        picker.hour.value = hour;
        picker.minute.value = minute;
    };
    const refresh = () => pickers.forEach(setPickerValue);

    app.querySelectorAll('input[type="time"]').forEach(input => {
        const required = input.required;
        const wrapper = document.createElement("div");
        wrapper.className = "d-flex gap-2 ns-quarter-hour-picker";
        const hour = document.createElement("select");
        const minute = document.createElement("select");
        hour.className = minute.className = "form-select";
        hour.setAttribute("aria-label", "Stunde");
        minute.setAttribute("aria-label", "Minute");
        hour.append(option("", "Stunde"));
        minute.append(option("", "Minute"));
        for (let value = 0; value < 24; value += 1) hour.append(option(String(value).padStart(2, "0")));
        ["00", "15", "30", "45"].forEach(value => minute.append(option(value)));
        hour.required = minute.required = required;
        input.required = false;
        input.type = "hidden";
        input.insertAdjacentElement("afterend", wrapper);
        wrapper.append(hour, minute);
        const picker = {input, hour, minute};
        pickers.push(picker);
        const update = () => {
            input.value = hour.value && minute.value ? `${hour.value}:${minute.value}` : "";
            input.dispatchEvent(new Event("input", {bubbles: true}));
            input.dispatchEvent(new Event("change", {bubbles: true}));
        };
        hour.addEventListener("change", update);
        minute.addEventListener("change", update);
        setPickerValue(picker);
    });
    window.nolteStundenbericht = window.nolteStundenbericht || {};
    window.nolteStundenbericht.refreshTimePickers = refresh;
    window.addEventListener("nolte:new-report", refresh);
});

/** Compact, keyboard-accessible destination picker for a complete work day. */
window.nolteDayCopy = {
    open({date, employeeName, employees, onNext, onEmployees}) {
        const dialog = document.createElement("dialog");
        dialog.className = "ns-day-copy-dialog border-0 rounded shadow p-4";
        dialog.style.cssText = "width:min(92vw,520px);max-height:90vh;overflow:auto";
        dialog.setAttribute("aria-labelledby", "ns-day-copy-title");
        const title = document.createElement("h2"); title.className = "h5"; title.id = "ns-day-copy-title";
        title.textContent = "Tag kopieren …";
        const source = document.createElement("p"); source.className = "text-muted small";
        source.textContent = `${employeeName} · ${new Date(`${date}T12:00:00`).toLocaleDateString("de-DE")}`;
        const next = document.createElement("button"); next.type = "button"; next.className = "btn btn-outline-primary w-100 mb-3";
        next.textContent = "Auf den Folgetag kopieren";
        const status = document.createElement("p"); status.className = "small mt-3 mb-0 d-none"; status.setAttribute("role", "status");
        const finish = result => {
            if (result.success) dialog.close();
            else { status.textContent = result.message; status.classList.remove("d-none"); }
        };
        next.onclick = () => finish(onNext());
        dialog.append(title, source, next);
        if (employees.length) {
            const heading = document.createElement("h3"); heading.className = "h6 border-top pt-3";
            heading.textContent = "An andere Mitarbeiter kopieren";
            const hint = document.createElement("p"); hint.className = "small text-muted";
            hint.textContent = "Mehrfachauswahl möglich. Vorhandene Zeiten werden nicht überschrieben. Übernachtungen werden nicht kopiert.";
            const choices = document.createElement("div"); choices.style.cssText = "max-height:26vh;overflow:auto";
            const selected = new Set();
            const copy = document.createElement("button"); copy.type = "button"; copy.className = "btn btn-primary w-100 mt-3";
            copy.textContent = "An ausgewählte Mitarbeiter kopieren"; copy.disabled = true;
            for (const employee of employees) {
                const label = document.createElement("label"); label.className = "d-flex align-items-center gap-2 border-bottom py-3";
                const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.className = "form-check-input m-0";
                checkbox.onchange = () => {
                    if (checkbox.checked) selected.add(String(employee.id)); else selected.delete(String(employee.id));
                    copy.disabled = selected.size === 0;
                };
                const name = document.createElement("span"); name.textContent = employee.name;
                label.append(checkbox, name); choices.append(label);
            }
            copy.onclick = () => finish(onEmployees([...selected]));
            dialog.append(heading, hint, choices, copy);
        }
        const close = document.createElement("button"); close.type = "button"; close.className = "btn btn-outline-secondary w-100 mt-3";
        close.textContent = "Schließen"; close.onclick = () => dialog.close();
        dialog.append(status, close);
        dialog.addEventListener("close", () => dialog.remove());
        document.body.append(dialog); dialog.showModal();
    },
};

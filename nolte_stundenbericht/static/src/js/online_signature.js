document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-online-signature]");
    if (!form) return;
    const canvas = form.querySelector("canvas");
    const context = canvas.getContext("2d");
    const status = form.querySelector("[data-signature-status]");
    let drawing = false, signed = false, last;
    const point = event => {
        const bounds = canvas.getBoundingClientRect();
        return {x: (event.clientX - bounds.left) * canvas.width / bounds.width, y: (event.clientY - bounds.top) * canvas.height / bounds.height};
    };
    canvas.addEventListener("pointerdown", event => {
        event.preventDefault(); drawing = true; last = point(event); canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
        if (!drawing) return;
        event.preventDefault();
        const next = point(event);
        context.lineWidth = 3; context.lineCap = "round"; context.strokeStyle = "#172b3f";
        context.beginPath(); context.moveTo(last.x, last.y); context.lineTo(next.x, next.y); context.stroke();
        signed = true; last = next;
    });
    const stop = () => { drawing = false; };
    canvas.addEventListener("pointerup", stop); canvas.addEventListener("pointercancel", stop);
    form.querySelector("[data-online-signature-clear]").addEventListener("click", () => {
        context.clearRect(0, 0, canvas.width, canvas.height); signed = false;
    });
    form.addEventListener("submit", event => {
        if (!signed) {
            event.preventDefault(); status.textContent = "Bitte zuerst Ihre Unterschrift zeichnen."; return;
        }
        form.querySelector("[data-signature-value]").value = canvas.toDataURL("image/png");
        form.querySelector("[data-online-signature-submit]").disabled = true;
        status.textContent = "Ihre Bestätigung wird gespeichert. Bitte warten …";
    });
});

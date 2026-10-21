/** @odoo-module **/
document.addEventListener("DOMContentLoaded", () => {
    const panel = document.querySelector("[data-return-trip]");
    if (!panel) return;
    const storageKey = "nolte-stundenbericht-confirmed-report";
    const message = document.querySelector("[data-message]");
    const mainForm = document.querySelector("[data-report-form]");
    const say = (text, error=false) => { message.textContent=text; message.className=`alert ${error ? "alert-danger" : "alert-info"}`; };
    const show = report => { if (report && ["customer_confirmed", "internally_amended"].includes(report.state)) panel.classList.remove("d-none"); };
    const getStored = () => JSON.parse(sessionStorage.getItem(storageKey) || "null");
    show(getStored());
    // The optional return trip belongs to the normal time-and-travel section.
    // If it is not known yet, it can still be added in the internal panel.
    const earlyStart = mainForm.querySelector("[data-return-early-start]");
    const earlyEnd = mainForm.querySelector("[data-return-early-end]");
    const earlyKm = mainForm.querySelector("[data-return-early-km]");
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
        if (String(args[0]).includes("/reports/upsert") && args[1]?.body) {
            const request = JSON.parse(args[1].body);
            const start = earlyStart?.value;
            const end = earlyEnd?.value;
            if (start && end && !request.params.payload.segments.some(segment => segment.type === "return_travel" && !segment.internalOnly)) request.params.payload.segments.push({segmentUuid:window.nolteUuid(),type:"return_travel",start,end,kilometers:Number(earlyKm?.value || 0),internalOnly:false});
            args[1] = {...args[1], body:JSON.stringify(request)};
        }
        const response = await originalFetch(...args);
        if (String(args[0]).includes("/reports/customer-confirm")) {
            try {
                const body = await response.clone().json();
                if (body.result) { sessionStorage.setItem(storageKey, JSON.stringify(body.result)); show(body.result); }
            } catch (_) { /* normal API error is handled by the main app */ }
        }
        return response;
    };
    panel.querySelector("[data-return-save]").addEventListener("click", async () => {
        const report = getStored();
        const start = panel.querySelector("[data-return-start]").value;
        const end = panel.querySelector("[data-return-end]").value;
        const kilometers = Number(panel.querySelector("[data-return-km]").value || 0);
        if (!report || !start || !end) return say("Bitte Beginn und Ende der Rückfahrt eingeben.", true);
        try {
            const response = await originalFetch("/nolte_stundenbericht/api/v1/reports/internal-amendment", {
                method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"},
                body:JSON.stringify({jsonrpc:"2.0",method:"call",id:Date.now(),params:{mobile_uuid:report.mobileUuid,expected_server_revision:report.serverRevision,payload:{segments:[{segmentUuid:window.nolteUuid(),type:"return_travel",start,end,kilometers,internalOnly:true}]}}}),
            });
            const body = await response.json();
            if (body.error) throw Error(body.error.data?.message || body.error.message);
            sessionStorage.setItem(storageKey, JSON.stringify(body.result));
            say("Rückfahrt wurde intern ergänzt.");
        } catch (error) { say(`Rückfahrt konnte nicht gespeichert werden: ${error.message}`, true); }
    });
});

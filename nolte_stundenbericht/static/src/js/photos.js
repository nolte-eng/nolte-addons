document.addEventListener("DOMContentLoaded", () => {
    const app = document.querySelector("#nolte-stundenbericht-mobile");
    if (!app) return;
    const inputs = [...app.querySelectorAll("[data-photo-input]")];
    const status = app.querySelector("[data-photo-status]");
    const preview = app.querySelector("[data-photo-preview]");
    const read = file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
    const database = new Promise((resolve, reject) => {
        const open = indexedDB.open("nolte_stundenbericht_offline", 1);
        open.onupgradeneeded = () => open.result.createObjectStore("photos", {keyPath: "id"});
        open.onsuccess = () => resolve(open.result);
        open.onerror = () => reject(open.error);
    });
    const transaction = async (mode, action) => {
        const db = await database;
        return new Promise((resolve, reject) => {
            const request = action(db.transaction("photos", mode).objectStore("photos"));
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    };
    let activeDraftUuid = window.nolteStundenbericht?.getCurrentDraftUuid?.() || null;
    const allPhotos = () => transaction("readonly", store => store.getAll());
    const queued = async (draftUuid = activeDraftUuid) => {
        const entries = await allPhotos();
        return draftUuid ? entries.filter(photo => photo.draftUuid === draftUuid || !photo.draftUuid) : [];
    };
    const save = item => transaction("readwrite", store => store.put(item));
    const remove = id => transaction("readwrite", store => store.delete(id));
    const updateStatus = async message => {
        const entries = await queued();
        status.textContent = message || (entries.length ? `${entries.length} Foto(s) für diesen Entwurf vorgemerkt.` : "Noch keine Fotos für diesen Entwurf ausgewählt.");
    };
    const render = async () => {
        const entries = await queued();
        preview.replaceChildren();
        entries.forEach(photo => {
            const cell = document.createElement("div"); cell.className = "col-6";
            const image = document.createElement("img"); image.src = photo.data; image.alt = photo.name; image.className = "img-fluid rounded border";
            const removeButton = document.createElement("button"); removeButton.type = "button"; removeButton.className = "btn btn-sm btn-outline-danger w-100 mt-1"; removeButton.textContent = "Entfernen";
            removeButton.onclick = async () => { await remove(photo.id); await render(); await updateStatus(); };
            cell.append(image, removeButton); preview.append(cell);
        });
    };
    const addSelectedPhotos = async input => {
        try {
            activeDraftUuid = await window.nolteStundenbericht?.ensureDraft?.();
            if (!activeDraftUuid) throw new Error("Kein Entwurf verfügbar");
            for (const file of [...input.files]) await save({id: window.nolteUuid(), draftUuid: activeDraftUuid, name: file.name || "Einsatzfoto.jpg", data: await read(file)});
            input.value = "";
            await updateStatus();
            await render();
            window.dispatchEvent(new Event("nolte:report-content-changed"));
        } catch { status.textContent = "Fotos konnten nicht lokal gespeichert werden."; }
    };
    inputs.forEach(input => { input.onchange = () => addSelectedPhotos(input); });
    const previousFetch = window.fetch;
    window.fetch = async (...args) => {
        const isUpsert = String(args[0]).includes("/reports/upsert");
        const response = await previousFetch(...args);
        if (!isUpsert || !response.ok) return response;
        const body = await response.clone().json().catch(() => null);
        const mobileUuid = body?.result?.mobileUuid;
        const entries = await queued(mobileUuid);
        if (!mobileUuid || !entries.length) return response;
        try {
            for (const photo of entries) {
                const upload = await previousFetch("/nolte_stundenbericht/api/v1/reports/photo-upload", {
                    method: "POST", headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({jsonrpc: "2.0", method: "call", id: Date.now(), params: {mobile_uuid: mobileUuid, filename: photo.name, data: photo.data}}),
                });
                const uploadBody = await upload.json().catch(() => null);
                if (!upload.ok || uploadBody?.error) throw new Error("upload failed");
                await remove(photo.id);
            }
            await updateStatus("Fotos wurden hochgeladen.");
            await render();
        } catch { status.textContent = "Fotos bleiben vorgemerkt und werden beim nächsten Synchronisieren erneut versucht."; }
        return response;
    };
    window.addEventListener("nolte:draft-loaded", async () => { activeDraftUuid = window.nolteStundenbericht?.getCurrentDraftUuid?.() || null; await updateStatus(); await render(); });
    window.addEventListener("nolte:new-report", async () => { activeDraftUuid = null; await updateStatus(); await render(); });
    window.addEventListener("nolte:draft-deleted", async event => {
        for (const photo of await allPhotos()) if (photo.draftUuid === event.detail.mobileUuid) await remove(photo.id);
        await updateStatus(); await render();
    });
    Promise.all([updateStatus(), render()]).catch(() => { status.textContent = "Offline-Fotos sind auf diesem Gerät nicht verfügbar."; });
});

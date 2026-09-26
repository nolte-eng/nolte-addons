import json
from odoo import http, _
from odoo.exceptions import AccessError
from odoo.http import request

class NolteStundenberichtMobile(http.Controller):
    @http.route("/my/stundenbericht", type="http", auth="user", website=True, sitemap=False)
    def mobile_page(self, **kwargs):
        if not request.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(_("Sie sind nicht für den mobilen Stundenbericht freigeschaltet."))
        response = request.render("nolte_stundenbericht.mobile_page_v2")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    @http.route("/nolte_stundenbericht/manifest.webmanifest", type="http", auth="public", methods=["GET"])
    def manifest(self):
        return request.make_response(json.dumps({"name":"Nolte Stundenbericht","short_name":"Stundenbericht","start_url":"/my/stundenbericht?v=23","display":"standalone","background_color":"#ffffff","theme_color":"#183b56"}), headers=[("Content-Type", "application/manifest+json"), ("Cache-Control", "no-cache")])

    @http.route("/nolte_stundenbericht/service-worker.js", type="http", auth="public", methods=["GET"])
    def service_worker(self):
        script = "const C='nolte-stundenbericht-v23';self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.add('/my/stundenbericht?v=23')).then(()=>self.skipWaiting()).catch(()=>self.skipWaiting())));self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('nolte-stundenbericht-')&&k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{if(r.ok){let x=r.clone();caches.open(C).then(c=>c.put(e.request,x));}return r;}).catch(()=>caches.match(e.request).then(r=>r||caches.match('/my/stundenbericht?v=23'))));});"
        return request.make_response(script, headers=[("Content-Type", "application/javascript"), ("Service-Worker-Allowed", "/"), ("Cache-Control", "no-cache")])

// La Jefatura Suite — Nexus CRM browser bridge (PATH B, no repo required)
//
// WHY THIS EXISTS
//   Nexus CRM (nexus-crm-global.ai.studio) persists everything in IndexedDB.
//   There is no server DB to "extract results" from. This snippet runs INSIDE
//   the CRM tab, reads its Dexie/IndexedDB store, and POSTs deltas to Mission
//   Control so the CEO console + PDF reports see the real pipeline.
//
// HOW TO USE
//   1. Fill MC_ENDPOINT below (the cloudflared tunnel URL or http://localhost:8090).
//   2. In Nexus: paste into DevTools console once, OR install as a userscript
//      (Violentmonkey/Tampermonkey) with @match nexus-crm-global.ai.studio/*.
//   3. It syncs every 5 minutes while the tab is open. Keys are upserted by id.
//
// If the IndexedDB table names differ in a future build, inspect with:
//   indexedDB.databases().then(console.log)

(async () => {
  const MC_ENDPOINT = "https://YOUR-TUNNEL.trycloudflare.com/api/nexus/push"; // <-- FILL
  const SYNC_MS = 5 * 60 * 1000;

  async function readAll(dbName, storeNames) {
    return new Promise((resolve) => {
      const req = indexedDB.open(dbName);
      req.onsuccess = () => {
        const db = req.result;
        const out = {};
        let pending = storeNames.length;
        if (!pending) return resolve(out);
        storeNames.forEach((s) => {
          try {
            const tx = db.transaction(s, "readonly");
            const get = tx.objectStore(s).getAll();
            get.onsuccess = () => { out[s] = get.result; if (!--pending) resolve(out); };
            get.onerror = () => { if (!--pending) resolve(out); };
          } catch { if (!--pending) resolve(out); }
        });
      };
      req.onerror = () => resolve({});
    });
  }

  async function sync() {
    const dbs = await indexedDB.databases().catch(() => []);
    let leads = [], visits = [];
    for (const d of dbs) {
      const name = (d.name || "").toLowerCase();
      if (!name) continue;
      // Nexus table names seen in the app bundle: leads/visitas (adjust if renamed)
      const data = await readAll(d.name, ["leads", "visitas", "visits", "leads-store"]);
      leads = leads.concat(data.leads || data["leads-store"] || []);
      visits = visits.concat(data.visitas || data.visits || []);
    }
    if (!leads.length && !visits.length) return console.log("[bridge] nothing to sync");
    const r = await fetch(MC_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bridge": "browser" },
      body: JSON.stringify({ leads, visits }),
    });
    console.log("[bridge] synced:", r.status, await r.text());
  }

  await sync();
  setInterval(sync, SYNC_MS);
  console.log("[bridge] Nexus->La Jefatura sync active (5 min interval)");
})();

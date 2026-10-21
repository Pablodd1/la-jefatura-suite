/*
 * La Jefatura — Voice Widget (embeddable, white-label)
 *
 * WHAT IT IS
 *   A dependency-free floating assistant for the CEO console (or any tenant
 *   site). One button: speak a command, the whole site obeys. Also types.
 *
 * COMMANDS (ES + EN, matched by regex — see GRAMMAR below)
 *   "cambiar a MBMB" / "switch to CEDEXX"   -> action switch_company
 *   "descargar informe" / "download report" -> action download_report
 *   "completar tarea 2"  / "complete task 1"-> action complete_task
 *   "leer resumen" / "read brief"           -> action read_brief (TTS)
 *   "qué hay de nuevo" / "what's new"       -> action status_digest
 *   "actualizar" / "refresh"                -> action refresh
 *   "ayuda" / "help"                        -> action help
 *
 * EMBED (tenant site, white-label):
 *   <script>
 *     window.LJ_WIDGET = { api: "https://TUNNEL/api", lang: "es", tenant: "mbmb" };
 *   </script>
 *   <script src="https://YOUR-CDN/lajefatura-widget.js"></script>
 *
 * HOST PAGE REGISTERS ACTIONS (see mock/demo.html for the full example):
 *   window.LJ.register("switch_company", (name) => {...});
 *
 * DEGRADATION: no SpeechRecognition -> text input mode. No speechSynthesis ->
 * responses render as text only. api unreachable -> local actions still work.
 */
(function () {
  function boot() {
  const CFG = Object.assign({
    api: "",            // Mission Control base URL ("" = console mode, local actions only)
    lang: (document.documentElement.lang || "es").startsWith("es") ? "es" : "en",
    tenant: "",
    accent: "#23d9b0",
    position: "bottom-right",
  }, window.LJ_WIDGET || {});

  const T = {
    es: { title: "La Jefatura — voz", placeholder: "Escribe un comando…",
          listening: "Escuchando…", help: "Comandos: cambiar a «empresa» · descargar informe · completar tarea «n» · leer resumen · qué hay de nuevo · actualizar",
          unknown: "No entendí ese comando. Di «ayuda».", offline: "Sin micrófono — modo texto.",
          open: "Asistente de voz listo. Di «ayuda» para ver comandos." },
    en: { title: "La Jefatura — voice", placeholder: "Type a command…",
          listening: "Listening…", help: "Commands: switch to «company» · download report · complete task «n» · read brief · what's new · refresh",
          unknown: "I didn't catch that command. Say \"help\".", offline: "No mic — text mode.",
          open: "Voice assistant ready. Say \"help\" for commands." },
  }[CFG.lang];

  /* ── Grammar: [regex, action, argGroup?] — ES and EN both match ── */
  const GRAMMAR = [
    [/cambiar a|ir a|switch to|show\s+(me\s+)?(.*company)?\s*(\w+)$/i, "switch_company", null], // resolved below
    [/descargar|generar|download|get (the )?report/i, "download_report"],
    [/completar tarea\s+(\d+|\w.*)|complete task\s+(\d+|\w.*)/i, "complete_task"],
    [/(leer|lee) resumen|read (the )?brief|resume/i, "read_brief"],
    [/qué hay de nuevo|novedades|what('s| is) new|status/i, "status_digest"],
    [/actualizar|recargar|refresh|reload/i, "refresh"],
    [/ayuda|help|comandos|commands/i, "help"],
  ];

  const state = { open: false, listening: false, transcript: "", log: [] };
  const actions = {};   // host-registered
  window.LJ = window.LJ || {};
  window.LJ.register = (name, fn) => { actions[name] = fn; };
  window.LJ.execute = execute;   // exposed so hosts/tests can drive it headless

  /* ── Command resolution ── */
  function parse(text) {
    const t = text.trim();
    // company switch: "cambiar a X" / "switch to X"
    const sw = t.match(/^(?:cambiar a|ir a|switch to|muestra(?:me)?|show(?: me)?)\s+(.+)$/i);
    if (sw) return { action: "switch_company", arg: sw[1].trim() };
    const ct = t.match(/^(?:completar|marcar|complete|done(?: with)?)\s+(?:tarea|task)?\s*(.+)$/i);
    if (ct) return { action: "complete_task", arg: ct[1].trim() };
    for (const [re, action] of GRAMMAR) {
      if (re.test(t)) {
        const m = t.match(re);
        return { action, arg: (m && (m[1] || m[2])) || "" };
      }
    }
    return { action: null };
  }

  function speak(text) {
    state.log.push({ who: "lj", text });
    renderLog();
    if ("speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = CFG.lang === "es" ? "es-US" : "en-US";
      u.rate = 1.05;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    }
  }

  function execute(text) {
    const { action, arg } = parse(text);
    state.log.push({ who: "user", text });
    if (!action) { speak(T.unknown); return { ok: false }; }
    if (actions[action]) {
      const r = actions[action](arg) ?? "";
      if (typeof r === "string" && r) speak(r);
      return { ok: true, action, arg };
    }
    // default: server-backed actions via MC api
    if (CFG.api) {
      fetch(CFG.api + "/api/voice/command", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: text, tenant: CFG.tenant, lang: CFG.lang }),
      }).then(r => r.json()).then(d => speak(d.reply || T.unknown)).catch(() => speak(T.offline));
      return { ok: true, action, arg, delegated: true };
    }
    speak(T.unknown);
    return { ok: false };
  }

  /* ── UI ── */
  const css = `
#ljw{position:fixed;${CFG.position.includes("left") ? "left:18px" : "right:18px"};bottom:18px;z-index:9999;font-family:-apple-system,'SF Pro Display',Inter,Arial,sans-serif}
#ljw .fab{width:56px;height:56px;border-radius:50%;border:0;cursor:pointer;background:${CFG.accent};color:#04241c;font-size:24px;box-shadow:0 8px 26px rgba(0,0,0,.4);transition:.2s;display:flex;align-items:center;justify-content:center}
#ljw .fab:hover{transform:scale(1.06)}
#ljw .fab.on{animation:ljpulse 1.6s infinite}
@keyframes ljpulse{50%{box-shadow:0 0 0 12px rgba(35,217,176,.12)}}
#ljw .panel{position:absolute;bottom:68px;${CFG.position.includes("left") ? "left:0" : "right:0"};width:320px;max-height:420px;background:#0d1322;border:1px solid rgba(255,255,255,.09);border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.5);display:none;flex-direction:column;overflow:hidden}
#ljw .panel.open{display:flex}
#ljw .head{padding:12px 16px;color:#8b96b0;font-size:11px;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid rgba(255,255,255,.07)}
#ljw .log{flex:1;overflow-y:auto;padding:10px 14px;font-size:13px}
#ljw .msg{margin-bottom:9px;line-height:1.45}
#ljw .msg.user{color:#23d9b0;text-align:right}
#ljw .msg.lj{color:#e8edf7}
#ljw .input{display:flex;border-top:1px solid rgba(255,255,255,.07)}
#ljw .input input{flex:1;background:none;border:0;color:#e8edf7;padding:11px 14px;font-size:13px;outline:none}
#ljw .input button{background:none;border:0;color:${CFG.accent};font-size:18px;cursor:pointer;padding:0 14px}`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  const root = document.createElement("div");
  root.id = "ljw";
  root.innerHTML = `
    <div class="panel" id="ljw-panel">
      <div class="head">${T.title}</div>
      <div class="log" id="ljw-log"></div>
      <div class="input">
        <input id="ljw-in" placeholder="${T.placeholder}" autocomplete="off">
        <button id="ljw-mic" title="voice">🎙</button>
      </div>
    </div>
    <button class="fab" id="ljw-fab">🎙</button>`;
  document.body.appendChild(root);

  const $ = (s) => root.querySelector(s);
  const panel = $("#ljw-panel"), fab = $("#ljw-fab"), input = $("#ljw-in"), log = $("#ljw-log");

  function renderLog() {
    log.innerHTML = state.log.slice(-30).map(m =>
      `<div class="msg ${m.who}">${m.who === "user" ? "▸ " : ""}${m.text}</div>`).join("");
    log.scrollTop = log.scrollHeight;
  }

  fab.onclick = () => {
    state.open = !state.open;
    panel.classList.toggle("open", state.open);
    if (state.open && !state._greeted) { state._greeted = true; speak(T.open); }
    if (state.open) input.focus();
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && input.value.trim()) { execute(input.value); input.value = ""; }
  });

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  function startMic() {
    if (!SR) { execute("help"); return; }   // no mic API -> show help text
    if (state.listening) { rec.stop(); return; }
    rec = new SR();
    rec.lang = CFG.lang === "es" ? "es-US" : "en-US";
    rec.interimResults = false;
    rec.onstart = () => { state.listening = true; fab.classList.add("on"); $("#ljw-mic").textContent = "■"; input.placeholder = T.listening; };
    rec.onend = () => { state.listening = false; fab.classList.remove("on"); $("#ljw-mic").textContent = "🎙"; input.placeholder = T.placeholder; };
    rec.onerror = () => { state.listening = false; };
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      input.value = text;
      setTimeout(() => { execute(text); input.value = ""; }, 350);
    };
    rec.start();
  }
  $("#ljw-mic").onclick = startMic;
  fab.addEventListener("contextmenu", (e) => { e.preventDefault(); startMic(); }); // long-press alt
  }
  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();

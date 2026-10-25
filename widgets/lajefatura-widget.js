/*
 * La Jefatura — Grok 3.0 Voice & DOM-Aware Brain Layer (white-label, embeddable)
 *
 * CAPABILITIES:
 *   1. Grok 3.0 Voice Command & Conversational Brain (Bilingual ES/EN, Web Speech STT + Neural TTS)
 *   2. Full Website DOM Awareness — reads live KPIs, active tab, company filter, tasks, drafts,
 *      and can touch/click ANY button, tab, or link on screen by voice or text command.
 *   3. Behavioral & Temporal Telemetry — observes mouse focus, clicks, typing cadence, and
 *      time-of-day routines (Morning / Afternoon / Evening) to foresee CEO needs in advance.
 */
(function () {
  function boot() {
    const CFG = Object.assign({
      api: "",
      lang: (document.documentElement.lang || "es").startsWith("es") ? "es" : "en",
      tenant: "default",
      accent: "#23d9b0",
      position: "bottom-right",
    }, window.LJ_WIDGET || {});

    const COPY = {
      es: {
        title: "EL JEFESITO · VOZ Y TEXTO",
        sub: "Voz Neural Colombiana (es-CO · Rápida) · Aprende de ti",
        placeholder: "Habla o escribe (ej. «abrir blogs», «aprobar borrador», «pedir café»)…",
        listening: "Escuchando voz con Grok 3.0…",
        help: "Comandos Grok 3.0: cambiar a «empresa» · abrir «pestaña» (mando, bandeja, resultados, cerebro, setup, blogs) · aprobar borrador · redactar respuesta · completar tarea «n» · preparar café · explicar planes · qué hay en pantalla · descargar informe.",
        unknown: "Analicé la pantalla pero no encontré esa acción exacta. Prueba: «abrir blogs», «aprobar borrador», «cambiar a CEDEXX» o «leer resumen».",
        offline: "Modo local activo.",
        open: "Soy El Jefesito. Te atiendo por voz o texto, aprendo de cada interacción y puedo cambiar el tema, el idioma, el saludo, cerrar el día o imprimir tu resumen. ¿Qué hacemos?",
        chips: [
          ["Leer Resumen", "leer resumen"],
          ["Aprobar Borrador", "aprobar borrador"],
          ["Guardar Nota", "guardar nota: Revisar cierre Doral Urgent Care y métricas BuildingApp"],
          ["¿Qué notas tengo?", "qué notas tengo"],
          ["Miembros BuildingApp", "cuántos miembros nuevos hay en BuildingApp"],
          ["Mi Café 07:45", "preparar café"],
          ["Ir a Blogs", "abrir blogs"]
        ]
      },
      en: {
        title: "EL JEFESITO · VOICE & TEXT",
        sub: "Fast Neural Voice (Colombian ES / EN) · Self-Learning",
        placeholder: "Speak or type (e.g. 'open blogs', 'approve draft', 'order coffee')…",
        listening: "Grok 3.0 listening…",
        help: "Grok 3.0 Commands: switch to «company» · open «tab» (overview, comms, outcomes, brain, setup, blogs) · approve draft · draft reply · complete task «n» · order coffee · explain plans · what is on screen · download report.",
        unknown: "I scanned the page but couldn't match that exact command. Try: 'open blogs', 'approve draft', 'switch to CEDEXX', or 'read brief'.",
        offline: "Local brain mode active.",
        open: "I'm El Jefesito. I take voice or text, learn from every interaction, and can change the theme, language, greeting, close the day or print your summary. What should we do?",
        chips: [
          ["Read Brief", "read brief"],
          ["Approve Draft", "approve draft"],
          ["Save Note", "save note: Review Doral Urgent Care closure and BuildingApp metrics"],
          ["My Notes", "what notes do I have"],
          ["BuildingApp Members", "how many members in BuildingApp"],
          ["My 07:45 Coffee", "order coffee"],
          ["Open Blogs", "open blogs"]
        ]
      }
    };

    const state = { open: false, listening: false, speaking: false, log: [], channel: "text" };
    const actions = {};
    window.LJ = window.LJ || {};
    window.LJ.register = (name, fn) => { actions[name] = fn; };
    window.LJ.execute = execute;
    window.LJ.inspectDOM = inspectDOM;
    window.LJ.setLang = (l) => { CFG.lang = l === "en" ? "en" : "es"; renderPanelLocale(); };
    window.LJ.speak = (t) => speak(t);

    function getT() {
      return COPY[CFG.lang] || COPY.es;
    }

    /* ── Visual DOM Touch Highlight ── */
    function highlightElement(el) {
      if (!el) return;
      el.classList.remove("lj-voice-touch");
      void el.offsetWidth;
      el.classList.add("lj-voice-touch");
      try { el.scrollIntoView({ behavior: "smooth", block: "nearest" }); } catch (_) {}
      setTimeout(() => el.classList.remove("lj-voice-touch"), 1800);
    }

    /* ── Full Website DOM Inspector ── */
    function inspectDOM() {
      const activeTabEl = document.querySelector(".nav-tab.active");
      const activeCompanyEl = document.querySelector("#companySeg button.on");
      const kpiCards = Array.from(document.querySelectorAll(".kpi-card")).map(c => c.innerText.replace(/\s+/g, " ").trim());
      const buttons = Array.from(document.querySelectorAll("button, a, [data-voice-target]")).map(b => ({
        text: (b.innerText || b.getAttribute("aria-label") || b.id || "").trim(),
        id: b.id,
        el: b
      })).filter(b => b.text.length > 0);
      return {
        activeTab: activeTabEl ? activeTabEl.innerText.trim() : "Overview",
        activeCompany: activeCompanyEl ? activeCompanyEl.innerText.trim() : "All",
        kpis: kpiCards.slice(0, 4),
        interactiveCount: buttons.length,
        buttons
      };
    }

    /* ── Command & Natural Language Resolution ── */
    function parse(text) {
      const t = text.trim();
      const low = t.toLowerCase();

      // 0. Knowledge intents (save note/task/meeting/email, list, search, metric questions) are
      //    answered ONLY by the server from stored data — checked first so words inside the
      //    note («mañana», «café»…) cannot trigger other commands.
      if (/^(guardar|guarda|anotar|anota|agregar|agrega|a[ñn]adir|save|add|take|create|crear|crea|new|nota|note|recu[eé]rdame|remind me)\b/i.test(t) &&
          /(nota|note|tarea|task|reuni[oó]n|meeting|correo|email|recu[eé]rdame|remind me)/i.test(low)) {
        return { action: "server_cmd", arg: t };
      }
      if (/^(buscar|busca|search|find|encuentra|qu[eé] dijo|what did)\b/i.test(low) ||
          (/\b(notas?|notes?|tareas?|tasks?|reuniones?|meetings?)\b/i.test(low) &&
           /\b(qu[eé]|cu[aá]les|cu[aá]ntas?|lista|listar|lee|leer|read|list|show|what|how many|dame|muestra)\b/i.test(low) &&
           !/^(ir a|abrir|abre|open|go to)\b/i.test(low)) ||
          /\b(miembros|members|conversaciones|conversations|abandono|abandonment|contactos|contacts|alertas|alerts|generaciones|generations|renders|costo|cost)\b/i.test(low)) {
        return { action: "server_cmd", arg: t };
      }

      // 0b. Jefesito control requests (theme, language, greeting, close day, print, profile, name)
      //     are executed by the server so they persist and are learned.
      if (/\b(tema|temas|theme|themes|saludo|greeting|idioma|language|perfil|profile|aprendido|learned)\b/i.test(low) ||
          /(cierra|cerrar|close)\b.*\b(d[ií]a|day)\b/i.test(low) ||
          /resumen (del d[ií]a|diario)|daily (summary|brief)|imprim|\bprint\b/i.test(low) ||
          /\b(habla|hablar|speak|talk)\b.*(ingl[eé]s|english|espa[nñ]ol|spanish)/i.test(low) ||
          /^(ll[aá]mame|me llamo|mi nombre es|call me)\b/i.test(low)) {
        return { action: "server_cmd", arg: t };
      }

      // 1. Tab switching
      const tabMap = [
        [/\b(blogs?|gu[ií]as?|paso a paso|step by step|funciones|explicaci[oó]n)\b/i, "blogs"],
        [/\b(setup|configuraci[oó]n|onboarding|integraciones|conectar|white[- ]?label)\b/i, "setup"],
        [/\b(cerebro|behavior|conductual|h[aá]bitos|habits|rutina|aprendizaje|learning)\b/i, "behavior"],
        [/\b(resultados|outcomes|monitoreo|estudios|gr[aá]ficas|personas|clientes|c[aá]maras)\b/i, "outcomes"],
        [/\b(bandeja|comms|correos|mensajes|borradores|inbox|emails?|whatsapp|telegram)\b/i, "comms"],
        [/\b(mando|overview|consola|dashboard|inicio|home|resumen principal)\b/i, "overview"]
      ];
      if (/^(ir a|abrir|abre|open|go to|ver|mostrar|show|tab|pesta[ñn]a)\b/i.test(low)) {
        for (const [re, tabId] of tabMap) {
          if (re.test(low)) return { action: "open_tab", arg: tabId };
        }
      }
      for (const [re, tabId] of tabMap) {
        if (re.test(low) && /(pesta[ñn]a|tab|secci[oó]n|page|p[aá]gina)/i.test(low)) {
          return { action: "open_tab", arg: tabId };
        }
      }

      // 2. Time-of-day routine switch
      if (/\b(ma[ñn]ana|morning)\b/i.test(low) && /\b(rutina|modo|horario|routine|mode|slot)\b/i.test(low)) {
        return { action: "switch_slot", arg: "morning" };
      }
      if (/\b(tarde|afternoon)\b/i.test(low) && /\b(rutina|modo|horario|routine|mode|slot)\b/i.test(low)) {
        return { action: "switch_slot", arg: "afternoon" };
      }
      if (/\b(noche|evening|night)\b/i.test(low) && /\b(rutina|modo|horario|routine|mode|slot)\b/i.test(low)) {
        return { action: "switch_slot", arg: "evening" };
      }

      // 3. Coffee / foresight action
      if (/\b(caf[eé]|coffee|espresso|cortado)\b/i.test(low)) {
        return { action: "confirm_coffee", arg: "" };
      }

      // 4. Draft approval & reply generation
      if (/\b(aprobar|aprueba|approve|enviar borrador|send draft)\b/i.test(low)) {
        const num = low.match(/(\d+)/);
        return { action: "approve_draft", arg: num ? num[1] : "1" };
      }
      if (/\b(redactar|borrador|draft|responder|reply)\b/i.test(low)) {
        return { action: "draft_reply", arg: "" };
      }

      // 5. Company switching
      const sw = t.match(/^(?:cambiar a|ir a|switch to|muestra(?:me)?|show(?: me)?|filtrar)\s+(.+)$/i);
      if (sw) return { action: "switch_company", arg: sw[1].trim() };

      // 6. Complete task
      const ct = t.match(/^(?:completar|marcar|complete|done(?: with)?)\s+(?:tarea|task)?\s*(.+)$/i);
      if (ct) return { action: "complete_task", arg: ct[1].trim() };

      // 7. DOM awareness & plans explanation
      if (/\b(qu[eé] hay en (la )?(pantalla|p[aá]gina|sitio)|what('s| is) on (the )?(screen|page|site)|inspect|dom)\b/i.test(low)) {
        return { action: "inspect_page", arg: "" };
      }
      if (/\b(explica|explain|planes|plans|c[oó]mo funciona|how does it work|arquitectura)\b/i.test(low)) {
        return { action: "explain_plans", arg: "" };
      }

      // 8. Standard commands
      if (/\b(descargar|generar|download|get (the )?report|pdf)\b/i.test(low)) return { action: "download_report", arg: "" };
      if (/\b((leer|lee) resumen|read (the )?brief|resume|resumen del d[ií]a)\b/i.test(low)) return { action: "read_brief", arg: "" };
      if (/\b(qu[eé] hay de nuevo|novedades|what('s| is) new|status)\b/i.test(low)) return { action: "status_digest", arg: "" };
      if (/\b(actualizar|recargar|refresh|reload)\b/i.test(low)) return { action: "refresh", arg: "" };
      if (/\b(ayuda|help|comandos|commands)\b/i.test(low)) return { action: "help", arg: "" };

      // 9. Direct DOM button/link click by label ("click X" / "tocar X" / "pulsar X")
      const clickMatch = t.match(/^(?:click|clic|tocar|toca|pulsar|pulsa|presionar|press|touch)\s+(.+)$/i);
      if (clickMatch) {
        return { action: "click_dom", arg: clickMatch[1].trim() };
      }

      return { action: null, raw: t };
    }

    let currentAudio = null;
    function stopAudio() {
      try {
        if (currentAudio) {
          currentAudio.pause();
          currentAudio.currentTime = 0;
          currentAudio = null;
        }
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      } catch (_) {}
      state.speaking = false;
      root.classList.remove("speaking");
    }
    window.LJ.stopAudio = stopAudio;

    function _browserFallbackSpeak(text) {
      if (!("speechSynthesis" in window)) return;
      try {
        const u = new SpeechSynthesisUtterance(text);
        u.lang = CFG.lang === "es" ? "es-CO" : "en-US";
        u.rate = 1.24;
        const voices = window.speechSynthesis.getVoices() || [];
        const coVoice = voices.find(v => /es[-_]CO/i.test(v.lang)) ||
                        voices.find(v => /Salome|Gonzalo|Colomb/i.test(v.name)) ||
                        voices.find(v => /^es/i.test(v.lang) && /Natural|Neural|Online/i.test(v.name));
        if (CFG.lang === "es" && coVoice) u.voice = coVoice;
        u.onstart = () => { state.speaking = true; root.classList.add("speaking"); };
        u.onend = () => { state.speaking = false; root.classList.remove("speaking"); };
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
      } catch (_) {}
    }

    function speak(text, logIt = true) {
      if (logIt) {
        state.log.push({ who: "lj", text });
        renderLog();
      }
      stopAudio();
      const url = (CFG.api || "") + "/api/tts?lang=" + encodeURIComponent(CFG.lang) +
                  "&rate=" + encodeURIComponent("+22%") +
                  "&text=" + encodeURIComponent((text || "").slice(0, 850));
      try {
        const a = new Audio(url);
        currentAudio = a;
        a.onplay = () => { state.speaking = true; root.classList.add("speaking"); };
        a.onended = () => { state.speaking = false; root.classList.remove("speaking"); currentAudio = null; };
        a.onerror = () => { currentAudio = null; _browserFallbackSpeak(text); };
        const p = a.play();
        if (p && typeof p.catch === "function") {
          p.catch(() => { currentAudio = null; _browserFallbackSpeak(text); });
        }
      } catch (_) {
        _browserFallbackSpeak(text);
      }
    }
    window.LJ.speak = (t, logIt = false) => speak(t, logIt);

    // Every locally-handled interaction is recorded so El Jefesito can learn the user's profile.
    function learn(text, action) {
      try {
        fetch((CFG.api || "") + "/api/jefesito/learn", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, CFG.token ? { "X-MC-Token": CFG.token } : {}),
          body: JSON.stringify({ text, action, channel: state.channel, lang: CFG.lang }),
        }).catch(() => {});
      } catch (_) {}
    }

    function execute(text) {
      const T = getT();
      const { action, arg } = parse(text);
      state.log.push({ who: "user", text });
      renderLog();

      // Log voice interaction into Behavioral Brain
      if (window.LJ_BEHAVIOR && typeof window.LJ_BEHAVIOR.track === "function") {
        window.LJ_BEHAVIOR.track("voice_query", action || "natural_query", { text, action, arg });
      }

      if (action && action !== "server_cmd") learn(text, action);

      if (action === "server_cmd") {
        fetch((CFG.api || "") + "/api/voice/command", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, CFG.token ? { "X-MC-Token": CFG.token } : {}),
          body: JSON.stringify({ command: text, tenant: CFG.tenant, lang: CFG.lang, channel: state.channel }),
        })
          .then(r => r.ok ? r.json() : Promise.reject(r.status))
          .then(d => {
            speak((d.reply || T.unknown) + (d.sources && d.sources.length && d.grounded
              ? (CFG.lang === "es" ? " Fuente: " : " Source: ") + d.sources.slice(0, 2).join("; ") : ""));
            if (d.ui && typeof window.LJ_applyUi === "function") window.LJ_applyUi(d.ui);
            if (typeof window.loadKnowledgeVault === "function") window.loadKnowledgeVault(false);
          })
          .catch(() => speak(CFG.lang === "es"
              ? "No pude consultar el servidor, así que no voy a inventar una respuesta."
              : "I couldn't reach the server, so I won't make up an answer."));
        return { ok: true, action, delegated: true };
      }

      if (action === "inspect_page") {
        const dom = inspectDOM();
        const msg = CFG.lang === "es"
          ? `Conciencia DOM Grok 3.0: Estás en la pestaña «${dom.activeTab}», filtrando empresa «${dom.activeCompany}». Veo ${dom.interactiveCount} controles interactivos y KPIs activos: ${dom.kpis.slice(0, 2).join(" | ")}.`
          : `Grok 3.0 DOM Awareness: You are viewing tab "${dom.activeTab}", filtering company "${dom.activeCompany}". I see ${dom.interactiveCount} interactive controls and active KPIs: ${dom.kpis.slice(0, 2).join(" | ")}.`;
        speak(msg);
        return { ok: true, action, dom };
      }

      if (action === "click_dom") {
        const dom = inspectDOM();
        const target = dom.buttons.find(b => b.text.toLowerCase().includes(arg.toLowerCase()));
        if (target && target.el) {
          highlightElement(target.el);
          target.el.click();
          const msg = CFG.lang === "es" ? `Tocando botón «${target.text}».` : `Touching control "${target.text}".`;
          speak(msg);
          return { ok: true, action, target: target.text };
        }
      }

      if (action && actions[action]) {
        const r = actions[action](arg) ?? "";
        if (typeof r === "string" && r) speak(r);
        return { ok: true, action, arg, reply: r };
      }

      // Fallback: Try matching any visible button/tab on screen by text
      const dom = inspectDOM();
      const matchedBtn = dom.buttons.find(b => b.text.length > 2 && text.toLowerCase().includes(b.text.toLowerCase()));
      if (matchedBtn && matchedBtn.el) {
        highlightElement(matchedBtn.el);
        matchedBtn.el.click();
        const msg = CFG.lang === "es" ? `Ejecutando «${matchedBtn.text}» en pantalla.` : `Triggering "${matchedBtn.text}" on screen.`;
        speak(msg);
        return { ok: true, action: "dom_match", target: matchedBtn.text };
      }

      // Server fallback (grounded: answers from stored data or says it has no data)
      fetch((CFG.api || "") + "/api/voice/command", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, CFG.token ? { "X-MC-Token": CFG.token } : {}),
        body: JSON.stringify({ command: text, tenant: CFG.tenant, lang: CFG.lang, channel: state.channel }),
      })
        .then(r => r.json())
        .then(d => speak(d.reply || T.unknown))
        .catch(() => speak(T.unknown));

      return { ok: Boolean(action), action, arg, delegated: true };
    }

    /* ── Widget Styles & DOM ── */
    const css = `
.lj-voice-touch{outline:2px solid #23d9b0 !important;box-shadow:0 0 0 6px rgba(35,217,176,.35) !important;transition:box-shadow .25s ease !important}
#ljw{position:fixed;${CFG.position.includes("left") ? "left:20px" : "right:20px"};bottom:20px;z-index:9999;font-family:-apple-system,'SF Pro Display',Inter,Segoe UI,sans-serif}
#ljw .fab{padding:0 18px;height:44px;border-radius:999px;border:1px solid rgba(255,255,255,.22);cursor:pointer;background:#111318;color:#f5f5f7;font-size:11.5px;font-weight:800;letter-spacing:.08em;box-shadow:0 10px 28px rgba(0,0,0,.55);transition:.2s;display:flex;align-items:center;justify-content:center;gap:8px;position:relative}
#ljw .fab::before{content:"";width:7px;height:7px;border-radius:50%;background:#ffd400;box-shadow:0 0 8px #ffd400}
#ljw .fab:hover{transform:translateY(-1px);border-color:#ffd400}
#ljw .fab.on,#ljw.speaking .fab{animation:ljpulse 1.4s infinite}
#ljw .fab-badge{display:none}
@keyframes ljpulse{50%{box-shadow:0 0 0 14px rgba(35,217,176,.18)}}
#ljw .panel{position:absolute;bottom:72px;${CFG.position.includes("left") ? "left:0" : "right:0"};width:370px;max-height:520px;background:rgba(13,19,34,.97);backdrop-filter:blur(18px);border:1px solid rgba(35,217,176,.28);border-radius:18px;box-shadow:0 22px 60px rgba(0,0,0,.65);display:none;flex-direction:column;overflow:hidden}
#ljw .panel.open{display:flex}
#ljw .head{padding:13px 16px;background:linear-gradient(90deg,rgba(35,217,176,.12),rgba(124,108,255,.12));border-bottom:1px solid rgba(255,255,255,.08);display:flex;justify-content:space-between;align-items:center}
#ljw .head-title{color:#e8edf7;font-size:11.5px;font-weight:800;letter-spacing:.8px}
#ljw .head-sub{color:#23d9b0;font-size:10px;margin-top:2px;display:flex;align-items:center;gap:5px}
#ljw .wave{display:flex;gap:3px;align-items:center;height:16px}
#ljw .wave span{width:3px;height:6px;background:#23d9b0;border-radius:2px;transition:.2s}
#ljw.speaking .wave span,#ljw .fab.on ~ .panel .wave span{animation:ljwave .7s infinite ease-in-out}
#ljw .wave span:nth-child(2){animation-delay:.1s}
#ljw .wave span:nth-child(3){animation-delay:.2s}
#ljw .wave span:nth-child(4){animation-delay:.3s}
#ljw .wave span:nth-child(5){animation-delay:.15s}
@keyframes ljwave{0%,100%{height:5px}50%{height:16px}}
#ljw .chips{display:flex;flex-wrap:wrap;gap:5px;padding:9px 12px;border-bottom:1px solid rgba(255,255,255,.06);background:rgba(7,11,20,.55)}
#ljw .chip{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);color:#cfd8ea;font-size:11px;padding:4px 9px;border-radius:14px;cursor:pointer;transition:.15s}
#ljw .chip:hover{background:rgba(35,217,176,.18);border-color:#23d9b0;color:#fff}
#ljw .log{flex:1;overflow-y:auto;padding:12px 14px;font-size:12.5px;min-height:170px;max-height:250px}
#ljw .msg{margin-bottom:9px;line-height:1.45;padding:7px 10px;border-radius:10px}
#ljw .msg.user{background:rgba(35,217,176,.14);color:#23d9b0;margin-left:28px;text-align:right}
#ljw .msg.lj{background:rgba(255,255,255,.05);color:#e8edf7;margin-right:18px;border-left:2px solid #23d9b0}
#ljw .input{display:flex;border-top:1px solid rgba(255,255,255,.08);background:#080d18}
#ljw .input input{flex:1;background:none;border:0;color:#e8edf7;padding:12px 14px;font-size:12.5px;outline:none}
#ljw .input button{background:none;border:0;color:#23d9b0;font-size:17px;cursor:pointer;padding:0 12px;font-weight:700}`;

    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);

    const root = document.createElement("div");
    root.id = "ljw";
    root.innerHTML = `
      <div class="panel" id="ljw-panel">
        <div class="head">
          <div>
            <div class="head-title" id="ljw-title"></div>
            <div class="head-sub"><span style="width:6px;height:6px;border-radius:50%;background:#23d9b0;display:inline-block"></span><span id="ljw-sub"></span></div>
          </div>
          <div class="wave" title="Grok 3.0 Audio Engine"><span></span><span></span><span></span><span></span><span></span></div>
        </div>
        <div class="chips" id="ljw-chips"></div>
        <div class="log" id="ljw-log"></div>
        <div class="input">
          <input id="ljw-in" autocomplete="off">
          <button id="ljw-send" title="Send" style="font-size:12px">ENVIAR</button>
          <button id="ljw-mic" title="Voice Input" style="font-size:11px">VOZ</button>
        </div>
      </div>
      <button class="fab" id="ljw-fab" title="El Jefesito · Voz y Texto">JEFESITO · VOZ</button>`;
    document.body.appendChild(root);

    const $ = (s) => root.querySelector(s);
    const panel = $("#ljw-panel"), fab = $("#ljw-fab"), input = $("#ljw-in"), log = $("#ljw-log"), chips = $("#ljw-chips");

    function renderPanelLocale() {
      const T = getT();
      $("#ljw-title").textContent = T.title;
      $("#ljw-sub").textContent = T.sub;
      input.placeholder = T.placeholder;
      chips.innerHTML = T.chips.map(([label, cmd]) =>
        `<button class="chip" data-cmd="${cmd}">${label}</button>`
      ).join("");
      chips.querySelectorAll(".chip").forEach(btn => {
        btn.onclick = () => execute(btn.getAttribute("data-cmd"));
      });
    }

    function renderLog() {
      log.innerHTML = state.log.slice(-30).map(m =>
        `<div class="msg ${m.who}">${m.text}</div>`
      ).join("");
      log.scrollTop = log.scrollHeight;
    }

    fab.onclick = () => {
      state.open = !state.open;
      panel.classList.toggle("open", state.open);
      if (state.open && !state._greeted) {
        state._greeted = true;
        speak(getT().open);
      }
      if (state.open) input.focus();
    };

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        execute(input.value);
        input.value = "";
      }
    });
    $("#ljw-send").onclick = () => {
      if (input.value.trim()) {
        execute(input.value);
        input.value = "";
      }
    };

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    let rec = null;
    function startMic() {
      const T = getT();
      if (!SR) { execute("help"); return; }
      if (state.listening && rec) { rec.stop(); return; }
      rec = new SR();
      rec.lang = CFG.lang === "es" ? "es-CO" : "en-US";
      rec.interimResults = false;
      rec.onstart = () => {
        state.listening = true;
        fab.classList.add("on");
        $("#ljw-mic").textContent = "PARAR";
        input.placeholder = T.listening;
      };
      rec.onend = () => {
        state.listening = false;
        fab.classList.remove("on");
        $("#ljw-mic").textContent = "VOZ";
        input.placeholder = T.placeholder;
      };
      rec.onerror = () => { state.listening = false; };
      rec.onresult = (e) => {
        const text = e.results[0][0].transcript;
        input.value = text;
        setTimeout(() => { state.channel = "voice"; execute(text); state.channel = "text"; input.value = ""; }, 300);
      };
      rec.start();
    }
    $("#ljw-mic").onclick = startMic;
    fab.addEventListener("contextmenu", (e) => { e.preventDefault(); startMic(); });

    renderPanelLocale();
  }

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();

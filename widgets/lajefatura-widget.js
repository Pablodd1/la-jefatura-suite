/*
 * La Jefatura — Grok 3.0 Voice, Chat & Close-Word Function Router Widget
 * Made & Powered by Building Innovation
 *
 * CAPABILITIES:
 *   1. Direct Voice & Chat Control over Master Control (menus, projects, links, PDFs, notes,
 *      Google Calendar real-time appointments, and email reminders).
 *   2. Close-Word & Partial-Word Recognition via /api/voice/command + DOM fallback.
 *   3. Live Speech-to-Text (interim + final transcript preview) & Colombian Neural TTS (es-CO-SalomeNeural).
 *   4. Instant Click-to-Stop or Click-Mic-to-Interrupt while speaking.
 */
(function () {
  function boot() {
    const CFG = Object.assign({
      api: "",
      lang: (document.documentElement.lang || "es").toLowerCase().startsWith("en") ? "en" : "es",
      tenant: "default",
      accent: "#cdb68c",
      position: "bottom-right",
    }, window.LJ_WIDGET || {});

    const COPY = {
      es: {
        title: "LA JEFATURA · CHATBOT Y VOZ MAESTRA",
        sub: "Voz Colombiana (es-CO) · Control Total de Menús, Notas, Google Calendar y Email",
        placeholder: "Habla o escribe (ej: «cam», «uni», «nota:...», «cita mañana 3pm», «recordatorio por correo...»)…",
        listening: "🎙️ Escuchando tu voz en vivo… habla ahora",
        help: "Puedes pedir con palabras completas o cercanas: «cámaras / cam», «unitec / uni», «building / renders», «espacios / contenedores», «nexus / crm», «bandeja / correos», «resultados / gráficas», «periódico pdf», «anota...», «agenda cita mañana a las 3pm» o «recordatorio por correo...».",
        unknown: "No encontré ese dato exacto y jamás adivino. Prueba decir una palabra cercana como «cam», «uni», «building», «agenda cita...», «nota:...» o «catálogo de funciones».",
        offline: "Modo local activo.",
        open: "Listo, Jefe. Habla con el botón de micrófono o escribe aquí abajo. Reconozco palabras cortas o cercanas para abrir cualquier menú, empresa o enlace, guardar notas, agendar en Google Calendar en tiempo real y enviar recordatorios por correo.",
        sendBtn: "ENVIAR",
        micBtn: "🎙️ VOZ",
        stopBtn: "⏹️ LISTO",
        fabBtn: "💬 CHATBOT · CONTROL",
        micFabBtn: "🎙️ HABLAR",
        chips: [
          ["📖 Todas las Funciones", "catálogo de funciones"],
          ["📹 55 Cámaras", "abrir cámaras"],
          ["🏢 UNITEC USA", "cambiar a unitec"],
          ["🏗️ BuildingApp", "cambiar a building"],
          ["📝 + Nota", "nota: Revisar despacho de contenedores WPC en Miami"],
          ["📅 + Cita Google Cal", "agendar cita Revisión ejecutiva UNITEC y Building mañana a las 10:00"],
          ["⏰ + Email Reminder", "recordatorio por correo Confirmar reporte de 55 cámaras mañana 09:00"],
          ["📰 Periódico PDF", "abrir periódico pdf"]
        ]
      },
      en: {
        title: "LA JEFATURA · MASTER VOICE & CHATBOT",
        sub: "Neural Voice · Full Menu, Link, Notes, Google Calendar & Email Control",
        placeholder: "Speak or type (e.g. 'cam', 'uni', 'note:...', 'appointment tomorrow 3pm', 'email reminder...')…",
        listening: "🎙️ Listening live… speak now",
        help: "Use full or close words: 'cameras / cam', 'unitec / uni', 'building / renders', 'espacios', 'nexus / crm', 'inbox', 'outcomes', 'newspaper pdf', 'note:...', 'schedule appointment tomorrow 3pm', or 'email reminder...'.",
        unknown: "I couldn't match that exact item and I never guess. Try a close word like 'cam', 'uni', 'building', 'schedule appointment...', 'note:...', or 'functions catalog'.",
        offline: "Local brain mode active.",
        open: "Ready, CEO. Click the microphone to talk or type below. I recognize close or partial words to open any menu, company, or link, save notes, sync appointments to Google Calendar in real time, and send email reminders.",
        sendBtn: "SEND",
        micBtn: "🎙️ VOICE",
        stopBtn: "⏹️ DONE",
        fabBtn: "💬 CHATBOT · CONTROL",
        micFabBtn: "🎙️ SPEAK",
        chips: [
          ["📖 All Functions", "functions catalog"],
          ["📹 55 Cameras", "open cameras"],
          ["🏢 UNITEC USA", "switch to unitec"],
          ["🏗️ BuildingApp", "switch to building"],
          ["📝 + Note", "note: Review WPC container dispatch in Miami"],
          ["📅 + Google Cal Event", "schedule appointment Executive review tomorrow at 10:00"],
          ["⏰ + Email Reminder", "email reminder Confirm 55 cameras report tomorrow 09:00"],
          ["📰 Newspaper PDF", "open newspaper pdf"]
        ]
      }
    };

    const state = { open: false, listening: false, speaking: false, log: [], channel: "text" };
    const actions = {};
    window.LJ = window.LJ || {};
    window.LJ.register = (name, fn) => { actions[name] = fn; };
    window.LJ.execute = execute;
    window.LJ.inspectDOM = inspectDOM;

    function getLang() {
      const dLang = (document.documentElement.lang || "").toLowerCase();
      if (dLang.startsWith("en")) { CFG.lang = "en"; return "en"; }
      if (dLang.startsWith("es")) { CFG.lang = "es"; return "es"; }
      return CFG.lang === "en" ? "en" : "es";
    }

    function getT() {
      return COPY[getLang()] || COPY.es;
    }

    window.LJ.setLang = (l) => {
      const nextLang = (l && String(l).toLowerCase().startsWith("en")) ? "en" : "es";
      CFG.lang = nextLang;
      if (window.LJ_WIDGET) window.LJ_WIDGET.lang = nextLang;
      document.documentElement.lang = nextLang;
      stopAudio();
      renderPanelLocale();
      renderLog();
    };
    window.LJ.speak = (t, logIt = false, langOverride = null) => speak(t, logIt, langOverride);

    function highlightElement(el) {
      if (!el) return;
      el.classList.remove("lj-voice-touch");
      void el.offsetWidth;
      el.classList.add("lj-voice-touch");
      try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (_) {}
      setTimeout(() => el.classList.remove("lj-voice-touch"), 2200);
    }

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

    let currentAudio = null;
    let speakSeq = 0;
    let manuallyStopped = false;

    function _setSpeakingUI(isSpeaking) {
      state.speaking = isSpeaking;
      const curLang = getLang();
      if (root) root.classList.toggle("speaking", isSpeaking);
      const bar = document.getElementById("ljGlobalStopBar");
      if (bar) bar.style.display = isSpeaking ? "flex" : "none";
      const stopBtns = document.querySelectorAll(".lj-stop-voice-btn");
      stopBtns.forEach(b => {
        b.style.opacity = isSpeaking ? "1" : "0.9";
        b.classList.toggle("is-speaking", isSpeaking);
      });
      const stopFab = document.getElementById("ljw-stop-fab");
      if (stopFab) stopFab.style.display = isSpeaking ? "inline-flex" : "none";
      const playBriefBtn = document.getElementById("headerPlayBriefBtn");
      if (playBriefBtn) {
        if (isSpeaking) {
          playBriefBtn.textContent = curLang === "en" ? "🛑 SPEAKING · CLICK TO STOP" : "🛑 HABLANDO · CLIC PARA CALLAR";
          playBriefBtn.style.background = "#EB5757";
          playBriefBtn.style.color = "#FFFFFF";
          playBriefBtn.style.borderColor = "#EB5757";
        } else {
          playBriefBtn.textContent = curLang === "en" ? "🔊 Listen Summary" : "🔊 Escuchar Resumen";
          playBriefBtn.style.background = "rgba(16,185,129,.14)";
          playBriefBtn.style.color = "#10B981";
          playBriefBtn.style.borderColor = "rgba(16,185,129,.4)";
        }
      }
      if (typeof fab !== "undefined" && fab) {
        if (isSpeaking) {
          fab.textContent = curLang === "en" ? "🛑 STOP / OPEN CHAT" : "🛑 CALLAR / ABRIR CHAT";
          fab.style.background = "#EB5757";
          fab.style.color = "#FFFFFF";
          fab.style.borderColor = "#EB5757";
        } else {
          fab.textContent = getT().fabBtn;
          fab.style.background = "#ffffff";
          fab.style.color = "#12100d";
          fab.style.borderColor = "#cdb68c";
        }
      }
    }

    function stopAudio() {
      speakSeq++;
      manuallyStopped = true;
      window._ljUserStoppedSpeech = true;
      try { window.jfPendingSpeech = null; } catch (_) {}
      try {
        if (currentAudio) {
          currentAudio.onplay = null;
          currentAudio.onended = null;
          currentAudio.onerror = null;
          currentAudio.pause();
          currentAudio.currentTime = 0;
          currentAudio = null;
        }
      } catch (_) {}
      try {
        if (window._commsTtsAudio) {
          window._commsTtsAudio.pause();
          window._commsTtsAudio = null;
        }
      } catch (_) {}
      try {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      } catch (_) {}
      _setSpeakingUI(false);
    }
    window.LJ.stopAudio = stopAudio;
    window.LJ.isSpeaking = () => Boolean(state.speaking);
    window.stopAllBotVoice = stopAudio;

    function _browserFallbackSpeak(text, langCode, mySeq) {
      if (manuallyStopped || mySeq !== speakSeq) return;
      if (!("speechSynthesis" in window)) { _setSpeakingUI(false); return; }
      try {
        const curLang = (langCode || getLang()) === "en" ? "en" : "es";
        const u = new SpeechSynthesisUtterance(text);
        u.lang = curLang === "en" ? "en-US" : "es-CO";
        u.rate = 1.22;
        const voices = window.speechSynthesis.getVoices() || [];
        if (curLang === "en") {
          const enVoice = voices.find(v => /^en[-_]US/i.test(v.lang)) || voices.find(v => /^en/i.test(v.lang));
          if (enVoice) u.voice = enVoice;
        } else {
          const coVoice = voices.find(v => /es[-_]CO/i.test(v.lang)) ||
                          voices.find(v => /Salome|Gonzalo|Colomb/i.test(v.name)) ||
                          voices.find(v => /^es/i.test(v.lang));
          if (coVoice) u.voice = coVoice;
        }
        u.onstart = () => { if (!manuallyStopped && mySeq === speakSeq) _setSpeakingUI(true); else window.speechSynthesis.cancel(); };
        u.onend = () => { if (mySeq === speakSeq) _setSpeakingUI(false); };
        u.onerror = () => { if (mySeq === speakSeq) _setSpeakingUI(false); };
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
      } catch (_) {
        _setSpeakingUI(false);
      }
    }

    function speak(text, logIt = true, langOverride = null, extraMeta = null) {
      if (!text) return;
      const curLang = (langOverride || getLang()) === "en" ? "en" : "es";
      if (logIt) {
        state.log.push({ who: "lj", text, meta: extraMeta || null });
        renderLog();
      }
      try {
        if (currentAudio) {
          currentAudio.onplay = null;
          currentAudio.onended = null;
          currentAudio.onerror = null;
          currentAudio.pause();
          currentAudio = null;
        }
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      } catch (_) {}

      const mySeq = ++speakSeq;
      manuallyStopped = false;
      _setSpeakingUI(true);

      const url = (CFG.api || "") + "/api/tts?lang=" + encodeURIComponent(curLang) +
                  "&rate=" + encodeURIComponent("+22%") +
                  "&text=" + encodeURIComponent((text || "").slice(0, 850));
      try {
        const a = new Audio(url);
        currentAudio = a;
        a.onplay = () => {
          if (manuallyStopped || mySeq !== speakSeq) { a.pause(); return; }
          _setSpeakingUI(true);
        };
        a.onended = () => {
          if (mySeq === speakSeq) { _setSpeakingUI(false); currentAudio = null; }
        };
        a.onerror = () => {
          if (manuallyStopped || mySeq !== speakSeq) return;
          currentAudio = null;
          _browserFallbackSpeak(text, curLang, mySeq);
        };
        const p = a.play();
        if (p && typeof p.catch === "function") {
          p.catch(() => {
            if (manuallyStopped || mySeq !== speakSeq) return;
            currentAudio = null;
            _browserFallbackSpeak(text, curLang, mySeq);
          });
        }
      } catch (_) {
        if (!manuallyStopped && mySeq === speakSeq) {
          _browserFallbackSpeak(text, curLang, mySeq);
        }
      }
    }

    function execute(rawText, channelOverride = null) {
      const text = (rawText || "").trim();
      if (!text) return;
      const curLang = getLang();
      const T = getT();
      const ch = channelOverride || state.channel || "text";

      state.log.push({ who: "user", text });
      renderLog();

      if (window.LJ_BEHAVIOR && typeof window.LJ_BEHAVIOR.track === "function") {
        window.LJ_BEHAVIOR.track("voice_query", "master_command", { text, channel: ch });
      }

      // Route ALL commands through the unified Server Voice & Close-Word Catalog Router (/api/voice/command)
      fetch((CFG.api || "") + "/api/voice/command", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, CFG.token ? { "X-MC-Token": CFG.token } : {}),
        body: JSON.stringify({ command: text, tenant: CFG.tenant, lang: curLang, channel: ch }),
      })
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(d => {
          const replyLang = (d.ui && d.ui.set_lang) ? d.ui.set_lang : getLang();
          if (d.ui && typeof window.LJ_applyUi === "function") {
            window.LJ_applyUi(d.ui);
          }
          if (typeof window.loadKnowledgeVault === "function") window.loadKnowledgeVault(false);
          if (typeof window.loadProjectMemoryBox === "function") window.loadProjectMemoryBox();
          if (window.LJCal && typeof window.LJCal.load === "function") window.LJCal.load();
          if (typeof window.updateMasterControlChatFeedback === "function") {
            window.updateMasterControlChatFeedback(text, d);
          }
          const spokenReply = d.reply || T.unknown;
          speak(spokenReply, true, replyLang, {
            matched_function: d.matched_function || null,
            ui: d.ui || null,
            gcal_sync: d.gcal_sync || null,
            record: d.record || null,
            sources: d.sources || []
          });
        })
        .catch(() => {
          speak(
            curLang === "es"
              ? "No pude consultar el servidor en este momento; jamás invento una respuesta."
              : "I couldn't reach the server right now; I never make up an answer.",
            true,
            curLang
          );
        });

      return { ok: true, delegated: true };
    }

    /* ── Widget Styles & DOM ── */
    const css = `
.lj-voice-touch{outline:2px solid #10b981 !important;box-shadow:0 0 0 6px rgba(16,185,129,.35) !important;transition:box-shadow .25s ease !important}
#ljw{position:fixed;${CFG.position.includes("left") ? "left:20px" : "right:20px"};bottom:18px;z-index:9999;font-family:-apple-system,'SF Pro Display',Inter,Segoe UI,sans-serif}
#ljw .fab-row{display:flex;align-items:center;gap:8px;justify-content:flex-end}
#ljw .fab,#ljw .mic-fab,#ljw .stop-fab{padding:0 16px;height:44px;border-radius:999px;border:1px solid #cdb68c;cursor:pointer;font-size:11.5px;font-weight:800;letter-spacing:.06em;box-shadow:0 10px 28px rgba(0,0,0,.45);transition:.2s;display:inline-flex;align-items:center;justify-content:center;gap:7px}
#ljw .fab{background:#ffffff;color:#12100d}
#ljw .mic-fab{background:linear-gradient(135deg,#10b981,#059669);color:#ffffff;border-color:#10b981}
#ljw .mic-fab.on{background:#EB5757;border-color:#EB5757;animation:ljpulse 1.1s infinite}
#ljw .stop-fab{background:#EB5757;color:#ffffff;border-color:#EB5757;display:none}
#ljw .fab:hover,#ljw .mic-fab:hover{transform:translateY(-1px)}
#ljw .fab.on,#ljw.speaking .fab{animation:ljpulse 1.4s infinite}
@keyframes ljpulse{50%{box-shadow:0 0 0 12px rgba(235,87,87,.32)}}
#ljw .panel{position:absolute;bottom:56px;${CFG.position.includes("left") ? "left:0" : "right:0"};width:410px;max-width:94vw;max-height:580px;background:#ffffff;color:#18181b;border:1px solid #e5d8c0;border-radius:18px;box-shadow:0 22px 60px rgba(0,0,0,.55);display:none;flex-direction:column;overflow:hidden}
#ljw .panel.open{display:flex}
#ljw .head{padding:12px 15px;background:#faf8f5;border-bottom:1px solid #ece7df;display:flex;justify-content:space-between;align-items:center;gap:8px}
#ljw .head-title{color:#12100d;font-size:11.5px;font-weight:900;letter-spacing:.6px}
#ljw .head-sub{color:#8e734b;font-size:10px;margin-top:2px;display:flex;align-items:center;gap:5px;font-weight:600}
#ljw .wave{display:flex;gap:3px;align-items:center;height:16px}
#ljw .wave span{width:3px;height:6px;background:#8e734b;border-radius:2px;transition:.2s}
#ljw.speaking .wave span{animation:ljwave .7s infinite ease-in-out}
@keyframes ljwave{0%,100%{height:5px}50%{height:16px}}
#ljw .chips{display:flex;flex-wrap:wrap;gap:5px;padding:8px 12px;border-bottom:1px solid #ece7df;background:#f8f6f2}
#ljw .chip{background:#ffffff;border:1px solid #dcd5c7;color:#27272a;font-size:10.5px;font-weight:700;padding:4px 9px;border-radius:14px;cursor:pointer;transition:.15s}
#ljw .chip:hover{background:#f5efe4;border-color:#8e734b;color:#12100d}
#ljw .log{flex:1;overflow-y:auto;padding:12px 14px;font-size:12.5px;min-height:190px;max-height:290px;background:#ffffff;color:#18181b}
#ljw .msg{margin-bottom:9px;line-height:1.45;padding:8px 11px;border-radius:10px}
#ljw .msg.user{background:#f5efe4;color:#12100d;border:1px solid #e5d8c0;margin-left:28px;text-align:right;font-weight:600}
#ljw .msg.lj{background:#f8f6f2;color:#18181b;margin-right:12px;border-left:3px solid #8e734b}
#ljw .fn-meta{margin-top:6px;padding:6px 8px;border-radius:8px;background:#ffffff;border:1px solid #e5d8c0;font-size:11px;line-height:1.4}
#ljw .fn-links{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px}
#ljw .fn-links a{display:inline-block;padding:3px 8px;border-radius:999px;background:#10b981;color:#fff;font-size:10px;font-weight:800;text-decoration:none}
#ljw .input{display:flex;border-top:1px solid #ece7df;background:#ffffff;align-items:center}
#ljw .input input{flex:1;background:none;border:0;color:#18181b;padding:12px 12px;font-size:12.5px;outline:none}
#ljw .input button{background:none;border:0;color:#8e734b;font-size:12px;cursor:pointer;padding:0 10px;font-weight:800}`;

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
            <div class="head-sub"><span style="width:6px;height:6px;border-radius:50%;background:#10b981;display:inline-block"></span><span id="ljw-sub"></span></div>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <button type="button" id="ljw-stop-voice" class="lj-stop-voice-btn" title="Callar voz inmediatamente (Esc)" style="background:#EB5757;color:#fff;border:0;border-radius:999px;padding:4px 10px;font-size:10.5px;font-weight:900;cursor:pointer">🛑 CALLAR</button>
            <button type="button" id="ljw-close-panel" title="Cerrar panel" style="background:transparent;border:0;color:#18181b;font-size:16px;font-weight:900;cursor:pointer;padding:0 4px">✕</button>
          </div>
        </div>
        <div class="chips" id="ljw-chips"></div>
        <div class="log" id="ljw-log"></div>
        <div class="input">
          <input id="ljw-in" autocomplete="off">
          <button type="button" id="ljw-send" title="Enviar orden">ENVIAR</button>
          <button type="button" id="ljw-mic" title="Hablar por micrófono" style="color:#10b981">🎙️ VOZ</button>
          <button type="button" id="ljw-quiet" title="Detener voz" style="color:#EB5757;font-weight:900">🛑</button>
        </div>
      </div>
      <div class="fab-row">
        <button type="button" class="stop-fab" id="ljw-stop-fab" title="Detener voz ahora">🛑 CALLAR VOZ</button>
        <button type="button" class="mic-fab" id="ljw-mic-fab" title="Hablar por voz con La Jefatura">🎙️ HABLAR</button>
        <button type="button" class="fab" id="ljw-fab" title="Abrir Chatbot y Control Maestro">💬 CHATBOT · CONTROL</button>
      </div>`;
    document.body.appendChild(root);

    const $ = (s) => root.querySelector(s);
    const panel = $("#ljw-panel"), fab = $("#ljw-fab"), micFab = $("#ljw-mic-fab"), stopFab = $("#ljw-stop-fab"), input = $("#ljw-in"), log = $("#ljw-log"), chips = $("#ljw-chips");

    function renderPanelLocale() {
      const T = getT();
      $("#ljw-title").textContent = T.title;
      $("#ljw-sub").textContent = T.sub;
      input.placeholder = T.placeholder;
      $("#ljw-send").textContent = T.sendBtn;
      $("#ljw-mic").textContent = state.listening ? T.stopBtn : T.micBtn;
      if (micFab) micFab.textContent = state.listening ? "⏹️ ESCUCHANDO…" : T.micFabBtn;
      fab.textContent = T.fabBtn;
      chips.innerHTML = T.chips.map(([label, cmd]) =>
        `<button type="button" class="chip" data-cmd="${cmd.replace(/"/g, '&quot;')}">${label}</button>`
      ).join("");
      chips.querySelectorAll(".chip").forEach(btn => {
        btn.onclick = () => execute(btn.getAttribute("data-cmd"), "text");
      });
    }

    function renderLog() {
      log.innerHTML = state.log.slice(-30).map(m => {
        let extra = "";
        if (m.meta) {
          const mf = m.meta.matched_function;
          const ui = m.meta.ui || {};
          if (mf) {
            extra += `<div class="fn-meta">
              <b>⚡ ${mf.title_es}</b><br>
              <span><b>Qué hace:</b> ${mf.what_it_does_es}</span><br>
              <span style="color:#52525b"><b>Cómo funciona:</b> ${mf.how_it_works_es}</span>
            </div>`;
          }
          const links = [];
          if (ui.gcal_template_url) {
            links.push(`<a href="${ui.gcal_template_url}" target="_blank" rel="noopener">📅 Confirmar en Google Calendar</a>`);
          }
          if (ui.gmail_compose_url) {
            links.push(`<a href="${ui.gmail_compose_url}" target="_blank" rel="noopener" style="background:#2563eb">✉️ Abrir Recordatorio en Gmail</a>`);
          }
          if (ui.open_url) {
            links.push(`<a href="${ui.open_url}" target="_blank" rel="noopener" style="background:#8e734b">🔗 Abrir Enlace / PDF</a>`);
          }
          if (links.length) {
            extra += `<div class="fn-links">${links.join("")}</div>`;
          }
        }
        return `<div class="msg ${m.who}"><div>${m.text}</div>${extra}</div>`;
      }).join("");
      log.scrollTop = log.scrollHeight;
    }

    function openPanelAndFocus(stopCurrentSpeech = true) {
      if (state.speaking) {
        if (stopCurrentSpeech) stopAudio();
      }
      state.open = true;
      panel.classList.add("open");
      if (!state.log.length) {
        state.log.push({ who: "lj", text: getT().open });
        renderLog();
      }
      setTimeout(() => input.focus(), 60);
    }
    window.LJ.openChat = openPanelAndFocus;

    fab.onclick = () => {
      if (state.speaking) {
        stopAudio();
      }
      state.open = !state.open;
      panel.classList.toggle("open", state.open);
      if (state.open) {
        if (!state.log.length) {
          state.log.push({ who: "lj", text: getT().open });
          renderLog();
        }
        setTimeout(() => input.focus(), 60);
      }
    };

    if ($("#ljw-close-panel")) {
      $("#ljw-close-panel").onclick = () => {
        state.open = false;
        panel.classList.remove("open");
      };
    }

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        const val = input.value.trim();
        input.value = "";
        execute(val, "text");
      }
    });
    $("#ljw-send").onclick = () => {
      if (input.value.trim()) {
        const val = input.value.trim();
        input.value = "";
        execute(val, "text");
      }
    };

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    let rec = null;
    let lastTranscript = "";

    function startMic(targetInputEl = null) {
      const curLang = getLang();
      const T = getT();
      stopAudio();
      openPanelAndFocus(true);

      if (!SR) {
        state.log.push({
          who: "lj",
          text: curLang === "es"
            ? "Tu navegador actual bloqueó el micrófono directo. Escribe tu orden en la caja de texto aquí abajo (reconozco palabras cercanas, notas, citas y recordatorios)."
            : "Your browser blocked direct microphone access. Type your command in the box below."
        });
        renderLog();
        input.focus();
        return;
      }
      if (state.listening && rec) {
        try { rec.stop(); } catch (_) {}
        return;
      }
      lastTranscript = "";
      rec = new SR();
      rec.lang = curLang === "en" ? "en-US" : "es-CO";
      rec.interimResults = true;
      rec.continuous = false;
      rec.maxAlternatives = 1;
      rec.onstart = () => {
        state.listening = true;
        fab.classList.add("on");
        if (micFab) { micFab.classList.add("on"); micFab.textContent = "⏹️ ESCUCHANDO…"; }
        $("#ljw-mic").textContent = T.stopBtn;
        input.placeholder = T.listening;
        const mcBtn = document.getElementById("mcVoiceMicBtn");
        if (mcBtn) { mcBtn.textContent = "⏹️ ESCUCHANDO EN VIVO… (CLIC PARA ENVIAR)"; mcBtn.style.background = "#EB5757"; }
      };
      rec.onresult = (e) => {
        let interim = "";
        let finalTxt = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const tr = e.results[i][0].transcript;
          if (e.results[i].isFinal) finalTxt += tr;
          else interim += tr;
        }
        const combined = (finalTxt || interim || "").trim();
        if (combined) {
          lastTranscript = combined;
          input.value = combined;
          if (targetInputEl) targetInputEl.value = combined;
          const mcInp = document.getElementById("masterControlChatInput");
          if (mcInp) mcInp.value = combined;
        }
      };
      rec.onend = () => {
        state.listening = false;
        fab.classList.remove("on");
        if (micFab) { micFab.classList.remove("on"); micFab.textContent = getT().micFabBtn; }
        $("#ljw-mic").textContent = getT().micBtn;
        input.placeholder = getT().placeholder;
        const mcBtn = document.getElementById("mcVoiceMicBtn");
        if (mcBtn) { mcBtn.textContent = "🎙️ HABLAR POR VOZ"; mcBtn.style.background = "#10B981"; }
        if (lastTranscript.trim()) {
          const toRun = lastTranscript.trim();
          lastTranscript = "";
          input.value = "";
          const mcInp = document.getElementById("masterControlChatInput");
          if (mcInp) mcInp.value = "";
          state.channel = "voice";
          execute(toRun, "voice");
          state.channel = "text";
        }
      };
      rec.onerror = (ev) => {
        state.listening = false;
        fab.classList.remove("on");
        if (micFab) { micFab.classList.remove("on"); micFab.textContent = getT().micFabBtn; }
        $("#ljw-mic").textContent = getT().micBtn;
        const mcBtn = document.getElementById("mcVoiceMicBtn");
        if (mcBtn) { mcBtn.textContent = "🎙️ HABLAR POR VOZ"; mcBtn.style.background = "#10B981"; }
        if (ev && ev.error === "not-allowed") {
          state.log.push({
            who: "lj",
            text: "Permiso de micrófono denegado en el navegador. Haz clic en el ícono de candado/micrófono de la barra de dirección para permitirlo, o escribe tu comando aquí abajo."
          });
          renderLog();
        }
      };
      try {
        rec.start();
      } catch (_) {}
    }

    window.LJ.startMic = startMic;

    $("#ljw-mic").onclick = () => startMic();
    if (micFab) micFab.onclick = () => startMic();
    if (stopFab) stopFab.onclick = (e) => { e.stopPropagation(); stopAudio(); };
    if ($("#ljw-stop-voice")) $("#ljw-stop-voice").onclick = (e) => { e.stopPropagation(); stopAudio(); };
    if ($("#ljw-quiet")) $("#ljw-quiet").onclick = (e) => { e.stopPropagation(); stopAudio(); };
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") stopAudio();
    });
    fab.addEventListener("contextmenu", (e) => { e.preventDefault(); startMic(); });

    renderPanelLocale();
  }

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();

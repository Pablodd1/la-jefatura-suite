# Architecture

```
                        ┌────────────────────────────────────────────┐
                        │              LA JEFATURA SUITE             │
                        └────────────────────────────────────────────┘

 NEXUS CRM (sellers)                    MISSION CONTROL (mc.db, port 8090)
 ┌──────────────────────┐   PATH A      ┌────────────────────────────────┐
 │ Nexus repo: replace  │ ────────────► │ server/nexus_ingest.py         │
 │ IndexedDB layer with │  POST /api/   │  · nexus_leads (upsert)        │
 │ POST /api/nexus/push │  nexus/push   │  · nexus_visits (upsert)       │
 └──────────────────────┘               │  · summary() = dashboard shape │
           OR (zero repo access)        └───────┬────────────────────────┘
 ┌──────────────────────┐               PATH B   │ reads
 │ scripts/             │ ──────────────────────►│
 │ nexus_bridge_        │   POST every 5 min     ▼
 │ snippet.js           │               ┌────────────────────────────────┐
 │ (userscript in CRM   │               │ CEO CONSOLE (mock/demo.html)   │
 │  tab, reads Dexie)   │               │  · company switcher (5 cos)    │
 └──────────────────────┘               │  · KPI tiles / agenda / tasks  │
                                        │  · pipeline funnel + by country│
 CAMERAS (unknown brands yet)           │  · TG alerts + Gmail unread    │
 ┌──────────────────────┐               │  · camera tiles (demo=canvas,  │
 │ server/cameras.py    │               │    real=GET /snap/:id)         │
 │  · ONVIF discovery   │               │  · EN/ES by page setting       │
 │  · ffmpeg snapshots  │               │  · client PDF via jsPDF        │
 │  · ffmpeg motion     │               └───────┬────────────────────────┘
 │  · cam_events log    │                       │
 └─────────┬────────────┘               ┌───────▼────────────────────────┐
           │ snapshots + events         │ server/reports_pdf.py          │
           ▼                            │  · collect (nexus + tasks +    │
 ┌──────────────────────┐               │    agenda + cams)              │
 │ server/ai_insights.py│ ◄──────────── │  · aggregate (SQL/code — never │
 │  · Gemini temp=0     │   pre-computed│    LLM math)                   │
 │  · report_narative   │   metrics     │  · AI narrative (fallback      │
 │  · lead_insight      │               │    template if no key)         │
 │  · camera digest     │               │  · reportlab + matplotlib PDF  │
 └──────────────────────┘               └───────┬────────────────────────┘
                                                │ distribute
                          ┌─────────────────────▼───────────────────────┐
                          │ Telegram (text + edge-tts voice brief,        │
                          │ 8:17am Miami) · email (Brevo) · /api/report   │
                          └─────────────────────────────────────────────┘
```

## Voice & widget layer (added per owner request Oct 22)

```
Tenant site / console          window.LJ.register(action, fn)
       │                       (demo.html registers 6 actions)
       ▼                                  │
 widgets/lajefatura-widget.js ──parse──┐  │ local action? run it + TTS reply
 (Web Speech STT/TTS, bilingual,     │  │
  text fallback, zero deps)           ▼  ▼
                              no local → POST /api/voice/command
                                          (server/voice_commands.py —
                                           same grammar, mutates real state:
                                           tasks→mc.db, PDF→reportlab,
                                           digests→ai_insights)
```

Control-plane rule: **voice commands are deterministic** (regex grammar,
no LLM in the loop). AI only narrates digests/briefs — never decides what
a command means. Telegram/WhatsApp voice notes plug into the same executor
later via the Whisper hook documented in `voice_commands.py`.

## Data contract (the piece that must never drift)

`nexus_ingest.summary()` returns exactly what the Nexus dashboard displays:
`kpis{leads_activos, pipeline_total_estimado_usd, ventas_cerradas_total_usd,
visitas_registradas}`, `pipeline_por_etapa[{etapa,count,valor_usd}]`,
`pipeline_por_pais`, `top_vendedores`, `visitas_recientes`, `top_leads`.
The demo HTML, the PDF generator, and any future frontend all consume this
one shape — validated by `data/samples/nexus_crm.json`.

## AI usage (only where it earns its cost)

| Surface | Model | Job | Fallback |
|---|---|---|---|
| Executive narrative (PDF + brief) | gemini-2.5-flash, temp 0 | narrate pre-computed KPIs in 3 paragraphs | template string |
| Lead insights | same | one-line "why now" per lead | value+stage line |
| Camera digest | same (+ vision on newest snapshot) | summarize event list, flag out-of-hours | rule-based sentence |
| Voice brief | edge-tts `es-US-AlonsoNeural` | TTS of the brief | text-only |

## White-label multi-tenancy (the 10-company ask)

- `companies` table drives the switcher; every data table carries `company_id`.
- The PDF report is parameterized by company → one cron job generates N
  reports, one per tenant.
- Per-tenant branding = name + accent color + logo slot on the cover.

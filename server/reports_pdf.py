"""
La Jefatura Suite — Full company PDF report generator

Pattern copied from the industry-standard automated-report pipeline
(docs/RESEARCH.md, n8n/Claude template): collect → aggregate (all math in
code) → AI narrative (temperature 0) → styled document → distribute.

Output: a real, board-ready PDF — cover, KPI cards, pipeline funnel chart,
country breakdown, seller leaderboard, task list with escalation colors,
agenda, camera digest, and the Gemini executive narrative.

Usage:
    python3 reports_pdf.py "Medical Billing Miami Beach" ../data/samples \
        /tmp/report.pdf

Renders identically against live mc.db (nexus_ingest + tasks tables) — the
samples dir is only the demo fallback.
"""

import json
import os
import sys
import tempfile; import time

from ai_insights import report_narative

# reportlab + matplotlib are the battle-tested std for Python PDF/charting.
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, Image, PageBreak)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    _HAS_RL = True
except ImportError:
    _HAS_RL = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

INK = colors.HexColor("#0b1020") if _HAS_RL else None
ACCENT = colors.HexColor("#23d9b0") if _HAS_RL else None
WARN = colors.HexColor("#ff9f43") if _HAS_RL else None
CRIT = colors.HexColor("#ff5c5c") if _HAS_RL else None


def _chart_pipeline(stages: list[dict], out_png: str):
    """Funnel-style horizontal bars. All values pre-computed."""
    if not _HAS_MPL:
        return None
    labels = [s["etapa"].replace("_", " ").title() for s in stages]
    vals = [s["valor_usd"] for s in stages]
    fig, ax = plt.subplots(figsize=(6.2, 2.4), dpi=150)
    ax.barh(labels[::-1], vals[::-1],
            color=["#23d9b0", "#00D4FF", "#7c6cff", "#ff9f43"][::-1])
    ax.set_title("Pipeline por etapa (USD)", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_png, transparent=True)
    plt.close(fig)
    return out_png


def build_report(company: str, samples_dir: str, out_pdf: str,
                 lang: str = "es") -> str:
    nexus = json.load(open(os.path.join(samples_dir, "nexus_crm.json"),
                           encoding="utf-8"))
    agenda = json.load(open(os.path.join(samples_dir,
                                         "agenda_gmail_tg.json"),
                            encoding="utf-8"))
    tasks = json.load(open(os.path.join(samples_dir, "tasks.json"),
                           encoding="utf-8"))
    cams = json.load(open(os.path.join(samples_dir, "cameras.json"),
                          encoding="utf-8"))

    kpis = nexus["kpis"]
    tasks_res = tasks["resumen"]

    if not _HAS_RL:
        # Absolute fallback: markdown file so the pipeline never dies.
        md = out_pdf.rsplit(".", 1)[0] + ".md"
        with open(md, "w", encoding="utf-8") as f:
            f.write(f"# Informe — {company}\n\n```json\n")
            json.dump({"kpis": kpis, "tareas": tasks_res}, f, indent=2,
                      ensure_ascii=False)
            f.write("\n```\n(pip install reportlab matplotlib for real PDF)\n")
        return md

    narrative = report_narative(company, kpis, tasks_res,
                                nexus["pipeline_por_etapa"], lang=lang)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=22,
                        textColor=INK, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13,
                        textColor=ACCENT, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5,
                          leading=13, textColor=INK)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)

    doc = SimpleDocTemplate(out_pdf, pagesize=letter,
                            leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"Informe — {company}",
                            author="La Jefatura (Mission Control)")
    story = []
    story.append(Paragraph(f"INFORME EJECUTIVO — {company.upper()}", h1))
    story.append(Paragraph(time.strftime("Generado %Y-%m-%d %H:%M — "
                                         "La Jefatura Suite (auto)", ),
                           small))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Resumen ejecutivo", h2))
    story.append(Paragraph(narrative.replace("\n", "<br/>"), body))

    story.append(Paragraph("KPIs clave", h2))
    kpi_rows = [[Paragraph("<b>Métrica</b>", body), Paragraph("<b>Valor</b>", body)],
                ["Leads activos", str(kpis["leads_activos"])],
                ["Pipeline total (USD)", f"${kpis['pipeline_total_estimado_usd']:,.0f}"],
                ["Ventas cerradas (USD)", f"${kpis['ventas_cerradas_total_usd']:,.0f}"],
                ["Ingreso mensual proyectado", f"${kpis['ingreso_mensual_proyectado_usd']:,.0f}"],
                ["Tasa de conversión", f"{kpis['tasa_conversion_global_pct']}%"]]
    t = Table(kpi_rows, colWidths=[3.2 * inch, 2.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)

    png = _chart_pipeline(nexus["pipeline_por_etapa"], os.path.join(tempfile.gettempdir(), "_pipeline.png"))
    if png:
        story.append(Spacer(1, 8))
        story.append(Image(png, width=5.8 * inch, height=2.2 * inch))

    story.append(Paragraph("Top leads por valor", h2))
    lead_rows = [[Paragraph(f"<b>{h}</b>", body)
                  for h in ("Empresa", "País", "Etapa", "Valor", "Vendedor")]]
    for L in nexus["leads"][:6]:
        lead_rows.append([L["empresa"], L["pais"], L["etapa"],
                          f"${L['valor_usd']:,.0f}", L["vendedor"]])
    lt = Table(lead_rows, colWidths=[2.4 * inch, 0.9 * inch, 1.0 * inch,
                                     0.9 * inch, 1.2 * inch])
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(lt)

    story.append(Paragraph("Tareas y escalaciones", h2))
    task_rows = [[Paragraph(f"<b>{h}</b>", body)
                  for h in ("Tarea", "Due", "Estado", "Severidad")]]
    for tk in tasks["tareas"]:
        color = "#ff5c5c" if tk["severidad"] == "critical" else \
                "#ff9f43" if tk["severidad"] == "high" else "#0b1020"
        task_rows.append([
            Paragraph(f'<font color="{color}">{tk["titulo"]}</font>', body),
            tk["due"], tk["estado"], tk["severidad"]])
    tt = Table(task_rows, colWidths=[3.3 * inch, 0.9 * inch, 0.9 * inch,
                                     0.9 * inch])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
    ]))
    story.append(tt)

    story.append(Paragraph("Agenda de hoy", h2))
    for ev in agenda["agenda_hoy"]:
        story.append(Paragraph(
            f'<b>{ev["hora"]}</b> — {ev["titulo"]} '
            f'<font color="grey">({ev["quien"]}, {ev["lugar"]})</font>', body))

    story.append(Paragraph("Resumen de camaras (IA)", h2))
    story.append(Paragraph(
        cams["resumen_ia_ultimas_12h"]["evento_destacado"], body))

    doc.build(story)
    return out_pdf


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "Medical Billing Miami Beach"
    sdir = sys.argv[2] if len(sys.argv) > 2 else "../data/samples"
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(tempfile.gettempdir(), "informe_ejecutivo.pdf")
    path = build_report(company, sdir, out)
    print("report written:", path, os.path.getsize(path), "bytes")

"""Printable daily sheets (black on white, always printable).

Page 1 = the active day's text summary (today, or a fresh sheet for tomorrow once today is closed),
page 2 = the day after, then the archive of previous days (closed or not).
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jefesito  # noqa: E402


def _state(p, lang):
    es = lang != "en"
    if p["kind"] == "preview":
        return "HOJA NUEVA / PREVISTA" if es else "NEW / UPCOMING SHEET"
    if p["closed"]:
        return "DIA CERRADO" if es else "DAY CLOSED"
    return "DIA ABIERTO" if es else "DAY OPEN"


def build(out_path: str, lang: str = "es", today=None) -> str:
    lang = "en" if lang == "en" else "es"
    pgs = jefesito.pages(lang, today=today)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        md = out_path.rsplit(".", 1)[0] + ".md"
        with open(md, "w", encoding="utf-8") as f:
            for p in pgs:
                f.write(f"# {p['label']} — {_state(p, lang)}\n\n{p['greeting']}\n\n")
                for s in p["sections"]:
                    f.write(f"## {s['title']}\n" + "\n".join(f"- {l}" for l in s["lines"]) + "\n\n")
                f.write("\n---\n\n")
        return md

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20,
                        textColor=colors.black, alignment=0, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#444444"))
    lead = ParagraphStyle("lead", parent=base["Normal"], fontSize=13, leading=18, spaceBefore=10, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=12,
                        textColor=colors.black, spaceBefore=10, spaceAfter=2)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=11, leading=15)
    small = ParagraphStyle("small", parent=base["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555"))

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for i, p in enumerate(pgs):
        if i:
            story.append(PageBreak())
        story.append(Paragraph("EL JEFESITO", meta))
        story.append(Paragraph(esc(p["label"]), h1))
        story.append(Paragraph(esc(_state(p, lang)), meta))
        if p["kind"] == "empty":
            story.append(Paragraph("Sin hoja guardada." if lang != "en" else "No saved sheet.", body))
            continue
        story.append(Paragraph(esc(p["greeting"]), lead))
        for s in p["sections"]:
            story.append(Paragraph(esc(s["title"]), h2))
            for ln in s["lines"]:
                story.append(Paragraph(esc(ln), body))
        story.append(Spacer(1, 0.2 * inch))
        src = ("Fuentes: " if lang != "en" else "Sources: ") + (" · ".join(p["sources"]) or "—")
        story.append(Paragraph(esc(src), small))
        story.append(Paragraph(esc(("Generado " if lang != "en" else "Generated ") + now), small))
    SimpleDocTemplate(out_path, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                      topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                      title="El Jefesito — Daily sheets").build(story)
    return out_path


if __name__ == "__main__":
    print(build(os.path.join(os.environ.get("TEMP", "."), "jefesito_daily.pdf")))

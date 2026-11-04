"""La Jefatura — Executive PDF Report Builder (`server/reports_pdf.py`).

Delegates to the Morning Executive Newspaper PDF generator (`daily_pdf.build`)
so both `/api/daily.pdf` and `/api/report.pdf` produce the full, zero-guessing
"LA JEFATURA — EL PERIÓDICO MATUTINO DEL CEO · Made & Powered by Building Innovation"
with live weather, South America timezones, embedded matplotlib charts, CTO/CFO
project telemetry, and all CEO tasks, reminders, events, and memorized notes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import daily_pdf


def build_report(company: str, samples_dir: str, out_path: str, lang: str = "es") -> str:
    return daily_pdf.build(out_path, lang=lang, focus_company=company)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(HERE), "data", "report_test.pdf")
    path = build_report("Building Innovation", "", out, lang="es")
    print("report written:", path, os.path.getsize(path), "bytes")

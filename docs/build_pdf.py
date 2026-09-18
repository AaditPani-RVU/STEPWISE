#!/usr/bin/env python3
"""Render the markdown documents in docs/ to PDF.

The markdown is the source of truth; the PDFs are generated for human reading.
Regenerate them whenever a document changes (requirements spec, change control CC-4).

Usage:
    python docs/build_pdf.py                  # rebuild every .md in docs/
    python docs/build_pdf.py docs/FOO.md      # rebuild one file

Needs `weasyprint` and `markdown`, which are documentation-only dependencies and
deliberately not in the project requirements. The throwaway way to get them:

    uv venv /tmp/docsenv && uv pip install --python /tmp/docsenv/bin/python weasyprint markdown
    /tmp/docsenv/bin/python docs/build_pdf.py
"""

import re
import sys
from pathlib import Path

import markdown
from weasyprint import CSS, HTML

DOCS = Path(__file__).resolve().parent

STYLE = """
@page {
  size: A4; margin: 18mm 16mm 20mm 16mm;
  @top-right { content: string(doctitle);
               font-family: 'DejaVu Sans', sans-serif; font-size: 7.5pt; color: #8a8a8a; }
  @bottom-right { content: counter(page) " / " counter(pages);
               font-family: 'DejaVu Sans', sans-serif; font-size: 8pt; color: #8a8a8a; }
  @bottom-left { content: string(docdate);
               font-family: 'DejaVu Sans', sans-serif; font-size: 8pt; color: #b0b0b0; }
}
@page :first { @top-right { content: ""; } }
html { font-size: 10pt; }
body { font-family: 'DejaVu Serif', Georgia, serif; color: #1c1c1c; line-height: 1.45;
       hyphens: auto; -weasy-hyphens: auto; }
h1, h2, h3, h4 { font-family: 'DejaVu Sans', Helvetica, sans-serif; color: #15304a; line-height: 1.25; }
h1 { font-size: 21pt; margin: 0 0 4pt; letter-spacing: -0.3pt; string-set: doctitle content(); }
h1 + p { font-size: 9.5pt; color: #4a4a4a; }
h2 { font-size: 14pt; margin: 22pt 0 7pt; padding-bottom: 4pt;
     border-bottom: 1.6pt solid #15304a; break-after: avoid; break-before: page; }
body > h2:first-of-type { break-before: avoid; }
h3 { font-size: 11.5pt; margin: 15pt 0 5pt; color: #1f4468; break-after: avoid; }
h4 { font-size: 10pt; margin: 11pt 0 4pt; break-after: avoid; }
p { margin: 0 0 7pt; text-align: justify; }
strong { color: #0f2338; }
del { color: #8a8a8a; }
ul, ol { margin: 0 0 8pt; padding-left: 16pt; }
li { margin-bottom: 2.5pt; }
hr { border: 0; border-top: 0.6pt solid #d8dde3; margin: 14pt 0; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 12pt;
        font-family: 'DejaVu Sans', sans-serif; font-size: 7.8pt; line-height: 1.32; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #15304a; color: #fff; text-align: left; font-weight: 600;
     padding: 4.5pt 5pt; border: 0.5pt solid #15304a; }
td { padding: 4pt 5pt; border: 0.5pt solid #ccd4dc; vertical-align: top; text-align: left; }
tbody tr:nth-child(even) td { background: #f4f6f9; }
td:first-child { white-space: nowrap; font-weight: 600; color: #15304a; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt;
       background: #eef1f5; padding: 0.5pt 2.5pt; border-radius: 2pt; color: #123; }
th code, td code { font-size: 7.2pt; }
pre { background: #f4f6f9; border: 0.5pt solid #d8dde3; border-left: 2.5pt solid #15304a;
      padding: 7pt 9pt; margin: 6pt 0 11pt; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 7.8pt; line-height: 1.4; }
em { color: #333; }
blockquote { margin: 0 0 8pt; padding-left: 10pt; border-left: 2pt solid #ccd4dc; color: #444; }
.docdate { string-set: docdate content(); font-size: 0; height: 0; }
"""


def strikethrough(text: str) -> str:
    """python-markdown has no ~~del~~; apply it outside fenced blocks."""
    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i, part in enumerate(parts):
        if not part.startswith("```"):
            parts[i] = re.sub(r"~~(.+?)~~", r"<del>\1</del>", part)
    return "".join(parts)


def title_of(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.M)
    return match.group(1).strip() if match else fallback


def date_of(text: str) -> str:
    match = re.search(r"\b(20\d\d-\d\d-\d\d)\b", text)
    return match.group(1) if match else ""


def build(src: Path) -> Path:
    raw = src.read_text()
    body = markdown.markdown(
        strikethrough(raw),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    out = src.with_suffix(".pdf")
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{title_of(raw, src.stem)}</title></head><body>"
        f'<div class="docdate">{date_of(raw)}</div>{body}</body></html>'
    )
    HTML(string=html, base_url=str(src.parent)).write_pdf(out, stylesheets=[CSS(string=STYLE)])
    return out


def main() -> None:
    targets = [Path(a) for a in sys.argv[1:]] or [
        p for p in sorted(DOCS.glob("*.md")) if p.name != "README.md"
    ]
    if not targets:
        sys.exit(f"no markdown documents found in {DOCS}")
    for src in targets:
        print(f"{src} -> {build(src)}")


if __name__ == "__main__":
    main()

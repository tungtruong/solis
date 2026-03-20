#!/usr/bin/env python3
"""Render all TT99 Appendix I forms into editable HTML/PDF templates.

Input source:
  data/regulations/tt99_2025_appendix1_form_templates.json

Output directory:
  data/regulations/tt99_2025_template_engine/all_forms
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MM_TO_PT = 72.0 / 25.4


def mm(v: float) -> float:
    return v * MM_TO_PT


def detect_font() -> Tuple[str, str]:
    times_regular = Path("C:/Windows/Fonts/times.ttf")
    times_bold = Path("C:/Windows/Fonts/timesbd.ttf")
    arial_regular = Path("C:/Windows/Fonts/arial.ttf")
    arial_bold = Path("C:/Windows/Fonts/arialbd.ttf")

    if times_regular.exists() and times_bold.exists():
        pdfmetrics.registerFont(TTFont("FormSerifRegular", str(times_regular)))
        pdfmetrics.registerFont(TTFont("FormSerifBold", str(times_bold)))
        return "FormSerifRegular", "FormSerifBold"

    if arial_regular.exists() and arial_bold.exists():
        pdfmetrics.registerFont(TTFont("FormSansRegular", str(arial_regular)))
        pdfmetrics.registerFont(TTFont("FormSansBold", str(arial_bold)))
        return "FormSansRegular", "FormSansBold"

    return "Helvetica", "Helvetica-Bold"


def safe_code(code: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "_", code, flags=re.UNICODE)
    return cleaned.strip("_")


def should_landscape(form: Dict[str, object]) -> bool:
    table_schema = form.get("table_schema", {})
    col_count = len(table_schema.get("table_columns", [])) if isinstance(table_schema, dict) else 0
    return col_count >= 10 or str(form.get("form_group", "")).upper() == "LĐTL"


def render_html(form: Dict[str, object]) -> str:
    code = str(form["form_code"])
    title = str(form["title"])
    fields = form.get("fields", [])
    signatures = form.get("signatures", [])
    table_schema = form.get("table_schema", {})

    field_rows = "\n".join(
        f'<tr><td class="label">{html.escape(str(f.get("label", "")))}</td><td class="value"></td></tr>'
        for f in fields
    )

    table_html = ""
    if isinstance(table_schema, dict) and table_schema.get("has_grid"):
        cols = table_schema.get("table_columns", [])
        rows = table_schema.get("table_rows", [])
        if cols:
            header_cells = "".join(f"<th>{html.escape(str(c.get('label', '')))}</th>" for c in cols)
            body_count = max(8, len(rows))
            body_rows = "".join("<tr>" + "".join("<td></td>" for _ in cols) + "</tr>" for _ in range(body_count))
            table_html = (
                "<section><h3>Bảng nhập liệu</h3>"
                "<table class=\"grid\"><thead><tr>"
                + header_cells
                + "</tr></thead><tbody>"
                + body_rows
                + "</tbody></table></section>"
            )

    sig_html = ""
    if signatures:
        sig_html = "".join(f'<div class="sig">{html.escape(str(s))}<div class="hint">(Ký, họ tên)</div></div>' for s in signatures)
    else:
        sig_html = "".join('<div class="sig">Người ký<div class="hint">(Ký, họ tên)</div></div>' for _ in range(3))

    return f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)} ({html.escape(code)})</title>
  <style>
    @page {{ size: A4 {'landscape' if should_landscape(form) else 'portrait'}; margin: 0; }}
    body {{ margin: 0; background: #eef1f5; font-family: 'Times New Roman', serif; color: #111; }}
    .toolbar {{ position: sticky; top: 0; background: #101317; color: #fff; padding: 8px 12px; z-index: 10; }}
    .sheet {{ width: {'297mm; height: 210mm' if should_landscape(form) else '210mm; height: 297mm'}; margin: 10px auto 20px; background: #fff; box-shadow: 0 8px 18px rgba(0,0,0,0.15); box-sizing: border-box; padding: 10mm; overflow: hidden; }}
    h1 {{ margin: 0 0 2mm; text-align: center; font-size: 15pt; text-transform: uppercase; }}
    .meta {{ font-size: 10pt; margin-bottom: 3mm; }}
    h3 {{ margin: 3mm 0 1.5mm; font-size: 11pt; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
    td, th {{ border: 1px solid #111; padding: 2.5mm 2mm; vertical-align: top; }}
    td.label {{ width: 38%; font-weight: 700; }}
    td.value {{ height: 8mm; }}
    .grid td {{ height: 7mm; }}
    .signatures {{ margin-top: 6mm; display: grid; grid-template-columns: repeat(3, 1fr); gap: 6mm; }}
    .sig {{ text-align: center; min-height: 24mm; border-top: 1px dashed #888; padding-top: 2mm; font-weight: 700; }}
    .hint {{ margin-top: 2mm; font-weight: 400; font-size: 9pt; }}
    @media print {{ body {{ background: #fff; }} .toolbar {{ display: none; }} .sheet {{ margin: 0; box-shadow: none; }} }}
  </style>
</head>
<body>
    <div class=\"toolbar\">{html.escape(code)} - {html.escape(title)} | <button onclick=\"window.print()\">In</button></div>
  <main class=\"sheet\">
    <h1>{html.escape(title)}</h1>
        <div class=\"meta\"><b>Mã biểu mẫu:</b> {html.escape(code)} | <b>Thông tư:</b> 99/2025/TT-BTC</div>
    <section>
            <h3>Thông tin điền mẫu</h3>
      <table><tbody>{field_rows}</tbody></table>
    </section>
    {table_html}
    <section>
      <h3>Chữ ký</h3>
      <div class=\"signatures\">{sig_html}</div>
    </section>
  </main>
</body>
</html>
"""


def draw_pdf(form: Dict[str, object], output_pdf: Path) -> None:
    is_landscape = should_landscape(form)
    page_size = landscape(A4) if is_landscape else A4
    page_w_pt, page_h_pt = page_size
    page_w_mm = 297.0 if is_landscape else 210.0

    font_regular, font_bold = detect_font()
    c = canvas.Canvas(str(output_pdf), pagesize=page_size)

    margin_l = 12.0
    margin_r = 12.0
    y = 14.0

    title = str(form.get("title", "Biểu mẫu"))
    code = str(form.get("form_code", "N/A"))

    c.setFont(font_bold, 14)
    c.drawCentredString(mm(page_w_mm / 2), page_h_pt - mm(y), title)
    y += 7

    c.setFont(font_regular, 9.5)
    c.drawString(mm(margin_l), page_h_pt - mm(y), f"Mã biểu mẫu: {code}")
    c.drawRightString(mm(page_w_mm - margin_r), page_h_pt - mm(y), "Thông tư 99/2025/TT-BTC")
    y += 8

    fields = form.get("fields", [])
    c.setFont(font_bold, 10)
    c.drawString(mm(margin_l), page_h_pt - mm(y), "Thông tin điền mẫu")
    y += 5

    c.setFont(font_regular, 9)
    for fld in fields:
        if y > (185 if is_landscape else 260):
            break
        label = str(fld.get("label", ""))
        c.drawString(mm(margin_l), page_h_pt - mm(y), f"{label}:")
        c.line(mm(70), page_h_pt - mm(y + 0.7), mm(page_w_mm - margin_r), page_h_pt - mm(y + 0.7))
        y += 6

    table_schema = form.get("table_schema", {})
    if isinstance(table_schema, dict) and table_schema.get("has_grid") and y < (140 if is_landscape else 215):
        cols = table_schema.get("table_columns", [])
        if cols:
            y += 2
            c.setFont(font_bold, 10)
            c.drawString(mm(margin_l), page_h_pt - mm(y), "Bảng nhập liệu")
            y += 3

            table_left = margin_l
            table_right = page_w_mm - margin_r
            table_width = table_right - table_left
            col_w = table_width / len(cols)
            rows = 8
            row_h = 6.5

            for idx, col in enumerate(cols):
                x = table_left + idx * col_w
                c.rect(mm(x), page_h_pt - mm(y + row_h), mm(col_w), mm(row_h), stroke=1, fill=0)
                c.setFont(font_bold, 7.8)
                label = str(col.get("label", ""))
                c.drawCentredString(mm(x + col_w / 2), page_h_pt - mm(y + 2.1), label[:20])

            c.setFont(font_regular, 8)
            for ridx in range(rows):
                yy = y + row_h * (ridx + 1)
                for cidx in range(len(cols)):
                    xx = table_left + cidx * col_w
                    c.rect(mm(xx), page_h_pt - mm(yy + row_h), mm(col_w), mm(row_h), stroke=1, fill=0)

            y += row_h * (rows + 1) + 2

    signatures = form.get("signatures", [])
    if not signatures:
        signatures = ["Người lập", "Kế toán", "Thủ trưởng"]

    c.setFont(font_bold, 10)
    c.drawString(mm(margin_l), page_h_pt - mm(y), "Chữ ký")
    y += 5

    sig_count = min(4, max(3, len(signatures)))
    sig_labels = [str(s) for s in signatures[:sig_count]]
    box_w = (page_w_mm - margin_l - margin_r) / sig_count

    for idx, sig in enumerate(sig_labels):
        x = margin_l + idx * box_w
        c.setFont(font_bold, 9)
        c.drawCentredString(mm(x + box_w / 2), page_h_pt - mm(y), sig)
        c.setFont(font_regular, 8)
        c.drawCentredString(mm(x + box_w / 2), page_h_pt - mm(y + 4), "(Ký, họ tên)")
        c.line(mm(x + 4), page_h_pt - mm(y + 22), mm(x + box_w - 4), page_h_pt - mm(y + 22))

    c.showPage()
    c.save()


def build_index(output_dir: Path, items: List[Tuple[str, str]]) -> None:
    links = "\n".join(
        f'<li><a href="{html.escape(code)}.html" target="_blank">{html.escape(code)} - {html.escape(title)}</a></li>'
        for code, title in items
    )
    doc = f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>TT99 Full Templates</title>
  <style>body {{ font-family: 'Times New Roman', serif; margin: 24px; }} li {{ margin: 6px 0; }}</style>
</head>
<body>
  <h1>Thông tư 99 - Toàn bộ biểu mẫu (HTML + PDF)</h1>
  <ul>{links}</ul>
</body>
</html>
"""
    (output_dir / "index.html").write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render all TT99 forms into printable templates")
    parser.add_argument("--input-json", default="data/regulations/tt99_2025_appendix1_form_templates.json")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_template_engine/all_forms")
    args = parser.parse_args()

    input_json = Path(args.input_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_json.read_text(encoding="utf-8"))
    forms = data.get("forms", [])

    index_items: List[Tuple[str, str]] = []
    for form in forms:
        code = str(form.get("form_code", "UNKNOWN"))
        title = str(form.get("title", "Biểu mẫu"))
        safe = safe_code(code)

        html_path = out_dir / f"{safe}.html"
        pdf_path = out_dir / f"{safe}.pdf"

        html_path.write_text(render_html(form), encoding="utf-8")
        draw_pdf(form, pdf_path)
        index_items.append((safe, title))

    build_index(out_dir, index_items)
    print(f"Generated forms: {len(forms)}")
    print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render TT99 form 01-LDTL (Bang thanh toan tien luong) from template."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MM_TO_PT = 72.0 / 25.4


@dataclass
class LineItem:
    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float
    width_pt: float = 0.65


@dataclass
class TextItem:
    x_mm: float
    y_mm: float
    text: str
    size_pt: float = 9.0
    bold: bool = False
    align: str = "left"


SAMPLE_01LDTL: Dict[str, str] = {
    "don_vi": "CONG TY TNHH ABC",
    "bo_phan": "Khoi san xuat",
    "thang": "03",
    "nam": "2026",
    "so": "LDTL-0001",
    "ngay": "20",
    "tong_tien_chu": "Mot tram hai muoi trieu dong",
}


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


def layout_01ldtl(data: Dict[str, str]) -> Tuple[List[LineItem], List[TextItem]]:
    lines: List[LineItem] = []
    texts: List[TextItem] = []

    page_w = 297.0
    texts.append(TextItem(12, 13, f"Don vi: {data['don_vi']}", 9.5, True))
    texts.append(TextItem(12, 18, f"Bo phan: {data['bo_phan']}", 8.8))
    texts.append(TextItem(page_w - 12, 13, "Mau so 01 - LDTL", 9.0, True, "right"))
    texts.append(TextItem(page_w - 12, 17.5, "(Thong tu 99/2025/TT-BTC)", 7.8, False, "right"))

    texts.append(TextItem(page_w / 2, 27, "BANG THANH TOAN TIEN LUONG", 13.5, True, "center"))
    texts.append(TextItem(page_w / 2, 33, f"Thang {data['thang']} nam {data['nam']}", 9.2, False, "center"))
    texts.append(TextItem(20, 33, f"So: {data['so']}", 9.0))

    left = 10.0
    top = 40.0
    widths = [10, 34, 20, 14, 16, 18, 18, 18, 18, 20, 20, 20, 20, 18]
    row_h = 7.8
    rows = 14

    x = left
    for w in widths:
        lines.append(LineItem(x, top, x, top + row_h * rows))
        x += w
    lines.append(LineItem(x, top, x, top + row_h * rows))

    for i in range(rows + 1):
        y = top + row_h * i
        lines.append(LineItem(left, y, left + sum(widths), y))

    headers = [
        "STT", "Ho va ten", "Bac luong", "He so", "So cong", "Luong TG", "Luong SP",
        "Phu cap", "Khac", "Tong", "Tam ung", "Khau tru", "Ky II", "Ky nhan",
    ]
    x = left
    for idx, w in enumerate(widths):
        texts.append(TextItem(x + w / 2, top + 4.8, headers[idx], 7.8, True, "center"))
        x += w

    sample_rows = [
        ("1", "Nguyen Van A", "3/7", "3.20", "26", "12,000,000", "0", "1,200,000", "500,000", "13,700,000", "2,000,000", "1,300,000", "10,400,000", "x"),
        ("2", "Tran Thi B", "2/7", "2.80", "25", "10,500,000", "0", "1,000,000", "400,000", "11,900,000", "1,500,000", "1,100,000", "9,300,000", "x"),
        ("3", "Le Van C", "4/7", "3.60", "27", "13,200,000", "0", "1,300,000", "650,000", "15,150,000", "2,200,000", "1,500,000", "11,450,000", "x"),
    ]

    for ridx, row in enumerate(sample_rows, start=1):
        y = top + row_h * (ridx + 0.65)
        x = left
        for cidx, w in enumerate(widths):
            align = "left" if cidx == 1 else "center"
            tx = x + 0.9 if align == "left" else x + w / 2
            texts.append(TextItem(tx, y, row[cidx], 7.8, False, align))
            x += w

    y_sum = top + row_h * 12.65
    texts.append(TextItem(left + widths[0] + widths[1] / 2, y_sum, "Cong", 8.2, True, "center"))
    x = left + sum(widths[:5])
    totals = ["35,700,000", "0", "3,500,000", "1,550,000", "40,750,000", "5,700,000", "3,900,000", "31,150,000"]
    for val in totals:
        w = widths[[5, 6, 7, 8, 9, 10, 11, 12][totals.index(val)]]
        texts.append(TextItem(x + w / 2, y_sum, val, 7.8, True, "center"))
        x += w

    texts.append(TextItem(12, 154, f"Tong so tien (viet bang chu): {data['tong_tien_chu']}", 9.0))
    texts.append(TextItem(page_w - 12, 161, f"Ngay {data['ngay']} thang {data['thang']} nam {data['nam']}", 8.8, False, "right"))

    sig_titles = ["Nguoi lap bang", "Ke toan truong", "Giam doc"]
    sig_x = [190, 230, 270]
    for i, title in enumerate(sig_titles):
        texts.append(TextItem(sig_x[i], 170, title, 9.0, True, "center"))
        texts.append(TextItem(sig_x[i], 175, "(Ky, ho ten)", 8.0, False, "center"))

    return lines, texts


def draw_pdf(output_pdf: Path, lines: List[LineItem], texts: List[TextItem]) -> None:
    page_size = landscape(A4)
    page_w_pt, page_h_pt = page_size
    f_regular, f_bold = detect_font()
    c = canvas.Canvas(str(output_pdf), pagesize=page_size)

    for ln in lines:
        c.setLineWidth(ln.width_pt)
        c.line(mm(ln.x1_mm), page_h_pt - mm(ln.y1_mm), mm(ln.x2_mm), page_h_pt - mm(ln.y2_mm))

    for tx in texts:
        font_name = f_bold if tx.bold else f_regular
        c.setFont(font_name, tx.size_pt)
        x = mm(tx.x_mm)
        y = page_h_pt - mm(tx.y_mm)
        if tx.align == "left":
            wrapped = simpleSplit(tx.text, font_name, tx.size_pt, mm(130))
            if len(wrapped) > 1:
                for idx, line in enumerate(wrapped):
                    c.drawString(x, y - idx * tx.size_pt * 1.15, line)
                continue
        if tx.align == "center":
            c.drawCentredString(x, y, tx.text)
        elif tx.align == "right":
            c.drawRightString(x, y, tx.text)
        else:
            c.drawString(x, y, tx.text)

    c.showPage()
    c.save()


def draw_html(output_html: Path, lines: List[LineItem], texts: List[TextItem]) -> None:
    line_svg = "\n".join(
        f'<line x1="{ln.x1_mm:.3f}mm" y1="{ln.y1_mm:.3f}mm" x2="{ln.x2_mm:.3f}mm" y2="{ln.y2_mm:.3f}mm" stroke="#111" stroke-width="{max(0.2, ln.width_pt * 0.11):.3f}mm" />'
        for ln in lines
    )
    text_divs = "\n".join(
        f'<div class="txt {tx.align} {"bold" if tx.bold else ""}" style="left:{tx.x_mm:.3f}mm;top:{tx.y_mm:.3f}mm;font-size:{tx.size_pt:.2f}pt;">{tx.text}</div>'
        for tx in texts
    )

    html = f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>01-LDTL Template Engine</title>
  <style>
    @page {{ size: A4 landscape; margin: 0; }}
    body {{ margin: 0; background: #f0f2f5; font-family: 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #111; color: #fff; padding: 8px 12px; }}
    .sheet {{ position: relative; width: 297mm; height: 210mm; margin: 10px auto 20px; background: #fff; box-shadow: 0 8px 20px rgba(0,0,0,0.15); overflow: hidden; }}
    .grid {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
    .txt {{ position: absolute; color: #111; white-space: nowrap; line-height: 1.1; transform: translateY(-0.85em); }}
    .txt.bold {{ font-weight: 800; }}
    .txt.center {{ transform: translate(-50%, -0.85em); text-align: center; }}
    .txt.right {{ transform: translate(-100%, -0.85em); text-align: right; }}
    @media print {{ body {{ background: #fff; }} .toolbar {{ display: none; }} .sheet {{ margin: 0; box-shadow: none; }} }}
  </style>
</head>
<body>
  <div class=\"toolbar\">Mau 01-LDTL (template dung tu dau) | <button onclick=\"window.print()\">In</button></div>
  <section class=\"sheet\"><svg class=\"grid\" xmlns=\"http://www.w3.org/2000/svg\">{line_svg}</svg>{text_divs}</section>
</body>
</html>
"""
    output_html.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render TT99 form 01-LDTL from template")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_template_engine")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines, texts = layout_01ldtl(SAMPLE_01LDTL)
    pdf_path = out_dir / "sample_01_LDTL_template.pdf"
    html_path = out_dir / "sample_01_LDTL_template.html"

    draw_pdf(pdf_path, lines, texts)
    draw_html(html_path, lines, texts)
    print(f"Generated: {pdf_path}")
    print(f"Generated: {html_path}")


if __name__ == "__main__":
    main()

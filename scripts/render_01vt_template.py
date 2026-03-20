#!/usr/bin/env python3
"""Render TT99 form 01-VT (Phieu nhap kho) from a structured template."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4
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
    width_pt: float = 0.7


@dataclass
class TextItem:
    x_mm: float
    y_mm: float
    text: str
    size_pt: float = 10.0
    bold: bool = False
    align: str = "left"


SAMPLE_01VT: Dict[str, str] = {
    "don_vi": "CONG TY TNHH ABC",
    "bo_phan": "Kho thanh pham",
    "ngay": "20",
    "thang": "03",
    "nam": "2026",
    "so": "PNK-0012",
    "no": "1521",
    "co": "3311",
    "nguoi_giao": "Nguyen Van B",
    "theo": "Hoa don GTGT",
    "so_ct": "000125",
    "ngay_ct": "20/03/2026",
    "cua": "Cong ty TNHH Nha Cung Cap X",
    "kho": "Kho A",
    "dia_diem": "Ha Noi",
    "tong_tien_chu": "Bon muoi ba trieu sau tram nghin dong",
    "so_ct_goc": "01",
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


def layout_01vt(data: Dict[str, str]) -> Tuple[List[LineItem], List[TextItem]]:
    lines: List[LineItem] = []
    texts: List[TextItem] = []

    page_w = 210.0
    texts.append(TextItem(15, 15, f"Don vi: {data['don_vi']}", 10.2, True))
    texts.append(TextItem(15, 20, f"Bo phan: {data['bo_phan']}", 9.2))
    texts.append(TextItem(page_w - 12, 13, "Mau so 01 - VT", 9.2, True, "right"))
    texts.append(TextItem(page_w - 12, 17.5, "(Thong tu 99/2025/TT-BTC)", 8.0, False, "right"))

    texts.append(TextItem(page_w / 2, 29, "PHIEU NHAP KHO", 14, True, "center"))
    texts.append(TextItem(page_w / 2, 35, f"Ngay {data['ngay']} thang {data['thang']} nam {data['nam']}", 9.2, False, "center"))

    texts.append(TextItem(146, 39, f"So: {data['so']}", 9.5, True))
    texts.append(TextItem(146, 44, f"No: {data['no']}", 9.0))
    texts.append(TextItem(146, 49, f"Co: {data['co']}", 9.0))

    texts.append(TextItem(15, 57, f"- Ho va ten nguoi giao: {data['nguoi_giao']}", 9.2))
    texts.append(TextItem(15, 63, f"- Theo {data['theo']} so {data['so_ct']} ngay {data['ngay_ct']} cua {data['cua']}", 9.0))
    texts.append(TextItem(15, 69, f"Nhap tai kho: {data['kho']}    dia diem: {data['dia_diem']}", 9.0))

    left = 15.0
    top = 76.0
    widths = [14, 60, 14, 14, 20, 20, 18, 23]
    row_h = 8.5
    rows = 9

    x = left
    for w in widths:
        lines.append(LineItem(x, top, x, top + row_h * rows))
        x += w
    lines.append(LineItem(x, top, x, top + row_h * rows))

    for i in range(rows + 1):
        y = top + row_h * i
        lines.append(LineItem(left, y, left + sum(widths), y))

    headers = [
        "STT",
        "Ten, nhan hieu, quy cach",
        "Ma so",
        "DVT",
        "SL theo CT",
        "SL thuc nhap",
        "Don gia",
        "Thanh tien",
    ]
    x = left
    for idx, w in enumerate(widths):
        texts.append(TextItem(x + w / 2, top + 5.5, headers[idx], 8.2, True, "center"))
        x += w

    sample_rows = [
        ("1", "Thep tam 2mm", "VT001", "Kg", "1200", "1200", "18,000", "21,600,000"),
        ("2", "Son lot ngoai that", "VT014", "Lon", "80", "78", "210,000", "16,380,000"),
        ("3", "Bu long M12", "PK022", "Bo", "500", "500", "11,200", "5,600,000"),
    ]
    for ridx, row in enumerate(sample_rows, start=1):
        y = top + row_h * (ridx + 0.6)
        x = left
        for cidx, w in enumerate(widths):
            align = "left" if cidx == 1 else "center"
            tx = x + 1.0 if align == "left" else x + w / 2
            texts.append(TextItem(tx, y, row[cidx], 8.5, False, align))
            x += w

    texts.append(TextItem(15, 156, f"- Tong so tien (viet bang chu): {data['tong_tien_chu']}", 9.0))
    texts.append(TextItem(15, 162, f"- So chung tu goc kem theo: {data['so_ct_goc']}", 9.0))

    texts.append(TextItem(page_w - 15, 172, f"Ngay {data['ngay']} thang {data['thang']} nam {data['nam']}", 9.0, False, "right"))
    sig_titles = ["Nguoi lap phieu", "Nguoi giao hang", "Thu kho", "Ke toan truong"]
    sig_x = [30, 78, 122, 170]
    for idx, title in enumerate(sig_titles):
        texts.append(TextItem(sig_x[idx], 180, title, 9.1, True, "center"))
        texts.append(TextItem(sig_x[idx], 185, "(Ky, ho ten)", 8.0, False, "center"))

    return lines, texts


def draw_pdf(output_pdf: Path, lines: List[LineItem], texts: List[TextItem]) -> None:
    page_w_pt, page_h_pt = A4
    f_regular, f_bold = detect_font()
    c = canvas.Canvas(str(output_pdf), pagesize=A4)

    for ln in lines:
        c.setLineWidth(ln.width_pt)
        c.line(mm(ln.x1_mm), page_h_pt - mm(ln.y1_mm), mm(ln.x2_mm), page_h_pt - mm(ln.y2_mm))

    for tx in texts:
        font_name = f_bold if tx.bold else f_regular
        c.setFont(font_name, tx.size_pt)
        x = mm(tx.x_mm)
        y = page_h_pt - mm(tx.y_mm)
        if tx.align == "left":
            wrapped = simpleSplit(tx.text, font_name, tx.size_pt, mm(180))
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
  <title>01-VT Template Engine</title>
  <style>
    @page {{ size: A4 portrait; margin: 0; }}
    body {{ margin: 0; background: #f0f2f5; font-family: 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #111; color: #fff; padding: 8px 12px; }}
    .sheet {{ position: relative; width: 210mm; height: 297mm; margin: 10px auto 20px; background: #fff; box-shadow: 0 8px 20px rgba(0,0,0,0.15); overflow: hidden; }}
    .grid {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
    .txt {{ position: absolute; color: #111; white-space: nowrap; line-height: 1.12; transform: translateY(-0.85em); }}
    .txt.bold {{ font-weight: 800; }}
    .txt.center {{ transform: translate(-50%, -0.85em); text-align: center; }}
    .txt.right {{ transform: translate(-100%, -0.85em); text-align: right; }}
    @media print {{ body {{ background: #fff; }} .toolbar {{ display: none; }} .sheet {{ margin: 0; box-shadow: none; }} }}
  </style>
</head>
<body>
  <div class=\"toolbar\">Mau 01-VT (template dung tu dau) | <button onclick=\"window.print()\">In</button></div>
  <section class=\"sheet\"><svg class=\"grid\" xmlns=\"http://www.w3.org/2000/svg\">{line_svg}</svg>{text_divs}</section>
</body>
</html>
"""
    output_html.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render TT99 form 01-VT from template")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_template_engine")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines, texts = layout_01vt(SAMPLE_01VT)
    pdf_path = out_dir / "sample_01_VT_template.pdf"
    html_path = out_dir / "sample_01_VT_template.html"

    draw_pdf(pdf_path, lines, texts)
    draw_html(html_path, lines, texts)
    print(f"Generated: {pdf_path}")
    print(f"Generated: {html_path}")


if __name__ == "__main__":
    main()

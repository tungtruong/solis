#!/usr/bin/env python3
"""Render TT99 form 01-TT from a structured template to PDF and HTML.

This script intentionally avoids OCR coordinates. It uses explicit layout rules
so the output is stable, printable, and easy to maintain.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4, A5, landscape
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
    width_pt: float = 0.8


@dataclass
class TextItem:
    x_mm: float
    y_mm: float
    text: str
    size_pt: float = 10.5
    bold: bool = False
    align: str = "left"


SAMPLE_01TT: Dict[str, str] = {
    "don_vi": "CÔNG TY TNHH ABC",
    "dia_chi_don_vi": "Số 18, Trần Duy Hưng, Hà Nội",
    "ngay": "20",
    "thang": "03",
    "nam": "2026",
    "quyen_so": "Q1/2026",
    "so_phieu": "PT-0007",
    "tai_khoan_no": "1111",
    "tai_khoan_co": "1311",
    "nguoi_nop": "Nguyễn Văn A",
    "dia_chi_nguoi_nop": "Hà Nội",
    "ly_do": "Thu tiền khách hàng theo HĐ 2026-015",
    "so_tien": "58.000.000",
    "so_tien_chu": "Năm mươi tám triệu đồng chẵn",
    "chung_tu_goc": "01",
    "ngay_ky": "20",
    "thang_ky": "03",
    "nam_ky": "2026",
}


def mm(v: float) -> float:
    return v * MM_TO_PT


def detect_font() -> Tuple[str, str]:
    """Register a Unicode-capable font if available on Windows."""
    font_candidates = [
        ("FormSerif", Path("C:/Windows/Fonts/times.ttf")),
        ("FormSerif", Path("C:/Windows/Fonts/timesbd.ttf")),
        ("FormSerif", Path("C:/Windows/Fonts/tahoma.ttf")),
        ("FormSerif", Path("C:/Windows/Fonts/arial.ttf")),
    ]
    for font_name, font_path in font_candidates:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            return font_name, font_name
    return "Helvetica", "Helvetica-Bold"


def layout_01tt(data: Dict[str, str]) -> Tuple[List[LineItem], List[TextItem]]:
    lines: List[LineItem] = []
    texts: List[TextItem] = []

    # Compact A5 layout (148 x 210 mm), tuned for 2-copy printing.
    page_w = 148.0

    # Header
    texts.append(TextItem(8, 12, f"Đơn vị: {data['don_vi']}", 8.8, True))
    texts.append(TextItem(8, 17, f"Đ/c: {data['dia_chi_don_vi']}", 8.2))

    texts.append(TextItem(page_w - 8, 10, "Mẫu số 01 - TT", 8.8, True, "right"))
    texts.append(TextItem(page_w - 8, 14.8, "(Thông tư 99/2025/TT-BTC)", 7.4, False, "right"))
    texts.append(TextItem(page_w - 8, 19.2, "ngày 27/10/2025", 7.4, False, "right"))

    texts.append(TextItem(page_w / 2, 28.5, "PHIẾU THU", 14, True, "center"))
    texts.append(TextItem(page_w / 2, 34.5, f"Ngày {data['ngay']} tháng {data['thang']} năm {data['nam']}", 8.8, False, "center"))

    # Right info block
    texts.append(TextItem(104, 38, f"Số: {data['so_phieu']}", 8.8, True))
    texts.append(TextItem(104, 43, f"Nợ: {data['tai_khoan_no']}", 8.8))
    texts.append(TextItem(104, 48, f"Có: {data['tai_khoan_co']}", 8.8))

    # Main body
    texts.append(TextItem(8, 58, f"Họ và tên người nộp tiền: {data['nguoi_nop']}", 8.8, True))
    texts.append(TextItem(8, 65, f"Địa chỉ: {data['dia_chi_nguoi_nop']}", 8.5))
    texts.append(TextItem(8, 72, f"Lý do nộp: {data['ly_do']}", 8.5))
    texts.append(TextItem(8, 79, f"Số tiền: {data['so_tien']}   (Viết bằng chữ): {data['so_tien_chu']}", 8.5))
    texts.append(TextItem(8, 86, f"Kèm theo: {data['chung_tu_goc']}    Chứng từ gốc: ........", 8.5))

    # Signature area (no table/grid lines)
    left = 8.0
    right = page_w - 8.0
    col_count = 5
    col_w = (right - left) / col_count

    titles = ["Giám đốc", "Kế toán trưởng", "Người nộp tiền", "Người lập phiếu", "Thủ quỹ"]
    subtitles = [
        "(Ký, họ tên, đóng dấu)",
        "(Ký, họ tên)",
        "(Ký, họ tên)",
        "(Ký, họ tên)",
        "(Ký, họ tên)",
    ]

    for idx, title in enumerate(titles):
        cx = left + col_w * idx + col_w / 2
        texts.append(TextItem(cx, 104, title, 8.7, True, "center"))
        texts.append(TextItem(cx, 109, subtitles[idx], 7.4, False, "center"))
        lines.append(LineItem(cx - col_w * 0.40, 131, cx + col_w * 0.40, 131, 0.6))

    texts.append(
        TextItem(
            page_w - 8,
            97,
            f"Ngày {data['ngay_ky']} tháng {data['thang_ky']} năm {data['nam_ky']}",
            8.5,
            False,
            "right",
        )
    )

    # Footer notes
    texts.append(TextItem(8, 143, "Đã nhận đủ số tiền (viết bằng chữ): .................................................", 8.5))
    texts.append(TextItem(8, 149, "+ Tỷ giá ngoại tệ (vàng bạc, đá quý): ...............................................", 8.5))
    texts.append(TextItem(8, 155, "+ Số tiền quy đổi: ...................................................................", 8.5))
    texts.append(TextItem(8, 163, "(Liên gửi ra ngoài phải đóng dấu)", 7.8))

    texts.append(
        TextItem(
            8,
            173,
            "Ghi chú: Doanh nghiệp có thể tùy biến mẫu phù hợp đặc điểm hoạt động nhưng phải đủ nội dung bắt buộc.",
            7.3,
        )
    )

    return lines, texts


def to_a5_landscape_space(
    lines: List[LineItem],
    texts: List[TextItem],
) -> Tuple[List[LineItem], List[TextItem]]:
    """Map compact portrait A5 layout to landscape A5 page space."""
    # Source logical space: 148 x 210 mm
    # Target page space: 210 x 148 mm (A5 landscape)
    sx = 1.32
    sy = 0.72
    ox = 8.0
    oy = 6.0

    mapped_lines: List[LineItem] = []
    for ln in lines:
        mapped_lines.append(
            LineItem(
                x1_mm=ln.x1_mm * sx + ox,
                y1_mm=ln.y1_mm * sy + oy,
                x2_mm=ln.x2_mm * sx + ox,
                y2_mm=ln.y2_mm * sy + oy,
                width_pt=max(0.5, ln.width_pt * 0.85),
            )
        )

    mapped_texts: List[TextItem] = []
    for tx in texts:
        mapped_texts.append(
            TextItem(
                x_mm=tx.x_mm * sx + ox,
                y_mm=tx.y_mm * sy + oy,
                text=tx.text,
                size_pt=max(6.6, tx.size_pt * 0.83),
                bold=tx.bold,
                align=tx.align,
            )
        )

    return mapped_lines, mapped_texts


def draw_pdf(output_pdf: Path, lines: List[LineItem], texts: List[TextItem], paper: str) -> None:
    page_size = landscape(A5) if paper.upper() == "A5" else A4
    page_w_pt, page_h_pt = page_size
    paper_w_mm = 148.0 if paper.upper() == "A5" else 210.0
    font_regular, font_bold = detect_font()

    c = canvas.Canvas(str(output_pdf), pagesize=page_size)

    for ln in lines:
        c.setLineWidth(ln.width_pt)
        x1 = mm(ln.x1_mm)
        x2 = mm(ln.x2_mm)
        y1 = page_h_pt - mm(ln.y1_mm)
        y2 = page_h_pt - mm(ln.y2_mm)
        c.line(x1, y1, x2, y2)

    for tx in texts:
        c.setFont(font_bold if tx.bold else font_regular, tx.size_pt)
        x = mm(tx.x_mm)
        y = page_h_pt - mm(tx.y_mm)
        if tx.align == "left":
            wrapped = simpleSplit(tx.text, font_bold if tx.bold else font_regular, tx.size_pt, mm(paper_w_mm - 16.0))
            if len(wrapped) > 1:
                line_gap = tx.size_pt * 1.2
                for idx, line in enumerate(wrapped):
                    c.drawString(x, y - idx * line_gap, line)
                continue
        if tx.align == "center":
            c.drawCentredString(x, y, tx.text)
        elif tx.align == "right":
            c.drawRightString(x, y, tx.text)
        else:
            c.drawString(x, y, tx.text)

    c.showPage()
    c.save()


def draw_html(output_html: Path, lines: List[LineItem], texts: List[TextItem], paper: str) -> None:
    paper_upper = paper.upper()
    page_w_mm = 210 if paper_upper == "A5" else 210
    page_h_mm = 148 if paper_upper == "A5" else 297
    line_svg = "\n".join(
        (
            f'<line x1="{ln.x1_mm:.3f}mm" y1="{ln.y1_mm:.3f}mm" '
            f'x2="{ln.x2_mm:.3f}mm" y2="{ln.y2_mm:.3f}mm" '
            f'stroke="#111" stroke-width="{max(0.2, ln.width_pt * 0.12):.3f}mm" />'
        )
        for ln in lines
    )

    text_divs = "\n".join(
        (
            f'<div class="txt {tx.align} {"bold" if tx.bold else ""}" '
            f'style="left:{tx.x_mm:.3f}mm;top:{tx.y_mm:.3f}mm;font-size:{tx.size_pt:.2f}pt;">{tx.text}</div>'
        )
        for tx in texts
    )

    html_doc = f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>01-TT Template Engine</title>
  <style>
    @page {{ size: {paper_upper} {'landscape' if paper_upper == 'A5' else 'portrait'}; margin: 0; }}
    body {{ margin: 0; background: #f0f2f5; font-family: 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #111; color: #fff; padding: 8px 12px; }}
    .sheet {{ position: relative; width: {page_w_mm}mm; height: {page_h_mm}mm; margin: 10px auto 20px; background: #fff; box-shadow: 0 8px 20px rgba(0,0,0,0.15); overflow: hidden; }}
    .grid {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
    .txt {{ position: absolute; color: #111; white-space: nowrap; line-height: 1.12; transform: translateY(-0.85em); }}
    .txt.bold {{ font-weight: 700; }}
    .txt.center {{ transform: translate(-50%, -0.85em); text-align: center; }}
    .txt.right {{ transform: translate(-100%, -0.85em); text-align: right; }}
    @media print {{
      body {{ background: #fff; }}
      .toolbar {{ display: none; }}
      .sheet {{ margin: 0; box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <div class=\"toolbar\">Mẫu 01-TT (template dựng từ đầu) | <button onclick=\"window.print()\">In</button></div>
  <section class=\"sheet\">
    <svg class=\"grid\" xmlns=\"http://www.w3.org/2000/svg\">{line_svg}</svg>
    {text_divs}
  </section>
</body>
</html>
"""
    output_html.write_text(html_doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render TT99 form 01-TT from template definitions")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_template_engine")
    parser.add_argument("--paper", default="A5", choices=["A5", "A4"], help="Paper size")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines, texts = layout_01tt(SAMPLE_01TT)
    if args.paper.upper() == "A5":
        lines, texts = to_a5_landscape_space(lines, texts)

    suffix = args.paper.lower()
    output_pdf = out_dir / f"sample_01_TT_template_{suffix}.pdf"
    output_html = out_dir / f"sample_01_TT_template_{suffix}.html"

    draw_pdf(output_pdf, lines, texts, args.paper)
    draw_html(output_html, lines, texts, args.paper)

    print(f"Generated: {output_pdf}")
    print(f"Generated: {output_html}")


if __name__ == "__main__":
    main()

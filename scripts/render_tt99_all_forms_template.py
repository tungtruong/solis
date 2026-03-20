#!/usr/bin/env python3
"""Render all TT99 forms with the approved compact voucher style (A5 landscape)."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A5, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MM_TO_PT = 72.0 / 25.4
PAGE_W_MM = 210.0
PAGE_H_MM = 148.0

GROUP_PRESETS: Dict[str, Dict[str, float]] = {
    "TT": {
        "title_size": 12.8,
        "date_size": 8.5,
        "body_size": 8.5,
        "table_header_size": 7.3,
        "table_row_h": 7.2,
        "table_header_h": 8.0,
        "table_rows": 6,
        "sig_size": 8.8,
        "sig_note_size": 7.5,
        "sig_y": 90.4,
    },
    "VT": {
        "title_size": 11.9,
        "date_size": 8.3,
        "body_size": 8.2,
        "table_header_size": 6.9,
        "table_row_h": 6.7,
        "table_header_h": 7.4,
        "table_rows": 6,
        "sig_size": 8.4,
        "sig_note_size": 7.2,
        "sig_y": 96.2,
    },
    "LĐTL": {
        "title_size": 10.8,
        "date_size": 8.1,
        "body_size": 7.9,
        "table_header_size": 6.4,
        "table_row_h": 6.0,
        "table_header_h": 6.7,
        "table_rows": 7,
        "sig_size": 8.2,
        "sig_note_size": 7.0,
        "sig_y": 98.6,
    },
    "BH": {
        "title_size": 11.7,
        "date_size": 8.3,
        "body_size": 8.1,
        "table_header_size": 6.9,
        "table_row_h": 6.4,
        "table_header_h": 7.2,
        "table_rows": 6,
        "sig_size": 8.4,
        "sig_note_size": 7.2,
        "sig_y": 97.0,
    },
    "TSCĐ": {
        "title_size": 11.5,
        "date_size": 8.2,
        "body_size": 8.0,
        "table_header_size": 6.7,
        "table_row_h": 6.2,
        "table_header_h": 7.0,
        "table_rows": 6,
        "sig_size": 8.3,
        "sig_note_size": 7.1,
        "sig_y": 97.6,
    },
}


@dataclass
class LineItem:
    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float
    width_pt: float = 0.6


@dataclass
class TextItem:
    x_mm: float
    y_mm: float
    text: str
    size_pt: float = 8.5
    bold: bool = False
    align: str = "left"


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


def cap_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned.upper()


def norm_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def clean_ocr_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    # Targeted fixes for common OCR artifacts in this appendix.
    replacements = {
        "tiề n": "tiền",
        "là m": "làm",
        "khoả n": "khoản",
        "ki ểm": "kiểm",
        "vậ t": "vật",
        "c ông": "công",
        "đồ ng": "đồng",
        "nhậ p": "nhập",
        "xuấ t": "xuất",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def sanitize_signatures(raw_sigs: List[str]) -> List[str]:
    cleaned: List[str] = []
    for raw in raw_sigs:
        s = clean_ocr_text(str(raw).strip())
        s = re.sub(r"\(.*?\)", "", s).strip(" -()")
        if not s:
            continue
        s_norm = norm_text(s)
        if "nhu cau nhap" in s_norm:
            s = "Kế toán trưởng"
        if len(s) < 3:
            continue
        if s not in cleaned:
            cleaned.append(s)
    return cleaned


def build_layout(form: Dict[str, object]) -> Tuple[List[LineItem], List[TextItem]]:
    lines: List[LineItem] = []
    texts: List[TextItem] = []

    code = str(form.get("form_code", "N/A"))
    title = cap_title(clean_ocr_text(str(form.get("title", "BIỂU MẪU"))))
    fields = form.get("fields", []) if isinstance(form.get("fields"), list) else []
    table_schema = form.get("table_schema", {}) if isinstance(form.get("table_schema"), dict) else {}
    layout_text = str(form.get("layout_text", ""))
    form_group = str(form.get("form_group", "")).upper()
    preset = GROUP_PRESETS.get(form_group, GROUP_PRESETS["TT"])

    texts.append(TextItem(8, 11, "Đơn vị: ........................................", 8.8, True))
    texts.append(TextItem(8, 16, "Địa chỉ/Bộ phận: ........................", 8.0))
    texts.append(TextItem(PAGE_W_MM - 8, 10, f"Mẫu số {code.replace('-', ' - ')}", 8.6, True, "right"))
    texts.append(TextItem(PAGE_W_MM - 8, 14.5, "(Thông tư 99/2025/TT-BTC)", 7.4, False, "right"))

    texts.append(TextItem(PAGE_W_MM / 2, 24, title, preset["title_size"], True, "center"))
    texts.append(TextItem(PAGE_W_MM / 2, 29.2, "Ngày ..... tháng ..... năm .....", preset["date_size"], False, "center"))

    y = 35.0
    has_grid = bool(table_schema.get("has_grid"))
    cols = table_schema.get("table_columns", []) if isinstance(table_schema.get("table_columns"), list) else []
    is_tt_form = code.endswith("-TT")

    labels = [clean_ocr_text(str(f.get("label", "")).strip()) for f in fields]

    def pick(token: str) -> str:
        token_norm = norm_text(token)
        for lb in labels:
            if token_norm in norm_text(lb):
                return lb
        return token

    if is_tt_form:
        texts.append(TextItem(146, 37.0, f"{pick('Số')}: .....................", 8.6, True))
        texts.append(TextItem(146, 42.2, f"{pick('Nợ')}: .....................", 8.4))
        texts.append(TextItem(146, 47.4, f"{pick('Có')}: .....................", 8.4))

        payer_label = pick("Họ và tên người")
        addr_label = pick("Địa chỉ")
        reason_label = pick("Lý do")
        money_label = pick("Số tiền")
        words_label = re.sub(r"^[\s(]+|[\s)]+$", "", pick("Viết bằng chữ"))
        attach_label = pick("Kèm theo")
        origin_label = pick("Chứng từ gốc")

        texts.append(TextItem(8, 56.0, f"{payer_label}: ........................................................", 8.7, True))
        texts.append(TextItem(8, 62.4, f"{addr_label}: ..............................................................", 8.4))
        texts.append(TextItem(8, 68.8, f"{reason_label}: .............................................................", 8.4))
        texts.append(TextItem(8, 75.2, f"{money_label}: ..................   ({words_label}): ........................", 8.5, True))
        texts.append(TextItem(8, 81.6, f"{attach_label}: ............    {origin_label}: ............", 8.4))
        y = 80.4

    elif has_grid and cols:
        left = 8.0
        right = PAGE_W_MM - 8.0
        top = y
        header_h = preset["table_header_h"]
        row_h = preset["table_row_h"]
        row_count = int(preset["table_rows"])
        table_h = header_h + row_h * row_count
        col_w = (right - left) / len(cols)

        for cidx in range(len(cols) + 1):
            x = left + cidx * col_w
            lines.append(LineItem(x, top, x, top + table_h, 0.55))

        for ridx in range(row_count + 2):
            yy = top + ridx * row_h
            if ridx == 1:
                yy = top + header_h
            lines.append(LineItem(left, yy, right, yy, 0.55))

        for cidx, col in enumerate(cols):
            label = str(col.get("label", ""))
            texts.append(
                TextItem(
                    left + cidx * col_w + col_w / 2,
                    top + header_h * 0.66,
                    label[:24],
                    preset["table_header_size"],
                    True,
                    "center",
                )
            )

        y = top + table_h + 4.0
    else:
        max_fields = 7
        for fld in fields[:max_fields]:
            label = str(fld.get("label", "")).strip()
            if not label:
                continue
            texts.append(TextItem(8, y, f"{label}: ...............................................................", preset["body_size"]))
            y += 6.2

    sigs = form.get("signatures", []) if isinstance(form.get("signatures"), list) else []
    sig_labels = sanitize_signatures([str(s) for s in sigs if str(s).strip()])
    if not sig_labels:
        sig_labels = ["Giám đốc", "Kế toán trưởng", "Người lập phiếu", "Người nhận"]
    sig_labels = sig_labels[:5]

    if is_tt_form:
        y = min(y + 2.0, 108.0)
    else:
        y = max(preset["sig_y"] - 8.0, y + 2.0)
    texts.append(TextItem(PAGE_W_MM - 8, y, "Ngày ..... tháng ..... năm .....", preset["date_size"], False, "right"))
    y += 8.0

    left = 8.0
    right = PAGE_W_MM - 8.0
    col_w = (right - left) / len(sig_labels)
    for idx, label in enumerate(sig_labels):
        cx = left + idx * col_w + col_w / 2
        texts.append(TextItem(cx, y, label, preset["sig_size"], True, "center"))
        sig_note = "(Ký, họ tên)"
        label_norm = norm_text(label)
        if idx == 0 and "giam" in label_norm and (" doc" in label_norm or " đoc" in label_norm):
            sig_note = "(Ký, họ tên, đóng dấu)"
        texts.append(TextItem(cx, y + 4.7, sig_note, preset["sig_note_size"], False, "center"))
        lines.append(LineItem(cx - col_w * 0.33, y + 18.5, cx + col_w * 0.33, y + 18.5, 0.55))

    if is_tt_form:
        texts.append(TextItem(8, 118.2, f"{pick('Đã nhận đủ số tiền')}: .................................................", 8.1))
        texts.append(TextItem(8, 123.0, f"{pick('Tỷ giá ngoại tệ')}: ......................................................", 8.1))
        texts.append(TextItem(8, 127.8, f"{pick('Số tiền quy đổi')}: ........................................................", 8.1))
        if "Liên gửi ra ngoài phải đóng dấu" in layout_text:
            texts.append(TextItem(8, 132.4, "(Liên gửi ra ngoài phải đóng dấu)", 7.6))

    if "Ghi chú" in layout_text:
        texts.append(TextItem(8, 139.2, "Ghi chú: Biểu mẫu được xây dựng theo TT99/2025/TT-BTC.", 7.2))

    return lines, texts


def draw_pdf(output_pdf: Path, lines: List[LineItem], texts: List[TextItem]) -> None:
    page_w_pt, page_h_pt = landscape(A5)
    font_regular, font_bold = detect_font()
    c = canvas.Canvas(str(output_pdf), pagesize=landscape(A5))

    for ln in lines:
        c.setLineWidth(ln.width_pt)
        c.line(mm(ln.x1_mm), page_h_pt - mm(ln.y1_mm), mm(ln.x2_mm), page_h_pt - mm(ln.y2_mm))

    for tx in texts:
        c.setFont(font_bold if tx.bold else font_regular, tx.size_pt)
        x = mm(tx.x_mm)
        y = page_h_pt - mm(tx.y_mm)
        if tx.align == "center":
            c.drawCentredString(x, y, tx.text)
        elif tx.align == "right":
            c.drawRightString(x, y, tx.text)
        else:
            c.drawString(x, y, tx.text)

    c.showPage()
    c.save()


def render_html(code: str, title: str, lines: List[LineItem], texts: List[TextItem]) -> str:
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
            f'style="left:{tx.x_mm:.3f}mm;top:{tx.y_mm:.3f}mm;font-size:{tx.size_pt:.2f}pt;">{html.escape(tx.text)}</div>'
        )
        for tx in texts
    )

    return f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)} ({html.escape(code)})</title>
  <style>
    @page {{ size: A5 landscape; margin: 0; }}
    body {{ margin: 0; background: #f0f2f5; font-family: 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #111; color: #fff; padding: 8px 12px; }}
    .sheet {{ position: relative; width: 210mm; height: 148mm; margin: 10px auto 20px; background: #fff; box-shadow: 0 8px 20px rgba(0,0,0,0.15); overflow: hidden; }}
    .grid {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
    .txt {{ position: absolute; color: #111; white-space: nowrap; line-height: 1.12; transform: translateY(-0.85em); }}
    .txt.bold {{ font-weight: 800; }}
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
  <div class=\"toolbar\">{html.escape(code)} - {html.escape(title)} | <button onclick=\"window.print()\">In</button></div>
  <section class=\"sheet\">
    <svg class=\"grid\" xmlns=\"http://www.w3.org/2000/svg\">{line_svg}</svg>
    {text_divs}
  </section>
</body>
</html>
"""


def build_index(output_dir: Path, items: List[Tuple[str, str]]) -> None:
    links = "\n".join(
        f'<li><a href="{html.escape(code)}.html" target="_blank">{html.escape(code)} - {html.escape(title)}</a></li>'
        for code, title in items
    )
    content = f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>TT99 A5 Landscape Templates</title>
  <style>
    body {{ font-family: 'Times New Roman', serif; margin: 24px; }}
    li {{ margin: 6px 0; }}
  </style>
</head>
<body>
  <h1>Thông tư 99 - Bộ biểu mẫu theo style phiếu đã duyệt</h1>
  <ul>{links}</ul>
</body>
</html>
"""
    (output_dir / "index.html").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render all TT99 forms in approved voucher style")
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

        lines, texts = build_layout(form)

        html_path = out_dir / f"{safe}.html"
        pdf_path = out_dir / f"{safe}.pdf"

        html_path.write_text(render_html(code, title, lines, texts), encoding="utf-8")
        draw_pdf(pdf_path, lines, texts)
        index_items.append((safe, title))

    build_index(out_dir, index_items)
    print(f"Generated forms: {len(forms)}")
    print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()

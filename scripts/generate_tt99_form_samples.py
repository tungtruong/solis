#!/usr/bin/env python3
"""Generate sample TT99 forms by overlaying values on PDF page images."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz


SAMPLE_VALUES: Dict[str, Dict[str, str]] = {
    "01-LĐTL": {
        "ngay_lap": "20",
        "thang_lap": "03",
        "nam_lap": "2026",
        "so": "LDTL-0001",
        "tong_so_tien_viet_bang_chu": "Một trăm hai mươi triệu đồng",
    },
    "01-TT": {
        "ngay_lap": "20",
        "thang_lap": "03",
        "nam_lap": "2026",
        "so": "PT-0007",
        "ho_va_ten_nguoi_nop_tien": "Nguyễn Văn A",
        "dia_chi": "Hà Nội",
        "ly_do_nop": "Thu tiền khách hàng theo HĐ 2026-015",
        "so_tien": "58,000,000",
    },
    "01-VT": {
        "ngay_lap": "20",
        "thang_lap": "03",
        "nam_lap": "2026",
        "so": "PNK-0012",
        "ho_ten_nguoi_giao_hang": "Trần Thị B",
        "theo_so": "INV-2026-411",
        "ngay_thang_nam": "20/03/2026",
        "nhap_tai_kho": "1521",
    },
}

GRID_ROWS: Dict[str, List[List[str]]] = {
    "01-LĐTL": [
        ["1", "Nguyễn Văn A", "Kế toán", "3.0", "", "26", "24,000,000", "", "", "", "", "", "", "0", "24,000,000", "A"],
        ["2", "Trần Thị B", "Thủ quỹ", "2.6", "", "26", "18,000,000", "", "", "", "", "", "", "0", "18,000,000", "B"],
    ],
    "01-TT": [],
    "01-VT": [
        ["1", "Giấy A4", "Ram", "200", "65,000", "13,000,000"],
        ["2", "Mực in", "Hộp", "40", "420,000", "16,800,000"],
    ],
}


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D")
    return text


def normalize_for_match(text: str) -> str:
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_templates(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def value_for(field_key: str, form_code: str) -> str:
    by_code = SAMPLE_VALUES.get(form_code, {})
    if field_key in by_code:
        return by_code[field_key]
    if field_key.startswith("ngay"):
        return "20"
    if field_key.startswith("thang"):
        return "03"
    if field_key.startswith("nam"):
        return "2026"
    return "..."


def resolve_path(input_json_path: Path, path_text: str) -> Path:
    path_obj = Path(path_text)
    if path_obj.is_absolute() and path_obj.exists():
        return path_obj

    from_json = (input_json_path.parent / path_obj).resolve()
    if from_json.exists():
        return from_json

    from_workspace = path_obj.resolve()
    if from_workspace.exists():
        return from_workspace

    raise FileNotFoundError(f"Path not found: {path_text}")


def find_label_rect(page: fitz.Page, label: str) -> Optional[fitz.Rect]:
    candidates = [label, label.replace("(", "").replace(")", ""), label.lstrip("- ")]
    for cand in candidates:
        if not cand:
            continue
        rects = page.search_for(cand)
        if rects:
            return rects[0]

    label_norm = normalize_for_match(label)
    words = page.get_text("words")
    by_line: Dict[Tuple[int, int], List[Tuple[float, float, float, float, str]]] = {}
    for x0, y0, x1, y1, w, block_no, line_no, _word_no in words:
        by_line.setdefault((block_no, line_no), []).append((x0, y0, x1, y1, str(w)))

    for _line_key, line_words in by_line.items():
        ordered = sorted(line_words, key=lambda item: item[0])
        line_text = " ".join(w[4] for w in ordered)
        if label_norm and label_norm in normalize_for_match(line_text):
            return fitz.Rect(ordered[0][0], ordered[0][1], ordered[-1][2], ordered[-1][3])

    return None


def page_to_png(page: fitz.Page, out_path: Path, zoom: float) -> Tuple[int, int]:
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_path))
    return pix.width, pix.height


def build_field_overlays(
    page: fitz.Page,
    fields: List[Dict[str, object]],
    form_code: str,
    zoom: float,
) -> List[Dict[str, object]]:
    overlays: List[Dict[str, object]] = []
    fallback_y = 110.0

    for field in fields:
        label = str(field.get("label", "")).strip()
        if not label:
            continue
        value = value_for(str(field.get("field_key", "")), form_code)
        rect = find_label_rect(page, label)

        if rect:
            x = (rect.x1 + 6.0) * zoom
            y = (rect.y0 - 1.0) * zoom
        else:
            x = page.rect.width * 0.62 * zoom
            y = fallback_y * zoom
            fallback_y += 9.0

        overlays.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "font_size": 12,
                "text": value,
            }
        )

    return overlays


def build_grid_overlays(
    page: fitz.Page,
    table_schema: Dict[str, object],
    form_code: str,
    zoom: float,
) -> List[Dict[str, object]]:
    if not table_schema.get("has_grid"):
        return []

    grid_rows = GRID_ROWS.get(form_code, [])
    if not grid_rows:
        return []

    stt_rects = page.search_for("STT")
    if not stt_rects:
        return []

    stt = stt_rects[0]
    col_count = len(table_schema.get("table_columns", []))
    if col_count <= 0:
        return []

    left = max(22.0, stt.x0 - 2.0)
    right = page.rect.width - 22.0
    col_w = (right - left) / col_count
    row_h = 6.2
    start_y = stt.y1 + 12.0

    overlays: List[Dict[str, object]] = []
    for r_idx, row in enumerate(grid_rows):
        for c_idx, val in enumerate(row[:col_count]):
            if not val:
                continue
            x = (left + c_idx * col_w + 1.5) * zoom
            y = (start_y + r_idx * row_h) * zoom
            overlays.append(
                {
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "font_size": 9,
                    "text": str(val),
                }
            )

    return overlays


def render_sample_html(
    form: Dict[str, object],
    pdf_path: Path,
    out_dir: Path,
    zoom: float,
) -> str:
    form_code = str(form["form_code"])
    title = str(form["title"])
    start_page = int(form["source_page_start"])
    end_page = int(form["source_page_end"])
    fields: List[Dict[str, object]] = form.get("fields", [])  # type: ignore[assignment]
    table_schema: Dict[str, object] = form.get("table_schema", {})  # type: ignore[assignment]

    doc = fitz.open(str(pdf_path))
    page_blocks: List[str] = []
    asset_dir = out_dir / "assets"

    try:
        for page_num in range(start_page, end_page + 1):
            page = doc[page_num - 1]
            image_name = f"{form_code.replace('-', '_')}_p{page_num}.png"
            image_path = asset_dir / image_name
            width_px, height_px = page_to_png(page, image_path, zoom)

            overlays = build_field_overlays(page, fields, form_code, zoom) if page_num == start_page else []
            overlays.extend(build_grid_overlays(page, table_schema, form_code, zoom) if page_num == start_page else [])

            overlay_html = "\n".join(
                (
                    f"<div class=\"ov\" style=\"left:{ov['x']}px;top:{ov['y']}px;font-size:{ov['font_size']}px;\">"
                    + html.escape(str(ov["text"]))
                    + "</div>"
                )
                for ov in overlays
            )

            page_blocks.append(
                "\n".join(
                    [
                        f"<section class=\"page\" style=\"width:{width_px}px;height:{height_px}px;\">",
                        f"  <img class=\"bg\" src=\"assets/{html.escape(image_name)}\" alt=\"{html.escape(form_code)} page {page_num}\" />",
                        f"  <div class=\"overlay\">{overlay_html}</div>",
                        "</section>",
                    ]
                )
            )
    finally:
        doc.close()

    return f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)} ({html.escape(form_code)}) - Bản điền thử</title>
  <style>
    :root {{ --paper-shadow: 0 8px 24px rgba(0, 0, 0, 0.14); }}
    body {{ margin: 0; background: #e9edf2; font-family: 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #101317; color: #fff; padding: 10px 14px; }}
    .toolbar button {{ padding: 6px 10px; }}
    .container {{ padding: 14px 0 28px; }}
    .page {{ position: relative; margin: 0 auto 16px; box-shadow: var(--paper-shadow); background: #fff; }}
    .bg {{ display: block; width: 100%; height: 100%; }}
    .overlay {{ position: absolute; inset: 0; pointer-events: none; }}
    .ov {{ position: absolute; color: #0a0a0a; white-space: nowrap; line-height: 1.1; }}
    @media print {{
      body {{ background: #fff; }}
      .toolbar {{ display: none; }}
      .page {{ box-shadow: none; margin: 0 auto; break-after: page; }}
    }}
  </style>
</head>
<body>
  <div class=\"toolbar\">{html.escape(form_code)} - {html.escape(title)} | <button onclick=\"window.print()\">In</button></div>
  <main class=\"container\">
    {''.join(page_blocks)}
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample forms using PDF visual layout")
    parser.add_argument("--input-json", default="data/regulations/tt99_2025_appendix1_form_templates.json")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_appendix1_form_samples_html")
    parser.add_argument("--zoom", type=float, default=2.0, help="Render scale for PDF pages")
    parser.add_argument("--codes", nargs="*", default=["01-LĐTL", "01-TT", "01-VT"], help="Form codes to export")
    args = parser.parse_args()

    input_json_path = Path(args.input_json)
    data = load_templates(input_json_path)
    forms: List[Dict[str, object]] = data["forms"]  # type: ignore[assignment]
    by_code = {str(f["form_code"]): f for f in forms}

    pdf_path = resolve_path(input_json_path, str(data["source_pdf"]))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    links: List[Tuple[str, str, str]] = []
    for code in args.codes:
        if code not in by_code:
            continue
        form = by_code[code]
        file_name = f"sample_{code.replace('-', '_')}.html"
        html_output = render_sample_html(form, pdf_path, out_dir, args.zoom)
        (out_dir / file_name).write_text(html_output, encoding="utf-8")
        links.append((code, file_name, str(form["title"])))

    index_html = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>TT99 Visual Samples</title></head><body>",
        "<h1>Bản điền thử theo layout ảnh PDF</h1>",
        "<ul>",
    ]
    for code, file_name, title in links:
        index_html.append(f"<li><a href='{html.escape(file_name)}' target='_blank'>{html.escape(code)} - {html.escape(title)}</a></li>")
    index_html.extend(["</ul>", "</body></html>"])
    (out_dir / "index.html").write_text("\n".join(index_html), encoding="utf-8")

    print(f"Generated sample dir: {out_dir}")
    print(f"Total sample files: {len(links)}")


if __name__ == "__main__":
    main()

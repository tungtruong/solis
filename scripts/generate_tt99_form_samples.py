#!/usr/bin/env python3
"""Generate sample TT99 forms by OCR-reconstructing page layout with PaddleOCR."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz
import numpy as np
from paddleocr import PaddleOCR


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


def pix_to_ndarray(page: fitz.Page, zoom: float) -> Tuple[np.ndarray, int, int]:
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    if pix.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return arr, pix.width, pix.height


def run_ocr(ocr: PaddleOCR, img: np.ndarray) -> List[Dict[str, object]]:
    lines = []
    try:
        raw = ocr.ocr(img, cls=True)
        lines = raw[0] if raw and isinstance(raw, list) and len(raw) > 0 else []
    except Exception:
        raw = ocr.predict(img)
        lines = raw[0] if raw and isinstance(raw, list) and len(raw) > 0 else []

    blocks: List[Dict[str, object]] = []
    for item in lines:
        if not item:
            continue

        if isinstance(item, list) and len(item) >= 2:
            box = item[0]
            text = str(item[1][0]).strip() if item[1] else ""
            conf = float(item[1][1]) if item[1] and len(item[1]) > 1 else 0.0
        elif isinstance(item, dict):
            points = item.get("dt_polys") or item.get("rec_polys")
            recs = item.get("rec_text")
            scores = item.get("rec_score")
            if points is None or recs is None:
                continue
            box = points[0]
            text = str(recs[0]).strip() if recs else ""
            conf = float(scores[0]) if scores else 0.0
        else:
            continue

        if not text:
            continue

        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        blocks.append(
            {
                "text": text,
                "norm": normalize_for_match(text),
                "x": x0,
                "y": y0,
                "w": x1 - x0,
                "h": y1 - y0,
                "conf": conf,
            }
        )

    return blocks


def extract_pdf_text_blocks(page: fitz.Page, zoom: float) -> List[Dict[str, object]]:
    text_dict = page.get_text("dict")
    blocks: List[Dict[str, object]] = []

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not text:
                continue

            x0, y0, x1, y1 = line.get("bbox", [0.0, 0.0, 0.0, 0.0])
            blocks.append(
                {
                    "text": text,
                    "norm": normalize_for_match(text),
                    "x": float(x0) * zoom,
                    "y": float(y0) * zoom,
                    "w": max(1.0, (float(x1) - float(x0)) * zoom),
                    "h": max(1.0, (float(y1) - float(y0)) * zoom),
                    "conf": 1.0,
                }
            )

    return blocks


def merge_ocr_with_pdf_text(
    ocr_blocks: List[Dict[str, object]],
    pdf_blocks: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if not pdf_blocks:
        return ocr_blocks

    merged: List[Dict[str, object]] = []
    for ocr_b in ocr_blocks:
        ox = float(ocr_b["x"])
        oy = float(ocr_b["y"])
        ow = float(ocr_b["w"])
        oh = float(ocr_b["h"])
        ocx = ox + ow / 2.0
        ocy = oy + oh / 2.0

        best: Optional[Dict[str, object]] = None
        best_score = 1e18

        for pdf_b in pdf_blocks:
            px = float(pdf_b["x"])
            py = float(pdf_b["y"])
            pw = float(pdf_b["w"])
            ph = float(pdf_b["h"])
            pcx = px + pw / 2.0
            pcy = py + ph / 2.0

            dy = abs(ocy - pcy)
            if dy > max(12.0, oh * 0.95):
                continue

            dx = abs(ocx - pcx)
            score = dx + dy * 3.5 + abs(ow - pw) * 0.2
            if score < best_score:
                best_score = score
                best = pdf_b

        if best is not None:
            new_text = str(best["text"]).strip()
            if new_text:
                updated = dict(ocr_b)
                updated["text"] = new_text
                updated["norm"] = normalize_for_match(new_text)
                merged.append(updated)
                continue

        merged.append(ocr_b)

    return merged


def extract_pdf_vector_lines(page: fitz.Page, zoom: float) -> List[Dict[str, float]]:
    lines: List[Dict[str, float]] = []
    drawings = page.get_drawings()
    for drawing in drawings:
        raw_width = drawing.get("width", 0.6)
        try:
            width = float(raw_width) * zoom
        except Exception:
            width = 0.6
        if width <= 0:
            width = 0.6

        for item in drawing.get("items", []):
            if not item:
                continue
            op = item[0]

            if op == "l" and len(item) >= 3:
                p1, p2 = item[1], item[2]
                lines.append(
                    {
                        "x1": float(p1.x) * zoom,
                        "y1": float(p1.y) * zoom,
                        "x2": float(p2.x) * zoom,
                        "y2": float(p2.y) * zoom,
                        "w": width,
                    }
                )
            elif op == "re" and len(item) >= 2:
                r = item[1]
                x0 = float(r.x0) * zoom
                y0 = float(r.y0) * zoom
                x1 = float(r.x1) * zoom
                y1 = float(r.y1) * zoom
                lines.extend(
                    [
                        {"x1": x0, "y1": y0, "x2": x1, "y2": y0, "w": width},
                        {"x1": x1, "y1": y0, "x2": x1, "y2": y1, "w": width},
                        {"x1": x1, "y1": y1, "x2": x0, "y2": y1, "w": width},
                        {"x1": x0, "y1": y1, "x2": x0, "y2": y0, "w": width},
                    ]
                )

    return cleanup_vector_lines(lines)


def cleanup_vector_lines(lines: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Drop noisy tiny segments and deduplicate near-identical vector lines."""
    if not lines:
        return []

    min_len = 10.0
    axis_tol = 1.2
    grid = 0.5
    seen = set()
    cleaned: List[Dict[str, float]] = []

    for ln in lines:
        x1 = float(ln["x1"])
        y1 = float(ln["y1"])
        x2 = float(ln["x2"])
        y2 = float(ln["y2"])
        w = float(ln.get("w", 0.6))

        # Keep only near axis-aligned segments to avoid text-outline noise.
        is_h = abs(y1 - y2) <= axis_tol
        is_v = abs(x1 - x2) <= axis_tol
        if not (is_h or is_v):
            continue

        if is_h:
            y = (y1 + y2) / 2.0
            a, b = sorted([x1, x2])
            if (b - a) < min_len:
                continue
            key = ("h", round(y / grid), round(a / grid), round(b / grid), round(max(0.5, min(1.4, w)), 1))
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"x1": a, "y1": y, "x2": b, "y2": y, "w": w})
            continue

        x = (x1 + x2) / 2.0
        a, b = sorted([y1, y2])
        if (b - a) < min_len:
            continue
        key = ("v", round(x / grid), round(a / grid), round(b / grid), round(max(0.5, min(1.4, w)), 1))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"x1": x, "y1": a, "x2": x, "y2": b, "w": w})

    return cleaned


def strip_cong_bao_footer(
    blocks: List[Dict[str, object]],
    vector_lines: List[Dict[str, float]],
    page_width: int,
    page_height: int,
) -> Tuple[List[Dict[str, object]], List[Dict[str, float]]]:
    footer_anchor: Optional[float] = None
    for b in blocks:
        norm = str(b.get("norm", ""))
        if "cong bao" in norm:
            y = float(b.get("y", 0.0))
            footer_anchor = y if footer_anchor is None else min(footer_anchor, y)

    if footer_anchor is None:
        return blocks, vector_lines

    footer_top = max(0.0, footer_anchor - 18.0)

    filtered_blocks: List[Dict[str, object]] = []
    for b in blocks:
        text = str(b.get("text", "")).strip()
        norm = str(b.get("norm", ""))
        y = float(b.get("y", 0.0))
        x = float(b.get("x", 0.0))

        # Remove gazette footer line and trailing page number near page bottom.
        is_footer_text = y >= footer_top and (
            ("cong bao" in norm)
            or ("/ngay" in norm)
            or bool(re.search(r"\bso\s*\d", norm))
            or (
                bool(re.fullmatch(r"\d{1,4}", text))
                and y <= (footer_anchor + 160.0)
                and x >= page_width * 0.80
            )
            or (bool(re.fullmatch(r"\d{1,4}", text)) and y >= page_height * 0.90)
        )
        if is_footer_text:
            continue

        filtered_blocks.append(b)

    filtered_lines: List[Dict[str, float]] = []
    for ln in vector_lines:
        x1 = float(ln.get("x1", 0.0))
        y1 = float(ln.get("y1", 0.0))
        x2 = float(ln.get("x2", 0.0))
        y2 = float(ln.get("y2", 0.0))

        is_h = abs(y1 - y2) <= 1.4
        seg_len = abs(x2 - x1) if is_h else abs(y2 - y1)

        is_footer_line = is_h and seg_len >= page_width * 0.30 and min(y1, y2) >= footer_top
        if is_footer_line:
            continue

        filtered_lines.append(ln)

    return filtered_blocks, filtered_lines


def find_label_block(blocks: List[Dict[str, object]], label: str) -> Optional[Dict[str, object]]:
    candidates = [label, label.replace("(", "").replace(")", ""), label.lstrip("- ")]
    norms = [normalize_for_match(c) for c in candidates if c.strip()]

    for target in norms:
        for b in blocks:
            if target and target in str(b["norm"]):
                return b

    return None


def build_field_overlays(
    blocks: List[Dict[str, object]],
    fields: List[Dict[str, object]],
    form_code: str,
    page_width: int,
) -> List[Dict[str, object]]:
    overlays: List[Dict[str, object]] = []
    fallback_y = 140.0

    for field in fields:
        label = str(field.get("label", "")).strip()
        if not label:
            continue

        value = value_for(str(field.get("field_key", "")), form_code)
        block = find_label_block(blocks, label)

        if block:
            x = float(block["x"]) + float(block["w"]) + 8.0
            y = float(block["y"])
            fs = max(10, min(16, int(float(block["h"]) * 0.8)))
        else:
            x = page_width * 0.62
            y = fallback_y
            fs = 12
            fallback_y += 22.0

        overlays.append({"x": round(x, 1), "y": round(y, 1), "font_size": fs, "text": value})

    return overlays


def find_stt_block(blocks: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    for b in blocks:
        if str(b["norm"]) == "stt" or str(b["norm"]).startswith("stt "):
            return b
    for b in blocks:
        if " stt " in f" {b['norm']} ":
            return b
    return None


def build_grid_overlays(
    blocks: List[Dict[str, object]],
    table_schema: Dict[str, object],
    form_code: str,
    page_width: int,
) -> List[Dict[str, object]]:
    if not table_schema.get("has_grid"):
        return []

    rows = GRID_ROWS.get(form_code, [])
    if not rows:
        return []

    stt_block = find_stt_block(blocks)
    if not stt_block:
        return []

    col_count = len(table_schema.get("table_columns", []))
    if col_count <= 0:
        return []

    left = max(20.0, float(stt_block["x"]) - 3.0)
    right = float(page_width) - 24.0
    col_w = (right - left) / col_count
    row_h = max(14.0, float(stt_block["h"]) * 1.1)
    start_y = float(stt_block["y"]) + float(stt_block["h"]) + 24.0

    overlays: List[Dict[str, object]] = []
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row[:col_count]):
            if not val:
                continue
            x = left + c_idx * col_w + 2.0
            y = start_y + r_idx * row_h
            overlays.append({"x": round(x, 1), "y": round(y, 1), "font_size": 10, "text": str(val)})

    return overlays


def render_page_html(
    blocks: List[Dict[str, object]],
    overlays: List[Dict[str, object]],
    vector_lines: List[Dict[str, float]],
    width: int,
    height: int,
) -> str:
    base_text = "\n".join(
        (
            f"<div class=\"txt\" style=\"left:{round(float(b['x']),1)}px;top:{round(float(b['y']),1)}px;"
            f"min-width:{round(float(b['w']),1)}px;height:{round(float(b['h']),1)}px;"
            f"font-size:{max(9, min(18, int(float(b['h']) * 0.82)))}px;\">"
            + html.escape(str(b["text"]))
            + "</div>"
        )
        for b in blocks
        if str(b.get("text", "")).strip()
    )

    line_svg = "".join(
        f"<line x1=\"{ln['x1']:.1f}\" y1=\"{ln['y1']:.1f}\" x2=\"{ln['x2']:.1f}\" y2=\"{ln['y2']:.1f}\" stroke=\"#2b2b2b\" stroke-width=\"{max(0.5, min(1.4, ln['w'])):.2f}\" />"
        for ln in vector_lines
    )

    filled_text = "\n".join(
        (
            f"<div class=\"fill\" style=\"left:{ov['x']}px;top:{ov['y']}px;font-size:{ov['font_size']}px;\">"
            + html.escape(str(ov["text"]))
            + "</div>"
        )
        for ov in overlays
    )

    return "\n".join(
        [
            f"<section class=\"page\" style=\"width:{width}px;height:{height}px;\">",
            f"  <svg class=\"grid\" viewBox=\"0 0 {width} {height}\" preserveAspectRatio=\"none\">{line_svg}</svg>",
            "  <div class=\"layer text-layer\">",
            f"{base_text}",
            "  </div>",
            "  <div class=\"layer fill-layer\">",
            f"{filled_text}",
            "  </div>",
            "</section>",
        ]
    )


def render_sample_html(
    form: Dict[str, object],
    pdf_path: Path,
    ocr: PaddleOCR,
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

    try:
        for page_num in range(start_page, end_page + 1):
            page = doc[page_num - 1]
            img, width_px, height_px = pix_to_ndarray(page, zoom)
            ocr_blocks = run_ocr(ocr, img)
            pdf_blocks = extract_pdf_text_blocks(page, zoom)
            layout_blocks = merge_ocr_with_pdf_text(ocr_blocks, pdf_blocks)
            vector_lines = extract_pdf_vector_lines(page, zoom)

            base_blocks = pdf_blocks if pdf_blocks else layout_blocks
            base_blocks, vector_lines = strip_cong_bao_footer(base_blocks, vector_lines, width_px, height_px)

            overlays: List[Dict[str, object]] = []
            if page_num == start_page:
                overlays.extend(build_field_overlays(layout_blocks, fields, form_code, width_px))
                overlays.extend(build_grid_overlays(layout_blocks, table_schema, form_code, width_px))

            page_blocks.append(render_page_html(base_blocks, overlays, vector_lines, width_px, height_px))
    finally:
        doc.close()

    return f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)} ({html.escape(form_code)}) - OCR Layout</title>
  <style>
    :root {{ --paper-shadow: 0 8px 24px rgba(0, 0, 0, 0.14); }}
    body {{ margin: 0; background: #e9edf2; font-family: 'Tahoma', 'Arial Unicode MS', 'Times New Roman', serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; background: #101317; color: #fff; padding: 10px 14px; }}
    .toolbar button {{ padding: 6px 10px; }}
    .container {{ padding: 14px 0 28px; }}
    .page {{ position: relative; margin: 0 auto 16px; box-shadow: var(--paper-shadow); background: #fff; overflow: hidden; }}
    .grid {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
    .layer {{ position: absolute; inset: 0; }}
    .txt {{ position: absolute; color: #111; white-space: nowrap; overflow: visible; line-height: 1.0; }}
    .fill {{ position: absolute; color: #0a56c2; font-weight: 600; white-space: nowrap; line-height: 1.08; }}
    @media print {{
      body {{ background: #fff; }}
      .toolbar {{ display: none; }}
      .page {{ box-shadow: none; margin: 0 auto; break-after: page; }}
    }}
  </style>
</head>
<body>
  <div class=\"toolbar\">{html.escape(form_code)} - {html.escape(title)} | OCR layout (PaddleOCR) | <button onclick=\"window.print()\">In</button></div>
  <main class=\"container\">
    {''.join(page_blocks)}
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample forms using OCR text-layout reconstruction")
    parser.add_argument("--input-json", default="data/regulations/tt99_2025_appendix1_form_templates.json")
    parser.add_argument("--out-dir", default="data/regulations/tt99_2025_appendix1_form_samples_html")
    parser.add_argument("--zoom", type=float, default=2.0, help="Render scale before OCR")
    parser.add_argument("--codes", nargs="*", default=["01-LĐTL", "01-TT", "01-VT"], help="Form codes to export")
    args = parser.parse_args()

    input_json_path = Path(args.input_json)
    data = load_templates(input_json_path)
    forms: List[Dict[str, object]] = data["forms"]  # type: ignore[assignment]
    by_code = {str(f["form_code"]): f for f in forms}

    pdf_path = resolve_path(input_json_path, str(data["source_pdf"]))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ocr = PaddleOCR(use_angle_cls=True, lang="vi", show_log=False)

    links: List[Tuple[str, str, str]] = []
    for code in args.codes:
        if code not in by_code:
            continue
        form = by_code[code]
        file_name = f"sample_{code.replace('-', '_')}.html"
        html_output = render_sample_html(form, pdf_path, ocr, args.zoom)
        (out_dir / file_name).write_text(html_output, encoding="utf-8")
        links.append((code, file_name, str(form["title"])))

    index_html = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>TT99 OCR Layout Samples</title></head><body>",
        "<h1>Bản điền thử theo OCR layout (PaddleOCR)</h1>",
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

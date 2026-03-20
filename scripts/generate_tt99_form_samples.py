#!/usr/bin/env python3
"""Generate filled sample HTML files from TT99 Appendix I templates."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, List


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


def fill_value_cells(template_html: str, values: List[str]) -> str:
    idx = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal idx
        value = values[idx] if idx < len(values) else "..."
        idx += 1
        quote = match.group(1)
        return f"<td class={quote}value{quote}>{html.escape(value)}</td>"

    pattern = re.compile(r"<td class=(['\"])value\1>.*?</td>", re.DOTALL)
    return pattern.sub(repl, template_html)


def fill_grid_rows(template_html: str, form_code: str) -> str:
    table_pattern = re.compile(
        r"(<table class=\"grid\">.*?<tbody>)(.*?)(</tbody>.*?</table>)",
        re.DOTALL,
    )
    table_match = table_pattern.search(template_html)
    if not table_match:
        return template_html

    table_full = table_match.group(0)
    col_count = len(re.findall(r"<th>", table_full))
    if col_count == 0:
        return template_html

    grid_rows = GRID_ROWS.get(form_code, [])
    if not grid_rows:
        return template_html

    flat_values: List[str] = []
    for row in grid_rows:
        padded = row + [""] * max(0, col_count - len(row))
        flat_values.extend(padded[:col_count])

    cell_idx = 0

    def cell_repl(match: re.Match[str]) -> str:
        nonlocal cell_idx
        if cell_idx >= len(flat_values):
            return match.group(0)
        value = html.escape(flat_values[cell_idx])
        cell_idx += 1
        return f"<td>{value if value else '&nbsp;'}</td>"

    body_filled = re.sub(r"<td>.*?</td>", cell_repl, table_match.group(2), flags=re.DOTALL)
    replaced = table_match.group(1) + body_filled + table_match.group(3)
    return template_html.replace(table_full, replaced, 1)


def render_sample_html(form: Dict[str, object], input_json_path: Path) -> str:
    form_code = str(form["form_code"])
    fields: List[Dict[str, object]] = form["fields"]  # type: ignore[assignment]
    template_rel = str(form.get("print_template_html", "")).strip()
    if not template_rel:
        raise ValueError(f"Missing print_template_html for form {form_code}")

    template_path = (input_json_path.parent / template_rel).resolve()
    if not template_path.exists():
        template_path = Path(template_rel)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found for {form_code}: {template_rel}")

    template_html = template_path.read_text(encoding="utf-8")
    values = [value_for(str(f["field_key"]), form_code) for f in fields]

    filled_html = fill_value_cells(template_html, values)
    filled_html = fill_grid_rows(filled_html, form_code)

    return filled_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate filled sample forms")
    parser.add_argument(
        "--input-json",
        default="data/regulations/tt99_2025_appendix1_form_templates.json",
    )
    parser.add_argument(
        "--out-dir",
        default="data/regulations/tt99_2025_appendix1_form_samples_html",
    )
    parser.add_argument(
        "--codes",
        nargs="*",
        default=["01-LĐTL", "01-TT", "01-VT"],
        help="Form codes to export sample",
    )
    args = parser.parse_args()

    input_json_path = Path(args.input_json)
    data = load_templates(input_json_path)
    forms: List[Dict[str, object]] = data["forms"]  # type: ignore[assignment]
    by_code = {str(f["form_code"]): f for f in forms}

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    links = []
    for code in args.codes:
        if code not in by_code:
            continue
        form = by_code[code]
        filename = f"sample_{code.replace('-', '_')}.html"
        path = out_dir / filename
        path.write_text(render_sample_html(form, input_json_path), encoding="utf-8")
        links.append((code, filename, str(form["title"])))

    index = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>TT99 Sample Forms</title></head><body>",
        "<h1>Bản điền thử một số mẫu TT99</h1>",
        "<ul>",
    ]
    for code, file_name, title in links:
        index.append(f"<li><a href='{html.escape(file_name)}' target='_blank'>{html.escape(code)} - {html.escape(title)}</a></li>")
    index.extend(["</ul>", "</body></html>"])
    (out_dir / "index.html").write_text("\n".join(index), encoding="utf-8")

    print(f"Generated sample dir: {out_dir}")
    print(f"Total sample files: {len(links)}")


if __name__ == "__main__":
    main()

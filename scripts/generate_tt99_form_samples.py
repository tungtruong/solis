#!/usr/bin/env python3
"""Generate filled sample HTML files from TT99 Appendix I templates."""

from __future__ import annotations

import argparse
import html
import json
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


def render_sample_html(form: Dict[str, object]) -> str:
    form_code = str(form["form_code"])
    title = html.escape(str(form["title"]))
    fields: List[Dict[str, object]] = form["fields"]  # type: ignore[assignment]
    table_schema: Dict[str, object] = form["table_schema"]  # type: ignore[assignment]

    field_rows = "\n".join(
        f"<tr><td class='label'>{html.escape(str(f['label']))}</td><td class='value'>{html.escape(value_for(str(f['field_key']), form_code))}</td></tr>"
        for f in fields
    )

    table_html = ""
    if table_schema.get("has_grid"):
        cols = table_schema.get("table_columns", [])
        rows = GRID_ROWS.get(form_code, [])
        if not rows:
            rows = [["" for _ in cols] for _ in range(5)]

        head = "".join(f"<th>{html.escape(str(c.get('label', '')))}</th>" for c in cols)
        body_rows = []
        for r in rows:
            padded = r + [""] * max(0, len(cols) - len(r))
            tds = "".join(f"<td>{html.escape(str(v))}</td>" for v in padded[: len(cols)])
            body_rows.append(f"<tr>{tds}</tr>")
        table_html = (
            "<h3>Dữ liệu bảng (mẫu điền thử)</h3>"
            "<table class='grid'><thead><tr>"
            + head
            + "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table>"
        )

    return f"""<!doctype html>
<html lang='vi'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{title} - Bản điền thử</title>
  <style>
    @page {{ size: A4 portrait; margin: 16mm 14mm; }}
    body {{ font-family: 'Times New Roman', serif; margin: 0; color: #111; }}
    .page {{ width: 210mm; min-height: 297mm; box-sizing: border-box; padding: 10mm 10mm; margin: 0 auto; }}
    h1 {{ font-size: 18px; margin: 0 0 2mm; text-transform: uppercase; }}
    .meta {{ font-size: 12px; margin-bottom: 4mm; }}
    h3 {{ font-size: 14px; margin: 3mm 0 2mm; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    td, th {{ border: 1px solid #111; padding: 4px 6px; }}
    td.label {{ width: 38%; font-weight: 600; }}
    .grid td {{ height: 20px; }}
    .actions {{ position: fixed; right: 12px; bottom: 12px; }}
    @media print {{ .actions {{ display: none; }} .page {{ width: auto; min-height: auto; padding: 0; }} }}
  </style>
</head>
<body>
  <div class='actions'><button onclick='window.print()'>In thử</button></div>
  <main class='page'>
    <h1>{title}</h1>
    <div class='meta'>Mã mẫu: <b>{html.escape(form_code)}</b> | Bản điền thử</div>
    <h3>Thông tin đầu vào</h3>
    <table><tbody>{field_rows}</tbody></table>
    {table_html}
  </main>
</body>
</html>
"""


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

    data = load_templates(Path(args.input_json))
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
        path.write_text(render_sample_html(form), encoding="utf-8")
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

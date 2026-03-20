#!/usr/bin/env python3
"""Extract Appendix I form templates from TT99 PDF into JSON/XML/HTML.

Usage:
    python scripts/extract_tt99_appendix1_form_templates.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple

from pypdf import PdfReader

FORM_CODE_RE = re.compile(r"Mẫu\s*số\s*:?\s*([0-9]{2}[ab]?\s*-\s*[A-ZĐ]+)", re.IGNORECASE)
DATE_LINE_RE = re.compile(r"Ngày\.*\s*tháng\.*\s*năm\.*", re.IGNORECASE)
LABEL_DOTS_RE = re.compile(r"([^:\n]{2,80}):\s*\.{3,}")
LABEL_VALUE_DOTS_RE = re.compile(r"([^:\n]{2,80}):\s*(.+?\.{3,}.*?)$")
SIGNATURE_HINT_RE = re.compile(r"\(Ký", re.IGNORECASE)
HEADER_TOKEN_RE = re.compile(r"\b(?:STT|A|B|C|D|E|\d{1,2})\b")


def normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", code).replace("\\", "")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "field"


def collect_pages(pdf_path: Path) -> List[str]:
    reader = PdfReader(str(pdf_path))
    return [(p.extract_text() or "").replace("\r\n", "\n") for p in reader.pages]


def find_form_headers(pages: List[str]) -> List[Tuple[int, str]]:
    headers: List[Tuple[int, str]] = []
    for idx, text in enumerate(pages, start=1):
        for m in FORM_CODE_RE.finditer(text):
            headers.append((idx, normalize_code(m.group(1))))
    # Keep first occurrence per page+code in order.
    dedup: List[Tuple[int, str]] = []
    seen = set()
    for item in headers:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup


def line_iter(block: str) -> List[str]:
    lines = [ln.strip() for ln in block.split("\n")]
    return [ln for ln in lines if ln]


def extract_segment(
    pages: List[str],
    headers: List[Tuple[int, str]],
    i: int,
) -> Tuple[int, int, str]:
    start_page, code = headers[i]
    end_page = headers[i + 1][0] - 1 if i + 1 < len(headers) else len(pages)
    text_parts = [pages[p - 1] for p in range(start_page, end_page + 1)]
    segment = "\n".join(text_parts)

    # Trim leading content before this form header on first page.
    m = FORM_CODE_RE.search(segment)
    if m:
        segment = segment[m.start() :]

    # Trim trailing content after next form header if same-page overlap exists.
    if i + 1 < len(headers):
        next_code = headers[i + 1][1]
        next_code_pattern = re.escape(next_code).replace("-", r"\s*-\s*")
        next_match = re.search(rf"Mẫu\s*số\s*:?\s*{next_code_pattern}", segment, re.IGNORECASE)
        if next_match and next_match.start() > 0:
            segment = segment[: next_match.start()]

    return start_page, end_page, segment


def infer_title(lines: List[str]) -> str:
    candidates: List[str] = []
    started = False
    for ln in lines:
        if not started and FORM_CODE_RE.search(ln):
            started = True
            continue
        if not started:
            continue
        if "(Kèm theo" in ln:
            continue
        if DATE_LINE_RE.search(ln):
            break
        if len(ln) <= 3:
            continue
        if ln.startswith("("):
            continue
        # Prefer uppercase-ish title lines.
        uppercase_ratio = sum(1 for c in ln if c.isupper()) / max(1, sum(1 for c in ln if c.isalpha()))
        if uppercase_ratio > 0.45 or ln.isupper():
            candidates.append(ln)
        elif candidates:
            break
    title = " ".join(candidates).strip()
    return title or "Biểu mẫu kế toán"


def extract_fields(lines: List[str]) -> List[Dict[str, str]]:
    fields: List[Dict[str, str]] = []
    seen_keys = set()

    # Dedicated date placeholders line.
    for ln in lines:
        if DATE_LINE_RE.search(ln):
            for key, label in [("ngay", "Ngày"), ("thang", "Tháng"), ("nam", "Năm")]:
                full = f"{key}_lap"
                if full not in seen_keys:
                    fields.append({"field_key": full, "label": label, "type": "integer", "required": False})
                    seen_keys.add(full)

    for ln in lines:
        for m in LABEL_DOTS_RE.finditer(ln):
            label = m.group(1).strip(" .")
            key = slugify(label)
            if key in seen_keys:
                continue
            fields.append({"field_key": key, "label": label, "type": "string", "required": False})
            seen_keys.add(key)

        m2 = LABEL_VALUE_DOTS_RE.search(ln)
        if m2:
            label = m2.group(1).strip(" .")
            key = slugify(label)
            if key not in seen_keys:
                fields.append({"field_key": key, "label": label, "type": "string", "required": False})
                seen_keys.add(key)

    return fields


def extract_signatures(lines: List[str]) -> List[str]:
    sigs: List[str] = []
    for i, ln in enumerate(lines):
        if SIGNATURE_HINT_RE.search(ln):
            if i > 0:
                prev = lines[i - 1].strip()
                if prev and len(prev) < 80 and ":" not in prev and prev not in sigs:
                    sigs.append(prev)
    return sigs


def parse_index_items(index_text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for raw in index_text.split("\n"):
        ln = raw.strip()
        m = re.search(r"^\d+\s+(.+?)\s+([0-9]{2}[ab]?\s*-\s*[A-ZĐ]+)\s*$", ln)
        if not m:
            continue
        name = m.group(1).strip()
        code = normalize_code(m.group(2))
        mapping[code] = name
    return mapping


def detect_table_schema(lines: List[str]) -> Dict[str, object]:
    """Infer a grid schema from table-like lines in a form."""
    stt_idx = -1
    for i, ln in enumerate(lines):
        if "STT" in ln:
            stt_idx = i
            break

    if stt_idx < 0:
        return {"has_grid": False, "table_columns": [], "table_rows": []}

    # Find row marker line, e.g. "A B 1 2 3 ..."
    marker_idx = -1
    marker_tokens: List[str] = []
    for i in range(stt_idx, min(len(lines), stt_idx + 40)):
        toks = HEADER_TOKEN_RE.findall(lines[i])
        short_ratio = len(toks) / max(1, len(lines[i].split()))
        marker_hint = ("A B" in lines[i]) or lines[i].startswith("A ") or lines[i].startswith("A B ")
        if marker_hint and len(toks) >= 3:
            marker_idx = i
            marker_tokens = toks
            break
        if len(toks) >= 4 and short_ratio >= 0.35:
            marker_idx = i
            marker_tokens = toks
            break

    if marker_idx < 0:
        return {"has_grid": False, "table_columns": [], "table_rows": []}

    col_count = max(2, len(marker_tokens))
    columns: List[Dict[str, object]] = []
    for c in range(col_count):
        key = f"col_{c + 1}"
        label = "STT" if c == 0 else f"Cột {c + 1}"
        columns.append({"key": key, "label": label, "data_type": "string", "required": False})

    # Default editable rows for grid-entry UX.
    rows: List[Dict[str, object]] = []
    for r in range(1, 11):
        rows.append(
            {
                "row_key": f"row_{r}",
                "row_type": "data",
                "cells": {f"col_{c + 1}": "" for c in range(col_count)},
            }
        )

    return {
        "has_grid": True,
        "header_line_index": marker_idx,
        "table_columns": columns,
        "table_rows": rows,
    }


def render_form_html(form: Dict[str, object]) -> str:
    title = html.escape(str(form["title"]))
    form_code = html.escape(str(form["form_code"]))
    fields = form["fields"]
    signatures = form["signatures"]
    table_schema = form["table_schema"]
    layout_text = html.escape(str(form["layout_text"]))

    field_rows = "\n".join(
        f"<tr><td class=\"label\">{html.escape(str(f['label']))}</td><td class=\"value\">&nbsp;</td></tr>" for f in fields
    )

    table_html = ""
    if table_schema.get("has_grid"):
        cols = table_schema["table_columns"]
        rows = table_schema["table_rows"]
        thead = "".join(f"<th>{html.escape(str(c['label']))}</th>" for c in cols)
        tbody_parts: List[str] = []
        for row in rows:
            tds = "".join("<td>&nbsp;</td>" for _ in cols)
            tbody_parts.append(f"<tr>{tds}</tr>")
        table_html = (
            "<section><h3>Khu vực nhập liệu dạng bảng</h3>"
            "<table class=\"grid\"><thead><tr>"
            + thead
            + "</tr></thead><tbody>"
            + "".join(tbody_parts)
            + "</tbody></table></section>"
        )

    sig_html = "".join(f"<div class=\"sig\">{html.escape(str(s))}</div>" for s in signatures)

    return f"""<!doctype html>
<html lang=\"vi\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title} ({form_code})</title>
  <style>
    @page {{ size: A4 portrait; margin: 18mm 14mm 18mm 14mm; }}
    body {{ font-family: 'Times New Roman', serif; margin: 0; color: #111; }}
    .page {{ width: 210mm; min-height: 297mm; box-sizing: border-box; padding: 12mm 10mm; margin: 0 auto; }}
    h1 {{ font-size: 18px; margin: 0 0 4mm; text-transform: uppercase; }}
    .meta {{ font-size: 12px; margin-bottom: 4mm; }}
    h3 {{ font-size: 14px; margin: 4mm 0 2mm; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    td, th {{ border: 1px solid #111; padding: 4px 6px; vertical-align: top; }}
    td.label {{ width: 35%; font-weight: 600; }}
    td.value {{ height: 22px; }}
    .grid td {{ height: 20px; }}
    .sigs {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8mm; margin-top: 8mm; }}
    .sig {{ min-height: 20mm; border-top: 1px dashed #888; padding-top: 2mm; text-align: center; font-size: 12px; }}
    .raw {{ white-space: pre-wrap; border: 1px solid #ccc; padding: 3mm; margin-top: 4mm; font-size: 11px; line-height: 1.4; }}
    .print-btn {{ position: fixed; right: 12px; bottom: 12px; padding: 8px 12px; }}
    @media print {{ .print-btn {{ display: none; }} .page {{ padding: 0; width: auto; min-height: auto; }} }}
  </style>
</head>
<body>
  <button class=\"print-btn\" onclick=\"window.print()\">In biểu mẫu</button>
  <main class=\"page\">
    <h1>{title}</h1>
    <div class=\"meta\">Mã biểu mẫu: <b>{form_code}</b></div>

    <section>
      <h3>Thông tin điền mẫu</h3>
      <table>
        <tbody>
          {field_rows}
        </tbody>
      </table>
    </section>

    {table_html}

    <section>
      <h3>Chữ ký</h3>
      <div class=\"sigs\">{sig_html}</div>
    </section>

    <section>
      <h3>Bố cục gốc để in đối chiếu</h3>
      <div class=\"raw\">{layout_text}</div>
    </section>
  </main>
</body>
</html>
"""


def write_html_outputs(forms: List[Dict[str, object]], out_dir: Path) -> List[Dict[str, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, str]] = []
    index_items: List[str] = []

    for form in forms:
        filename = f"{form['form_code'].replace('-', '_')}.html"
        html_path = out_dir / filename
        html_path.write_text(render_form_html(form), encoding="utf-8")
        rel = str(html_path).replace("\\", "/")
        files.append({"form_code": str(form["form_code"]), "path": rel})
        index_items.append(
            f"<li><a href=\"{html.escape(filename)}\" target=\"_blank\">{html.escape(str(form['form_code']))} - {html.escape(str(form['title']))}</a></li>"
        )
        form["print_template_html"] = rel

    index_html = f"""<!doctype html>
<html lang=\"vi\"><head>
<meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>TT99 Appendix I HTML Templates</title>
<style>
body {{ font-family: Georgia, serif; margin: 24px; }}
h1 {{ margin-bottom: 8px; }}
li {{ margin: 6px 0; }}
</style>
</head><body>
<h1>TT99 - Phụ lục I (HTML print-ready)</h1>
<ul>{''.join(index_items)}</ul>
</body></html>"""
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    return files


def to_xml(data: Dict[str, object], xml_path: Path) -> None:
    root = ET.Element("TT99AppendixIForms", attrib={"document": str(data["document"]), "source_pdf": str(data["source_pdf"])})
    meta = ET.SubElement(root, "Meta")
    ET.SubElement(meta, "GeneratedBy").text = str(data["generated_by"])
    ET.SubElement(meta, "TotalForms").text = str(data["total_forms"])

    forms_node = ET.SubElement(root, "Forms")
    for form in data["forms"]:  # type: ignore[index]
        f_node = ET.SubElement(
            forms_node,
            "Form",
            attrib={
                "code": str(form["form_code"]),
                "id": str(form["form_id"]),
                "group": str(form["form_group"]),
                "start_page": str(form["source_page_start"]),
                "end_page": str(form["source_page_end"]),
            },
        )
        ET.SubElement(f_node, "Title").text = str(form["title"])

        fields_node = ET.SubElement(f_node, "Fields")
        for fld in form["fields"]:
            ET.SubElement(
                fields_node,
                "Field",
                attrib={
                    "key": str(fld["field_key"]),
                    "label": str(fld["label"]),
                    "type": str(fld["type"]),
                    "required": str(fld["required"]).lower(),
                },
            )

        sig_node = ET.SubElement(f_node, "Signatures")
        for signer in form["signatures"]:
            ET.SubElement(sig_node, "Signer").text = str(signer)

        layout = ET.SubElement(f_node, "LayoutText")
        layout.text = str(form["layout_text"])

        if form.get("print_template_html"):
            ET.SubElement(f_node, "PrintTemplateHtml").text = str(form["print_template_html"])

        t_schema = form.get("table_schema", {})
        schema_node = ET.SubElement(f_node, "TableSchema", attrib={"has_grid": str(t_schema.get("has_grid", False)).lower()})
        cols_node = ET.SubElement(schema_node, "Columns")
        for col in t_schema.get("table_columns", []):
            ET.SubElement(
                cols_node,
                "Column",
                attrib={
                    "key": str(col.get("key", "")),
                    "label": str(col.get("label", "")),
                    "type": str(col.get("data_type", "string")),
                    "required": str(col.get("required", False)).lower(),
                },
            )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract TT99 Appendix I form templates")
    parser.add_argument("--pdf", default="data/regulations/TT99/2025_1563 + 1564_99-2025-TT-BTC.pdf")
    parser.add_argument("--out-json", default="data/regulations/tt99_2025_appendix1_form_templates.json")
    parser.add_argument("--out-xml", default="data/regulations/tt99_2025_appendix1_form_templates.xml")
    parser.add_argument("--out-html-dir", default="data/regulations/tt99_2025_appendix1_form_templates_html")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_json = Path(args.out_json)
    out_xml = Path(args.out_xml)
    out_html_dir = Path(args.out_html_dir)

    pages = collect_pages(pdf_path)
    headers = find_form_headers(pages)
    if not headers:
        raise RuntimeError("Không tìm thấy biểu mẫu trong PDF")

    # Two index pages above form bodies in this volume.
    index_text = "\n".join(pages[33:35])
    index_names = parse_index_items(index_text)

    forms: List[Dict[str, object]] = []
    for i, (_page, code) in enumerate(headers):
        start_page, end_page, segment = extract_segment(pages, headers, i)
        lines = line_iter(segment)
        title = infer_title(lines)
        if code in index_names:
            title = index_names[code]

        suffix = code.split("-")[-1]
        form = {
            "form_id": f"tt99_appendix1_{slugify(code)}",
            "form_code": code,
            "form_group": suffix,
            "title": title,
            "source_page_start": start_page,
            "source_page_end": end_page,
            "fields": extract_fields(lines),
            "table_schema": detect_table_schema(lines),
            "signatures": extract_signatures(lines),
            "layout_text": segment.strip(),
        }
        forms.append(form)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    html_files = write_html_outputs(forms, out_html_dir)
    data: Dict[str, object] = {
        "document": "Thông tư 99/2025/TT-BTC",
        "appendix": "Phụ lục I - Danh mục và biểu mẫu chứng từ kế toán",
        "source_pdf": str(pdf_path).replace("\\", "/"),
        "generated_by": "scripts/extract_tt99_appendix1_form_templates.py",
        "total_forms": len(forms),
        "html_output_dir": str(out_html_dir).replace("\\", "/"),
        "html_files": html_files,
        "forms": forms,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    to_xml(data, out_xml)

    print(f"Generated JSON: {out_json}")
    print(f"Generated XML: {out_xml}")
    print(f"Generated HTML dir: {out_html_dir}")
    print(f"Total forms: {len(forms)}")


if __name__ == "__main__":
    main()

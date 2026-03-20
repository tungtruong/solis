#!/usr/bin/env python3
"""Extract Appendix I form templates from TT99 PDF into JSON and XML.

Usage:
  python scripts/extract_tt99_appendix1_form_templates.py
"""

from __future__ import annotations

import argparse
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

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract TT99 Appendix I form templates")
    parser.add_argument("--pdf", default="data/regulations/TT99/2025_1563 + 1564_99-2025-TT-BTC.pdf")
    parser.add_argument("--out-json", default="data/regulations/tt99_2025_appendix1_form_templates.json")
    parser.add_argument("--out-xml", default="data/regulations/tt99_2025_appendix1_form_templates.xml")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_json = Path(args.out_json)
    out_xml = Path(args.out_xml)

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
            "signatures": extract_signatures(lines),
            "layout_text": segment.strip(),
        }
        forms.append(form)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, object] = {
        "document": "Thông tư 99/2025/TT-BTC",
        "appendix": "Phụ lục I - Danh mục và biểu mẫu chứng từ kế toán",
        "source_pdf": str(pdf_path).replace("\\", "/"),
        "generated_by": "scripts/extract_tt99_appendix1_form_templates.py",
        "total_forms": len(forms),
        "forms": forms,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    to_xml(data, out_xml)

    print(f"Generated JSON: {out_json}")
    print(f"Generated XML: {out_xml}")
    print(f"Total forms: {len(forms)}")


if __name__ == "__main__":
    main()

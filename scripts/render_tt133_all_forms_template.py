#!/usr/bin/env python3
"""Render TT133 forms using extracted template metadata."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render TT133 all forms (HTML/PDF)")
    parser.add_argument("--input-json", default="data/regulations/_probe_tt133_15583.json")
    parser.add_argument("--out-dir", default="data/regulations/tt133_2016_template_engine/all_forms")
    args = parser.parse_args()

    script = Path("scripts/render_tt99_all_forms_template.py")
    cmd = [
        sys.executable,
        str(script),
        "--input-json",
        args.input_json,
        "--out-dir",
        args.out_dir,
        "--circular-code",
        "133/2016/TT-BTC",
        "--index-title",
        "Thông tư 133 - Bộ biểu mẫu theo style phiếu đã duyệt",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

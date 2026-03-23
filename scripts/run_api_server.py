import importlib
import sys
from pathlib import Path

import uvicorn

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = WORKSPACE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

importlib.import_module("tt133_mvp.web_api")


if __name__ == "__main__":
    uvicorn.run("tt133_mvp.web_api:app", host="0.0.0.0", port=8000, reload=False)

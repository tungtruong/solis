import sys
from pathlib import Path
import importlib

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = WORKSPACE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

tt133_mvp = importlib.import_module("tt133_mvp")
PostingEngine = tt133_mvp.PostingEngine
RuleStore = tt133_mvp.RuleStore


if __name__ == "__main__":
    workspace_root = str(WORKSPACE_ROOT)
    store = RuleStore.from_workspace(workspace_root)
    engine = PostingEngine(store)

    sample_event = {
        "source_id": "purchase_invoice_xml",
        "event_type": "mua_dich_vu",
        "invoice_no": "INV-0001",
        "issue_date": "2026-03-15",
        "seller_tax_code": "0109999999",
        "goods_service_type": "service",
        "amount": 5500000,
        "amount_untaxed": 5000000,
        "amount_total": 5500000,
        "untaxed_amount": 5000000,
        "vat_amount": 500000,
        "total_amount": 5500000,
        "service_term_months": 24,
        "payment_account": "331",
        "has_vat": True,
    }

    result = engine.post(sample_event)
    if not result.accepted:
        print(f"Rejected: {result.reason}")
    else:
        print("Accepted")
        print(result.journal_entry)

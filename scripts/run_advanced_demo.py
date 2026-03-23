import importlib
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = WORKSPACE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

tt133_mvp = importlib.import_module("tt133_mvp")
RuleStore = tt133_mvp.RuleStore
PostingEngine = tt133_mvp.PostingEngine

reporting_mod = importlib.import_module("tt133_mvp.reporting")
controls_mod = importlib.import_module("tt133_mvp.advanced_controls")
ReportService = reporting_mod.ReportService
AdjustmentControlService = controls_mod.AdjustmentControlService

if __name__ == "__main__":
    store = RuleStore.from_workspace(str(WORKSPACE_ROOT))
    posting_engine = PostingEngine(store)

    sales_event = {
        "source_id": "sales_invoice_xml",
        "event_type": "ban_hang_dich_vu",
        "invoice_no": "OUT-2026-0001",
        "issue_date": "2026-03-10",
        "buyer_tax_code": "0310001111",
        "amount_untaxed": 10000000,
        "vat_amount": 1000000,
        "amount_total": 11000000,
        "total_amount": 11000000,
        "untaxed_amount": 10000000,
        "receipt_account": "131",
        "has_vat": True,
        "payment_status": "unpaid",
    }
    tax_payment_event = {
        "source_id": "bank_statement",
        "event_type": "nop_thue",
        "statement_date": "2026-03-20",
        "reference_no": "STMT-0001",
        "amount": 2000000,
        "debit_credit_flag": "debit",
        "counterparty_name": "Kho bac Nha nuoc",
        "description": "Nop thue ky 03/2026",
        "tax_payable_account": "3331",
        "payment_channel": "bank",
    }

    je1 = posting_engine.post(sales_event)
    je2 = posting_engine.post(tax_payment_event)
    entries = [r.journal_entry for r in [je1, je2] if r.accepted and r.journal_entry]

    report_service = ReportService(store)
    request = report_service.build_request(
        report_code="BCTC_BANG_CAN_DOI_KE_TOAN",
        frequency="month",
        as_of_date="2026-03-31",
    )
    print("Report request")
    print(request)
    print("Financial statements")
    print(report_service.generate_financial_statements(entries, "2026-03-31"))
    print("Tax reports")
    print(report_service.generate_tax_reports(entries, "2026-03-31"))

    adjustment_service = AdjustmentControlService(store)
    adjustment = adjustment_service.create_adjustment_request(
        {
            "maker_id": "user_ke_toan_01",
            "checker_id": "chief_accountant_01",
            "target_entry_id": "JE-20260315120000000000",
            "edit_mode": "adjustment_entry",
            "reason": "Dieu chinh phan loai chi phi theo chung tu bo sung",
        }
    )
    print("Adjustment request")
    print(adjustment)

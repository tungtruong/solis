import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = WORKSPACE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

app_mod = importlib.import_module("tt133_mvp.web_api")
client = TestClient(app_mod.app)


def main() -> None:
    login = client.post(
        "/api/auth/login-demo",
        json={"email": "demo@sme.vn", "password": "demo123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.post(
        "/api/company/profile",
        headers=headers,
        json={
            "company_name": "SME Demo",
            "tax_code": "0312345678",
            "address": "HCM",
            "fiscal_year_start": "2026-01-01",
            "tax_declaration_cycle": "month",
            "default_bank_account": "1121",
            "accountant_email": "accountant@sme.vn",
        },
    )
    assert profile.status_code == 200, profile.text

    post = client.post(
        "/api/events/post",
        headers=headers,
        json={
            "source_id": "purchase_invoice_xml",
            "event_type": "mua_dich_vu",
            "data": {
                "invoice_no": "IN-0001",
                "issue_date": "2026-03-15",
                "seller_tax_code": "0109999999",
                "goods_service_type": "service",
                "amount_untaxed": 5000000,
                "vat_amount": 500000,
                "amount_total": 5500000,
                "total_amount": 5500000,
                "untaxed_amount": 5000000,
                "payment_account": "331",
                "amount": 5500000,
                "has_vat": True,
                "service_term_months": 24,
            },
        },
    )
    assert post.status_code == 200, post.text
    assert post.json()["accepted"] is True, post.text

    financial = client.get("/api/reports/financial?as_of_date=2026-03-31", headers=headers)
    assert financial.status_code == 200, financial.text

    tax = client.get("/api/reports/tax?as_of_date=2026-03-31", headers=headers)
    assert tax.status_code == 200, tax.text

    print("API smoke test passed")


if __name__ == "__main__":
    main()

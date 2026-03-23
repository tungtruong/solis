from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from .rule_store import RuleStore


@dataclass
class ReportService:
    store: RuleStore

    def available_reports(self) -> Dict[str, List[Dict[str, Any]]]:
        catalog = self.store.report_catalog()
        return {
            "financial_reports": catalog.get("financial_reports", []),
            "tax_reports": catalog.get("tax_reports", []),
        }

    def build_request(
        self,
        report_code: str,
        frequency: str,
        as_of_date: str,
    ) -> Dict[str, Any]:
        catalog = self.available_reports()
        merged = catalog["financial_reports"] + catalog["tax_reports"]
        report = next((item for item in merged if item["report_code"] == report_code), None)
        if not report:
            raise ValueError("UNKNOWN_REPORT_CODE")

        if frequency not in report.get("frequency_supported", []):
            raise ValueError("UNSUPPORTED_FREQUENCY")

        # Validate YYYY-MM-DD early for predictable reporting jobs.
        date.fromisoformat(as_of_date)

        return {
            "report_code": report_code,
            "name": report["name"],
            "frequency": frequency,
            "as_of_date": as_of_date,
            "traceability_required": True,
        }

    def summarize_accounts(self, journal_entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        summary: Dict[str, Dict[str, Decimal]] = defaultdict(
            lambda: {"debit": Decimal("0"), "credit": Decimal("0")}
        )

        for entry in journal_entries:
            for line in entry.get("lines", []):
                account = str(line.get("account", ""))
                amount = Decimal(str(line.get("amount", 0)))
                side = line.get("side")
                if side == "debit":
                    summary[account]["debit"] += amount
                elif side == "credit":
                    summary[account]["credit"] += amount

        return {
            account: {
                "debit": float(values["debit"]),
                "credit": float(values["credit"]),
                "balance": float(values["debit"] - values["credit"]),
            }
            for account, values in summary.items()
        }

    def generate_financial_statements(
        self,
        journal_entries: List[Dict[str, Any]],
        as_of_date: str,
    ) -> Dict[str, Any]:
        # Validate format early for consistent report period handling.
        date.fromisoformat(as_of_date)
        by_account = self.summarize_accounts(journal_entries)

        def balance(account_prefix: str) -> Decimal:
            total = Decimal("0")
            for code, vals in by_account.items():
                if code.startswith(account_prefix):
                    total += Decimal(str(vals["balance"]))
            return total

        assets = balance("1") + balance("2")
        liabilities = Decimal("0")
        equity = Decimal("0")
        for code, vals in by_account.items():
            bal = Decimal(str(vals["balance"]))
            if code.startswith("3"):
                liabilities += bal * Decimal("-1")
            if code.startswith("4"):
                equity += bal * Decimal("-1")

        revenue = Decimal("0")
        expense = Decimal("0")
        for code, vals in by_account.items():
            bal = Decimal(str(vals["balance"]))
            if code.startswith("5") or code.startswith("7"):
                revenue += bal * Decimal("-1")
            if code.startswith("6") or code.startswith("8"):
                expense += bal

        profit_before_tax = revenue - expense

        cash_in = Decimal("0")
        cash_out = Decimal("0")
        for entry in journal_entries:
            for line in entry.get("lines", []):
                account = str(line.get("account", ""))
                amount = Decimal(str(line.get("amount", 0)))
                side = line.get("side")
                if account in {"111", "112"} and side == "debit":
                    cash_in += amount
                if account in {"111", "112"} and side == "credit":
                    cash_out += amount

        return {
            "as_of_date": as_of_date,
            "bang_can_doi_ke_toan": {
                "tong_tai_san": float(assets),
                "tong_no_phai_tra": float(liabilities),
                "von_chu_so_huu": float(equity),
            },
            "ket_qua_hoat_dong_kinh_doanh": {
                "doanh_thu": float(revenue),
                "chi_phi": float(expense),
                "loi_nhuan_truoc_thue": float(profit_before_tax),
            },
            "luu_chuyen_tien_te": {
                "luu_chuyen_tien_vao": float(cash_in),
                "luu_chuyen_tien_ra": float(cash_out),
                "luu_chuyen_thuan": float(cash_in - cash_out),
            },
            "thuyet_minh": {
                "tong_so_but_toan": len(journal_entries),
                "co_the_truy_vet_chung_tu": True,
            },
        }

    def generate_tax_reports(
        self,
        journal_entries: List[Dict[str, Any]],
        as_of_date: str,
    ) -> Dict[str, Any]:
        date.fromisoformat(as_of_date)
        by_account = self.summarize_accounts(journal_entries)

        vat_payable = Decimal("0")
        vat_deductible = Decimal("0")
        pit_payable = Decimal("0")
        cit_payable = Decimal("0")

        for code, vals in by_account.items():
            bal = Decimal(str(vals["balance"]))
            if code.startswith("3331"):
                vat_payable += bal * Decimal("-1")
            if code.startswith("1331"):
                vat_deductible += bal
            if code.startswith("3335"):
                pit_payable += bal * Decimal("-1")
            if code.startswith("3334"):
                cit_payable += bal * Decimal("-1")

        return {
            "as_of_date": as_of_date,
            "thue_gtgt": {
                "thue_dau_ra": float(vat_payable),
                "thue_dau_vao_duoc_khau_tru": float(vat_deductible),
                "thue_gtgt_thuan": float(vat_payable - vat_deductible),
            },
            "thue_tncn": {
                "so_phai_nop": float(pit_payable),
            },
            "thue_tndn": {
                "so_phai_nop": float(cit_payable),
            },
        }

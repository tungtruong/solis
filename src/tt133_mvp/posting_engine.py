from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .ingestion import IngestionValidator
from .rule_store import RuleStore


@dataclass
class PostingResult:
    accepted: bool
    reason: Optional[str]
    journal_entry: Optional[Dict[str, Any]]


class PostingEngine:
    def __init__(self, store: RuleStore) -> None:
        self.store = store
        self._event_to_methods = store.event_to_methods()
        self._methods_by_id = store.methods_by_id()
        self._classification_rules = store.classification_rules().get("rules", [])
        narration_rules = store.narration_rules()
        narration_items = narration_rules.get("items", [])
        self._narration_policy = narration_rules.get("narration_policy", {})
        self._narration_by_event = {item["event_code"]: item for item in narration_items}
        self._ingestion_validator = IngestionValidator(store.ingestion_sources())

    def post(self, event: Dict[str, Any]) -> PostingResult:
        ingestion_errors = self._ingestion_validator.validate(event)
        if ingestion_errors:
            return PostingResult(False, ";".join(ingestion_errors), None)

        event_type = event.get("event_type")
        method_ids = self._event_to_methods.get(event_type, [])
        if not method_ids:
            return PostingResult(False, "NO_RULE_MATCH", None)

        classification = self._resolve_classification(event)
        method = self._select_method(method_ids, event, classification)
        if not method:
            return PostingResult(False, "NO_RULE_MATCH", None)

        lines = self._render_lines(method, event)
        if not lines:
            return PostingResult(False, "NO_JOURNAL_LINES", None)

        if not self._is_balanced(lines):
            return PostingResult(False, "VALIDATION_FAILED:BALANCED_ENTRY", None)

        journal_entry = {
            "entry_id": f"JE-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
            "event_type": event_type,
            "source_id": event.get("source_id"),
            "classification": classification,
            "method_id": method["method_id"],
            "lines": lines,
            "normal_narration": self._render_narration(event),
            "meta": {
                "source_reference": event.get("reference_no") or event.get("invoice_no"),
                "event_date": event.get("event_date") or event.get("issue_date") or event.get("statement_date"),
            },
        }
        return PostingResult(True, None, journal_entry)

    def _resolve_classification(self, event: Dict[str, Any]) -> Optional[str]:
        event_type = event.get("event_type")
        for rule in self._classification_rules:
            if rule.get("applies_to_event") != event_type:
                continue
            if self._rule_matches(rule, event):
                return rule.get("output")
        return None

    def _rule_matches(self, rule: Dict[str, Any], event: Dict[str, Any]) -> bool:
        if "when_all" in rule:
            return all(self._check_condition(c, event) for c in rule["when_all"])
        if "when_any" in rule:
            return any(self._check_condition(c, event) for c in rule["when_any"])
        return False

    def _check_condition(self, cond: Dict[str, Any], event: Dict[str, Any]) -> bool:
        field = cond["field"]
        operator = cond["operator"]
        right = Decimal(str(cond["value"]))
        left = Decimal(str(event.get(field, 0)))

        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == "==":
            return left == right
        return False

    def _select_method(
        self,
        method_ids: List[str],
        event: Dict[str, Any],
        classification: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        has_vat = bool(event.get("has_vat"))

        for method_id in method_ids:
            method = self._methods_by_id.get(method_id)
            if not method:
                continue
            conditions = method.get("conditions", {})
            if "has_vat" in conditions and conditions["has_vat"] != has_vat:
                continue
            if "classification" in conditions and conditions["classification"] != classification:
                continue
            return method
        return None

    def _render_lines(self, method: Dict[str, Any], event: Dict[str, Any]) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for line in method.get("journal_lines", []):
            account = self._resolve_account(line["account"], event)
            amount = self._resolve_amount(line["amount_expr"], event)
            if amount == Decimal("0"):
                continue
            lines.append(
                {
                    "side": line["side"],
                    "account": account,
                    "amount": float(amount),
                }
            )
        return lines

    def _resolve_account(self, template: str, event: Dict[str, Any]) -> str:
        if template == "{cash_or_bank_account}":
            channel = event.get("payment_channel")
            return "111" if channel == "cash" else "112"
        if template == "{from_account}":
            return str(event.get("from_account", "112"))
        if template == "{to_account}":
            return str(event.get("to_account", "111"))
        if template == "{receipt_account_111_112_131}":
            return str(event.get("receipt_account", "131"))
        if template == "{payment_account_111_112_331}":
            return str(event.get("payment_account", "331"))
        if template == "{tax_payable_account_333x}":
            return str(event.get("tax_payable_account", "3331"))
        return template

    def _resolve_amount(self, expr: str, event: Dict[str, Any]) -> Decimal:
        if expr == "amount":
            return Decimal(str(event.get("amount", 0)))
        if expr == "untaxed_amount":
            return Decimal(
                str(
                    event.get(
                        "untaxed_amount",
                        event.get("amount_untaxed", event.get("amount", 0)),
                    )
                )
            )
        if expr == "vat_amount":
            return Decimal(str(event.get("vat_amount", 0)))
        if expr == "vat_amount_optional":
            return Decimal(str(event.get("vat_amount", 0)))
        if expr == "total_amount":
            if "total_amount" in event:
                return Decimal(str(event.get("total_amount", 0)))
            if "amount_total" in event:
                return Decimal(str(event.get("amount_total", 0)))
            untaxed = Decimal(str(event.get("untaxed_amount", 0)))
            vat = Decimal(str(event.get("vat_amount", 0)))
            return untaxed + vat
        return Decimal("0")

    def _is_balanced(self, lines: List[Dict[str, Any]]) -> bool:
        debit = Decimal("0")
        credit = Decimal("0")
        for line in lines:
            amount = Decimal(str(line["amount"]))
            if line["side"] == "debit":
                debit += amount
            elif line["side"] == "credit":
                credit += amount
        return debit == credit

    def _render_narration(self, event: Dict[str, Any]) -> str:
        event_type = str(event.get("event_type", ""))
        rule = self._narration_by_event.get(event_type)
        if not rule:
            return self._enforce_narration_policy("Công ty vừa ghi nhận một sự kiện kinh tế mới.")

        template = str(rule.get("template", "Công ty vừa ghi nhận một sự kiện kinh tế."))
        payment_status = str(event.get("payment_status") or "").strip().lower()
        payment_account = str(event.get("payment_account") or "").strip()
        is_payable_purchase = (
            event_type in {"mua_dich_vu", "mua_hang_dung_noi_bo", "mua_tscd"}
            and (
                payment_status in {"unpaid", "pending", "payable", "cong_no", "chua_thanh_toan"}
                or payment_account == "331"
            )
        )
        if is_payable_purchase:
            if event_type == "mua_dich_vu":
                template = "Công ty vừa ghi nhận hóa đơn dịch vụ {purpose} từ {counterparty}, công nợ phải trả nhà cung cấp."
            elif event_type == "mua_hang_dung_noi_bo":
                template = "Công ty vừa ghi nhận hóa đơn mua {purpose} từ {counterparty}, công nợ phải trả nhà cung cấp."
            elif event_type == "mua_tscd":
                template = "Công ty vừa ghi nhận mua tài sản cố định từ {counterparty}, công nợ phải trả nhà cung cấp."

        if event_type in {"ban_hang_dich_vu", "mua_dich_vu", "mua_hang_dung_noi_bo", "mua_tscd"}:
            template = "{purpose} cho {counterparty}"
        fallbacks = rule.get("fallbacks", {})

        amount = self._resolve_amount("total_amount", event)
        if amount == Decimal("0"):
            amount = self._resolve_amount("amount", event)

        values = {
            "amount_vnd_natural": self._format_vnd_natural(amount),
            "counterparty": str(
                event.get("counterparty_name")
                or event.get("counterparty")
                or event.get("seller_name")
                or event.get("buyer_name")
                or fallbacks.get("counterparty", "đối tác")
            ),
            "purpose": str(
                event.get("purpose")
                or event.get("description")
                or event.get("goods_service_type")
                or fallbacks.get("purpose", "hoạt động doanh nghiệp")
            ),
            "person_name": str(event.get("person_name") or event.get("employee_name") or fallbacks.get("person_name", "nhân sự phụ trách")),
            "service_name": str(event.get("service_name") or fallbacks.get("service_name", "theo hợp đồng")),
            "location": str(event.get("location") or fallbacks.get("location", "địa điểm kinh doanh")),
            "from_account": str(event.get("from_account", "112")),
            "to_account": str(event.get("to_account", "111")),
        }

        def replace_token(match: re.Match[str]) -> str:
            key = match.group(1)
            return values.get(key, fallbacks.get(key, ""))

        narration = re.sub(r"\{([a-zA-Z0-9_]+)\}", replace_token, template)
        return self._enforce_narration_policy(narration)

    def _enforce_narration_policy(self, text: str) -> str:
        narration = " ".join(str(text or "").split())
        uncertain_phrases = self._narration_policy.get("disallow_uncertain_phrases", [])
        for phrase in uncertain_phrases:
            token = str(phrase or "").strip()
            if not token:
                continue
            narration = re.sub(rf"\b{re.escape(token)}\b", "", narration, flags=re.IGNORECASE)
        narration = re.sub(r"\s{2,}", " ", narration).strip()
        if narration and not re.search(r"[\.!?]$", narration):
            narration += "."
        return narration

    def _format_vnd_natural(self, amount: Decimal) -> str:
        value = abs(float(amount))
        if value >= 1_000_000_000:
            txt = f"{value / 1_000_000_000:.2f}".rstrip("0").rstrip(".")
            return f"{txt.replace('.', ',')} tỷ đồng"
        if value >= 1_000_000:
            txt = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
            return f"{txt.replace('.', ',')} triệu đồng"
        if value >= 1_000:
            txt = f"{value / 1_000:.2f}".rstrip("0").rstrip(".")
            return f"{txt.replace('.', ',')} nghìn đồng"
        return f"{int(value):,}".replace(",", ".") + " đồng"

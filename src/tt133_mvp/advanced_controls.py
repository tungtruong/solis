from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .rule_store import RuleStore


@dataclass
class AdjustmentControlService:
    store: RuleStore

    def create_adjustment_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        controls = self.store.advanced_controls().get("controls", {})

        if controls.get("reason_required") and not payload.get("reason"):
            raise ValueError("REASON_REQUIRED")

        if controls.get("maker_checker_required") and not payload.get("checker_id"):
            raise ValueError("CHECKER_REQUIRED")

        if controls.get("forbid_direct_edit_locked_entry") and payload.get("edit_mode") == "direct_edit":
            raise ValueError("DIRECT_EDIT_FORBIDDEN")

        return {
            "request_id": f"ADJ-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "status": "pending_checker_approval",
            "maker_id": payload.get("maker_id"),
            "checker_id": payload.get("checker_id"),
            "target_entry_id": payload.get("target_entry_id"),
            "mode": "reversal_or_adjustment_entry_only",
            "reason": payload.get("reason"),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

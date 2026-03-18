import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class RuleStore:
    base_dir: Path

    @classmethod
    def from_workspace(cls, workspace_root: str) -> "RuleStore":
        return cls(base_dir=Path(workspace_root) / "data" / "regulations")

    def _load_json(self, name: str) -> Any:
        path = self.base_dir / name
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def event_rule_index(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_event_rule_index.json")

    def posting_methods(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_posting_methods.json")

    def validation_rules(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_validation_rules.json")

    def classification_rules(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_classification_rules.json")

    def ingestion_sources(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_ingestion_sources.json")

    def posting_router(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_posting_router.json")

    def auto_engine_policy(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_auto_engine_policy.json")

    def report_catalog(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_report_catalog.json")

    def advanced_controls(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_advanced_feature_controls.json")

    def attachment_parse_rules(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_attachment_parse_rules.json")

    def chart_of_accounts_tt133(self) -> List[Dict[str, Any]]:
        payload = self._load_json("chart_of_accounts_tt133.json")
        return payload if isinstance(payload, list) else []

    def narration_rules(self) -> Dict[str, Any]:
        return self._load_json("tt133_mvp_2026_event_narration_rules.json")

    def event_to_methods(self) -> Dict[str, List[str]]:
        items = self.event_rule_index().get("items", [])
        return {
            item["event_code"]: item.get("candidate_posting_method_ids", [])
            for item in items
        }

    def methods_by_id(self) -> Dict[str, Dict[str, Any]]:
        items = self.posting_methods().get("items", [])
        return {item["method_id"]: item for item in items}

from typing import Any, Dict, List


class IngestionValidator:
    def __init__(self, ingestion_policy: Dict[str, Any]) -> None:
        self.ingestion_policy = ingestion_policy
        self.allowed_sources = {
            item["source_id"]: item for item in ingestion_policy.get("allowed_sources", [])
        }

    def validate(self, payload: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        source_id = payload.get("source_id")
        if source_id not in self.allowed_sources:
            return ["SRC_NOT_ALLOWED"]

        source_cfg = self.allowed_sources[source_id]
        for field in source_cfg.get("required_fields", []):
            if payload.get(field) in (None, ""):
                errors.append(f"MISSING_REQUIRED_FIELD:{field}")

        event_type = payload.get("event_type")
        candidates = source_cfg.get("target_event_candidates", [])
        if event_type and event_type not in candidates:
            errors.append(f"EVENT_NOT_ALLOWED_FOR_SOURCE:{event_type}")

        return errors

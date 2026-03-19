from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AppStorage:
    db_path: Path

    @classmethod
    def from_workspace(cls, workspace_root: str) -> "AppStorage":
        backend = str(os.getenv("SOLIS_STORAGE_BACKEND", "sqlite") or "sqlite").strip().lower()
        if backend == "firestore":
            return FirestoreAppStorage.from_workspace(workspace_root)
        data_dir = Path(workspace_root) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(db_path=data_dir / "mvp_app.db")

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    company_id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    tax_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_companies (
                    email TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (email, company_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS company_profiles (
                    email TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS onboarding_companies (
                    email TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    tax_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (email, company_id)
                )
                """
            )
            self._ensure_column(conn, "users", "status", "TEXT NOT NULL DEFAULT 'active'")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS case_items (
                    case_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    event_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (case_id, email)
                )
                """
            )
            self._ensure_column(conn, "case_items", "event_at", "TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS case_events (
                    case_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (case_id, email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opening_balances (
                    email TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ui_content (
                    email TEXT NOT NULL,
                    content_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (email, content_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS adjustment_requests (
                    request_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_filings (
                    email TEXT NOT NULL,
                    period TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (email, period, report_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_submission_history (
                    history_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    period TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, column_ddl: str) -> None:
        columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(str(col[1]) == column_name for col in columns):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")

    def save_session(self, token: str, email: str, created_at: str) -> None:
        with self.connect() as conn:
            columns = conn.execute("PRAGMA table_info(sessions)").fetchall()
            has_expires_at = any(str(column[1]) == "expires_at" for column in columns)
            if has_expires_at:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions(token, email, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, email, created_at, created_at),
                )
                return
            conn.execute(
                "INSERT OR REPLACE INTO sessions(token, email, created_at) VALUES (?, ?, ?)",
                (token, email, created_at),
            )

    def upsert_user(self, email: str, payload: Dict[str, Any], created_at: str, updated_at: str) -> None:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            existing = conn.execute("SELECT created_at FROM users WHERE email = ?", (normalized_email,)).fetchone()
            effective_created_at = str(existing["created_at"]) if existing else created_at
            conn.execute(
                """
                INSERT OR REPLACE INTO users(email, full_name, role, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_email,
                    str(payload.get("full_name") or normalized_email),
                    str(payload.get("role") or "staff"),
                    str(payload.get("status") or "active"),
                    json.dumps(payload, ensure_ascii=False),
                    effective_created_at,
                    updated_at,
                ),
            )

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM users WHERE email = ?", (normalized_email,)).fetchone()
            if not row:
                return None
            return json.loads(str(row["payload_json"]))

    def list_users(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM users ORDER BY email ASC").fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def upsert_company(self, company_id: str, payload: Dict[str, Any], created_at: str, updated_at: str) -> None:
        normalized_company_id = company_id.strip()
        with self.connect() as conn:
            existing = conn.execute("SELECT created_at FROM companies WHERE company_id = ?", (normalized_company_id,)).fetchone()
            effective_created_at = str(existing["created_at"]) if existing else created_at
            conn.execute(
                """
                INSERT OR REPLACE INTO companies(company_id, company_name, tax_code, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_company_id,
                    str(payload.get("company_name") or normalized_company_id),
                    str(payload.get("tax_code") or ""),
                    json.dumps(payload, ensure_ascii=False),
                    effective_created_at,
                    updated_at,
                ),
            )

    def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        normalized_company_id = company_id.strip()
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM companies WHERE company_id = ?", (normalized_company_id,)).fetchone()
            if not row:
                return None
            return json.loads(str(row["payload_json"]))

    def list_companies(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM companies ORDER BY company_name ASC").fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def upsert_user_company_membership(
        self,
        email: str,
        company_id: str,
        role: str,
        is_default: bool,
        payload: Dict[str, Any],
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        with self.connect() as conn:
            if is_default:
                conn.execute("UPDATE user_companies SET is_default = 0 WHERE email = ?", (normalized_email,))
            conn.execute(
                """
                INSERT OR REPLACE INTO user_companies(email, company_id, role, is_default, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_email,
                    normalized_company_id,
                    role,
                    1 if is_default else 0,
                    json.dumps(payload, ensure_ascii=False),
                    updated_at,
                ),
            )

    def list_user_memberships(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT company_id, role, is_default, payload_json, updated_at
                FROM user_companies
                WHERE email = ?
                ORDER BY is_default DESC, company_id ASC
                """,
                (normalized_email,),
            ).fetchall()
            memberships = []
            for row in rows:
                payload = json.loads(str(row["payload_json"]))
                payload["company_id"] = str(row["company_id"])
                payload["role"] = str(row["role"])
                payload["is_default"] = bool(row["is_default"])
                payload["updated_at"] = str(row["updated_at"])
                memberships.append(payload)
            return memberships

    def get_default_company_id(self, email: str) -> Optional[str]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT company_id FROM user_companies WHERE email = ? AND is_default = 1",
                (normalized_email,),
            ).fetchone()
            return str(row["company_id"]) if row else None

    def get_session_email(self, token: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT email FROM sessions WHERE token = ?", (token,)).fetchone()
            return str(row["email"]) if row else None

    def upsert_company_profile(self, email: str, payload: Dict[str, Any], updated_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO company_profiles(email, payload_json, updated_at) VALUES (?, ?, ?)",
                (email, json.dumps(payload, ensure_ascii=False), updated_at),
            )

    def upsert_onboarding_company(
        self,
        email: str,
        company_id: str,
        tax_code: str,
        payload: Dict[str, Any],
        is_default: bool,
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        normalized_tax_code = str(tax_code or "").strip()
        with self.connect() as conn:
            created_row = conn.execute(
                "SELECT created_at FROM onboarding_companies WHERE email = ? AND company_id = ?",
                (normalized_email, normalized_company_id),
            ).fetchone()
            created_at = str(created_row["created_at"]) if created_row else updated_at
            if is_default:
                conn.execute("UPDATE onboarding_companies SET is_default = 0 WHERE email = ?", (normalized_email,))
            conn.execute(
                """
                INSERT OR REPLACE INTO onboarding_companies(
                    email, company_id, tax_code, payload_json, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_email,
                    normalized_company_id,
                    normalized_tax_code,
                    json.dumps(payload, ensure_ascii=False),
                    1 if is_default else 0,
                    created_at,
                    updated_at,
                ),
            )

    def list_onboarding_companies(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT company_id, tax_code, payload_json, is_default, created_at, updated_at
                FROM onboarding_companies
                WHERE email = ?
                ORDER BY is_default DESC, updated_at DESC
                """,
                (normalized_email,),
            ).fetchall()
            items: List[Dict[str, Any]] = []
            for row in rows:
                payload = json.loads(str(row["payload_json"]))
                payload["company_id"] = str(row["company_id"])
                payload["tax_code"] = str(row["tax_code"])
                payload["is_default"] = bool(row["is_default"])
                payload["created_at"] = str(row["created_at"])
                payload["updated_at"] = str(row["updated_at"])
                items.append(payload)
            return items

    def get_default_onboarding_company(self, email: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT company_id, tax_code, payload_json, is_default, created_at, updated_at
                FROM onboarding_companies
                WHERE email = ? AND is_default = 1
                LIMIT 1
                """,
                (normalized_email,),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(str(row["payload_json"]))
            payload["company_id"] = str(row["company_id"])
            payload["tax_code"] = str(row["tax_code"])
            payload["is_default"] = bool(row["is_default"])
            payload["created_at"] = str(row["created_at"])
            payload["updated_at"] = str(row["updated_at"])
            return payload

    def get_onboarding_company(self, email: str, company_id: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT company_id, tax_code, payload_json, is_default, created_at, updated_at
                FROM onboarding_companies
                WHERE email = ? AND company_id = ?
                LIMIT 1
                """,
                (normalized_email, normalized_company_id),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(str(row["payload_json"]))
            payload["company_id"] = str(row["company_id"])
            payload["tax_code"] = str(row["tax_code"])
            payload["is_default"] = bool(row["is_default"])
            payload["created_at"] = str(row["created_at"])
            payload["updated_at"] = str(row["updated_at"])
            return payload

    def find_onboarding_company_by_tax_code(self, email: str, tax_code: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        normalized_tax_code = str(tax_code or "").strip()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT company_id, tax_code, payload_json, is_default, created_at, updated_at
                FROM onboarding_companies
                WHERE email = ? AND tax_code = ?
                LIMIT 1
                """,
                (normalized_email, normalized_tax_code),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(str(row["payload_json"]))
            payload["company_id"] = str(row["company_id"])
            payload["tax_code"] = str(row["tax_code"])
            payload["is_default"] = bool(row["is_default"])
            payload["created_at"] = str(row["created_at"])
            payload["updated_at"] = str(row["updated_at"])
            return payload

    def set_default_onboarding_company(self, email: str, company_id: str, updated_at: str) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        with self.connect() as conn:
            conn.execute("UPDATE onboarding_companies SET is_default = 0 WHERE email = ?", (normalized_email,))
            conn.execute(
                """
                UPDATE onboarding_companies
                SET is_default = 1, updated_at = ?
                WHERE email = ? AND company_id = ?
                """,
                (updated_at, normalized_email, normalized_company_id),
            )

    def get_company_profile(self, email: str) -> Optional[Dict[str, Any]]:
        default_profile = self.get_default_onboarding_company(email)
        if default_profile:
            return default_profile
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM company_profiles WHERE email = ?", (email,)).fetchone()
            if not row:
                return None
            return json.loads(str(row["payload_json"]))

    def add_journal_entry(self, email: str, entry_id: str, event_type: str, payload: Dict[str, Any], created_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO journal_entries(entry_id, email, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (entry_id, email, event_type, json.dumps(payload, ensure_ascii=False), created_at),
            )

    def list_journal_entries(self, email: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM journal_entries WHERE email = ? ORDER BY created_at ASC",
                (email,),
            ).fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def clear_journal_entries(self, email: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM journal_entries WHERE email = ?", (email,))

    def replace_case_items(self, email: str, items: List[Dict[str, Any]], created_at: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM case_items WHERE email = ?", (email,))
            for sort_order, item in enumerate(items, start=1):
                case_id = str(item.get("id") or item.get("case_id") or f"CASE-{sort_order:04d}")
                payload = dict(item)
                payload["id"] = case_id
                event_at = str(payload.get("updatedAt") or payload.get("event_date") or "")
                conn.execute(
                    "INSERT OR REPLACE INTO case_items(case_id, email, sort_order, event_at, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (case_id, email, sort_order, event_at, json.dumps(payload, ensure_ascii=False), created_at),
                )

    def list_case_items(self, email: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM case_items WHERE email = ? ORDER BY event_at DESC, sort_order ASC",
                (email,),
            ).fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def replace_case_events(self, email: str, events: List[Dict[str, Any]], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            conn.execute("DELETE FROM case_events WHERE email = ?", (normalized_email,))
            for idx, event in enumerate(events, start=1):
                case_id = str(event.get("case_id") or event.get("id") or f"CASE-{idx:04d}")
                payload = dict(event)
                payload["case_id"] = case_id
                event_at = str(
                    payload.get("event_date")
                    or payload.get("statement_date")
                    or payload.get("issue_date")
                    or ""
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO case_events(case_id, email, event_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (case_id, normalized_email, event_at, json.dumps(payload, ensure_ascii=False), updated_at),
                )

    def upsert_case_event(self, email: str, case_id: str, event: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        normalized_case_id = case_id.strip()
        payload = dict(event)
        payload["case_id"] = normalized_case_id
        event_at = str(
            payload.get("event_date")
            or payload.get("statement_date")
            or payload.get("issue_date")
            or ""
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO case_events(case_id, email, event_at, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_case_id, normalized_email, event_at, json.dumps(payload, ensure_ascii=False), updated_at),
            )

    def list_case_events(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM case_events WHERE email = ? ORDER BY event_at ASC, case_id ASC",
                (normalized_email,),
            ).fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def upsert_opening_balances(self, email: str, payload: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opening_balances(email, payload_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (normalized_email, json.dumps(payload, ensure_ascii=False), updated_at),
            )

    def get_opening_balances(self, email: str) -> Dict[str, Any]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM opening_balances WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            if not row:
                return {"lines": []}
            return json.loads(str(row["payload_json"]))

    def upsert_ui_content(self, email: str, content_key: str, payload: Dict[str, Any], updated_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ui_content(email, content_key, payload_json, updated_at) VALUES (?, ?, ?, ?)",
                (email, content_key, json.dumps(payload, ensure_ascii=False), updated_at),
            )

    def get_ui_content(self, email: str, content_key: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM ui_content WHERE email = ? AND content_key = ?",
                (email, content_key),
            ).fetchone()
            if not row:
                return None
            return json.loads(str(row["payload_json"]))

    def add_adjustment_request(self, email: str, request_id: str, payload: Dict[str, Any], created_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO adjustment_requests(request_id, email, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (request_id, email, json.dumps(payload, ensure_ascii=False), created_at),
            )

    def list_adjustment_requests(self, email: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM adjustment_requests WHERE email = ? ORDER BY created_at DESC",
                (email,),
            ).fetchall()
            return [json.loads(str(r["payload_json"])) for r in rows]

    def upsert_compliance_filing(
        self,
        email: str,
        period: str,
        report_id: str,
        status: str,
        due_date: str,
        payload: Dict[str, Any],
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compliance_filings(email, period, report_id, status, due_date, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_email,
                    period,
                    report_id,
                    status,
                    due_date,
                    json.dumps(payload, ensure_ascii=False),
                    updated_at,
                ),
            )

    def list_compliance_filings(self, email: str, period: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT report_id, status, due_date, payload_json, updated_at
                FROM compliance_filings
                WHERE email = ? AND period = ?
                ORDER BY report_id ASC
                """,
                (normalized_email, period),
            ).fetchall()
            result = []
            for row in rows:
                payload = json.loads(str(row["payload_json"]))
                payload["report_id"] = str(row["report_id"])
                payload["status"] = str(row["status"])
                payload["due_date"] = str(row["due_date"])
                payload["updated_at"] = str(row["updated_at"])
                result.append(payload)
            return result

    def get_compliance_filing(self, email: str, period: str, report_id: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT status, due_date, payload_json, updated_at
                FROM compliance_filings
                WHERE email = ? AND period = ? AND report_id = ?
                """,
                (normalized_email, period, report_id),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(str(row["payload_json"]))
            payload["report_id"] = report_id
            payload["status"] = str(row["status"])
            payload["due_date"] = str(row["due_date"])
            payload["updated_at"] = str(row["updated_at"])
            return payload

    def add_compliance_submission_history(
        self,
        history_id: str,
        email: str,
        period: str,
        report_id: str,
        payload: Dict[str, Any],
        created_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compliance_submission_history(history_id, email, period, report_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (history_id, normalized_email, period, report_id, json.dumps(payload, ensure_ascii=False), created_at),
            )

    def list_compliance_submission_history(self, email: str, period: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        with self.connect() as conn:
            if period:
                rows = conn.execute(
                    """
                    SELECT history_id, report_id, period, payload_json, created_at
                    FROM compliance_submission_history
                    WHERE email = ? AND period = ?
                    ORDER BY created_at DESC
                    """,
                    (normalized_email, period),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT history_id, report_id, period, payload_json, created_at
                    FROM compliance_submission_history
                    WHERE email = ?
                    ORDER BY created_at DESC
                    """,
                    (normalized_email,),
                ).fetchall()

            result = []
            for row in rows:
                payload = json.loads(str(row["payload_json"]))
                payload["history_id"] = str(row["history_id"])
                payload["report_id"] = str(row["report_id"])
                payload["period"] = str(row["period"])
                payload["created_at"] = str(row["created_at"])
                result.append(payload)
            return result


@dataclass
class FirestoreAppStorage:
    project_id: str
    namespace: str
    database: str = "(default)"

    @classmethod
    def from_workspace(cls, workspace_root: str) -> "FirestoreAppStorage":
        del workspace_root
        project_id = str(
            os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GCLOUD_PROJECT")
            or os.getenv("GCP_PROJECT")
            or os.getenv("PROJECT_ID")
            or ""
        ).strip()
        if not project_id:
            try:
                import google.auth
                _, detected_project = google.auth.default()
                project_id = str(detected_project or "").strip()
            except Exception:
                project_id = ""
        namespace = str(os.getenv("SOLIS_FIRESTORE_NAMESPACE", "prod") or "prod").strip()
        database = str(os.getenv("SOLIS_FIRESTORE_DATABASE", "(default)") or "(default)").strip()
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required when SOLIS_STORAGE_BACKEND=firestore")
        return cls(project_id=project_id, namespace=namespace, database=database)

    def _client(self):
        from google.cloud import firestore
        return firestore.Client(project=self.project_id, database=self.database)

    def _root(self):
        return self._client().collection("tt133_mvp").document(self.namespace)

    def _col(self, name: str):
        return self._root().collection(name)

    def _doc_id(self, *parts: str) -> str:
        cleaned = [re.sub(r"[^A-Za-z0-9._@-]", "_", str(part or "").strip()) for part in parts]
        return "__".join([part for part in cleaned if part]) or "_"

    def _all_docs(self, collection: str) -> List[Dict[str, Any]]:
        return [doc.to_dict() or {} for doc in self._col(collection).stream()]

    def init_db(self) -> None:
        # Firestore is schemaless; collections/documents are created on first write.
        return

    def save_session(self, token: str, email: str, created_at: str) -> None:
        self._col("sessions").document(self._doc_id(token)).set({
            "token": token,
            "email": email.lower().strip(),
            "created_at": created_at,
        })

    def upsert_user(self, email: str, payload: Dict[str, Any], created_at: str, updated_at: str) -> None:
        normalized_email = email.lower().strip()
        doc_ref = self._col("users").document(self._doc_id(normalized_email))
        existing = doc_ref.get().to_dict() if doc_ref.get().exists else {}
        doc_ref.set({
            "email": normalized_email,
            "payload": payload,
            "created_at": str(existing.get("created_at") or created_at),
            "updated_at": updated_at,
        })

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        data = self._col("users").document(self._doc_id(normalized_email)).get()
        if not data.exists:
            return None
        payload = (data.to_dict() or {}).get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def list_users(self) -> List[Dict[str, Any]]:
        rows = []
        for doc in self._col("users").stream():
            payload = (doc.to_dict() or {}).get("payload")
            if isinstance(payload, dict):
                rows.append(payload)
        return sorted(rows, key=lambda item: str(item.get("email") or ""))

    def upsert_company(self, company_id: str, payload: Dict[str, Any], created_at: str, updated_at: str) -> None:
        normalized_company_id = company_id.strip()
        doc_ref = self._col("companies").document(self._doc_id(normalized_company_id))
        existing = doc_ref.get().to_dict() if doc_ref.get().exists else {}
        doc_ref.set({
            "company_id": normalized_company_id,
            "payload": payload,
            "created_at": str(existing.get("created_at") or created_at),
            "updated_at": updated_at,
        })

    def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        normalized_company_id = company_id.strip()
        data = self._col("companies").document(self._doc_id(normalized_company_id)).get()
        if not data.exists:
            return None
        payload = (data.to_dict() or {}).get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def list_companies(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for doc in self._col("companies").stream():
            payload = (doc.to_dict() or {}).get("payload")
            if isinstance(payload, dict):
                items.append(payload)
        return sorted(items, key=lambda item: str(item.get("company_name") or ""))

    def upsert_user_company_membership(
        self,
        email: str,
        company_id: str,
        role: str,
        is_default: bool,
        payload: Dict[str, Any],
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()

        if is_default:
            for doc in self._col("user_companies").stream():
                data = doc.to_dict() or {}
                if str(data.get("email") or "") != normalized_email:
                    continue
                data["is_default"] = False
                data["updated_at"] = updated_at
                doc.reference.set(data)

        self._col("user_companies").document(self._doc_id(normalized_email, normalized_company_id)).set({
            "email": normalized_email,
            "company_id": normalized_company_id,
            "role": role,
            "is_default": bool(is_default),
            "payload": payload,
            "updated_at": updated_at,
        })

    def list_user_memberships(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("user_companies").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = dict(data.get("payload") or {})
            payload["company_id"] = str(data.get("company_id") or "")
            payload["role"] = str(data.get("role") or "staff")
            payload["is_default"] = bool(data.get("is_default"))
            payload["updated_at"] = str(data.get("updated_at") or "")
            rows.append(payload)
        return sorted(rows, key=lambda item: (not bool(item.get("is_default")), str(item.get("company_id") or "")))

    def get_default_company_id(self, email: str) -> Optional[str]:
        memberships = self.list_user_memberships(email)
        for item in memberships:
            if bool(item.get("is_default")):
                company_id = str(item.get("company_id") or "")
                return company_id or None
        return None

    def get_session_email(self, token: str) -> Optional[str]:
        data = self._col("sessions").document(self._doc_id(token)).get()
        if not data.exists:
            return None
        return str((data.to_dict() or {}).get("email") or "") or None

    def upsert_company_profile(self, email: str, payload: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        self._col("company_profiles").document(self._doc_id(normalized_email)).set({
            "email": normalized_email,
            "payload": payload,
            "updated_at": updated_at,
        })

    def upsert_onboarding_company(
        self,
        email: str,
        company_id: str,
        tax_code: str,
        payload: Dict[str, Any],
        is_default: bool,
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        normalized_tax_code = str(tax_code or "").strip()
        if is_default:
            for doc in self._col("onboarding_companies").stream():
                data = doc.to_dict() or {}
                if str(data.get("email") or "") != normalized_email:
                    continue
                data["is_default"] = False
                data["updated_at"] = updated_at
                doc.reference.set(data)

        doc_ref = self._col("onboarding_companies").document(self._doc_id(normalized_email, normalized_company_id))
        existing = doc_ref.get().to_dict() if doc_ref.get().exists else {}
        doc_ref.set({
            "email": normalized_email,
            "company_id": normalized_company_id,
            "tax_code": normalized_tax_code,
            "payload": payload,
            "is_default": bool(is_default),
            "created_at": str(existing.get("created_at") or updated_at),
            "updated_at": updated_at,
        })

    def list_onboarding_companies(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("onboarding_companies").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = dict(data.get("payload") or {})
            payload["company_id"] = str(data.get("company_id") or "")
            payload["tax_code"] = str(data.get("tax_code") or "")
            payload["is_default"] = bool(data.get("is_default"))
            payload["created_at"] = str(data.get("created_at") or "")
            payload["updated_at"] = str(data.get("updated_at") or "")
            rows.append(payload)
        return sorted(rows, key=lambda item: (not bool(item.get("is_default")), str(item.get("updated_at") or "")), reverse=False)

    def get_default_onboarding_company(self, email: str) -> Optional[Dict[str, Any]]:
        rows = self.list_onboarding_companies(email)
        for item in rows:
            if bool(item.get("is_default")):
                return item
        return None

    def get_onboarding_company(self, email: str, company_id: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        data = self._col("onboarding_companies").document(self._doc_id(normalized_email, normalized_company_id)).get()
        if not data.exists:
            return None
        row = data.to_dict() or {}
        payload = dict(row.get("payload") or {})
        payload["company_id"] = str(row.get("company_id") or "")
        payload["tax_code"] = str(row.get("tax_code") or "")
        payload["is_default"] = bool(row.get("is_default"))
        payload["created_at"] = str(row.get("created_at") or "")
        payload["updated_at"] = str(row.get("updated_at") or "")
        return payload

    def find_onboarding_company_by_tax_code(self, email: str, tax_code: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        normalized_tax_code = str(tax_code or "").strip()
        for item in self.list_onboarding_companies(normalized_email):
            if str(item.get("tax_code") or "") == normalized_tax_code:
                return item
        return None

    def set_default_onboarding_company(self, email: str, company_id: str, updated_at: str) -> None:
        normalized_email = email.lower().strip()
        normalized_company_id = company_id.strip()
        for doc in self._col("onboarding_companies").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            data["is_default"] = str(data.get("company_id") or "") == normalized_company_id
            data["updated_at"] = updated_at
            doc.reference.set(data)

    def get_company_profile(self, email: str) -> Optional[Dict[str, Any]]:
        default_profile = self.get_default_onboarding_company(email)
        if default_profile:
            return default_profile
        normalized_email = email.lower().strip()
        data = self._col("company_profiles").document(self._doc_id(normalized_email)).get()
        if not data.exists:
            return None
        payload = (data.to_dict() or {}).get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def add_journal_entry(self, email: str, entry_id: str, event_type: str, payload: Dict[str, Any], created_at: str) -> None:
        self._col("journal_entries").document(self._doc_id(entry_id)).set({
            "entry_id": entry_id,
            "email": email.lower().strip(),
            "event_type": event_type,
            "payload": payload,
            "created_at": created_at,
        })

    def list_journal_entries(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("journal_entries").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = data.get("payload")
            if isinstance(payload, dict):
                rows.append(payload)
        rows.sort(key=lambda item: str(item.get("created_at") or ""))
        return rows

    def clear_journal_entries(self, email: str) -> None:
        normalized_email = email.lower().strip()
        for doc in self._col("journal_entries").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") == normalized_email:
                doc.reference.delete()

    def replace_case_items(self, email: str, items: List[Dict[str, Any]], created_at: str) -> None:
        normalized_email = email.lower().strip()
        for doc in self._col("case_items").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") == normalized_email:
                doc.reference.delete()

        for sort_order, item in enumerate(items, start=1):
            case_id = str(item.get("id") or item.get("case_id") or f"CASE-{sort_order:04d}")
            payload = dict(item)
            payload["id"] = case_id
            event_at = str(payload.get("updatedAt") or payload.get("event_date") or "")
            self._col("case_items").document(self._doc_id(normalized_email, case_id)).set({
                "email": normalized_email,
                "case_id": case_id,
                "sort_order": sort_order,
                "event_at": event_at,
                "payload": payload,
                "created_at": created_at,
            })

    def list_case_items(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("case_items").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = data.get("payload")
            if isinstance(payload, dict):
                rows.append(payload)
        rows.sort(key=lambda item: (str(item.get("updatedAt") or item.get("event_date") or ""), str(item.get("id") or "")), reverse=True)
        return rows

    def replace_case_events(self, email: str, events: List[Dict[str, Any]], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        for doc in self._col("case_events").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") == normalized_email:
                doc.reference.delete()

        for idx, event in enumerate(events, start=1):
            case_id = str(event.get("case_id") or event.get("id") or f"CASE-{idx:04d}")
            payload = dict(event)
            payload["case_id"] = case_id
            event_at = str(payload.get("event_date") or payload.get("statement_date") or payload.get("issue_date") or "")
            self._col("case_events").document(self._doc_id(normalized_email, case_id)).set({
                "email": normalized_email,
                "case_id": case_id,
                "event_at": event_at,
                "payload": payload,
                "updated_at": updated_at,
            })

    def upsert_case_event(self, email: str, case_id: str, event: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        normalized_case_id = case_id.strip()
        payload = dict(event)
        payload["case_id"] = normalized_case_id
        event_at = str(payload.get("event_date") or payload.get("statement_date") or payload.get("issue_date") or "")
        self._col("case_events").document(self._doc_id(normalized_email, normalized_case_id)).set({
            "email": normalized_email,
            "case_id": normalized_case_id,
            "event_at": event_at,
            "payload": payload,
            "updated_at": updated_at,
        })

    def list_case_events(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("case_events").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = data.get("payload")
            if isinstance(payload, dict):
                rows.append(payload)
        rows.sort(key=lambda item: (str(item.get("event_date") or item.get("statement_date") or item.get("issue_date") or ""), str(item.get("case_id") or "")))
        return rows

    def upsert_opening_balances(self, email: str, payload: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        self._col("opening_balances").document(self._doc_id(normalized_email)).set({
            "email": normalized_email,
            "payload": payload,
            "updated_at": updated_at,
        })

    def get_opening_balances(self, email: str) -> Dict[str, Any]:
        normalized_email = email.lower().strip()
        data = self._col("opening_balances").document(self._doc_id(normalized_email)).get()
        if not data.exists:
            return {"lines": []}
        payload = (data.to_dict() or {}).get("payload")
        return dict(payload) if isinstance(payload, dict) else {"lines": []}

    def upsert_ui_content(self, email: str, content_key: str, payload: Dict[str, Any], updated_at: str) -> None:
        normalized_email = email.lower().strip()
        self._col("ui_content").document(self._doc_id(normalized_email, content_key)).set({
            "email": normalized_email,
            "content_key": content_key,
            "payload": payload,
            "updated_at": updated_at,
        })

    def get_ui_content(self, email: str, content_key: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        data = self._col("ui_content").document(self._doc_id(normalized_email, content_key)).get()
        if not data.exists:
            return None
        payload = (data.to_dict() or {}).get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def add_adjustment_request(self, email: str, request_id: str, payload: Dict[str, Any], created_at: str) -> None:
        self._col("adjustment_requests").document(self._doc_id(request_id)).set({
            "request_id": request_id,
            "email": email.lower().strip(),
            "payload": payload,
            "created_at": created_at,
        })

    def list_adjustment_requests(self, email: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("adjustment_requests").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            payload = data.get("payload")
            if isinstance(payload, dict):
                rows.append(payload)
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def upsert_compliance_filing(
        self,
        email: str,
        period: str,
        report_id: str,
        status: str,
        due_date: str,
        payload: Dict[str, Any],
        updated_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        self._col("compliance_filings").document(self._doc_id(normalized_email, period, report_id)).set({
            "email": normalized_email,
            "period": period,
            "report_id": report_id,
            "status": status,
            "due_date": due_date,
            "payload": payload,
            "updated_at": updated_at,
        })

    def list_compliance_filings(self, email: str, period: str) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("compliance_filings").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email or str(data.get("period") or "") != period:
                continue
            payload = dict(data.get("payload") or {})
            payload["report_id"] = str(data.get("report_id") or "")
            payload["status"] = str(data.get("status") or "")
            payload["due_date"] = str(data.get("due_date") or "")
            payload["updated_at"] = str(data.get("updated_at") or "")
            rows.append(payload)
        return sorted(rows, key=lambda item: str(item.get("report_id") or ""))

    def get_compliance_filing(self, email: str, period: str, report_id: str) -> Optional[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        data = self._col("compliance_filings").document(self._doc_id(normalized_email, period, report_id)).get()
        if not data.exists:
            return None
        row = data.to_dict() or {}
        payload = dict(row.get("payload") or {})
        payload["report_id"] = report_id
        payload["status"] = str(row.get("status") or "")
        payload["due_date"] = str(row.get("due_date") or "")
        payload["updated_at"] = str(row.get("updated_at") or "")
        return payload

    def add_compliance_submission_history(
        self,
        history_id: str,
        email: str,
        period: str,
        report_id: str,
        payload: Dict[str, Any],
        created_at: str,
    ) -> None:
        normalized_email = email.lower().strip()
        self._col("compliance_submission_history").document(self._doc_id(history_id)).set({
            "history_id": history_id,
            "email": normalized_email,
            "period": period,
            "report_id": report_id,
            "payload": payload,
            "created_at": created_at,
        })

    def list_compliance_submission_history(self, email: str, period: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_email = email.lower().strip()
        rows: List[Dict[str, Any]] = []
        for doc in self._col("compliance_submission_history").stream():
            data = doc.to_dict() or {}
            if str(data.get("email") or "") != normalized_email:
                continue
            if period and str(data.get("period") or "") != period:
                continue
            payload = dict(data.get("payload") or {})
            payload["history_id"] = str(data.get("history_id") or "")
            payload["report_id"] = str(data.get("report_id") or "")
            payload["period"] = str(data.get("period") or "")
            payload["created_at"] = str(data.get("created_at") or "")
            rows.append(payload)
        return sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)

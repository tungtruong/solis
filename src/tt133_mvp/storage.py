from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AppStorage:
    db_path: Path

    @classmethod
    def from_workspace(cls, workspace_root: str) -> "AppStorage":
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

    def get_company_profile(self, email: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM company_profiles WHERE email = ?",
                (email,),
            ).fetchone()
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

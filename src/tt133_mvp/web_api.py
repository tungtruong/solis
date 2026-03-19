from __future__ import annotations

import base64
import binascii
import calendar
from collections import Counter
import json
import math
import mimetypes
import os
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .advanced_controls import AdjustmentControlService
from .posting_engine import PostingEngine
from .reporting import ReportService
from .rule_store import RuleStore
from .storage import AppStorage

WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])
store = RuleStore.from_workspace(WORKSPACE_ROOT)
storage = AppStorage.from_workspace(WORKSPACE_ROOT)
storage.init_db()
posting_engine = PostingEngine(store)
report_service = ReportService(store)
adjustment_service = AdjustmentControlService(store)

MOCK_COMPANY_ID = "COMP-WS-001"
MOCK_COMPANY_PROFILE = {
    "company_id": MOCK_COMPANY_ID,
    "company_name": "Công ty TNHH WSSMEAS Mock",
    "tax_code": "9999999998",
    "address": "12 Nguyễn Huệ, Quận 1, TP.HCM",
    "fiscal_year_start": "01-01",
    "tax_declaration_cycle": "monthly",
    "default_bank_account": "9704-0000-8899",
    "legal_representative": "Phạm Minh Đức",
    "industry": "Dịch vụ công nghệ và tư vấn kế toán",
}
MOCK_USERS = [
    {
        "email": "demo@wssmeas.local",
        "full_name": "Nguyễn Minh An",
        "role": "owner",
        "status": "active",
        "title": "Giám đốc điều hành",
        "phone": "0901000001",
    },
    {
        "email": "accountant@wssmeas.local",
        "full_name": "Trần Thu Hà",
        "role": "accountant",
        "status": "active",
        "title": "Kế toán trưởng",
        "phone": "0901000002",
    },
    {
        "email": "checker@wssmeas.local",
        "full_name": "Lê Quốc Bình",
        "role": "checker",
        "status": "active",
        "title": "Kiểm soát nội bộ",
        "phone": "0901000003",
    },
]
MOCK_USER_EMAILS = {str(item.get("email") or "").lower().strip() for item in MOCK_USERS}


def seed_mock_identity_data() -> None:
    now = datetime.utcnow().isoformat() + "Z"
    storage.upsert_company(MOCK_COMPANY_ID, MOCK_COMPANY_PROFILE, now, now)

    for user in MOCK_USERS:
        email = str(user["email"]).lower().strip()
        user_payload = {
            **user,
            "email": email,
            "company_id": MOCK_COMPANY_ID,
        }
        storage.upsert_user(email, user_payload, now, now)
        storage.upsert_user_company_membership(
            email=email,
            company_id=MOCK_COMPANY_ID,
            role=str(user.get("role") or "staff"),
            is_default=True,
            payload={
                "company_name": MOCK_COMPANY_PROFILE["company_name"],
                "title": user.get("title", ""),
                "scope": "full_access" if user.get("role") == "owner" else "accounting",
            },
            updated_at=now,
        )

        profile_payload = {
            "company_name": MOCK_COMPANY_PROFILE["company_name"],
            "tax_code": MOCK_COMPANY_PROFILE["tax_code"],
            "address": MOCK_COMPANY_PROFILE["address"],
            "legal_representative": MOCK_COMPANY_PROFILE["legal_representative"],
            "established_date": "2017-04-01",
            "fiscal_year_start": MOCK_COMPANY_PROFILE["fiscal_year_start"],
            "tax_declaration_cycle": MOCK_COMPANY_PROFILE["tax_declaration_cycle"],
            "default_bank_account": MOCK_COMPANY_PROFILE["default_bank_account"],
            "accountant_email": "accountant@wssmeas.local",
            "accounting_software_start_date": "2026-01-01",
            "company_id": MOCK_COMPANY_ID,
            "user_role": user.get("role"),
        }
        storage.upsert_company_profile(email, profile_payload, now)
        storage.upsert_onboarding_company(
            email=email,
            company_id=MOCK_COMPANY_ID,
            tax_code=MOCK_COMPANY_PROFILE["tax_code"],
            payload=profile_payload,
            is_default=True,
            updated_at=now,
        )
        storage.upsert_opening_balances(email, {"lines": []}, now)


seed_mock_identity_data()

app = FastAPI(title="TT133 MVP Web API", version="0.1.0")
allowed_origins_raw = os.getenv("SOLIS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

AUTH_ONBOARD_NO_STORE_PATHS = (
    "/api/auth/",
    "/api/company/",
    "/api/onboard/",
)


@app.middleware("http")
async def apply_sensitive_no_store_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(AUTH_ONBOARD_NO_STORE_PATHS):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
LOGIN_RATE_WINDOW_SECONDS = 300
LOGIN_RATE_MAX_ATTEMPTS = 6

UPLOADS_ROOT = Path(WORKSPACE_ROOT) / "data" / "uploads"
STAGING_UPLOADS_ROOT = Path(WORKSPACE_ROOT) / "data" / "uploads_staging"
ATTACHMENTS_BUCKET = str(os.getenv("SOLIS_ATTACHMENTS_BUCKET") or "").strip()
ATTACHMENTS_PREFIX = str(os.getenv("SOLIS_ATTACHMENTS_PREFIX") or "tt133_mvp").strip("/")
_GCS_CLIENT = None


def _attachments_use_gcs() -> bool:
    return bool(ATTACHMENTS_BUCKET)


def _get_gcs_bucket():
    global _GCS_CLIENT
    if _GCS_CLIENT is None:
        from google.cloud import storage as gcs_storage
        _GCS_CLIENT = gcs_storage.Client()
    return _GCS_CLIENT.bucket(ATTACHMENTS_BUCKET)


def _gcs_key(*parts: str) -> str:
    cleaned = [str(part or "").strip("/") for part in parts if str(part or "").strip("/")]
    prefix = ATTACHMENTS_PREFIX.strip("/")
    if prefix:
        cleaned = [prefix, *cleaned]
    return "/".join(cleaned)


def _safe_email_fragment(email: str) -> str:
    return str(email or "").lower().strip().replace("@", "_at_").replace(".", "_")


def _sanitize_case_id(case_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]", "", str(case_id or ""))
    return value or "CASE"


def _sanitize_file_name(file_name: str, fallback_name: str = "attachment.bin") -> str:
    name = Path(str(file_name or "")).name
    return name or fallback_name


def _sanitize_session_id(session_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))
    return value or "session"


def _build_permanent_attachment_path(email: str, case_id: str, file_name: str) -> Path:
    return UPLOADS_ROOT / _safe_email_fragment(email) / _sanitize_case_id(case_id) / _sanitize_file_name(file_name)


def _build_staged_attachment_path(email: str, case_id: str, session_id: str, file_name: str) -> Path:
    return (
        STAGING_UPLOADS_ROOT
        / _safe_email_fragment(email)
        / _sanitize_case_id(case_id)
        / _sanitize_session_id(session_id)
        / _sanitize_file_name(file_name)
    )


def _build_permanent_attachment_key(email: str, case_id: str, file_name: str) -> str:
    return _gcs_key("uploads", _safe_email_fragment(email), _sanitize_case_id(case_id), _sanitize_file_name(file_name))


def _build_staged_attachment_key(email: str, case_id: str, session_id: str, file_name: str) -> str:
    return _gcs_key(
        "uploads_staging",
        _safe_email_fragment(email),
        _sanitize_case_id(case_id),
        _sanitize_session_id(session_id),
        _sanitize_file_name(file_name),
    )


def _upload_attachment_bytes(key: str, content: bytes, mime_type: str = "application/octet-stream") -> None:
    bucket = _get_gcs_bucket()
    blob = bucket.blob(key)
    blob.upload_from_string(content, content_type=mime_type)


def _download_attachment_bytes(key: str) -> bytes:
    bucket = _get_gcs_bucket()
    blob = bucket.blob(key)
    if not blob.exists():
        return b""
    return blob.download_as_bytes()


def _delete_attachment_key(key: str) -> None:
    bucket = _get_gcs_bucket()
    blob = bucket.blob(key)
    if blob.exists():
        blob.delete()


def _copy_attachment_key(source_key: str, target_key: str) -> None:
    bucket = _get_gcs_bucket()
    source = bucket.blob(source_key)
    if not source.exists():
        return
    bucket.copy_blob(source, bucket, new_name=target_key)


def _delete_case_attachment_tree(email: str, case_id: str) -> None:
    normalized_email = _safe_email_fragment(email)
    normalized_case_id = _sanitize_case_id(case_id)
    if _attachments_use_gcs():
        bucket = _get_gcs_bucket()
        prefixes = [
            _gcs_key("uploads", normalized_email, normalized_case_id),
            _gcs_key("uploads_staging", normalized_email, normalized_case_id),
        ]
        for prefix in prefixes:
            for blob in bucket.list_blobs(prefix=f"{prefix}/"):
                blob.delete()
        return

    permanent_dir = UPLOADS_ROOT / normalized_email / normalized_case_id
    staging_dir = STAGING_UPLOADS_ROOT / normalized_email / normalized_case_id
    for candidate in [permanent_dir, staging_dir]:
        try:
            if candidate.exists():
                shutil.rmtree(candidate)
        except OSError:
            pass


def _load_attachment_bytes_by_ref(email: str, case_id: str, file_ref: str) -> Tuple[str, bytes]:
    normalized_email = email.lower().strip()
    normalized_case_id = _sanitize_case_id(case_id)
    normalized_ref = str(file_ref or "").strip()

    if normalized_ref.startswith("stg__"):
        parts = normalized_ref.split("__", 2)
        if len(parts) == 3:
            session_id = _sanitize_session_id(parts[1])
            staged_name = _sanitize_file_name(parts[2])
            if _attachments_use_gcs():
                key = _build_staged_attachment_key(normalized_email, normalized_case_id, session_id, staged_name)
                return staged_name, _download_attachment_bytes(key)
            path = _build_staged_attachment_path(normalized_email, normalized_case_id, session_id, staged_name)
            if path.exists() and path.is_file():
                return path.name, path.read_bytes()
        return "", b""

    if normalized_ref.startswith("perm__"):
        file_name = _sanitize_file_name(normalized_ref.split("__", 1)[1])
    else:
        file_name = _sanitize_file_name(normalized_ref)

    if _attachments_use_gcs():
        key = _build_permanent_attachment_key(normalized_email, normalized_case_id, file_name)
        return file_name, _download_attachment_bytes(key)

    path = _build_permanent_attachment_path(normalized_email, normalized_case_id, file_name)
    if path.exists() and path.is_file():
        return path.name, path.read_bytes()
    return "", b""


def _delete_staged_attachments(email: str, case_id: str, staged_attachments: List[Any]) -> None:
    for item in staged_attachments:
        if not isinstance(item, dict):
            continue
        session_id = str(item.get("session_id") or "")
        stored_name = str(item.get("stored_name") or item.get("name") or "")
        if not session_id or not stored_name:
            continue
        if _attachments_use_gcs():
            staged_key = _build_staged_attachment_key(email, case_id, session_id, stored_name)
            _delete_attachment_key(staged_key)
            continue
        staged_path = _build_staged_attachment_path(email, case_id, session_id, stored_name)
        try:
            if staged_path.exists():
                staged_path.unlink()
        except OSError:
            continue

    if _attachments_use_gcs():
        return

    case_staging_dir = STAGING_UPLOADS_ROOT / _safe_email_fragment(email) / _sanitize_case_id(case_id)
    try:
        if case_staging_dir.exists() and not any(case_staging_dir.rglob("*")):
            case_staging_dir.rmdir()
    except OSError:
        pass


def _commit_staged_attachments(email: str, case_id: str, staged_attachments: List[Any]) -> List[str]:
    committed_names: List[str] = []
    if not staged_attachments:
        return committed_names

    for item in staged_attachments:
        if not isinstance(item, dict):
            legacy_name = _sanitize_file_name(str(item or ""))
            if legacy_name:
                committed_names.append(legacy_name)
            continue

        session_id = str(item.get("session_id") or "")
        stored_name = _sanitize_file_name(str(item.get("stored_name") or item.get("name") or ""))
        if not session_id or not stored_name:
            continue

        if _attachments_use_gcs():
            staged_key = _build_staged_attachment_key(email, case_id, session_id, stored_name)
            permanent_key = _build_permanent_attachment_key(email, case_id, stored_name)
            _copy_attachment_key(staged_key, permanent_key)
            _delete_attachment_key(staged_key)
        else:
            staged_path = _build_staged_attachment_path(email, case_id, session_id, stored_name)
            permanent_path = _build_permanent_attachment_path(email, case_id, stored_name)
            permanent_path.parent.mkdir(parents=True, exist_ok=True)

            if staged_path.exists():
                shutil.move(str(staged_path), str(permanent_path))

        committed_names.append(stored_name)

    _delete_staged_attachments(email, case_id, staged_attachments)
    return committed_names


@app.get("/api/demo/evidence/{case_id}/{file_ref}")
def get_demo_evidence_file(
    case_id: str,
    file_ref: str,
    email: str = "demo@wssmeas.local",
) -> Response:
    file_name, payload = _load_attachment_bytes_by_ref(email, case_id, file_ref)
    if not payload:
        raise HTTPException(status_code=404, detail="EVIDENCE_FILE_NOT_FOUND")

    media_type = mimetypes.guess_type(str(file_name or file_ref))[0] or "application/octet-stream"
    return Response(content=payload, media_type=media_type)


class LoginPayload(BaseModel):
    email: str
    password: str = Field(min_length=3)


class CompanyProfilePayload(BaseModel):
    company_name: str
    tax_code: str
    address: str
    legal_representative: str = ""
    established_date: str = ""
    fiscal_year_start: str
    tax_declaration_cycle: str
    default_bank_account: str
    accountant_email: str
    accounting_software_start_date: str = ""
    tax_office_code: str = ""
    tax_office_name: str = ""
    province_code: str = ""
    province_name: str = ""
    company_id: str = ""


class SelectCompanyPayload(BaseModel):
    company_id: str


class EventPayload(BaseModel):
    source_id: str
    event_type: str
    data: Dict[str, Any]


class AdjustmentPayload(BaseModel):
    target_entry_id: str
    reason: str
    checker_id: str


class DemoUiActionPayload(BaseModel):
    email: str = "demo@wssmeas.local"
    company_id: str = ""
    action: str
    text: str = ""
    case_id: str = ""


class DemoAttachmentPayload(BaseModel):
    name: str
    mime_type: str = "application/octet-stream"
    size: int = 0
    content_base64: str


class DemoUiActionWithAttachmentsPayload(DemoUiActionPayload):
    attachments: List[DemoAttachmentPayload] = []


class ComplianceActionPayload(BaseModel):
    email: str = "demo@wssmeas.local"
    company_id: str = ""
    period: str
    report_id: str
    submitted_by: str = ""


class OpeningBalancesPayload(BaseModel):
    email: str = "demo@wssmeas.local"
    company_id: str = ""
    lines: List[Dict[str, Any]] = []


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="MISSING_BEARER_TOKEN")
    return authorization.replace("Bearer ", "", 1).strip()


def get_current_email(authorization: Optional[str] = Header(default=None)) -> str:
    token = _extract_token(authorization)
    email = storage.get_session_email(token)
    if not email:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    return email


def _normalize_tax_code(tax_code: str) -> str:
    return re.sub(r"[^0-9A-Za-z-]", "", str(tax_code or "")).strip().upper()


def _profile_complete(profile: Dict[str, Any]) -> bool:
    required_fields = [
        "company_name",
        "tax_code",
        "address",
        "legal_representative",
        "established_date",
        "accounting_software_start_date",
        "fiscal_year_start",
        "tax_declaration_cycle",
        "default_bank_account",
        "accountant_email",
    ]
    return all(str(profile.get(field) or "").strip() for field in required_fields)


def _check_login_rate_limit(email: str, request: Request) -> None:
    ip = str(request.client.host if request.client else "unknown")
    key = f"{email.lower().strip()}::{ip}"
    now_ts = time.time()
    recent = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now_ts - stamp <= LOGIN_RATE_WINDOW_SECONDS]
    if len(recent) >= LOGIN_RATE_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    recent.append(now_ts)
    LOGIN_ATTEMPTS[key] = recent


def _clear_login_rate_limit(email: str, request: Request) -> None:
    ip = str(request.client.host if request.client else "unknown")
    key = f"{email.lower().strip()}::{ip}"
    if key in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[key]


def _safe_fetch_json(url: str) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as response:
            content = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _lookup_company_by_tax_code_external(tax_code: str) -> Dict[str, Any]:
    normalized_tax = _normalize_tax_code(tax_code)
    if not normalized_tax:
        return {"found": False, "source": "none", "profile": None}

    vietqr_url = f"https://api.vietqr.io/v2/business/{urllib.parse.quote(normalized_tax)}"
    vietqr_payload = _safe_fetch_json(vietqr_url)
    if vietqr_payload and str(vietqr_payload.get("code") or "") == "00":
        data = vietqr_payload.get("data") if isinstance(vietqr_payload.get("data"), dict) else {}
        profile = {
            "tax_code": normalized_tax,
            "company_name": str(data.get("name") or "").strip(),
            "address": str(data.get("address") or "").strip(),
            "legal_representative": str(data.get("representative") or "").strip(),
            "established_date": str(data.get("issueDate") or "").strip(),
        }
        if profile["company_name"]:
            return {"found": True, "source": "vietqr", "profile": profile}

    esgoo_url = f"https://esgoo.net/api-mst/{urllib.parse.quote(normalized_tax)}.htm"
    esgoo_payload = _safe_fetch_json(esgoo_url)
    if esgoo_payload and int(esgoo_payload.get("error", 1) or 1) == 0:
        data = esgoo_payload.get("data") if isinstance(esgoo_payload.get("data"), dict) else {}
        profile = {
            "tax_code": normalized_tax,
            "company_name": str(data.get("ten") or data.get("company_name") or "").strip(),
            "address": str(data.get("diachi") or data.get("address") or "").strip(),
            "legal_representative": str(data.get("daidienphapluat") or data.get("legal_representative") or "").strip(),
            "established_date": str(data.get("ngaycap") or data.get("established_date") or "").strip(),
        }
        if profile["company_name"]:
            return {"found": True, "source": "esgoo", "profile": profile}

    return {
        "found": False,
        "source": "fallback",
        "profile": {
            "tax_code": normalized_tax,
            "company_name": "",
            "address": "",
            "legal_representative": "",
            "established_date": "",
        },
    }


def build_ui_hints(has_company_profile: bool, last_action: str) -> Dict[str, Any]:
    if not has_company_profile:
        return {
            "next_actions": ["create_company_profile"],
            "available_actions": ["company_setup"],
            "blocked_actions": ["post_event", "view_reports", "create_adjustment"],
            "context": "onboarding_required",
            "last_action": last_action,
        }
    return {
        "next_actions": ["upload_source_file", "post_event", "open_reports"],
        "available_actions": ["post_event", "view_reports", "create_adjustment"],
        "blocked_actions": [],
        "context": "ready",
        "last_action": last_action,
    }


def resolve_company_id_for_user(email: str, requested_company_id: str = "") -> str:
    normalized_email = email.lower().strip()
    requested = str(requested_company_id or "").strip()
    include_mock_company = normalized_email in MOCK_USER_EMAILS

    memberships = storage.list_user_memberships(normalized_email)
    membership_ids = {
        str(item.get("company_id") or "").strip()
        for item in memberships
        if include_mock_company or str(item.get("company_id") or "").strip() != MOCK_COMPANY_ID
    }
    membership_ids.discard("")

    if requested and requested in membership_ids:
        return requested

    if requested:
        onboard_company = storage.get_onboarding_company(normalized_email, requested)
        if onboard_company and str(onboard_company.get("company_id") or "").strip():
            return str(onboard_company.get("company_id"))
        raise HTTPException(status_code=403, detail="COMPANY_ACCESS_DENIED")

    default_membership = storage.get_default_company_id(normalized_email)
    if default_membership and (include_mock_company or str(default_membership).strip() != MOCK_COMPANY_ID):
        return str(default_membership)

    if memberships:
        first_membership_company_id = next(
            (
                str(item.get("company_id") or "").strip()
                for item in memberships
                if str(item.get("company_id") or "").strip()
                and (include_mock_company or str(item.get("company_id") or "").strip() != MOCK_COMPANY_ID)
            ),
            "",
        )
        if first_membership_company_id:
            return first_membership_company_id

    default_onboard = storage.get_default_onboarding_company(normalized_email)
    if default_onboard and str(default_onboard.get("company_id") or "").strip():
        return str(default_onboard.get("company_id"))

    return "COMP-DEFAULT"


def company_scope_key(company_id: str) -> str:
    normalized_company_id = str(company_id or "").strip() or "COMP-DEFAULT"
    return f"company::{normalized_company_id}"


def _build_accessible_company_items(email: str) -> tuple[list[dict[str, Any]], str]:
    normalized_email = email.lower().strip()
    include_mock_company = normalized_email in MOCK_USER_EMAILS
    memberships = storage.list_user_memberships(normalized_email)
    onboarding_companies = storage.list_onboarding_companies(normalized_email)

    combined: dict[str, dict[str, Any]] = {}

    for membership in memberships:
        company_id = str(membership.get("company_id") or "").strip()
        if not company_id:
            continue
        if not include_mock_company and company_id == MOCK_COMPANY_ID:
            continue
        company_payload = storage.get_company(company_id) or {}
        merged = {**company_payload, **membership}
        merged["company_id"] = company_id
        merged["company_name"] = str(
            merged.get("company_name") or company_payload.get("company_name") or membership.get("company_name") or company_id
        )
        merged["tax_code"] = str(merged.get("tax_code") or company_payload.get("tax_code") or membership.get("tax_code") or "")
        merged["is_default"] = bool(membership.get("is_default"))
        combined[company_id] = merged

    for onboarding in onboarding_companies:
        company_id = str(onboarding.get("company_id") or "").strip()
        if not company_id:
            continue
        if not include_mock_company and company_id == MOCK_COMPANY_ID:
            continue
        if company_id in combined:
            continue
        fallback = dict(onboarding)
        fallback["company_id"] = company_id
        fallback["company_name"] = str(fallback.get("company_name") or company_id)
        fallback["tax_code"] = str(fallback.get("tax_code") or "")
        fallback["is_default"] = bool(fallback.get("is_default"))
        combined[company_id] = fallback

    items = list(combined.values())
    items.sort(key=lambda item: (0 if bool(item.get("is_default")) else 1, str(item.get("company_name") or "")))
    default_company = next((item for item in items if bool(item.get("is_default"))), None)
    default_company_id = str(default_company.get("company_id") or "") if default_company else ""
    if not default_company_id and items:
        default_company_id = str(items[0].get("company_id") or "")
    return items, default_company_id


def build_demo_dashboard_meta() -> Dict[str, Any]:
    return {
        "trends": {
            "cash_pct": 5.2,
            "payable_pct": 12.0,
            "receivable_pct": -8.0,
        },
        "warnings": [
            "Công nợ phải trả tăng nhanh (+12%).",
            "2 khoản cần thanh toán trong 3 ngày tới.",
        ],
        "priorities": [
            "Thanh toán nhà cung cấp A.",
            "Thu hồi công nợ khách hàng B.",
        ],
    }


def _normalize_tax_declaration_cycle(value: str) -> str:
    token = str(value or "").strip().lower()
    if token in {"quarter", "quarterly", "quy", "q", "quý"}:
        return "quarter"
    return "month"


def _resolve_company_profile_for_scope(email: str, company_id: str) -> Dict[str, Any]:
    normalized_email = str(email or "").strip().lower()
    resolved_company_id = str(company_id or "").strip()

    company_payload = storage.get_company(resolved_company_id) or {}
    onboarding_payload = storage.get_onboarding_company(normalized_email, resolved_company_id) or {}
    if not onboarding_payload:
        default_onboarding = storage.get_default_onboarding_company(normalized_email) or {}
        if str(default_onboarding.get("company_id") or "").strip() in {"", resolved_company_id}:
            onboarding_payload = default_onboarding

    profile_payload = storage.get_company_profile(normalized_email) or {}
    if str(profile_payload.get("company_id") or "").strip() not in {"", resolved_company_id}:
        profile_payload = {}

    merged: Dict[str, Any] = {}
    for source in (profile_payload, onboarding_payload, company_payload):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

    if resolved_company_id:
        merged["company_id"] = resolved_company_id
    return merged


def _derive_period_for_cycle(cycle: str, reference_date: datetime) -> str:
    if cycle == "quarter":
        quarter = ((reference_date.month - 1) // 3) + 1
        return f"{reference_date.year}-Q{quarter}"
    return f"{reference_date.year}-{reference_date.month:02d}"


def _is_valid_period_for_cycle(period: str, cycle: str) -> bool:
    token = str(period or "").strip()
    if cycle == "quarter":
        return bool(re.fullmatch(r"\d{4}-Q[1-4]", token))
    return bool(re.fullmatch(r"\d{4}-\d{2}", token))


def _format_period_label(period: str, cycle: str) -> str:
    token = str(period or "").strip()
    if cycle == "quarter":
        match = re.fullmatch(r"(\d{4})-Q([1-4])", token)
        if not match:
            return token
        return f"Quý {int(match.group(2))}/{match.group(1)}"
    match = re.fullmatch(r"(\d{4})-(\d{2})", token)
    if not match:
        return token
    return f"Tháng {int(match.group(2))}/{match.group(1)}"


def _period_end_date(period: str, cycle: str) -> str:
    token = str(period or "").strip()
    if cycle == "quarter":
        match = re.fullmatch(r"(\d{4})-Q([1-4])", token)
        if match:
            year = int(match.group(1))
            quarter = int(match.group(2))
            month = quarter * 3
            day = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{day:02d}"
        return datetime.utcnow().date().isoformat()

    match = re.fullmatch(r"(\d{4})-(\d{2})", token)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        month = min(max(month, 1), 12)
        day = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-{day:02d}"
    return datetime.utcnow().date().isoformat()


def _vat_due_date_for_period(period: str, cycle: str) -> str:
    token = str(period or "").strip()
    if cycle == "quarter":
        match = re.fullmatch(r"(\d{4})-Q([1-4])", token)
        if match:
            year = int(match.group(1))
            quarter = int(match.group(2))
            end_month = quarter * 3
            due_month = end_month + 1
            due_year = year
            if due_month > 12:
                due_month -= 12
                due_year += 1
            due_day = calendar.monthrange(due_year, due_month)[1]
            return f"{due_year:04d}-{due_month:02d}-{due_day:02d}"
        return datetime.utcnow().date().isoformat()

    match = re.fullmatch(r"(\d{4})-(\d{2})", token)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        due_month = month + 1
        due_year = year
        if due_month > 12:
            due_month = 1
            due_year += 1
        return f"{due_year:04d}-{due_month:02d}-20"
    return datetime.utcnow().date().isoformat()


def _build_period_options(cycle: str, reference_date: datetime) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    if cycle == "quarter":
        current_quarter = ((reference_date.month - 1) // 3) + 1
        period_index = reference_date.year * 4 + (current_quarter - 1)
        for offset in range(0, 8):
            idx = period_index - offset
            year = idx // 4
            quarter = (idx % 4) + 1
            value = f"{year:04d}-Q{quarter}"
            options.append({"value": value, "label": f"Quý {quarter}/{year}"})
        return options

    total_month_index = reference_date.year * 12 + (reference_date.month - 1)
    for offset in range(0, 12):
        idx = total_month_index - offset
        year = idx // 12
        month = (idx % 12) + 1
        value = f"{year:04d}-{month:02d}"
        options.append({"value": value, "label": f"Tháng {month}/{year}"})
    return options


def _format_ddmmyyyy(date_iso: str) -> str:
    token = str(date_iso or "").strip()
    try:
        dt = datetime.fromisoformat(token)
        return f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"
    except ValueError:
        return ""


def _to_ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _build_simple_pdf_bytes(text_content: str) -> bytes:
    lines = [line.strip() for line in str(text_content or "").splitlines() if line.strip()]
    if not lines:
        lines = ["TO KHAI THUE"]
    lines = [_to_ascii_text(line) for line in lines[:220]]

    def _escape_pdf_text(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
    for idx, line in enumerate(lines):
        escaped = _escape_pdf_text(line)
        if idx == 0:
            stream_lines.append(f"({escaped}) Tj")
        else:
            stream_lines.append("T*")
            stream_lines.append(f"({escaped}) Tj")
    stream_lines.append("ET")
    stream_data = ("\n".join(stream_lines) + "\n").encode("latin-1", "ignore")

    objects: List[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(
        b"5 0 obj\n<< /Length " + str(len(stream_data)).encode("ascii") + b" >>\nstream\n" + stream_data + b"endstream\nendobj\n"
    )

    pdf_parts: List[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current_len = len(pdf_parts[0])
    for obj in objects:
        offsets.append(current_len)
        pdf_parts.append(obj)
        current_len += len(obj)

    xref_start = current_len
    xref_lines = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n \n")
    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    pdf_parts.append("".join(xref_lines).encode("ascii"))
    pdf_parts.append(trailer.encode("ascii"))
    return b"".join(pdf_parts)


def _strip_xml_ns(tag: str) -> str:
    token = str(tag or "")
    if "}" in token:
        return token.split("}", 1)[1]
    return token


def _build_pdf_from_xml(xml_text: str, title: str = "TO KHAI THUE") -> bytes:
    lines: List[str] = [str(title or "TO KHAI THUE").strip()]
    payload = str(xml_text or "").strip()
    if not payload:
        return _build_simple_pdf_bytes("\n".join(lines))

    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        # Fallback to raw XML lines when parser cannot parse malformed content.
        return _build_simple_pdf_bytes("\n".join([*lines, *payload.splitlines()]))

    def find_child(node: Optional[ET.Element], child_tag: str) -> Optional[ET.Element]:
        if node is None:
            return None
        for child in list(node):
            if _strip_xml_ns(child.tag) == child_tag:
                return child
        return None

    def find_path(node: Optional[ET.Element], *parts: str) -> Optional[ET.Element]:
        cursor = node
        for part in parts:
            cursor = find_child(cursor, part)
            if cursor is None:
                return None
        return cursor

    def text_of(node: Optional[ET.Element]) -> str:
        if node is None:
            return ""
        return str(node.text or "").strip()

    def text_at(node: Optional[ET.Element], *parts: str) -> str:
        return text_of(find_path(node, *parts))

    def collect_ct_values(node: Optional[ET.Element]) -> Dict[str, str]:
        values: Dict[str, str] = {}
        if node is None:
            return values
        for element in node.iter():
            tag = _strip_xml_ns(element.tag)
            if re.fullmatch(r"ct\d+[ab]?", tag):
                val = str(element.text or "").strip() or "0"
                values[tag] = val
        return values

    if _strip_xml_ns(root.tag) == "HSoThueDTu":
        hoso = find_child(root, "HSoKhaiThue")
        tkhai = find_path(hoso, "TTinChung", "TTinTKhaiThue", "TKhaiThue")
        nnt = find_path(hoso, "TTinChung", "TTinTKhaiThue", "NNT")
        ctieu = find_child(hoso, "CTieuTKhaiChinh")
        ct_values = collect_ct_values(ctieu)

        indicator_labels: Dict[str, str] = {
            "ct21": "Khong phat sinh hoat dong mua, ban trong ky",
            "ct22": "Thue GTGT con duoc khau tru ky truoc",
            "ct23": "Gia tri HHDV mua vao",
            "ct24": "Thue GTGT cua HHDV mua vao",
            "ct23a": "Gia tri HHDV nhap khau",
            "ct24a": "Thue GTGT HHDV nhap khau",
            "ct25": "Tong thue GTGT duoc khau tru ky nay",
            "ct26": "Doanh thu khong chiu thue GTGT",
            "ct27": "Doanh thu thue suat 0%",
            "ct28": "Thue GTGT cua HHDV thue suat 0%",
            "ct29": "Doanh thu khong phai ke khai tinh nop",
            "ct30": "Doanh thu thue suat 5%",
            "ct31": "Thue GTGT cua HHDV thue suat 5%",
            "ct32": "Doanh thu thue suat 10%",
            "ct33": "Thue GTGT cua HHDV thue suat 10%",
            "ct32a": "Doanh thu khong tinh thue theo TT80",
            "ct34": "Tong doanh thu HHDV ban ra",
            "ct35": "Tong thue GTGT cua HHDV ban ra",
            "ct36": "Thue GTGT phat sinh ky nay",
            "ct37": "Dieu chinh giam",
            "ct38": "Dieu chinh tang",
            "ct39a": "Thue GTGT da nop o dia phuong khac",
            "ct40a": "Thue GTGT con phai nop",
            "ct40b": "Thue GTGT con duoc khau tru chuyen ky sau",
            "ct40": "Thue GTGT phai nop",
            "ct41": "Thue GTGT chua khau tru het ky nay",
            "ct42": "Thue GTGT de nghi hoan",
            "ct43": "Thue GTGT con duoc khau tru chuyen ky sau",
        }
        preferred_order = [
            "ct21", "ct22", "ct23", "ct24", "ct23a", "ct24a", "ct25", "ct26", "ct27", "ct28", "ct29", "ct30", "ct31",
            "ct32", "ct33", "ct32a", "ct34", "ct35", "ct36", "ct37", "ct38", "ct39a", "ct40a", "ct40b", "ct40", "ct41",
            "ct42", "ct43",
        ]

        def format_amount(raw: str) -> str:
            token = str(raw or "").strip()
            if not token:
                return "0"
            try:
                return f"{int(round(float(token))):,}"
            except ValueError:
                return token

        lines = [
            "TO KHAI THUE GIA TRI GIA TANG - MAU 01/GTGT",
            "(Ban in tu file XML ke khai)",
            "",
            f"MST: {text_at(nnt, 'mst')}",
            f"Ten NNT: {text_at(nnt, 'tenNNT')}",
            f"Dia chi: {text_at(nnt, 'dchiNNT')}",
            f"Ky ke khai: {text_at(tkhai, 'KyKKhaiThue', 'kyKKhai')} ({text_at(tkhai, 'KyKKhaiThue', 'kieuKy')})",
            f"Tu ngay - Den ngay: {text_at(tkhai, 'KyKKhaiThue', 'kyKKhaiTuNgay')} - {text_at(tkhai, 'KyKKhaiThue', 'kyKKhaiDenNgay')}",
            f"Co quan thue: {text_at(tkhai, 'maCQTNoiNop')} - {text_at(tkhai, 'tenCQTNoiNop')}",
            f"Ngay lap: {text_at(tkhai, 'ngayLapTKhai')}    Nguoi ky: {text_at(tkhai, 'nguoiKy')}",
            "",
            "CHI TIEU CHINH",
            "---------------------------------------------------------------",
            "Ma    Noi dung                                               Gia tri",
            "---------------------------------------------------------------",
        ]

        for code in preferred_order:
            value_raw = ct_values.get(code, "0")
            label = indicator_labels.get(code, code)
            lines.append(f"[{code[2:]:<4}] {label:<54} {format_amount(value_raw):>14}")

        lines.append("---------------------------------------------------------------")
        return _build_simple_pdf_bytes("\n".join(lines))

    def walk(node: ET.Element, path_tokens: List[str]) -> None:
        current_tag = _strip_xml_ns(node.tag)
        current_path = [*path_tokens, current_tag]
        text_value = str(node.text or "").strip()
        if text_value:
            lines.append(f"{'/'.join(current_path)}: {text_value}")
        for attr_key, attr_val in (node.attrib or {}).items():
            lines.append(f"{'/'.join(current_path)}@{_strip_xml_ns(attr_key)}: {str(attr_val).strip()}")
        for child in list(node):
            walk(child, current_path)

    walk(root, [])
    return _build_simple_pdf_bytes("\n".join(lines))


def _build_vat_declaration_tt80(
    company_profile: Dict[str, Any],
    period: str,
    cycle: str,
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    tax_report = report_service.generate_tax_reports(entries, _period_end_date(period, cycle))
    account_summary = report_service.summarize_accounts(entries)

    doanh_thu_chiu_thue = 0.0
    for account_code, values in account_summary.items():
        if str(account_code).startswith("511"):
            credit = float(values.get("credit", 0) or 0)
            debit = float(values.get("debit", 0) or 0)
            doanh_thu_chiu_thue += max(credit - debit, 0.0)

    vat_output = max(float(tax_report.get("thue_gtgt", {}).get("thue_dau_ra", 0) or 0), 0.0)
    vat_input = max(float(tax_report.get("thue_gtgt", {}).get("thue_dau_vao_duoc_khau_tru", 0) or 0), 0.0)
    vat_net = float(tax_report.get("thue_gtgt", {}).get("thue_gtgt_thuan", 0) or 0)
    vat_payable = max(vat_net, 0.0)
    vat_carry_forward = max(-vat_net, 0.0)

    period_label = _format_period_label(period, cycle)
    cycle_label = "theo tháng" if cycle == "month" else "theo quý"
    company_name = str(company_profile.get("company_name") or "").strip()
    tax_code = _normalize_tax_code(str(company_profile.get("tax_code") or ""))
    ma_cqt = str(company_profile.get("tax_office_code") or "10101").strip()
    ten_cqt = str(company_profile.get("tax_office_name") or "Cơ quan thuế quản lý").strip()
    legal_representative = str(company_profile.get("legal_representative") or "").strip()
    full_address = str(company_profile.get("address") or "").strip()
    province_code = str(company_profile.get("province_code") or "").strip()
    province_name = str(company_profile.get("province_name") or "").strip()

    period_start = _period_end_date(period, cycle)
    try:
        end_date_dt = datetime.fromisoformat(period_start)
        if cycle == "quarter":
            quarter = ((end_date_dt.month - 1) // 3) + 1
            start_month = (quarter - 1) * 3 + 1
            start_date_iso = f"{end_date_dt.year:04d}-{start_month:02d}-01"
            ky_kkhai = f"{quarter}/{end_date_dt.year:04d}"
            kieu_ky = "Q"
        else:
            start_date_iso = f"{end_date_dt.year:04d}-{end_date_dt.month:02d}-01"
            ky_kkhai = f"{end_date_dt.month}/{end_date_dt.year:04d}"
            kieu_ky = "M"
    except ValueError:
        start_date_iso = datetime.utcnow().date().isoformat()
        period_start = start_date_iso
        ky_kkhai = period
        kieu_ky = "Q" if cycle == "quarter" else "M"

    ct23 = int(round(0))
    ct24 = int(round(vat_input))
    ct25 = int(round(vat_input))
    ct32 = int(round(doanh_thu_chiu_thue))
    ct33 = int(round(vat_output))
    ct34 = int(round(ct32))
    ct35 = int(round(ct33))
    ct40a = int(round(vat_payable))
    ct40b = int(round(vat_carry_forward))
    ct40 = int(round(ct40a))
    today_iso = datetime.utcnow().date().isoformat()

    xml_text = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<HSoThueDTu xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns=\"http://kekhaithue.gdt.gov.vn/TKhaiThue\">\n"
        "  <HSoKhaiThue id=\"ID_1\">\n"
        "    <TTinChung>\n"
        "      <TTinDVu>\n"
        "        <maDVu>HTKK</maDVu>\n"
        "        <tenDVu>HỖ TRỢ KÊ KHAI THUẾ</tenDVu>\n"
        "        <pbanDVu>5.6.1</pbanDVu>\n"
        "        <ttinNhaCCapDVu>D5CE995C9CD5C420614C8FE28EFFE163</ttinNhaCCapDVu>\n"
        "      </TTinDVu>\n"
        "      <TTinTKhaiThue>\n"
        "        <TKhaiThue>\n"
        "          <maTKhai>842</maTKhai>\n"
        "          <tenTKhai>TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG (Mẫu số 01/GTGT)</tenTKhai>\n"
        "          <moTaBMau>(Ban hành kèm theo Thông tư số 80/2021/TT-BTC ngày 29 tháng 9 năm 2021 của Bộ trưởng Bộ Tài chính)</moTaBMau>\n"
        "          <pbanTKhaiXML>2.8.3</pbanTKhaiXML>\n"
        "          <loaiTKhai>C</loaiTKhai>\n"
        "          <soLan>0</soLan>\n"
        "          <KyKKhaiThue>\n"
        f"            <kieuKy>{kieu_ky}</kieuKy>\n"
        f"            <kyKKhai>{xml_escape(ky_kkhai)}</kyKKhai>\n"
        f"            <kyKKhaiTuNgay>{_format_ddmmyyyy(start_date_iso)}</kyKKhaiTuNgay>\n"
        f"            <kyKKhaiDenNgay>{_format_ddmmyyyy(period_start)}</kyKKhaiDenNgay>\n"
        "            <kyKKhaiTuThang />\n"
        "            <kyKKhaiDenThang />\n"
        "          </KyKKhaiThue>\n"
        f"          <maCQTNoiNop>{xml_escape(ma_cqt)}</maCQTNoiNop>\n"
        f"          <tenCQTNoiNop>{xml_escape(ten_cqt)}</tenCQTNoiNop>\n"
        f"          <ngayLapTKhai>{today_iso}</ngayLapTKhai>\n"
        "          <GiaHan>\n"
        "            <maLyDoGiaHan />\n"
        "            <lyDoGiaHan />\n"
        "          </GiaHan>\n"
        f"          <nguoiKy>{xml_escape(legal_representative)}</nguoiKy>\n"
        f"          <ngayKy>{today_iso}</ngayKy>\n"
        "          <nganhNgheKD />\n"
        "        </TKhaiThue>\n"
        "        <NNT>\n"
        f"          <mst>{xml_escape(tax_code)}</mst>\n"
        f"          <tenNNT>{xml_escape(company_name)}</tenNNT>\n"
        f"          <dchiNNT>{xml_escape(full_address)}</dchiNNT>\n"
        "          <phuongXa />\n"
        "          <maHuyenNNT />\n"
        "          <tenHuyenNNT />\n"
        f"          <maTinhNNT>{xml_escape(province_code)}</maTinhNNT>\n"
        f"          <tenTinhNNT>{xml_escape(province_name)}</tenTinhNNT>\n"
        "          <dthoaiNNT />\n"
        "          <faxNNT />\n"
        "          <emailNNT />\n"
        "        </NNT>\n"
        "      </TTinTKhaiThue>\n"
        "    </TTinChung>\n"
        "    <CTieuTKhaiChinh>\n"
        "      <ma_NganhNghe>00</ma_NganhNghe>\n"
        "      <ten_NganhNghe>Hoạt động sản xuất kinh doanh thông thường</ten_NganhNghe>\n"
        "      <tieuMucHachToan>1701</tieuMucHachToan>\n"
        "      <Header>\n"
        "        <ct09 />\n"
        "        <ct10 />\n"
        "        <DiaChiHDSXKDKhacTinhNDTSC>\n"
        "          <ct11a_phuongXa_ma />\n"
        "          <ct11a_phuongXa_ten />\n"
        "          <ct11b_quanHuyen_ma />\n"
        "          <ct11b_quanHuyen_ten />\n"
        "          <ct11c_tinhTP_ma />\n"
        "          <ct11c_tinhTP_ten />\n"
        "        </DiaChiHDSXKDKhacTinhNDTSC>\n"
        "      </Header>\n"
        "      <ct21>0</ct21>\n"
        "      <ct22>0</ct22>\n"
        "      <GiaTriVaThueGTGTHHDVMuaVao>\n"
        f"        <ct23>{ct23}</ct23>\n"
        f"        <ct24>{ct24}</ct24>\n"
        "      </GiaTriVaThueGTGTHHDVMuaVao>\n"
        "      <HangHoaDichVuNhapKhau>\n"
        "        <ct23a>0</ct23a>\n"
        "        <ct24a>0</ct24a>\n"
        "      </HangHoaDichVuNhapKhau>\n"
        f"      <ct25>{ct25}</ct25>\n"
        "      <ct26>0</ct26>\n"
        "      <HHDVBRaChiuThueGTGT>\n"
        "        <ct27>0</ct27>\n"
        "        <ct28>0</ct28>\n"
        "      </HHDVBRaChiuThueGTGT>\n"
        "      <ct29>0</ct29>\n"
        "      <HHDVBRaChiuTSuat5>\n"
        "        <ct30>0</ct30>\n"
        "        <ct31>0</ct31>\n"
        "      </HHDVBRaChiuTSuat5>\n"
        "      <HHDVBRaChiuTSuat10>\n"
        f"        <ct32>{ct32}</ct32>\n"
        f"        <ct33>{ct33}</ct33>\n"
        "      </HHDVBRaChiuTSuat10>\n"
        "      <ct32a>0</ct32a>\n"
        "      <TongDThuVaThueGTGTHHDVBRa>\n"
        f"        <ct34>{ct34}</ct34>\n"
        f"        <ct35>{ct35}</ct35>\n"
        "      </TongDThuVaThueGTGTHHDVBRa>\n"
        "      <ct36>0</ct36>\n"
        "      <ct37>0</ct37>\n"
        "      <ct38>0</ct38>\n"
        "      <ct39a>0</ct39a>\n"
        f"      <ct40a>{ct40a}</ct40a>\n"
        f"      <ct40b>{ct40b}</ct40b>\n"
        f"      <ct40>{ct40}</ct40>\n"
        "      <ct41>0</ct41>\n"
        "      <ct42>0</ct42>\n"
        "      <ct43>0</ct43>\n"
        "    </CTieuTKhaiChinh>\n"
        "  </HSoKhaiThue>\n"
        "</HSoThueDTu>"
    )

    pdf_text = (
        "TO KHAI THUE GTGT MAU 01/GTGT (TT80/2021/TT-BTC)\n"
        f"Ky ke khai: {period_label} ({cycle_label})\n"
        f"Nguoi nop thue: {company_name} - MST: {tax_code}\n"
        f"[24] Thue GTGT dau vao: {int(round(vat_input))} VND\n"
        f"[32] Doanh thu chiu thue: {int(round(doanh_thu_chiu_thue))} VND\n"
        f"[33] Thue GTGT dau ra: {int(round(vat_output))} VND\n"
        f"[40a] GTGT con phai nop: {int(round(vat_payable))} VND\n"
        f"[40b] GTGT con duoc khau tru chuyen ky sau: {int(round(vat_carry_forward))} VND\n"
    )

    return {
        "form_code": "01/GTGT",
        "legal_basis": "Thông tư 80/2021/TT-BTC",
        "period": period,
        "period_label": period_label,
        "cycle": cycle,
        "cycle_label": cycle_label,
        "due_date": _vat_due_date_for_period(period, cycle),
        "indicators": {
            "23_prev_input_carry": 0,
            "24_input_vat_in_period": int(round(vat_input)),
            "25_input_vat_deducted": int(round(vat_input)),
            "32_taxable_revenue": int(round(doanh_thu_chiu_thue)),
            "33_output_vat": int(round(vat_output)),
            "40a_vat_payable": int(round(vat_payable)),
            "40b_vat_carry_forward": int(round(vat_carry_forward)),
        },
        "xml_text": xml_text,
        "pdf_text": pdf_text,
    }


def _compute_compliance_seed(
    entries: list[dict[str, Any]],
    as_of_date: str,
    period: str,
    cycle: str,
    vat_declaration: Optional[Dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    report = report_service.generate_financial_statements(entries, as_of_date)
    pl = report.get("ket_qua_hoat_dong_kinh_doanh", {})
    doanh_thu = float(pl.get("doanh_thu", 0) or 0)
    loi_nhuan = float(pl.get("loi_nhuan_truoc_thue", 0) or 0)

    vat_estimate = max(round(doanh_thu * 0.1), 0)
    pit_estimate = max(round(doanh_thu * 0.02), 0)
    cit_estimate = max(round(loi_nhuan * 0.2), 0)
    vat_amount = vat_estimate
    vat_due_date = _vat_due_date_for_period(period, cycle)
    vat_name = f"Tờ khai thuế GTGT mẫu 01/GTGT ({_format_period_label(period, cycle)})"
    if isinstance(vat_declaration, dict):
        vat_amount = int(vat_declaration.get("indicators", {}).get("40a_vat_payable", vat_amount) or vat_amount)
        vat_due_date = str(vat_declaration.get("due_date") or vat_due_date)

    return [
        {
            "report_id": "gtgt",
            "name": vat_name,
            "status": "chua_nop",
            "due_date": vat_due_date,
            "amount": vat_amount,
            "category": "tax_periodic",
            "cycle": cycle,
            "form_code": "01/GTGT",
            "legal_basis": "Thông tư 80/2021/TT-BTC",
        },
        {
            "report_id": "tncn",
            "name": "Thuế TNCN",
            "status": "da_nop",
            "due_date": "2026-04-20",
            "amount": pit_estimate,
            "category": "tax_periodic",
        },
        {
            "report_id": "tndn",
            "name": "Thuế TNDN tạm tính",
            "status": "chua_nop",
            "due_date": "2026-04-30",
            "amount": cit_estimate,
            "category": "tax_periodic",
        },
        {
            "report_id": "bctc",
            "name": "Báo cáo tài chính",
            "status": "chua_nop",
            "due_date": "2026-03-31",
            "amount": loi_nhuan,
            "category": "year_end",
        },
    ]


def ensure_compliance_seed(
    email: str,
    period: str,
    cycle: str,
    company_profile: Optional[Dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    normalized_email = email.lower().strip()
    existing = storage.list_compliance_filings(normalized_email, period)
    existing_by_id = {str(item.get("report_id")): item for item in existing}
    as_of_date = _period_end_date(period, cycle)
    entries = _derive_journal_entries_from_truth(normalized_email, as_of_date)
    vat_declaration = _build_vat_declaration_tt80(company_profile or {}, period, cycle, entries)
    seeds = _compute_compliance_seed(entries, as_of_date, period, cycle, vat_declaration)
    now = datetime.utcnow().isoformat() + "Z"
    for item in seeds:
        report_id = str(item["report_id"])
        prior = existing_by_id.get(report_id, {})
        merged_status = str(prior.get("status") or item["status"])
        merged = {**item, "status": merged_status}
        storage.upsert_compliance_filing(
            email=normalized_email,
            period=period,
            report_id=report_id,
            status=merged_status,
            due_date=str(item["due_date"]),
            payload=merged,
            updated_at=now,
        )
    return storage.list_compliance_filings(normalized_email, period)


def _apply_late_status(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now_ts = datetime.utcnow().timestamp()
    normalized = []
    for item in items:
        due_date = str(item.get("due_date") or "")
        status = str(item.get("status") or "chua_nop")
        due_ts = datetime.fromisoformat(due_date).timestamp() if due_date else now_ts
        if status != "da_nop" and due_ts < now_ts:
            status = "qua_han"
        normalized.append({**item, "status": status})
    return normalized


def _parse_amount_value(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "")
    matches = re.findall(r"\d[\d\.,]*", text)
    for token in matches:
        normalized = token.replace(".", "").replace(",", "")
        try:
            value = float(normalized)
            if value > 0:
                return value
        except ValueError:
            continue
    return 0.0


def _normalize_event_from_case_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_type = str(item.get("event_type") or "").strip()
    if not event_type:
        return None

    event_date = str(item.get("updatedAt") or datetime.utcnow().date().isoformat())
    amount = _parse_amount_value(item.get("amount"))
    case_id = str(item.get("id") or item.get("case_id") or "")
    description = str(item.get("title") or item.get("description") or "Hồ sơ nghiệp vụ")
    partner = str(item.get("partner") or item.get("counterparty_name") or "Đối tác")

    def _parse_currency_text(raw: Any) -> float:
        return _parse_amount_value(raw)

    def _extract_split_amounts() -> Tuple[float, float, float]:
        top_untaxed = _parse_currency_text(item.get("amount_untaxed") or item.get("untaxed_amount"))
        top_vat = _parse_currency_text(item.get("vat_amount"))
        top_total = _parse_currency_text(item.get("amount_total") or item.get("total_amount"))

        pending = item.get("pending_posting") if isinstance(item.get("pending_posting"), dict) else {}
        pending_event = pending.get("event") if isinstance(pending.get("event"), dict) else {}
        if pending_event:
            top_untaxed = top_untaxed or _parse_currency_text(pending_event.get("amount_untaxed") or pending_event.get("untaxed_amount"))
            top_vat = top_vat or _parse_currency_text(pending_event.get("vat_amount"))
            top_total = top_total or _parse_currency_text(pending_event.get("amount_total") or pending_event.get("total_amount") or pending_event.get("amount"))

        timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
        latest_posted_entry: Dict[str, Any] = {}
        for entry in reversed(timeline):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip().lower()
            if title == "thông tin đã post":
                latest_posted_entry = entry
                break

        if latest_posted_entry:
            rows = latest_posted_entry.get("table_rows") if isinstance(latest_posted_entry.get("table_rows"), list) else []
            by_label: Dict[str, str] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("label") or "").strip()
                value = str(row.get("value") or "").strip()
                if label:
                    by_label[label] = value
            top_untaxed = top_untaxed or _parse_currency_text(by_label.get("Số tiền trước thuế"))
            top_vat = top_vat or _parse_currency_text(by_label.get("Thuế VAT"))
            top_total = top_total or _parse_currency_text(by_label.get("Số tiền sau thuế") or by_label.get("Số tiền"))

        if top_total <= 0:
            top_total = amount

        if top_untaxed <= 0 and top_total > 0 and top_vat > 0 and top_total >= top_vat:
            top_untaxed = top_total - top_vat
        if top_vat <= 0 and top_total > 0 and top_untaxed > 0 and top_total >= top_untaxed:
            top_vat = top_total - top_untaxed

        if top_untaxed <= 0 and top_total > 0:
            # Legacy records may only have gross amount; assume common VAT 10% for fallback sync.
            top_untaxed = top_total / 1.1
            top_vat = top_total - top_untaxed

        return float(round(top_untaxed)), float(round(top_vat)), float(round(top_total))

    untaxed_amount, vat_amount, total_amount = _extract_split_amounts()

    if event_type == "gop_von":
        return {
            "case_id": case_id,
            "source_id": "bank_statement",
            "event_type": "gop_von",
            "statement_date": event_date,
            "counterparty_name": partner,
            "description": description,
            "amount": amount or 100000000.0,
            "reference_no": f"SYNC-CAP-{case_id[-6:]}",
            "debit_credit_flag": "credit",
        }
    if event_type == "nop_thue":
        return {
            "case_id": case_id,
            "source_id": "bank_statement",
            "event_type": "nop_thue",
            "statement_date": event_date,
            "counterparty_name": "Kho bạc Nhà nước",
            "description": description,
            "amount": amount or 3000000.0,
            "reference_no": f"SYNC-TAX-{case_id[-6:]}",
            "debit_credit_flag": "debit",
            "tax_payable_account": "3331",
            "payment_channel": "bank",
        }
    if event_type == "ban_hang_dich_vu":
        untaxed = untaxed_amount or 10000000.0
        vat = vat_amount if total_amount > 0 else round(untaxed * 0.1)
        total = total_amount if total_amount > 0 else (untaxed + vat)
        return {
            "case_id": case_id,
            "source_id": "sales_invoice_xml",
            "event_type": "ban_hang_dich_vu",
            "invoice_no": f"SYNC-OUT-{case_id[-6:]}",
            "issue_date": event_date,
            "buyer_tax_code": "0310001111",
            "counterparty_name": partner,
            "description": description,
            "amount_untaxed": untaxed,
            "vat_amount": vat,
            "amount_total": total,
            "total_amount": total,
            "untaxed_amount": untaxed,
            "has_vat": True,
            "payment_status": "unpaid",
        }

    untaxed = untaxed_amount or 6000000.0
    vat = vat_amount if total_amount > 0 else round(untaxed * 0.1)
    total = total_amount if total_amount > 0 else (untaxed + vat)
    return {
        "case_id": case_id,
        "source_id": "purchase_invoice_xml",
        "event_type": "mua_dich_vu",
        "invoice_no": f"SYNC-IN-{case_id[-6:]}",
        "issue_date": event_date,
        "seller_tax_code": "0109999999",
        "counterparty_name": partner,
        "description": description,
        "goods_service_type": "service",
        "amount_untaxed": untaxed,
        "vat_amount": vat,
        "amount_total": total,
        "total_amount": total,
        "untaxed_amount": untaxed,
        "service_term_months": 1,
        "payment_account": "331",
        "has_vat": True,
    }


def _derive_events_from_truth(email: str) -> List[Dict[str, Any]]:
    events = storage.list_case_events(email)
    if events:
        return events

    case_items = storage.list_case_items(email)
    derived: List[Dict[str, Any]] = []
    for item in case_items:
        if str(item.get("status") or "").strip() != "hoan_tat":
            continue
        normalized = _normalize_event_from_case_item(item)
        if normalized:
            derived.append(normalized)
    return derived


def _derive_journal_entries_from_truth(email: str, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    normalized_email = email.lower().strip()
    cutoff = as_of_date or datetime.utcnow().date().isoformat()
    derived_events = _derive_events_from_truth(normalized_email)

    def event_date_of(event: Dict[str, Any]) -> str:
        return str(event.get("statement_date") or event.get("issue_date") or event.get("event_date") or cutoff)

    accepted_entries: List[Dict[str, Any]] = []

    opening = storage.get_opening_balances(normalized_email)
    opening_lines = opening.get("lines") if isinstance(opening, dict) else []
    if isinstance(opening_lines, list) and opening_lines:
        normalized_lines = []
        for idx, line in enumerate(opening_lines, start=1):
            side_raw = str(line.get("side") or "debit").lower()
            side = "debit" if side_raw in {"debit", "nợ", "no"} else "credit"
            amount = float(line.get("amount", 0) or 0)
            account = str(line.get("account") or "")
            if not account or amount <= 0:
                continue
            normalized_lines.append({"line_no": idx, "side": side, "account": account, "amount": amount})
        if normalized_lines:
            accepted_entries.append(
                {
                    "entry_id": f"OB-{cutoff.replace('-', '')}",
                    "event_type": "opening_balance",
                    "normal_narration": "Số dư đầu kỳ",
                    "meta": {"event_date": cutoff, "source": "opening_balances"},
                    "lines": normalized_lines,
                }
            )

    filtered_events = [event for event in derived_events if event_date_of(event) <= cutoff]
    filtered_events.sort(key=event_date_of)

    for event in filtered_events:
        result = posting_engine.post(event)
        if result.accepted and result.journal_entry:
            accepted_entries.append(result.journal_entry)

    return accepted_entries


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": "tt133-mvp-web-api"}


@app.get("/api/demo/cases")
def get_demo_cases(email: str = "demo@wssmeas.local", company_id: str = "") -> Dict[str, Any]:
    normalized_email = email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, company_id)
    scoped_data_key = company_scope_key(resolved_company_id)
    items = storage.list_case_items(scoped_data_key)
    ui_content = storage.get_ui_content(scoped_data_key, "main_panels") or {}
    entries = _derive_journal_entries_from_truth(scoped_data_key)
    current_user = storage.get_user(normalized_email)
    default_company = storage.get_company(resolved_company_id)

    trial_balance = report_service.summarize_accounts(entries)

    def normalize_compare_text(value: str) -> str:
        lowered = str(value or "").lower()
        lowered = unicodedata.normalize("NFD", lowered)
        lowered = "".join(ch for ch in lowered if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^a-z0-9]", "", lowered)

    company_tax = _normalize_tax_code(str(default_company.get("tax_code") if isinstance(default_company, dict) else ""))
    company_name_norm = normalize_compare_text(str(default_company.get("company_name") if isinstance(default_company, dict) else ""))

    def is_same_company(name_value: str, tax_value: str) -> bool:
        normalized_tax = _normalize_tax_code(str(tax_value or ""))
        if company_tax and normalized_tax and normalized_tax == company_tax:
            return True
        candidate_norm = normalize_compare_text(name_value)
        if company_name_norm and candidate_norm:
            return company_name_norm in candidate_norm or candidate_norm in company_name_norm
        return False

    def is_generic_partner(name_value: str) -> bool:
        value = str(name_value or "").strip().lower()
        return value in {"", "-", "đối tác", "doi tac", "n/a"}

    def extract_partner_from_pending_xml(case_id_value: str, pending_posting: Dict[str, Any]) -> str:
        attachments = pending_posting.get("received_attachments") if isinstance(pending_posting, dict) else []
        if not isinstance(attachments, list):
            return ""

        candidate_refs: List[str] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            preview_ref = str(attachment.get("preview_ref") or "").strip()
            if not preview_ref:
                stored_name = str(attachment.get("stored_name") or attachment.get("name") or "").strip()
                if stored_name:
                    preview_ref = f"perm__{stored_name}"
            if not preview_ref:
                continue
            candidate_refs.append(preview_ref)

        for preview_ref in candidate_refs:
            file_name, payload = _load_attachment_bytes_by_ref(normalized_email, str(case_id_value), preview_ref)
            if not payload or Path(str(file_name or preview_ref)).suffix.lower() != ".xml":
                continue
            try:
                text = payload.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                continue

            seller_name_match = re.search(r"<NBan>.*?<Ten>([^<]+)</Ten>", text, flags=re.IGNORECASE | re.DOTALL)
            seller_tax_match = re.search(r"<NBan>.*?<MST>([^<]+)</MST>", text, flags=re.IGNORECASE | re.DOTALL)
            buyer_name_match = re.search(r"<NMua>.*?<(?:Ten|HVTNMHang)>([^<]+)</(?:Ten|HVTNMHang)>", text, flags=re.IGNORECASE | re.DOTALL)
            buyer_tax_match = re.search(r"<NMua>.*?<MST>([^<]+)</MST>", text, flags=re.IGNORECASE | re.DOTALL)

            seller_name = re.sub(r"\s+", " ", str(seller_name_match.group(1) if seller_name_match else "")).strip(" \t\r\n:;,-")[:180]
            seller_tax = _normalize_tax_code(seller_tax_match.group(1) if seller_tax_match else "")
            buyer_name = re.sub(r"\s+", " ", str(buyer_name_match.group(1) if buyer_name_match else "")).strip(" \t\r\n:;,-")[:180]
            buyer_tax = _normalize_tax_code(buyer_tax_match.group(1) if buyer_tax_match else "")

            if buyer_name and not is_same_company(buyer_name, buyer_tax):
                return buyer_name
            if seller_name and not is_same_company(seller_name, seller_tax):
                return seller_name

        return ""

    for item in items:
        if not isinstance(item, dict):
            continue
        pending_posting = item.get("pending_posting") if isinstance(item.get("pending_posting"), dict) else None
        if not pending_posting:
            continue

        parse_rows = pending_posting.get("parse_rows") if isinstance(pending_posting.get("parse_rows"), list) else []
        if not parse_rows:
            continue

        partner_row = None
        for row in parse_rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip().lower()
            if label in {"đối tác", "doi tac", "nhà cung cấp", "nha cung cap"}:
                partner_row = row
                break

        if not partner_row:
            continue

        current_partner = str(partner_row.get("value") or "").strip()
        if current_partner and not is_generic_partner(current_partner) and not is_same_company(current_partner, ""):
            continue

        pending_event = pending_posting.get("event") if isinstance(pending_posting.get("event"), dict) else {}
        candidate_names = [
            str(pending_event.get("counterparty_name") or "").strip(),
            str(pending_event.get("buyer_name") or "").strip(),
            str(pending_event.get("seller_name") or "").strip(),
            str(item.get("partner") or "").strip(),
        ]

        resolved_partner = ""
        for candidate in candidate_names:
            if is_generic_partner(candidate):
                continue
            if is_same_company(candidate, ""):
                continue
            resolved_partner = candidate
            break

        if not resolved_partner:
            resolved_partner = extract_partner_from_pending_xml(str(item.get("id") or ""), pending_posting)

        if resolved_partner:
            partner_row["label"] = "Đối tác"
            partner_row["value"] = resolved_partner
            item["partner"] = resolved_partner

    case_events = storage.list_case_events(scoped_data_key)
    event_by_case_id: Dict[str, Dict[str, Any]] = {}
    for event in case_events:
        if not isinstance(event, dict):
            continue
        event_case_id = str(event.get("case_id") or "").strip()
        if not event_case_id:
            continue
        event_by_case_id[event_case_id] = event

    def format_date_for_display(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "-"
        token_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", raw)
        if not token_match:
            return raw
        token = token_match.group(1).replace("/", "-")
        if re.fullmatch(r"\d{8}", token):
            try:
                return datetime.strptime(token, "%Y%m%d").strftime("%d/%m/%Y")
            except ValueError:
                return raw
        for fmt in ["%Y-%m-%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(token, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return raw

    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") != "hoan_tat":
            continue

        timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
        has_posted_summary = any(
            isinstance(entry, dict) and str(entry.get("title") or "").strip().lower() == "thông tin đã post"
            for entry in timeline
        )
        if has_posted_summary:
            continue

        case_id_value = str(item.get("id") or "").strip()
        event = event_by_case_id.get(case_id_value, {})
        if not isinstance(event, dict):
            event = {}

        partner_name = str(item.get("partner") or event.get("counterparty_name") or "Đối tác").strip() or "Đối tác"
        description = str(item.get("title") or event.get("description") or event.get("goods_service_type") or "-").strip() or "-"
        invoice_no = str(event.get("invoice_no") or event.get("reference_no") or "-").strip() or "-"
        invoice_date = format_date_for_display(str(event.get("issue_date") or event.get("statement_date") or event.get("event_date") or ""))
        total_value = float(event.get("amount_total") or event.get("total_amount") or event.get("amount") or 0)
        untaxed_value = float(event.get("amount_untaxed") or event.get("untaxed_amount") or 0)
        vat_value = float(event.get("vat_amount") or 0)
        if untaxed_value <= 0 and total_value > 0 and vat_value > 0 and total_value >= vat_value:
            untaxed_value = total_value - vat_value
        if vat_value <= 0 and total_value > 0 and untaxed_value > 0 and total_value >= untaxed_value:
            vat_value = total_value - untaxed_value
        untaxed_text = f"{untaxed_value:,.0f} đồng" if untaxed_value > 0 else "-"
        vat_text = f"{vat_value:,.0f} đồng" if vat_value > 0 else "-"
        total_text = f"{total_value:,.0f} đồng" if total_value > 0 else "-"

        summary_rows = [
            {"label": "Đối tác", "value": partner_name},
            {"label": "Nội dung", "value": description},
            {"label": "Số hóa đơn", "value": invoice_no},
            {"label": "Ngày hóa đơn", "value": invoice_date},
            {"label": "Số tiền trước thuế", "value": untaxed_text},
            {"label": "Thuế VAT", "value": vat_text},
            {"label": "Số tiền sau thuế", "value": total_text},
        ]

        synthetic_summary = {
            "id": f"{case_id_value}-posted-summary-backfill",
            "kind": "analysis",
            "role": "system",
            "title": "Thông tin đã post",
            "body": "Hệ thống đã thực hiện post với các thông tin cơ bản sau:",
            "table_rows": summary_rows,
            "time": datetime.utcnow().strftime("%H:%M"),
        }

        item["timeline"] = [*timeline, synthetic_summary]

    def prefix_balance(prefixes: list[str]) -> float:
        total = 0.0
        for account, values in trial_balance.items():
            if any(str(account).startswith(prefix) for prefix in prefixes):
                total += float(values.get("balance", 0) or 0)
        return total

    def format_vnd(amount: float) -> str:
        return f"{amount:,.0f} VND"

    cash_position = max(prefix_balance(["111", "112", "1281"]), 0.0)
    open_payables = max(-prefix_balance(["331"]), 0.0)
    open_receivables = max(prefix_balance(["131"]), 0.0)
    pending_case_count = len([item for item in items if str(item.get("status")) != "hoan_tat"])
    pending_sales_count = len(
        [
            item
            for item in items
            if str(item.get("event_type")) == "ban_hang_dich_vu" and str(item.get("status")) != "hoan_tat"
        ]
    )

    if not isinstance(ui_content, dict):
        ui_content = {}
    dashboard = ui_content.setdefault("dashboard", {})
    if not isinstance(dashboard, dict):
        dashboard = {}
        ui_content["dashboard"] = dashboard
    dashboard["cards"] = [
        {
            "title": "Vị thế tiền mặt",
            "value": format_vnd(cash_position),
            "note": f"Cập nhật từ sổ cái ({len(entries)} bút toán)",
        },
        {
            "title": "Công nợ phải trả mở",
            "value": format_vnd(open_payables),
            "note": f"{pending_case_count} hồ sơ chưa hoàn tất",
        },
        {
            "title": "Công nợ phải thu mở",
            "value": format_vnd(open_receivables),
            "note": f"{pending_sales_count} hồ sơ bán hàng đang mở",
        },
    ]

    status_dict = {"tat_ca": "Tất cả"}
    for item in items:
        status_value = str(item.get("status") or "").strip()
        if not status_value:
            continue
        status_label = str(item.get("statusLabel") or status_value)
        if status_value not in status_dict:
            status_dict[status_value] = status_label

    status_options = [{"value": key, "label": label} for key, label in status_dict.items()]
    return {
        "items": items,
        "total": len(items),
        "email": normalized_email,
        "current_user": current_user,
        "company": {
            **(default_company or {}),
            "company_id": resolved_company_id,
        },
        "dashboard_meta": build_demo_dashboard_meta(),
        "server_panels": {
            "reports_tips": [
                "Chọn đúng kỳ báo cáo trước khi drill-down.",
                "Đối chiếu biến động ở bảng chính rồi mới xem giao dịch chi tiết.",
                "Ưu tiên xử lý mục có chênh lệch lớn nhất theo giá trị.",
            ],
            "compliance_checklist": [
                "Kiểm tra trạng thái báo cáo: Chưa nộp, Đã nộp, Quá hạn.",
                "Rà soát cảnh báo auto-check trước khi xuất XML.",
                "Xác nhận người nộp và lưu dấu vết lịch sử.",
            ],
        },
        "status_options": status_options,
        "ui_content": ui_content,
    }


@app.get("/api/demo/identity")
def get_demo_identity() -> Dict[str, Any]:
    users = storage.list_users()
    companies = storage.list_companies()
    memberships = {
        str(user.get("email") or "").lower().strip(): storage.list_user_memberships(str(user.get("email") or ""))
        for user in users
    }
    return {
        "users": users,
        "companies": companies,
        "memberships": memberships,
        "total_users": len(users),
        "total_companies": len(companies),
    }


@app.get("/api/demo/compliance")
def get_demo_compliance(period: str = "2026-03", email: str = "demo@wssmeas.local", company_id: str = "") -> Dict[str, Any]:
    normalized_email = email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, company_id)
    scoped_data_key = company_scope_key(resolved_company_id)
    company_profile = _resolve_company_profile_for_scope(normalized_email, resolved_company_id)
    declaration_cycle = _normalize_tax_declaration_cycle(str(company_profile.get("tax_declaration_cycle") or ""))
    reference_date = datetime.utcnow().date()
    period_options = _build_period_options(declaration_cycle, reference_date)
    effective_period = str(period or "").strip()
    if not _is_valid_period_for_cycle(effective_period, declaration_cycle):
        effective_period = str(period_options[0].get("value") if period_options else _derive_period_for_cycle(declaration_cycle, reference_date))

    filings = ensure_compliance_seed(scoped_data_key, effective_period, declaration_cycle, company_profile)
    filings = _apply_late_status(filings)

    report_by_id = {str(item.get("report_id")): item for item in filings}
    gtgt_amount = float(report_by_id.get("gtgt", {}).get("amount", 0) or 0)
    period_end_date = _period_end_date(effective_period, declaration_cycle)
    entries = _derive_journal_entries_from_truth(scoped_data_key, period_end_date)
    financial = report_service.generate_financial_statements(entries, period_end_date)
    doanh_thu = float(financial.get("ket_qua_hoat_dong_kinh_doanh", {}).get("doanh_thu", 0) or 0)
    expected_vat = max(round(doanh_thu * 0.1), 0)
    vat_declaration = _build_vat_declaration_tt80(company_profile, effective_period, declaration_cycle, entries)

    gtgt_filing = report_by_id.get("gtgt") if isinstance(report_by_id.get("gtgt"), dict) else None
    if gtgt_filing is not None:
        normalized_gtgt = {
            **gtgt_filing,
            "name": f"Tờ khai thuế GTGT mẫu 01/GTGT ({vat_declaration.get('period_label')})",
            "amount": float(vat_declaration.get("indicators", {}).get("40a_vat_payable", 0) or 0),
            "due_date": str(vat_declaration.get("due_date") or gtgt_filing.get("due_date") or ""),
            "cycle": declaration_cycle,
            "form_code": "01/GTGT",
            "legal_basis": "Thông tư 80/2021/TT-BTC",
        }
        storage.upsert_compliance_filing(
            email=scoped_data_key,
            period=effective_period,
            report_id="gtgt",
            status=str(normalized_gtgt.get("status") or "chua_nop"),
            due_date=str(normalized_gtgt.get("due_date") or ""),
            payload=normalized_gtgt,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )
        filings = [normalized_gtgt if str(item.get("report_id") or "") == "gtgt" else item for item in filings]
        report_by_id["gtgt"] = normalized_gtgt
        gtgt_amount = float(normalized_gtgt.get("amount", 0) or 0)

    issues = []
    if gtgt_amount <= 0:
        issues.append("Thiếu hóa đơn đầu vào cho kỳ hiện tại.")
    if abs(gtgt_amount - expected_vat) > 1000000:
        issues.append("Lệch số giữa GTGT và doanh thu, cần đối chiếu lại.")
    if not issues:
        issues.append("Không phát hiện sai lệch trọng yếu trước khi nộp.")

    history = storage.list_compliance_submission_history(scoped_data_key, effective_period)
    active_report = filings[0] if filings else None
    xml_preview = ""
    if active_report and str(active_report.get("report_id") or "") == "gtgt":
        xml_preview = str(vat_declaration.get("xml_text") or "")
    elif active_report:
        xml_preview = (
            f"<ToKhai ky=\"{effective_period}\" loai=\"{active_report.get('report_id')}\">\n"
            f"  <SoTien>{int(float(active_report.get('amount', 0) or 0))}</SoTien>\n"
            "  <NguonDuLieu>reports.v1</NguonDuLieu>\n"
            "</ToKhai>"
        )

    return {
        "email": normalized_email,
        "company_id": resolved_company_id,
        "period": effective_period,
        "period_options": period_options,
        "declaration_cycle": declaration_cycle,
        "declaration_cycle_label": "Tháng" if declaration_cycle == "month" else "Quý",
        "reports": filings,
        "issues": issues,
        "history": history,
        "xml_preview": xml_preview,
        "vat_declaration": vat_declaration,
    }


@app.get("/api/demo/opening-balances")
def get_demo_opening_balances(email: str = "demo@wssmeas.local", company_id: str = "") -> Dict[str, Any]:
    normalized_email = email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, company_id)
    payload = storage.get_opening_balances(company_scope_key(resolved_company_id))
    return {
        "email": normalized_email,
        "company_id": resolved_company_id,
        "lines": payload.get("lines", []) if isinstance(payload, dict) else [],
    }


@app.post("/api/demo/opening-balances")
def upsert_demo_opening_balances(payload: OpeningBalancesPayload) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, payload.company_id)
    now = datetime.utcnow().isoformat() + "Z"
    data = {"lines": payload.lines}
    storage.upsert_opening_balances(company_scope_key(resolved_company_id), data, now)
    return {"saved": True, "email": normalized_email, "company_id": resolved_company_id, "lines": payload.lines}


@app.post("/api/demo/compliance/export-xml")
def export_demo_compliance_xml(payload: ComplianceActionPayload) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, payload.company_id)
    filing = storage.get_compliance_filing(company_scope_key(resolved_company_id), payload.period, payload.report_id)
    if not filing:
        raise HTTPException(status_code=404, detail="COMPLIANCE_REPORT_NOT_FOUND")

    scoped_data_key = company_scope_key(resolved_company_id)
    company_profile = _resolve_company_profile_for_scope(normalized_email, resolved_company_id)
    declaration_cycle = _normalize_tax_declaration_cycle(str(company_profile.get("tax_declaration_cycle") or ""))
    if str(payload.report_id) == "gtgt":
        if not _is_valid_period_for_cycle(payload.period, declaration_cycle):
            raise HTTPException(status_code=400, detail="INVALID_PERIOD_FOR_DECLARATION_CYCLE")
        period_end_date = _period_end_date(payload.period, declaration_cycle)
        entries = _derive_journal_entries_from_truth(scoped_data_key, period_end_date)
        declaration = _build_vat_declaration_tt80(company_profile, payload.period, declaration_cycle, entries)
        period_token = re.sub(r"[^0-9Q-]", "", str(payload.period or ""))
        return {
            "file_name": f"tokhai_gtgt_01gtgt_{period_token}.xml",
            "mime_type": "application/xml",
            "content_base64": base64.b64encode(str(declaration.get("xml_text") or "").encode("utf-8")).decode("ascii"),
        }

    xml_text = (
        f"<ToKhai ky=\"{payload.period}\" loai=\"{payload.report_id}\">\n"
        f"  <SoTien>{int(float(filing.get('amount', 0) or 0))}</SoTien>\n"
        "  <NguonDuLieu>reports.v1</NguonDuLieu>\n"
        "</ToKhai>"
    )
    return {
        "file_name": f"{payload.report_id}_{payload.period}.xml",
        "mime_type": "application/xml",
        "content_base64": base64.b64encode(xml_text.encode("utf-8")).decode("ascii"),
    }


@app.post("/api/demo/compliance/export-pdf")
def export_demo_compliance_pdf(payload: ComplianceActionPayload) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, payload.company_id)
    filing = storage.get_compliance_filing(company_scope_key(resolved_company_id), payload.period, payload.report_id)
    if not filing:
        raise HTTPException(status_code=404, detail="COMPLIANCE_REPORT_NOT_FOUND")

    scoped_data_key = company_scope_key(resolved_company_id)
    company_profile = _resolve_company_profile_for_scope(normalized_email, resolved_company_id)
    declaration_cycle = _normalize_tax_declaration_cycle(str(company_profile.get("tax_declaration_cycle") or ""))
    if str(payload.report_id) == "gtgt":
        if not _is_valid_period_for_cycle(payload.period, declaration_cycle):
            raise HTTPException(status_code=400, detail="INVALID_PERIOD_FOR_DECLARATION_CYCLE")
        period_end_date = _period_end_date(payload.period, declaration_cycle)
        entries = _derive_journal_entries_from_truth(scoped_data_key, period_end_date)
        declaration = _build_vat_declaration_tt80(company_profile, payload.period, declaration_cycle, entries)
        period_token = re.sub(r"[^0-9Q-]", "", str(payload.period or ""))
        xml_text = str(declaration.get("xml_text") or "")
        return {
            "file_name": f"tokhai_gtgt_01gtgt_{period_token}.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(_build_pdf_from_xml(xml_text, "TO KHAI GTGT 01/GTGT")).decode("ascii"),
        }

    xml_text = (
        f"<ToKhai ky=\"{payload.period}\" loai=\"{payload.report_id}\">\n"
        f"  <SoTien>{int(float(filing.get('amount', 0) or 0))}</SoTien>\n"
        "  <NguonDuLieu>reports.v1</NguonDuLieu>\n"
        "</ToKhai>"
    )
    return {
        "file_name": f"{payload.report_id}_{payload.period}.pdf",
        "mime_type": "application/pdf",
        "content_base64": base64.b64encode(
            _build_pdf_from_xml(xml_text, f"BAO CAO {str(filing.get('name') or payload.report_id)}")
        ).decode("ascii"),
    }


@app.post("/api/demo/compliance/submit")
def submit_demo_compliance(payload: ComplianceActionPayload) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, payload.company_id)
    scoped_data_key = company_scope_key(resolved_company_id)
    filing = storage.get_compliance_filing(scoped_data_key, payload.period, payload.report_id)
    if not filing:
        raise HTTPException(status_code=404, detail="COMPLIANCE_REPORT_NOT_FOUND")

    now = datetime.utcnow().isoformat() + "Z"
    updated = {**filing, "status": "da_nop"}
    storage.upsert_compliance_filing(
        email=scoped_data_key,
        period=payload.period,
        report_id=payload.report_id,
        status="da_nop",
        due_date=str(filing.get("due_date") or ""),
        payload=updated,
        updated_at=now,
    )

    submitted_by = payload.submitted_by.strip() or normalized_email
    history_record = {
        "report": str(filing.get("name") or payload.report_id),
        "submittedBy": submitted_by,
        "submittedAt": now,
        "fileName": (
            f"tokhai_gtgt_01gtgt_{re.sub(r'[^0-9Q-]', '', str(payload.period or ''))}.xml"
            if str(payload.report_id) == "gtgt"
            else f"{payload.report_id}_{payload.period}.xml"
        ),
    }
    storage.add_compliance_submission_history(
        history_id=f"HIS-{uuid.uuid4().hex[:8].upper()}",
        email=scoped_data_key,
        period=payload.period,
        report_id=payload.report_id,
        payload=history_record,
        created_at=now,
    )

    return {"submitted": True, "report_id": payload.report_id, "period": payload.period}


@app.post("/api/demo/ui-action")
def run_demo_ui_action(payload: DemoUiActionWithAttachmentsPayload) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, payload.company_id)
    scoped_data_key = company_scope_key(resolved_company_id)
    now = datetime.utcnow().isoformat() + "Z"
    text = payload.text.strip()
    selected_company_profile = _resolve_company_profile_for_scope(normalized_email, resolved_company_id)
    selected_company_tax_code = _normalize_tax_code(str(selected_company_profile.get("tax_code") or ""))
    selected_company_name = str(selected_company_profile.get("company_name") or "").strip()
    selected_company_address = str(selected_company_profile.get("address") or "").strip()

    def decode_attachment_content(raw_base64: str) -> bytes:
        payload_base64 = raw_base64
        if "," in payload_base64 and payload_base64.lower().startswith("data:"):
            payload_base64 = payload_base64.split(",", 1)[1]
        try:
            return base64.b64decode(payload_base64)
        except (ValueError, binascii.Error):
            return b""

    def save_case_attachments_to_staging(case_id: str, attachments: List[DemoAttachmentPayload]) -> List[Dict[str, Any]]:
        if not attachments:
            return []
        normalized_case_id = _sanitize_case_id(case_id)
        session_id = datetime.utcnow().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6]
        safe_session = _sanitize_session_id(session_id)
        case_dir = STAGING_UPLOADS_ROOT / _safe_email_fragment(normalized_email) / normalized_case_id / safe_session
        if not _attachments_use_gcs():
            case_dir.mkdir(parents=True, exist_ok=True)
        staged_items: List[Dict[str, Any]] = []
        timestamp_prefix = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        for idx, item in enumerate(attachments, start=1):
            original_name = Path(str(item.name or f"attachment_{idx}.bin")).name
            safe_name = f"{timestamp_prefix}_{idx:02d}_{original_name}"
            content = decode_attachment_content(str(item.content_base64 or ""))
            if _attachments_use_gcs():
                staged_key = _build_staged_attachment_key(normalized_email, normalized_case_id, safe_session, safe_name)
                _upload_attachment_bytes(staged_key, content, str(item.mime_type or "application/octet-stream"))
            else:
                file_path = case_dir / safe_name
                file_path.write_bytes(content)
            staged_items.append(
                {
                    "name": original_name,
                    "stored_name": safe_name,
                    "preview_ref": f"stg__{safe_session}__{safe_name}",
                    "session_id": safe_session,
                    "storage": "staging",
                    "mime_type": str(item.mime_type or "application/octet-stream"),
                    "size": int(item.size or 0),
                }
            )

        return staged_items

    def parse_number_token(token: str) -> float:
        cleaned = token.strip().replace(" ", "")
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                normalized = cleaned.replace(".", "").replace(",", ".")
            else:
                normalized = cleaned.replace(",", "")
        elif "," in cleaned:
            left, right = cleaned.split(",", 1)
            if 1 <= len(right) <= 2:
                normalized = f"{left}.{right}"
            else:
                normalized = cleaned.replace(",", "")
        else:
            normalized = cleaned
        try:
            return float(normalized)
        except ValueError:
            return 0.0

    def parse_money_mentions(raw_text: str) -> List[float]:
        values: List[float] = []
        text = str(raw_text or "")
        for match in re.finditer(r"(\d[\d\.,]*)\s*(triệu|trieu|nghìn|nghin|ngàn|ngan|k|đ|vnd|dong)?", text, flags=re.IGNORECASE):
            token = str(match.group(1) or "")
            unit = str(match.group(2) or "").lower()
            token_digits = re.sub(r"\D", "", token)
            base_value = parse_number_token(token)
            if base_value <= 0:
                continue
            # Ignore long numeric identifiers (invoice item codes, signature blocks) when no currency unit is present.
            if not unit and len(token_digits) > 10:
                continue
            if unit in {"triệu", "trieu"}:
                base_value *= 1_000_000
            elif unit in {"nghìn", "nghin", "ngàn", "ngan", "k"}:
                base_value *= 1_000
            elif unit in {"đ", "vnd", "dong"}:
                base_value *= 1
            elif base_value < 1000:
                continue
            elif base_value > 100_000_000_000:
                continue
            values.append(base_value)
        return values

    def detect_amount_from_text(raw_text: str) -> float:
        values = parse_money_mentions(raw_text)
        return max(values) if values else 0.0

    def extract_attachment_text(item: DemoAttachmentPayload) -> str:
        ext = Path(str(item.name or "")).suffix.lower()
        content = decode_attachment_content(str(item.content_base64 or ""))
        if not content:
            return ""
        if ext in {".xml", ".json", ".txt", ".csv", ".log"}:
            return content.decode("utf-8", errors="ignore")
        return ""

    def parse_attachment_details(attachments: List[DemoAttachmentPayload], attachment_names: List[str]) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "supplier_name": "",
            "service_name": "",
            "invoice_number": "",
            "invoice_date": "",
            "invoice_content": "",
            "seller_name": "",
            "buyer_name": "",
            "seller_address": "",
            "buyer_address": "",
            "seller_tax_code": "",
            "buyer_tax_code": "",
            "amount_untaxed": 0.0,
            "vat_amount": 0.0,
            "amount_total": 0.0,
            "vat_rate": 0.0,
            "amount": 0.0,
            "files": attachment_names,
            "parse_meta": {
                "invoice_type": "unknown",
                "schema_version": "",
                "status": "needs_review",
                "confidence": {
                    "supplier_name": 0.0,
                    "service_name": 0.0,
                    "invoice_number": 0.0,
                    "amount": 0.0,
                    "overall": 0.0,
                },
                "issues": [],
                "warnings": [],
                "reconcile": {},
                "company_validation": {
                    "company_tax_code": selected_company_tax_code,
                    "is_tax_code_match": False,
                    "matched_party": "",
                    "invoice_role": "",
                    "has_invoice_tax_code": False,
                    "blocking_reason": "",
                },
            },
        }

        issues: List[str] = []
        warnings: List[str] = []
        xml_schema_counter: Counter[str] = Counter()
        xml_versions: List[str] = []

        text_candidates: Dict[str, List[Dict[str, Any]]] = {
            "supplier_name": [],
            "service_name": [],
            "invoice_number": [],
            "seller_name": [],
            "buyer_name": [],
            "seller_address": [],
            "buyer_address": [],
        }
        amount_sources: List[Dict[str, Any]] = []
        date_sources: List[Dict[str, Any]] = []
        schema_totals: List[float] = []
        schema_subtotals: List[float] = []
        schema_vat_values: List[float] = []
        line_totals: List[float] = []
        tax_rates: List[float] = []

        def clean_extracted_value(value: str, max_len: int = 180) -> str:
            cleaned = re.sub(r"<[^>]+>", " ", str(value or ""))
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n:;,-")
            return cleaned[:max_len]

        def normalize_text_field(value: str) -> str:
            lowered = clean_extracted_value(value, max_len=240).lower()
            return re.sub(r"[^a-z0-9]", "", lowered)

        def local_tag(tag: str) -> str:
            raw = str(tag or "")
            if "}" in raw:
                raw = raw.rsplit("}", 1)[1]
            return raw.strip().lower()

        def to_amount(value: Any) -> float:
            text_value = clean_extracted_value(str(value or ""), max_len=120)
            if not text_value:
                return 0.0
            mentions = parse_money_mentions(text_value)
            if mentions:
                return float(max(mentions))
            token = re.sub(r"[^\d\.,-]", "", text_value)
            if not token:
                return 0.0
            return max(parse_number_token(token), 0.0)

        def add_text_candidate(field: str, value: str, confidence: float, source: str) -> None:
            cleaned = clean_extracted_value(value)
            if not cleaned:
                return
            text_candidates[field].append(
                {
                    "value": cleaned,
                    "confidence": max(0.0, min(float(confidence), 1.0)),
                    "source": source,
                }
            )

        def add_amount_source(value: float, confidence: float, source: str) -> None:
            if value <= 0:
                return
            amount_sources.append(
                {
                    "value": float(value),
                    "confidence": max(0.0, min(float(confidence), 1.0)),
                    "source": source,
                }
            )

        def normalize_date_value(value: str) -> str:
            raw = clean_extracted_value(value, max_len=80)
            if not raw:
                return ""

            raw = raw.replace("T", " ")
            date_token_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", raw)
            if not date_token_match:
                return ""

            token = date_token_match.group(1)
            normalized = token.replace("/", "-").strip()

            if re.fullmatch(r"\d{8}", normalized):
                try:
                    parsed = datetime.strptime(normalized, "%Y%m%d")
                    return parsed.date().isoformat()
                except ValueError:
                    return ""

            for fmt in ["%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    return parsed.date().isoformat()
                except ValueError:
                    continue

            return ""

        def add_date_source(value: str, confidence: float, source: str) -> None:
            normalized = normalize_date_value(value)
            if not normalized:
                return
            date_sources.append(
                {
                    "value": normalized,
                    "confidence": max(0.0, min(float(confidence), 1.0)),
                    "source": source,
                }
            )

        def collect_path_values(root: ET.Element) -> Dict[str, List[str]]:
            path_values: Dict[str, List[str]] = {}

            def walk(node: ET.Element, path: str = "") -> None:
                tag = local_tag(node.tag)
                if not tag:
                    return
                current_path = f"{path}_{tag}" if path else tag
                value = clean_extracted_value(str(node.text or ""))
                if value:
                    # Store full path and all suffix aliases to make schema-key mapping resilient
                    # across root prefixes and nesting differences.
                    path_parts = current_path.split("_")
                    for idx in range(len(path_parts)):
                        suffix_key = "_".join(path_parts[idx:])
                        path_values.setdefault(suffix_key, []).append(value)
                    path_values.setdefault(tag, []).append(value)
                for child in list(node):
                    walk(child, current_path)

            walk(root)
            return path_values

        def pick_first_path(path_values: Dict[str, List[str]], keys: List[str]) -> str:
            for key in keys:
                values = path_values.get(str(key).lower(), [])
                for value in values:
                    if value:
                        return value
            return ""

        def pick_all_amounts(path_values: Dict[str, List[str]], keys: List[str]) -> List[float]:
            collected: List[float] = []
            for key in keys:
                values = path_values.get(str(key).lower(), [])
                for value in values:
                    amount = to_amount(value)
                    if amount > 0:
                        collected.append(amount)
            return collected

        def detect_schema(root: ET.Element, xml_text: str, path_values: Dict[str, List[str]]) -> Dict[str, str]:
            xml_lower = str(xml_text or "").lower()
            root_name = local_tag(root.tag)
            namespace = ""
            root_tag = str(root.tag or "")
            if root_tag.startswith("{") and "}" in root_tag:
                namespace = root_tag[1:].split("}", 1)[0]

            version = ""
            for candidate in ["pban", "version", "schema_version"]:
                value = pick_first_path(path_values, [candidate])
                if value:
                    version = value
                    break

            has_signature = bool(re.search(r"<\s*signature\b|<\s*dscks\b|signedinfo", xml_lower, flags=re.IGNORECASE))

            invoice_type = "unknown"
            if "misa" in xml_lower or "amis" in xml_lower:
                invoice_type = "misa_custom"
            elif (
                root_name in {"hdon", "hoadon"}
                and pick_first_path(path_values, ["ttchung_shdon", "dlhdon_ttchung_shdon"])
                and pick_first_path(path_values, ["ndhdon_nban_ten", "dlhdon_ndhdon_nban_ten"])
            ):
                invoice_type = "viettel_variant"
            elif namespace or pick_first_path(path_values, ["invoice", "invoiceno", "amounttotal"]):
                invoice_type = "gdt_standard"

            if invoice_type == "unknown" and has_signature and root_name in {"hdon", "hoadon"}:
                invoice_type = "viettel_variant"

            return {
                "invoice_type": invoice_type,
                "version": version,
                "root_tag": root_name,
                "namespace": namespace,
            }

        def parse_by_schema(invoice_type: str, path_values: Dict[str, List[str]]) -> Dict[str, Any]:
            if invoice_type == "viettel_variant":
                return {
                    "supplier": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nban_ten",
                        "dlhdon_ndhdon_nban_ten",
                        "ndhdon_nban_ten",
                        "nban_ten",
                    ]),
                    "service": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_dshhdvu_hhdvu_thhdvu",
                        "dlhdon_ndhdon_dshhdvu_hhdvu_thhdvu",
                        "ndhdon_dshhdvu_hhdvu_thhdvu",
                        "thhdvu",
                    ]),
                    "invoice": pick_first_path(path_values, [
                        "hdon_dlhdon_ttchung_shdon",
                        "dlhdon_ttchung_shdon",
                        "ttchung_shdon",
                        "shdon",
                    ]),
                    "issue_date": pick_first_path(path_values, [
                        "hdon_dlhdon_ttchung_nlap",
                        "dlhdon_ttchung_nlap",
                        "ttchung_nlap",
                        "nlap",
                        "ngayhoadon",
                    ]),
                    "seller_tax_code": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nban_mst",
                        "dlhdon_ndhdon_nban_mst",
                        "ndhdon_nban_mst",
                        "nban_mst",
                    ]),
                    "buyer_tax_code": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nmua_mst",
                        "dlhdon_ndhdon_nmua_mst",
                        "ndhdon_nmua_mst",
                        "nmua_mst",
                    ]),
                    "seller_name": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nban_ten",
                        "dlhdon_ndhdon_nban_ten",
                        "ndhdon_nban_ten",
                        "nban_ten",
                    ]),
                    "buyer_name": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nmua_ten",
                        "dlhdon_ndhdon_nmua_ten",
                        "ndhdon_nmua_ten",
                        "hdon_dlhdon_ndhdon_nmua_hvtnmhang",
                        "dlhdon_ndhdon_nmua_hvtnmhang",
                        "ndhdon_nmua_hvtnmhang",
                        "nmua_hvtnmhang",
                        "nmua_ten",
                    ]),
                    "seller_address": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nban_dchi",
                        "dlhdon_ndhdon_nban_dchi",
                        "ndhdon_nban_dchi",
                        "nban_dchi",
                    ]),
                    "buyer_address": pick_first_path(path_values, [
                        "hdon_dlhdon_ndhdon_nmua_dchi",
                        "dlhdon_ndhdon_nmua_dchi",
                        "ndhdon_nmua_dchi",
                        "nmua_dchi",
                    ]),
                    "subtotal_candidates": pick_all_amounts(path_values, [
                        "hdon_dlhdon_ndhdon_ttoan_tgtcthue",
                        "dlhdon_ndhdon_ttoan_tgtcthue",
                        "ndhdon_ttoan_tgtcthue",
                        "tgtcthue",
                    ]),
                    "vat_candidates": pick_all_amounts(path_values, [
                        "hdon_dlhdon_ndhdon_ttoan_tgtthue",
                        "dlhdon_ndhdon_ttoan_tgtthue",
                        "ndhdon_ttoan_tgtthue",
                        "tgtthue",
                    ]),
                    "total_candidates": pick_all_amounts(path_values, [
                        "hdon_dlhdon_ndhdon_ttoan_tgtttbso",
                        "dlhdon_ndhdon_ttoan_tgtttbso",
                        "ndhdon_ttoan_tgtttbso",
                        "tgtttbso",
                    ]),
                    "line_amounts": pick_all_amounts(path_values, [
                        "hdon_dlhdon_ndhdon_dshhdvu_hhdvu_thtien",
                        "dlhdon_ndhdon_dshhdvu_hhdvu_thtien",
                        "ndhdon_dshhdvu_hhdvu_thtien",
                        "thtien",
                    ]),
                    "tax_rates": pick_all_amounts(path_values, [
                        "hdon_dlhdon_ndhdon_dshhdvu_hhdvu_tsuat",
                        "dlhdon_ndhdon_dshhdvu_hhdvu_tsuat",
                        "ndhdon_dshhdvu_hhdvu_tsuat",
                        "tsuat",
                    ]),
                }

            if invoice_type == "misa_custom":
                return {
                    "supplier": pick_first_path(path_values, ["sellername", "supplier", "counterparty_name"]),
                    "service": pick_first_path(path_values, ["description", "itemname", "tendichvu"]),
                    "invoice": pick_first_path(path_values, ["invoiceno", "invoice_no", "invoice"]),
                    "issue_date": pick_first_path(path_values, ["invoicedate", "issue_date", "ngayhoadon", "ngaylap"]),
                    "seller_tax_code": pick_first_path(path_values, ["sellertaxcode", "mst", "taxcode"]),
                    "buyer_tax_code": pick_first_path(path_values, ["buyertaxcode", "buyer_tax_code", "mst_buyer"]),
                    "seller_name": pick_first_path(path_values, ["sellername", "supplier", "counterparty_name"]),
                    "buyer_name": pick_first_path(path_values, [
                        "buyername",
                        "customername",
                        "counterparty_buyer_name",
                        "nmua_hvtnmhang",
                    ]),
                    "seller_address": pick_first_path(path_values, ["selleraddress", "supplier_address", "diachinguoiban"]),
                    "buyer_address": pick_first_path(path_values, ["buyeraddress", "customeraddress", "diachinguoimua"]),
                    "subtotal_candidates": pick_all_amounts(path_values, ["untaxedamount", "amount_untaxed", "subtotal"]),
                    "vat_candidates": pick_all_amounts(path_values, ["vatamount", "taxamount"]),
                    "total_candidates": pick_all_amounts(path_values, ["amounttotal", "totalamount", "amount_total"]),
                    "line_amounts": pick_all_amounts(path_values, ["lineamount", "thtien"]),
                    "tax_rates": pick_all_amounts(path_values, ["taxrate", "tsuat"]),
                }

            return {
                "supplier": pick_first_path(path_values, ["supplier", "sellername", "counterparty_name", "tennguoiban", "nban_ten"]),
                "service": pick_first_path(path_values, ["description", "itemname", "thhdvu", "diengiai"]),
                "invoice": pick_first_path(path_values, ["invoiceno", "invoice_no", "invoice", "shdon"]),
                "issue_date": pick_first_path(path_values, ["invoicedate", "issue_date", "ngayhoadon", "ngaylap", "nlap"]),
                "seller_tax_code": pick_first_path(path_values, ["sellertaxcode", "mst", "taxcode", "nban_mst"]),
                "buyer_tax_code": pick_first_path(path_values, ["buyertaxcode", "buyer_tax_code", "nmua_mst"]),
                "seller_name": pick_first_path(path_values, ["sellername", "supplier", "counterparty_name", "tennguoiban", "nban_ten"]),
                "buyer_name": pick_first_path(path_values, [
                    "buyername",
                    "customername",
                    "tennguoimua",
                    "nmua_ten",
                    "nmua_hvtnmhang",
                    "hdon_dlhdon_ndhdon_nmua_hvtnmhang",
                    "dlhdon_ndhdon_nmua_hvtnmhang",
                    "ndhdon_nmua_hvtnmhang",
                ]),
                "seller_address": pick_first_path(path_values, ["selleraddress", "nban_dchi", "diachinguoiban"]),
                "buyer_address": pick_first_path(path_values, ["buyeraddress", "nmua_dchi", "diachinguoimua"]),
                "subtotal_candidates": pick_all_amounts(path_values, ["untaxedamount", "subtotal", "tgtcthue", "amount_untaxed"]),
                "vat_candidates": pick_all_amounts(path_values, ["vatamount", "taxamount", "tgtthue"]),
                "total_candidates": pick_all_amounts(path_values, ["amounttotal", "totalamount", "tgtttbso", "amount_total"]),
                "line_amounts": pick_all_amounts(path_values, ["lineamount", "thtien"]),
                "tax_rates": pick_all_amounts(path_values, ["taxrate", "tsuat"]),
            }

        def pick_best_text(field: str) -> Dict[str, Any]:
            candidates = text_candidates[field]
            if not candidates:
                return {"value": "", "confidence": 0.0}
            sorted_candidates = sorted(candidates, key=lambda item: (item["confidence"], len(str(item["value"]))), reverse=True)
            return {"value": str(sorted_candidates[0]["value"]), "confidence": float(sorted_candidates[0]["confidence"])}

        def majority_vote_numeric(values: List[float]) -> Dict[str, Any]:
            positive_values = [float(v) for v in values if float(v) > 0]
            if not positive_values:
                return {"value": 0.0, "count": 0, "size": 0}
            rounded = [int(round(v)) for v in positive_values]
            counts = Counter(rounded)
            winner, count = counts.most_common(1)[0]
            return {
                "value": float(winner),
                "count": int(count),
                "size": len(rounded),
            }

        for item in attachments:
            text = extract_attachment_text(item)
            if not text:
                continue

            ext = Path(str(item.name or "")).suffix.lower()
            plain_text = text
            if ext == ".xml":
                plain_text = re.sub(r"<[^>]+>", " ", text)
                plain_text = re.sub(r"\s+", " ", plain_text).strip()

            if not details["invoice_content"]:
                details["invoice_content"] = " ".join(plain_text.split())[:260]

            if ext == ".xml":
                try:
                    root = ET.fromstring(text)
                    path_values = collect_path_values(root)
                    schema = detect_schema(root, text, path_values)
                    invoice_type = schema["invoice_type"]
                    xml_schema_counter[invoice_type] += 1
                    if schema.get("version"):
                        xml_versions.append(schema["version"])

                    mapped = parse_by_schema(invoice_type, path_values)
                    add_text_candidate("supplier_name", str(mapped.get("supplier") or ""), 0.95, f"{invoice_type}:supplier")
                    add_text_candidate("service_name", str(mapped.get("service") or ""), 0.9, f"{invoice_type}:service")
                    add_text_candidate("invoice_number", str(mapped.get("invoice") or ""), 0.95, f"{invoice_type}:invoice")
                    add_text_candidate("seller_name", str(mapped.get("seller_name") or ""), 0.9, f"{invoice_type}:seller_name")
                    add_text_candidate("buyer_name", str(mapped.get("buyer_name") or ""), 0.9, f"{invoice_type}:buyer_name")
                    add_text_candidate("seller_address", str(mapped.get("seller_address") or ""), 0.85, f"{invoice_type}:seller_address")
                    add_text_candidate("buyer_address", str(mapped.get("buyer_address") or ""), 0.85, f"{invoice_type}:buyer_address")
                    add_date_source(str(mapped.get("issue_date") or ""), 0.92, f"{invoice_type}:issue_date")

                    seller_tax_code = clean_extracted_value(str(mapped.get("seller_tax_code") or ""), max_len=30)
                    buyer_tax_code = clean_extracted_value(str(mapped.get("buyer_tax_code") or ""), max_len=30)
                    if seller_tax_code and not re.fullmatch(r"\d{10}(?:-\d{3})?", seller_tax_code):
                        issues.append(f"Mã số thuế người bán không đúng định dạng: {seller_tax_code}")
                    if buyer_tax_code and not re.fullmatch(r"\d{10}(?:-\d{3})?", buyer_tax_code):
                        issues.append(f"Mã số thuế người mua không đúng định dạng: {buyer_tax_code}")
                    if seller_tax_code and not details["seller_tax_code"]:
                        details["seller_tax_code"] = seller_tax_code
                    if buyer_tax_code and not details["buyer_tax_code"]:
                        details["buyer_tax_code"] = buyer_tax_code

                    mapped_subtotals = [float(v) for v in mapped.get("subtotal_candidates", []) if float(v) > 0]
                    mapped_vats = [float(v) for v in mapped.get("vat_candidates", []) if float(v) > 0]
                    mapped_totals = [float(v) for v in mapped.get("total_candidates", []) if float(v) > 0]
                    mapped_lines = [float(v) for v in mapped.get("line_amounts", []) if float(v) > 0]
                    mapped_rates = [float(v) for v in mapped.get("tax_rates", []) if float(v) > 0]

                    schema_subtotals.extend(mapped_subtotals)
                    schema_vat_values.extend(mapped_vats)
                    schema_totals.extend(mapped_totals)
                    line_totals.extend(mapped_lines)
                    tax_rates.extend(mapped_rates)

                    for value in mapped_totals:
                        add_amount_source(float(value), 0.95, f"{invoice_type}:total_tag")
                    for value in mapped_subtotals:
                        add_amount_source(float(value), 0.75, f"{invoice_type}:subtotal_tag")
                except ET.ParseError:
                    issues.append(f"Không parse được XML của tệp {item.name}")
                    add_amount_source(detect_amount_from_text(plain_text), 0.4, "xml:plain_text_fallback")
            else:
                supplier_match = re.search(r"(nhà\s*cung\s*cấp|supplier|vendor|seller)\s*[:\-]?\s*([^\n\r;]{3,120})", plain_text, flags=re.IGNORECASE)
                if supplier_match:
                    add_text_candidate("supplier_name", supplier_match.group(2), 0.6, "text:regex_supplier")

                service_match = re.search(r"(dịch\s*vụ|service|hàng\s*hóa|description|nội\s*dung)\s*[:\-]?\s*([^\n\r;]{3,160})", plain_text, flags=re.IGNORECASE)
                if service_match:
                    add_text_candidate("service_name", service_match.group(2), 0.6, "text:regex_service")

                invoice_match = re.search(r"(số\s*hóa\s*đơn|invoice\s*no|invoice|sohd)\s*[:\-]?\s*([A-Za-z0-9\-_/]{4,40})", plain_text, flags=re.IGNORECASE)
                if invoice_match:
                    add_text_candidate("invoice_number", invoice_match.group(2), 0.65, "text:regex_invoice")

                seller_tax_match = re.search(r"(mst\s*người\s*bán|mã\s*số\s*thuế\s*người\s*bán|seller\s*tax\s*code)\s*[:\-]?\s*(\d{10}(?:-\d{3})?)", plain_text, flags=re.IGNORECASE)
                if seller_tax_match and not details["seller_tax_code"]:
                    details["seller_tax_code"] = seller_tax_match.group(2)

                buyer_tax_match = re.search(r"(mst\s*người\s*mua|mã\s*số\s*thuế\s*người\s*mua|buyer\s*tax\s*code)\s*[:\-]?\s*(\d{10}(?:-\d{3})?)", plain_text, flags=re.IGNORECASE)
                if buyer_tax_match and not details["buyer_tax_code"]:
                    details["buyer_tax_code"] = buyer_tax_match.group(2)

                date_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", plain_text)
                if date_match:
                    add_date_source(date_match.group(1), 0.6, "text:regex_date")

                for money in parse_money_mentions(plain_text):
                    add_amount_source(float(money), 0.55, "text:money_mention")

        supplier_best = pick_best_text("supplier_name")
        service_best = pick_best_text("service_name")
        invoice_best = pick_best_text("invoice_number")
        seller_name_best = pick_best_text("seller_name")
        buyer_name_best = pick_best_text("buyer_name")
        seller_address_best = pick_best_text("seller_address")
        buyer_address_best = pick_best_text("buyer_address")

        details["supplier_name"] = supplier_best["value"]
        details["service_name"] = service_best["value"]
        details["invoice_number"] = invoice_best["value"]
        details["seller_name"] = seller_name_best["value"]
        details["buyer_name"] = buyer_name_best["value"]
        details["seller_address"] = seller_address_best["value"]
        details["buyer_address"] = buyer_address_best["value"]

        if date_sources:
            best_date = sorted(date_sources, key=lambda item: item["confidence"], reverse=True)[0]
            details["invoice_date"] = str(best_date["value"])

        subtotal_value = max(schema_subtotals) if schema_subtotals else 0.0
        vat_value = max(schema_vat_values) if schema_vat_values else 0.0
        total_tag_value = max(schema_totals) if schema_totals else 0.0
        lines_sum = sum(line_totals) if line_totals else 0.0
        computed_total = (subtotal_value + vat_value) if subtotal_value > 0 and vat_value >= 0 else 0.0
        lines_plus_vat = (lines_sum + vat_value) if lines_sum > 0 and vat_value >= 0 else 0.0

        vote_candidates = [value for value in [total_tag_value, computed_total, lines_plus_vat] if value > 0]
        vote = majority_vote_numeric(vote_candidates)

        final_amount = 0.0
        amount_confidence = 0.0
        if vote["count"] >= 2:
            final_amount = float(vote["value"])
            amount_confidence = 0.95
        elif total_tag_value > 0:
            final_amount = float(round(total_tag_value))
            amount_confidence = 0.88
        elif amount_sources:
            strongest = sorted(amount_sources, key=lambda item: (item["confidence"], item["value"]), reverse=True)[0]
            final_amount = float(round(float(strongest["value"])))
            amount_confidence = float(strongest["confidence"])

        details["amount"] = final_amount
        details["amount_total"] = final_amount
        details["vat_amount"] = float(round(vat_value)) if vat_value > 0 else 0.0
        if subtotal_value > 0:
            details["amount_untaxed"] = float(round(subtotal_value))
        elif final_amount > 0 and vat_value > 0 and final_amount >= vat_value:
            details["amount_untaxed"] = float(round(final_amount - vat_value))
        else:
            details["amount_untaxed"] = 0.0

        if subtotal_value > 0 and vat_value >= 0:
            details["vat_rate"] = round((vat_value / subtotal_value) * 100.0, 4)
        else:
            explicit_rates = [float(rate) for rate in tax_rates if float(rate) > 0]
            details["vat_rate"] = round(max(explicit_rates), 4) if explicit_rates else 0.0

        reconcile: Dict[str, Any] = {
            "total_tag": total_tag_value,
            "subtotal": subtotal_value,
            "vat": vat_value,
            "sum_line_items": lines_sum,
            "subtotal_plus_vat": computed_total,
            "sum_line_items_plus_vat": lines_plus_vat,
            "vote_count": vote["count"],
            "vote_size": vote["size"],
        }

        if total_tag_value > 0 and computed_total > 0 and abs(total_tag_value - computed_total) > 2:
            issues.append("Đối chiếu thất bại: tổng tiền khác subtotal + VAT")
        if total_tag_value > 0 and lines_sum > 0 and abs(total_tag_value - lines_sum - vat_value) > 3:
            issues.append("Đối chiếu thất bại: tổng tiền khác tổng dòng hàng + VAT")

        if final_amount <= 0:
            issues.append("Tổng tiền hóa đơn bằng 0 hoặc không xác định")
        if subtotal_value > 0 and vat_value > subtotal_value * 0.5:
            issues.append("VAT vượt ngưỡng bất thường (>50% subtotal)")
        if any(value < 0 for value in [total_tag_value, subtotal_value, vat_value, lines_sum]):
            issues.append("Phát hiện giá trị âm bất thường trong hóa đơn")

        if not details["supplier_name"]:
            issues.append("Không xác định được nhà cung cấp")
        if not details["invoice_number"]:
            issues.append("Không xác định được số hóa đơn")

        company_validation: Dict[str, Any] = {
            "company_tax_code": selected_company_tax_code,
            "is_tax_code_match": False,
            "matched_party": "",
            "invoice_role": "",
            "has_invoice_tax_code": False,
            "blocking_reason": "",
        }

        normalized_seller_tax = _normalize_tax_code(str(details.get("seller_tax_code") or ""))
        normalized_buyer_tax = _normalize_tax_code(str(details.get("buyer_tax_code") or ""))
        details["seller_tax_code"] = normalized_seller_tax
        details["buyer_tax_code"] = normalized_buyer_tax
        company_validation["has_invoice_tax_code"] = bool(normalized_seller_tax or normalized_buyer_tax)

        if selected_company_tax_code:
            if normalized_seller_tax == selected_company_tax_code:
                company_validation["is_tax_code_match"] = True
                company_validation["matched_party"] = "seller"
                company_validation["invoice_role"] = "outbound"
            elif normalized_buyer_tax == selected_company_tax_code:
                company_validation["is_tax_code_match"] = True
                company_validation["matched_party"] = "buyer"
                company_validation["invoice_role"] = "inbound"
            else:
                company_validation["blocking_reason"] = "Mã số thuế trên hóa đơn không thuộc công ty đang đăng nhập"

            matched_name = details.get("seller_name") if company_validation["matched_party"] == "seller" else details.get("buyer_name")
            matched_address = details.get("seller_address") if company_validation["matched_party"] == "seller" else details.get("buyer_address")
            normalized_company_name = normalize_text_field(selected_company_name)
            normalized_company_address = normalize_text_field(selected_company_address)
            normalized_matched_name = normalize_text_field(str(matched_name or ""))
            normalized_matched_address = normalize_text_field(str(matched_address or ""))

            if company_validation["is_tax_code_match"] and normalized_company_name and normalized_matched_name:
                if normalized_company_name not in normalized_matched_name and normalized_matched_name not in normalized_company_name:
                    warnings.append("Cảnh báo: MST khớp nhưng tên công ty trên hóa đơn khác hồ sơ công ty")

            if company_validation["is_tax_code_match"] and normalized_company_address and normalized_matched_address:
                if normalized_company_address not in normalized_matched_address and normalized_matched_address not in normalized_company_address:
                    warnings.append("Cảnh báo: MST khớp nhưng địa chỉ trên hóa đơn khác hồ sơ công ty")

        if xml_schema_counter:
            dominant_schema = xml_schema_counter.most_common(1)[0][0]
        else:
            dominant_schema = "unknown"

        overall_confidence = (
            supplier_best["confidence"]
            + service_best["confidence"]
            + invoice_best["confidence"]
            + amount_confidence
        ) / 4

        status = "ok"
        if any("bất thường" in item.lower() for item in issues):
            status = "suspicious"
        elif issues or overall_confidence < 0.75 or dominant_schema == "unknown":
            status = "needs_review"

        details["parse_meta"] = {
            "invoice_type": dominant_schema,
            "schema_version": max(xml_versions) if xml_versions else "",
            "status": status,
            "confidence": {
                "supplier_name": round(float(supplier_best["confidence"]), 3),
                "service_name": round(float(service_best["confidence"]), 3),
                "invoice_number": round(float(invoice_best["confidence"]), 3),
                "amount": round(float(amount_confidence), 3),
                "overall": round(float(overall_confidence), 3),
            },
            "issues": issues,
            "warnings": warnings,
            "reconcile": reconcile,
            "company_validation": company_validation,
        }

        return details

    def infer_event_from_input(command_text: str, file_names: List[str], details: Dict[str, Any]) -> Dict[str, Any]:
        def _normalize_compare_text(value: str) -> str:
            lowered = str(value or "").lower()
            return re.sub(r"[^a-z0-9]", "", lowered)

        def _to_money(value: Any) -> float:
            try:
                amount = float(value)
            except (TypeError, ValueError):
                return 0.0
            if not math.isfinite(amount):
                return 0.0
            return max(amount, 0.0)

        lowered = command_text.lower()
        joined_files = " ".join(file_names).lower()
        today = datetime.utcnow().date().isoformat()
        inferred_date = str(details.get("invoice_date") or today)
        detected_amount = detect_amount_from_text(command_text)
        supplier_name = str(details.get("supplier_name") or "Đối tác từ hồ sơ đính kèm")
        service_name = str(details.get("service_name") or "Mua dịch vụ từ hồ sơ đính kèm")
        invoice_number = str(details.get("invoice_number") or f"AUTO-IN-{datetime.utcnow().strftime('%H%M%S')}")
        amount_from_attachment = _to_money(details.get("amount"))
        parse_meta = details.get("parse_meta") if isinstance(details.get("parse_meta"), dict) else {}
        reconcile = parse_meta.get("reconcile") if isinstance(parse_meta.get("reconcile"), dict) else {}
        company_validation = parse_meta.get("company_validation") if isinstance(parse_meta.get("company_validation"), dict) else {}
        invoice_role = str(company_validation.get("invoice_role") or "").strip().lower()

        parsed_untaxed = _to_money(details.get("amount_untaxed") or reconcile.get("subtotal"))
        parsed_vat = _to_money(details.get("vat_amount") or reconcile.get("vat"))
        parsed_total = _to_money(details.get("amount_total") or reconcile.get("total_tag") or amount_from_attachment)
        parsed_vat_rate = _to_money(details.get("vat_rate"))

        normalized_company_tax = _normalize_tax_code(selected_company_tax_code)
        normalized_company_name = _normalize_compare_text(selected_company_name)

        seller_name = str(details.get("seller_name") or "").strip()
        buyer_name = str(details.get("buyer_name") or "").strip()
        seller_tax_code = _normalize_tax_code(str(details.get("seller_tax_code") or ""))
        buyer_tax_code = _normalize_tax_code(str(details.get("buyer_tax_code") or ""))

        def _is_own_company(name_value: str, tax_value: str) -> bool:
            normalized_name = _normalize_compare_text(name_value)
            normalized_tax = _normalize_tax_code(tax_value)
            if normalized_company_tax and normalized_tax and normalized_tax == normalized_company_tax:
                return True
            if normalized_company_name and normalized_name:
                return normalized_company_name in normalized_name or normalized_name in normalized_company_name
            return False

        def _pick_counterparty_name() -> str:
            def _pick_non_own(*candidates: Tuple[str, str]) -> str:
                for name_value, tax_value in candidates:
                    if not str(name_value or "").strip():
                        continue
                    if _is_own_company(str(name_value), str(tax_value)):
                        continue
                    return str(name_value)
                return ""

            if invoice_role == "outbound":
                picked = _pick_non_own((buyer_name, buyer_tax_code), (seller_name, seller_tax_code), (supplier_name, ""))
                return picked or "Đối tác"
            if invoice_role == "inbound":
                picked = _pick_non_own((seller_name, seller_tax_code), (buyer_name, buyer_tax_code), (supplier_name, ""))
                return picked or "Đối tác"

            candidates = [
                (buyer_name, buyer_tax_code),
                (seller_name, seller_tax_code),
            ]
            for name_value, tax_value in candidates:
                if not str(name_value or "").strip():
                    continue
                if _is_own_company(str(name_value), str(tax_value)):
                    continue
                return str(name_value)

            if not _is_own_company(supplier_name, ""):
                return supplier_name
            return "Đối tác"

        def _derive_invoice_amounts() -> Tuple[float, float, float]:
            untaxed_amount = parsed_untaxed
            vat_amount = parsed_vat
            total_amount = parsed_total

            if detected_amount > 0 and total_amount <= 0:
                total_amount = detected_amount

            if total_amount <= 0 and untaxed_amount > 0:
                total_amount = untaxed_amount + vat_amount

            if untaxed_amount <= 0 and total_amount > 0 and vat_amount > 0 and total_amount >= vat_amount:
                untaxed_amount = total_amount - vat_amount

            if vat_amount <= 0 and total_amount > 0 and untaxed_amount > 0 and total_amount >= untaxed_amount:
                vat_amount = total_amount - untaxed_amount

            if total_amount > 0 and untaxed_amount <= 0:
                applied_rate = parsed_vat_rate / 100.0 if parsed_vat_rate > 0 else 0.1
                if applied_rate > 0:
                    untaxed_amount = total_amount / (1.0 + applied_rate)
                    vat_amount = total_amount - untaxed_amount

            if total_amount <= 0 and untaxed_amount > 0:
                applied_rate = parsed_vat_rate / 100.0 if parsed_vat_rate > 0 else 0.1
                vat_amount = untaxed_amount * applied_rate
                total_amount = untaxed_amount + vat_amount

            return (
                float(round(untaxed_amount)),
                float(round(vat_amount)),
                float(round(total_amount)),
            )

        counterparty_name = _pick_counterparty_name()
        inferred_untaxed, inferred_vat, inferred_total = _derive_invoice_amounts()

        if "góp vốn" in lowered or "von" in lowered:
            amount = detected_amount or inferred_total or amount_from_attachment or 100000000.0
            return {
                "event_type": "gop_von",
                "event": {
                    "source_id": "bank_statement",
                    "event_type": "gop_von",
                    "statement_date": inferred_date,
                    "counterparty_name": counterparty_name,
                    "description": service_name,
                    "amount": amount,
                    "reference_no": f"AUTO-CAP-{datetime.utcnow().strftime('%H%M%S')}",
                    "debit_credit_flag": "credit",
                },
            }

        if "thuế" in lowered or "gtgt" in lowered or "vat" in lowered or "tax" in joined_files:
            amount = detected_amount or inferred_vat or inferred_total or amount_from_attachment or 3000000.0
            return {
                "event_type": "nop_thue",
                "event": {
                    "source_id": "bank_statement",
                    "event_type": "nop_thue",
                    "statement_date": inferred_date,
                    "counterparty_name": counterparty_name,
                    "description": service_name,
                    "amount": amount,
                    "reference_no": f"AUTO-TAX-{datetime.utcnow().strftime('%H%M%S')}",
                    "debit_credit_flag": "debit",
                    "tax_payable_account": "3331",
                    "payment_channel": "bank",
                },
            }

        if invoice_role == "outbound" or "bán" in lowered or "sales" in joined_files or "out-" in joined_files:
            untaxed = inferred_untaxed or 15000000.0
            vat_amount = inferred_vat if inferred_total > 0 else round(untaxed * 0.1)
            total_amount = inferred_total if inferred_total > 0 else (untaxed + vat_amount)
            return {
                "event_type": "ban_hang_dich_vu",
                "event": {
                    "source_id": "sales_invoice_xml",
                    "event_type": "ban_hang_dich_vu",
                    "invoice_no": invoice_number,
                    "issue_date": inferred_date,
                    "buyer_tax_code": "0310001111",
                    "counterparty_name": counterparty_name,
                    "description": service_name,
                    "amount_untaxed": untaxed,
                    "vat_amount": vat_amount,
                    "amount_total": total_amount,
                    "total_amount": total_amount,
                    "untaxed_amount": untaxed,
                    "has_vat": True,
                    "payment_status": "unpaid",
                },
            }

        if invoice_role and invoice_role != "inbound":
            invoice_role = "inbound"

        untaxed = inferred_untaxed or 6000000.0
        vat_amount = inferred_vat if inferred_total > 0 else round(untaxed * 0.1)
        total_amount = inferred_total if inferred_total > 0 else (untaxed + vat_amount)
        return {
            "event_type": "mua_dich_vu",
            "event": {
                "source_id": "purchase_invoice_xml",
                "event_type": "mua_dich_vu",
                "invoice_no": invoice_number,
                "issue_date": inferred_date,
                "seller_tax_code": "0109999999",
                "counterparty_name": counterparty_name,
                "description": service_name,
                "goods_service_type": "service",
                "amount_untaxed": untaxed,
                "vat_amount": vat_amount,
                "amount_total": total_amount,
                "total_amount": total_amount,
                "untaxed_amount": untaxed,
                "service_term_months": 1,
                "payment_account": "331",
                "has_vat": True,
            },
        }

    if payload.action == "dashboard_query":
        return {
            "ok": True,
            "message": f"AI đã phân tích: {text or 'Yêu cầu tổng quan'}.",
            "updated_at": now,
        }

    if payload.action == "case_command":
        reject_tokens = [
            "không đồng ý",
            "khong dong y",
            "không post",
            "khong post",
            "hủy post",
            "huy post",
            "sửa lại",
            "sua lai",
        ]

        def is_confirm_command(command_text: str) -> bool:
            lowered_cmd = str(command_text or "").lower()
            if any(token in lowered_cmd for token in reject_tokens):
                return False
            tokens = [
                "xác nhận",
                "xac nhan",
                "đồng ý post",
                "dong y post",
                "đồng ý hạch toán",
                "dong y hach toan",
                "confirm post",
                "post luôn",
                "thực hiện post",
            ]
            return any(token in lowered_cmd for token in tokens)

        def is_reject_command(command_text: str) -> bool:
            lowered_cmd = str(command_text or "").lower()
            return any(token in lowered_cmd for token in reject_tokens)

        case_id = payload.case_id or "CASE"
        case_items = storage.list_case_items(scoped_data_key)
        current_item: Optional[Dict[str, Any]] = None
        if payload.case_id:
            for item in case_items:
                if str(item.get("id") or "") == payload.case_id:
                    current_item = item
                    break

        pending_posting = current_item.get("pending_posting") if isinstance(current_item, dict) and isinstance(current_item.get("pending_posting"), dict) else None

        if pending_posting and is_reject_command(text):
            staged_for_cleanup = pending_posting.get("received_attachments") if isinstance(pending_posting, dict) else []
            if isinstance(staged_for_cleanup, list):
                _delete_staged_attachments(normalized_email, case_id, staged_for_cleanup)

            timeline_entries = [
                {
                    "id": f"{case_id}-user-reject-{uuid.uuid4().hex[:6]}",
                    "kind": "user",
                    "role": "user",
                    "title": "Bạn",
                    "body": text or "Chưa đồng ý post",
                    "time": datetime.utcnow().strftime("%H:%M"),
                },
                {
                    "id": f"{case_id}-reject-{uuid.uuid4().hex[:6]}",
                    "kind": "analysis",
                    "role": "system",
                    "title": "Yêu cầu cập nhật hồ sơ",
                    "body": "Đã ghi nhận yêu cầu chưa đồng ý post. Vui lòng cập nhật thông tin để hệ thống xử lý lại.",
                    "time": datetime.utcnow().strftime("%H:%M"),
                }
            ]
            if payload.case_id and current_item:
                next_items = []
                for item in case_items:
                    if str(item.get("id") or "") != payload.case_id:
                        next_items.append(item)
                        continue
                    current_timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
                    current_reasoning = item.get("reasoning") if isinstance(item.get("reasoning"), list) else []
                    updated_item = {
                        **item,
                        "timeline": [*current_timeline, *timeline_entries],
                        "reasoning": ["Khách hàng chưa đồng ý post. Cần chỉnh sửa hoặc bổ sung hồ sơ.", *current_reasoning],
                        "status": "dang_xu_ly",
                        "statusLabel": "Đang xử lý",
                        "pending_posting": None,
                        "staged_evidence": [],
                        "updatedAt": datetime.utcnow().date().isoformat(),
                    }
                    next_items.append(updated_item)
                storage.replace_case_items(scoped_data_key, next_items, now)

            return {
                "ok": True,
                "message": "Đã ghi nhận yêu cầu chưa đồng ý post. Vui lòng cập nhật thông tin hồ sơ để xử lý lại.",
                "timeline_entries": timeline_entries,
                "posting_accepted": False,
                "requires_confirmation": False,
                "updated_at": now,
            }

        if pending_posting and is_confirm_command(text):
            pending_event = pending_posting.get("event") if isinstance(pending_posting.get("event"), dict) else {}
            pending_event = dict(pending_event)
            pending_event["case_id"] = case_id
            pending_event["event_date"] = str(
                pending_event.get("statement_date")
                or pending_event.get("issue_date")
                or pending_event.get("event_date")
                or datetime.utcnow().date().isoformat()
            )
            posting_event_date = str(pending_event.get("event_date") or datetime.utcnow().date().isoformat())

            staged_attachments = pending_posting.get("received_attachments") if isinstance(pending_posting, dict) else []
            committed_attachment_names: List[str] = []
            if isinstance(staged_attachments, list):
                committed_attachment_names = _commit_staged_attachments(normalized_email, case_id, staged_attachments)

            posting_result = posting_engine.post(pending_event)
            posting_accepted = bool(posting_result.accepted and posting_result.journal_entry)
            if posting_accepted:
                storage.upsert_case_event(scoped_data_key, case_id, pending_event, now)

            def format_date_for_summary(value: str) -> str:
                raw = str(value or "").strip()
                if not raw:
                    return "-"
                token_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", raw)
                if not token_match:
                    return raw
                token = token_match.group(1).replace("/", "-")
                if re.fullmatch(r"\d{8}", token):
                    try:
                        return datetime.strptime(token, "%Y%m%d").strftime("%d/%m/%Y")
                    except ValueError:
                        return raw
                for fmt in ["%Y-%m-%d", "%d-%m-%Y"]:
                    try:
                        return datetime.strptime(token, fmt).strftime("%d/%m/%Y")
                    except ValueError:
                        continue
                return raw

            raw_parse_rows = pending_posting.get("parse_rows") if isinstance(pending_posting.get("parse_rows"), list) else []
            allowed_labels = [
                "Đối tác",
                "Nội dung",
                "MST đối tác",
                "Số hóa đơn",
                "Ngày hóa đơn",
                "Số tiền trước thuế",
                "Thuế VAT",
                "Số tiền sau thuế",
                "Số tiền",
            ]
            posted_summary_rows: List[Dict[str, str]] = []
            posted_by_label: Dict[str, str] = {}

            for row in raw_parse_rows:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("label") or "").strip()
                value = str(row.get("value") or "").strip()
                if label == "Nhà cung cấp":
                    label = "Đối tác"
                if label in {"MST người bán", "MST người mua", "Vai trò hóa đơn"}:
                    continue
                if label == "Số tiền":
                    label = "Số tiền sau thuế"
                if label not in allowed_labels:
                    continue
                if label == "MST đối tác" and (not value or value == "-"):
                    continue
                if label == "Ngày hóa đơn":
                    value = format_date_for_summary(value)
                posted_by_label[label] = value or "-"

            if not posted_by_label:
                fallback_date = str(
                    pending_event.get("issue_date")
                    or pending_event.get("statement_date")
                    or pending_event.get("event_date")
                    or ""
                )
                fallback_total = float(pending_event.get("amount_total") or pending_event.get("total_amount") or pending_event.get("amount") or 0)
                fallback_untaxed = float(pending_event.get("amount_untaxed") or pending_event.get("untaxed_amount") or 0)
                fallback_vat = float(pending_event.get("vat_amount") or 0)
                if fallback_untaxed <= 0 and fallback_total > 0 and fallback_vat > 0 and fallback_total >= fallback_vat:
                    fallback_untaxed = fallback_total - fallback_vat
                if fallback_vat <= 0 and fallback_total > 0 and fallback_untaxed > 0 and fallback_total >= fallback_untaxed:
                    fallback_vat = fallback_total - fallback_untaxed
                posted_by_label = {
                    "Đối tác": str(pending_event.get("counterparty_name") or "Đối tác"),
                    "Nội dung": str(pending_event.get("description") or pending_event.get("goods_service_type") or "-"),
                    "Số hóa đơn": str(pending_event.get("invoice_no") or pending_event.get("reference_no") or "-"),
                    "Ngày hóa đơn": format_date_for_summary(fallback_date),
                    "Số tiền trước thuế": f"{fallback_untaxed:,.0f} đồng" if fallback_untaxed > 0 else "-",
                    "Thuế VAT": f"{fallback_vat:,.0f} đồng" if fallback_vat > 0 else "-",
                    "Số tiền sau thuế": f"{fallback_total:,.0f} đồng" if fallback_total > 0 else "-",
                }

            for label in allowed_labels:
                if label not in posted_by_label:
                    continue
                posted_summary_rows.append({"label": label, "value": str(posted_by_label.get(label) or "-")})

            result_body = (
                "Đã tạo bút toán tự động thành công."
                if posting_accepted and posting_result.journal_entry
                else f"Không thể tạo bút toán tự động: {posting_result.reason or 'Thiếu dữ liệu chuẩn.'}"
            )

            timeline_entries = [
                {
                    "id": f"{case_id}-user-confirm-{uuid.uuid4().hex[:6]}",
                    "kind": "user",
                    "role": "user",
                    "title": "Bạn",
                    "body": text or "Xác nhận và đồng ý post",
                    "time": datetime.utcnow().strftime("%H:%M"),
                },
            ]

            if posting_accepted and posted_summary_rows:
                timeline_entries.append(
                    {
                        "id": f"{case_id}-posted-summary-{uuid.uuid4().hex[:6]}",
                        "kind": "analysis",
                        "role": "system",
                        "title": "Thông tin đã post",
                        "body": "Hệ thống đã thực hiện post với các thông tin cơ bản sau:",
                        "table_rows": posted_summary_rows,
                        "time": datetime.utcnow().strftime("%H:%M"),
                    }
                )

            timeline_entries.append(
                {
                    "id": f"{case_id}-result-{uuid.uuid4().hex[:6]}",
                    "kind": "analysis",
                    "role": "system",
                    "title": "Kết quả hạch toán",
                    "body": result_body,
                    "time": datetime.utcnow().strftime("%H:%M"),
                }
            )

            if payload.case_id and current_item:
                next_items = []
                for item in case_items:
                    if str(item.get("id") or "") != payload.case_id:
                        next_items.append(item)
                        continue

                    current_timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
                    current_reasoning = item.get("reasoning") if isinstance(item.get("reasoning"), list) else []
                    current_evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
                    merged_evidence = [*current_evidence]
                    for attachment_name in committed_attachment_names:
                        if attachment_name and attachment_name not in merged_evidence:
                            merged_evidence.append(attachment_name)
                    next_status = "hoan_tat" if posting_accepted else "dang_xu_ly"
                    next_status_label = "Hoàn tất" if posting_accepted else "Đang xử lý"
                    updated_item = {
                        **item,
                        "timeline": [*current_timeline, *timeline_entries],
                        "evidence": merged_evidence,
                        "reasoning": [
                            (
                                f"Khách hàng đã đồng ý post và hệ thống đã sinh bút toán {posting_result.journal_entry.get('entry_id')}."
                                if posting_accepted and posting_result.journal_entry
                                else f"Khách hàng đã đồng ý post nhưng hệ thống chưa thể sinh bút toán: {posting_result.reason or 'Thiếu dữ liệu'}"
                            ),
                            *current_reasoning,
                        ],
                        "status": next_status,
                        "statusLabel": next_status_label,
                        "pending_posting": None,
                        "staged_evidence": [],
                        "updatedAt": posting_event_date,
                    }
                    next_items.append(updated_item)
                storage.replace_case_items(scoped_data_key, next_items, now)

            return {
                "ok": True,
                "message": (
                    "Đã nhận xác nhận của khách hàng. Đã tạo bút toán tự động thành công."
                    if posting_accepted and posting_result.journal_entry
                    else f"Đã nhận xác nhận của khách hàng. {result_body}"
                ),
                "timeline_entries": timeline_entries,
                "posting_accepted": posting_accepted,
                "posting_reason": posting_result.reason,
                "requires_confirmation": False,
                "updated_at": now,
            }

        attachment_count = len(payload.attachments)
        staged_attachments = save_case_attachments_to_staging(case_id, payload.attachments)
        staged_attachment_names = [str(item.get("name") or item.get("stored_name") or "") for item in staged_attachments]
        attachment_details = parse_attachment_details(payload.attachments, staged_attachment_names)
        parse_meta = attachment_details.get("parse_meta") if isinstance(attachment_details.get("parse_meta"), dict) else {}
        company_validation = parse_meta.get("company_validation") if isinstance(parse_meta.get("company_validation"), dict) else {}
        parse_warnings = parse_meta.get("warnings") if isinstance(parse_meta.get("warnings"), list) else []
        tax_match_ok = bool(company_validation.get("is_tax_code_match"))
        blocking_reason = str(company_validation.get("blocking_reason") or "").strip()

        if not tax_match_ok:
            if payload.case_id:
                changed = False
                next_items = []
                for item in case_items:
                    if str(item.get("id") or "") != payload.case_id:
                        next_items.append(item)
                        continue

                    current_timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
                    current_reasoning = item.get("reasoning") if isinstance(item.get("reasoning"), list) else []
                    reject_message = blocking_reason or "Hóa đơn không thuộc công ty đang đăng nhập (MST không khớp)."
                    reject_timeline = {
                        "id": f"{case_id}-reject-tax-{uuid.uuid4().hex[:6]}",
                        "kind": "analysis",
                        "role": "system",
                        "title": "Từ chối hồ sơ",
                        "body": reject_message,
                        "time": datetime.utcnow().strftime("%H:%M"),
                    }

                    updated_item = {
                        **item,
                        "timeline": [*current_timeline, reject_timeline],
                        "reasoning": [
                            "Hệ thống từ chối hồ sơ vì MST trên hóa đơn không khớp với công ty đang đăng nhập.",
                            *current_reasoning,
                        ],
                        "status": "can_xu_ly",
                        "statusLabel": "Cần xử lý",
                        "updatedAt": datetime.utcnow().date().isoformat(),
                    }
                    next_items.append(updated_item)
                    changed = True

                if changed:
                    storage.replace_case_items(scoped_data_key, next_items, now)

            return {
                "ok": False,
                "message": blocking_reason or "Từ chối xử lý: mã số thuế trên hóa đơn không khớp công ty đang đăng nhập.",
                "received_attachments": staged_attachment_names,
                "staged_attachments": staged_attachments,
                "requires_confirmation": False,
                "proposed_posting": {
                    "attachment_count": attachment_count,
                    "parse_meta": parse_meta,
                },
                "updated_at": now,
            }

        inferred = infer_event_from_input(text, staged_attachment_names, attachment_details)
        inferred_event = dict(inferred["event"])
        inferred_event["case_id"] = case_id
        inferred_event["event_date"] = str(
            inferred_event.get("statement_date")
            or inferred_event.get("issue_date")
            or inferred_event.get("event_date")
            or datetime.utcnow().date().isoformat()
        )
        inferred_event_date = str(inferred_event.get("event_date") or datetime.utcnow().date().isoformat())

        def format_date_for_display(value: str) -> str:
            raw = str(value or "").strip()
            if not raw:
                return ""
            token_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", raw)
            if not token_match:
                return raw
            token = token_match.group(1).replace("/", "-")
            if re.fullmatch(r"\d{8}", token):
                try:
                    return datetime.strptime(token, "%Y%m%d").strftime("%d/%m/%Y")
                except ValueError:
                    return raw
            for fmt in ["%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(token, fmt).strftime("%d/%m/%Y")
                except ValueError:
                    continue
            return raw

        def normalize_compare_text(value: str) -> str:
            lowered = str(value or "").lower()
            lowered = unicodedata.normalize("NFD", lowered)
            lowered = "".join(ch for ch in lowered if unicodedata.category(ch) != "Mn")
            lowered = re.sub(r"[^a-z0-9]", "", lowered)
            return lowered

        supplier_name = str(attachment_details.get("supplier_name") or inferred_event.get("counterparty_name") or "Đối tác")
        service_name = str(attachment_details.get("service_name") or inferred_event.get("description") or "dịch vụ")
        parsed_total = float(attachment_details.get("amount_total") or attachment_details.get("amount") or inferred_event.get("amount_total") or inferred_event.get("amount") or 0)
        parsed_untaxed = float(attachment_details.get("amount_untaxed") or inferred_event.get("amount_untaxed") or inferred_event.get("untaxed_amount") or 0)
        parsed_vat = float(attachment_details.get("vat_amount") or inferred_event.get("vat_amount") or 0)
        if parsed_untaxed <= 0 and parsed_total > 0 and parsed_vat > 0 and parsed_total >= parsed_vat:
            parsed_untaxed = parsed_total - parsed_vat
        if parsed_vat <= 0 and parsed_total > 0 and parsed_untaxed > 0 and parsed_total >= parsed_untaxed:
            parsed_vat = parsed_total - parsed_untaxed
        amount_text_untaxed = f"{parsed_untaxed:,.0f}" if parsed_untaxed > 0 else "-"
        amount_text_vat = f"{parsed_vat:,.0f}" if parsed_vat > 0 else "-"
        amount_text_total = f"{parsed_total:,.0f}" if parsed_total > 0 else "-"
        invoice_no = str(attachment_details.get("invoice_number") or inferred_event.get("invoice_no") or "N/A")
        invoice_date = str(
            inferred_event.get("issue_date")
            or inferred_event.get("statement_date")
            or inferred_event.get("event_date")
            or ""
        )
        invoice_date_display = format_date_for_display(invoice_date)
        invoice_excerpt = str(attachment_details.get("invoice_content") or "")
        invoice_role = str(company_validation.get("invoice_role") or "").strip().lower()
        seller_name = str(attachment_details.get("seller_name") or "").strip()
        buyer_name = str(attachment_details.get("buyer_name") or "").strip()
        seller_tax_code = _normalize_tax_code(str(attachment_details.get("seller_tax_code") or "").strip())
        buyer_tax_code = _normalize_tax_code(str(attachment_details.get("buyer_tax_code") or "").strip())
        current_company_tax_code = _normalize_tax_code(str(selected_company_tax_code or ""))
        current_company_name_norm = normalize_compare_text(str(selected_company_name or ""))

        def is_current_company(name_value: str, tax_value: str) -> bool:
            normalized_tax = _normalize_tax_code(str(tax_value or ""))
            if current_company_tax_code and normalized_tax and normalized_tax == current_company_tax_code:
                return True
            normalized_name = normalize_compare_text(str(name_value or ""))
            if current_company_name_norm and normalized_name:
                return current_company_name_norm in normalized_name or normalized_name in current_company_name_norm
            return False

        def pick_partner(preferred: List[Tuple[str, str]], fallback_name: str) -> Tuple[str, str]:
            for name_value, tax_value in preferred:
                candidate_name = str(name_value or "").strip()
                if not candidate_name:
                    continue
                if is_current_company(candidate_name, tax_value):
                    continue
                return candidate_name, _normalize_tax_code(str(tax_value or ""))
            if fallback_name and not is_current_company(fallback_name, ""):
                return str(fallback_name), ""
            return "Đối tác", ""

        if invoice_role == "outbound":
            partner_name, partner_tax_code = pick_partner(
                [
                    (buyer_name, buyer_tax_code),
                    (str(inferred_event.get("counterparty_name") or ""), ""),
                    (seller_name, seller_tax_code),
                    (supplier_name, ""),
                ],
                supplier_name,
            )
        elif invoice_role == "inbound":
            partner_name, partner_tax_code = pick_partner(
                [
                    (seller_name, seller_tax_code),
                    (str(inferred_event.get("counterparty_name") or ""), ""),
                    (buyer_name, buyer_tax_code),
                    (supplier_name, ""),
                ],
                supplier_name,
            )
        else:
            partner_name, partner_tax_code = pick_partner(
                [
                    (str(inferred_event.get("counterparty_name") or ""), ""),
                    (seller_name, seller_tax_code),
                    (buyer_name, buyer_tax_code),
                    (supplier_name, ""),
                ],
                supplier_name,
            )

        partner_name = str(partner_name or "Đối tác")
        partner_tax_code = _normalize_tax_code(str(partner_tax_code or "").strip())

        parse_table_rows = [
            {"label": "Đối tác", "value": partner_name},
            {"label": "Nội dung", "value": service_name},
            {"label": "Số hóa đơn", "value": invoice_no},
            {"label": "Ngày hóa đơn", "value": invoice_date_display or "-"},
            {"label": "Số tiền trước thuế", "value": f"{amount_text_untaxed} đồng" if amount_text_untaxed != "-" else "-"},
            {"label": "Thuế VAT", "value": f"{amount_text_vat} đồng" if amount_text_vat != "-" else "-"},
            {"label": "Số tiền sau thuế", "value": f"{amount_text_total} đồng" if amount_text_total != "-" else "-"},
        ]
        if partner_tax_code:
            parse_table_rows.insert(2, {"label": "MST đối tác", "value": partner_tax_code})

        extract_body = (
            f"Đã tiếp nhận hồ sơ: {', '.join(staged_attachment_names)}"
            if staged_attachment_names
            else "Đã tiếp nhận hồ sơ: không có tệp đính kèm"
        )

        user_message = text or "Gửi hồ sơ đính kèm"
        if staged_attachment_names:
            user_message += f"\nĐính kèm: {', '.join(staged_attachment_names)}"

        confirm_body = "Vui lòng khách hàng xác nhận thông tin và trả lời 'Xác nhận và đồng ý post' để hệ thống thực hiện hạch toán."

        timeline_entries = [
            {
                "id": f"{case_id}-user-input-{uuid.uuid4().hex[:6]}",
                "kind": "user",
                "role": "user",
                "title": "Bạn",
                "body": user_message,
                "time": datetime.utcnow().strftime("%H:%M"),
            },
            {
                "id": f"{case_id}-extract-{uuid.uuid4().hex[:6]}",
                "kind": "analysis",
                "role": "system",
                "title": "Tiếp nhận hồ sơ",
                "body": extract_body,
                "time": datetime.utcnow().strftime("%H:%M"),
            },
            {
                "id": f"{case_id}-confirm-{uuid.uuid4().hex[:6]}",
                "kind": "analysis",
                "role": "system",
                "title": "Yêu cầu xác nhận",
                "body": confirm_body,
                "time": datetime.utcnow().strftime("%H:%M"),
            },
        ]

        if parse_warnings:
            timeline_entries.append(
                {
                    "id": f"{case_id}-warnings-{uuid.uuid4().hex[:6]}",
                    "kind": "analysis",
                    "role": "system",
                    "title": "Cảnh báo đối chiếu",
                    "body": "\n".join(str(item) for item in parse_warnings),
                    "time": datetime.utcnow().strftime("%H:%M"),
                }
            )

        if payload.case_id:
            changed = False
            next_items = []
            for item in case_items:
                if str(item.get("id") or "") != payload.case_id:
                    next_items.append(item)
                    continue

                current_timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
                current_reasoning = item.get("reasoning") if isinstance(item.get("reasoning"), list) else []

                updated_item = {
                    **item,
                    "timeline": [*current_timeline, *timeline_entries],
                    "staged_evidence": [
                        {
                            "name": str(attachment.get("name") or ""),
                            "preview_ref": str(attachment.get("preview_ref") or ""),
                            "storage": "staging",
                            "is_staged": True,
                        }
                        for attachment in staged_attachments
                    ],
                    "reasoning": [
                        f"Đã phân tích hồ sơ với {len(staged_attachment_names)} tệp đính kèm.",
                        "Đang chờ khách hàng xác nhận trước khi post bút toán.",
                        *current_reasoning,
                    ],
                    "amount": f"{parsed_total:,.0f} VND" if parsed_total > 0 else item.get("amount", "0 VND"),
                    "partner": str(partner_name or item.get("partner") or "Đối tác"),
                    "title": str(service_name or item.get("title") or "Hồ sơ kế toán"),
                    "status": "cho_xac_nhan",
                    "statusLabel": "Chờ khách hàng xác nhận",
                    "pending_posting": {
                        "event_type": inferred["event_type"],
                        "event": inferred_event,
                        "parse_rows": parse_table_rows,
                        "parse_meta": attachment_details.get("parse_meta", {}),
                        "received_attachments": staged_attachments,
                    },
                    "updatedAt": inferred_event_date,
                }
                next_items.append(updated_item)
                changed = True

            if changed:
                storage.replace_case_items(scoped_data_key, next_items, now)

        return {
            "ok": True,
            "message": "Đã tiếp nhận và phân tích hồ sơ. Vui lòng khách hàng xác nhận thông tin và đồng ý post để hệ thống hạch toán.",
            "timeline_entries": timeline_entries,
            "received_attachments": staged_attachment_names,
            "staged_attachments": staged_attachments,
            "posting_accepted": False,
            "requires_confirmation": True,
            "proposed_posting": {
                "event_type": inferred["event_type"],
                "supplier_name": supplier_name,
                "service_name": service_name,
                "invoice_number": invoice_no,
                "amount": parsed_total,
                "attachment_count": attachment_count,
                "staged_attachments": staged_attachments,
                "parse_rows": parse_table_rows,
                "parse_meta": attachment_details.get("parse_meta", {}),
            },
            "updated_at": now,
        }

    if payload.action == "new_case":
        case_id = f"CASE-NEW-{uuid.uuid4().hex[:6].upper()}"
        item = {
            "id": case_id,
            "code": case_id.replace("CASE", "CS"),
            "title": "Hồ sơ mới từ thao tác nhanh",
            "partner": "Chưa chọn đối tác",
            "amount": "0 VND",
            "updatedAt": datetime.utcnow().date().isoformat(),
            "status": "moi",
            "statusLabel": "Mới",
            "timeline": [],
            "evidence": [],
            "reasoning": ["Hồ sơ nháp vừa được tạo."],
        }
        now = datetime.utcnow().isoformat() + "Z"
        current = storage.list_case_items(scoped_data_key)
        storage.replace_case_items(scoped_data_key, [item, *current], now)
        return {"ok": True, "message": "Đã tạo hồ sơ mới.", "case": item}

    if payload.action == "delete_case":
        target_case_id = str(payload.case_id or "").strip()
        if not target_case_id:
            return {"ok": False, "message": "Thiếu mã hồ sơ cần xóa."}

        normalized_case_id = _sanitize_case_id(target_case_id)
        _delete_case_attachment_tree(normalized_email, normalized_case_id)

        current_items = storage.list_case_items(scoped_data_key)
        next_items = [item for item in current_items if str(item.get("id") or "") != target_case_id]
        removed_items = len(current_items) - len(next_items)
        if removed_items:
            storage.replace_case_items(scoped_data_key, next_items, now)

        current_events = storage.list_case_events(scoped_data_key)
        next_events = [event for event in current_events if str(event.get("case_id") or "") != target_case_id]
        removed_events = len(current_events) - len(next_events)
        if removed_events:
            storage.replace_case_events(scoped_data_key, next_events, now)

        if not removed_items and not removed_events:
            return {
                "ok": True,
                "message": "Không tìm thấy hồ sơ trong dữ liệu để xóa.",
                "deleted_case_id": target_case_id,
                "removed_items": 0,
                "removed_events": 0,
            }

        return {
            "ok": True,
            "message": "Đã xóa hồ sơ khỏi database.",
            "deleted_case_id": target_case_id,
            "removed_items": removed_items,
            "removed_events": removed_events,
        }

    return {"ok": True, "message": "Đã xử lý thao tác giao diện.", "updated_at": now}


@app.get("/api/demo/reports/detailed")
def get_demo_detailed_reports(
    as_of_date: Optional[str] = None,
    email: str = "demo@wssmeas.local",
    company_id: str = "",
) -> Dict[str, Any]:
    def format_date_for_display(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        token_match = re.search(r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})", raw)
        if not token_match:
            return raw
        token = token_match.group(1).replace("/", "-")
        if re.fullmatch(r"\d{8}", token):
            try:
                return datetime.strptime(token, "%Y%m%d").strftime("%d/%m/%Y")
            except ValueError:
                return raw
        for fmt in ["%Y-%m-%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(token, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return raw

    normalized_email = email.lower().strip()
    resolved_company_id = resolve_company_id_for_user(normalized_email, company_id)
    entries = _derive_journal_entries_from_truth(company_scope_key(resolved_company_id), as_of_date)

    derived_as_of_date = as_of_date
    if not derived_as_of_date:
        event_dates = [
            str(item.get("meta", {}).get("event_date", "")).strip()
            for item in entries
            if isinstance(item, dict)
        ]
        valid_dates = [value for value in event_dates if value]
        derived_as_of_date = max(valid_dates) if valid_dates else datetime.utcnow().date().isoformat()

    financial_report = report_service.generate_financial_statements(entries, derived_as_of_date)
    chart_accounts = store.chart_of_accounts_tt133()
    account_name_map = {
        str(item.get("account_code")): str(item.get("account_name"))
        for item in chart_accounts
        if isinstance(item, dict)
    }

    gl_items = []
    gl_posting_lines = []
    for idx, entry in enumerate(entries, start=1):
        lines = entry.get("lines", []) if isinstance(entry, dict) else []
        debit_total = 0.0
        credit_total = 0.0
        posting_lines = []

        for line in lines:
            side_raw = str(line.get("side", ""))
            amount = float(line.get("amount", 0) or 0)
            account = str(line.get("account", ""))
            if side_raw == "debit":
                debit_total += amount
            if side_raw == "credit":
                credit_total += amount

            posting = {
                "side": "Nợ" if side_raw == "debit" else "Có",
                "account": account,
                "account_name": account_name_map.get(account, "Chưa gắn tên tài khoản TT133"),
                "amount": amount,
            }
            posting_lines.append(posting)
            gl_posting_lines.append(posting)

        meta = entry.get("meta", {}) if isinstance(entry, dict) else {}
        event_date_raw = str(meta.get("event_date") or derived_as_of_date)
        gl_items.append(
            {
                "stt": idx,
                "entry_id": entry.get("entry_id"),
                "event_type": entry.get("event_type"),
            "event_date": format_date_for_display(event_date_raw),
            "event_date_iso": event_date_raw,
                "narration": entry.get("normal_narration") or "",
                "debit_total": debit_total,
                "credit_total": credit_total,
                "line_count": len(lines),
                "postings": posting_lines,
            }
        )

    trial_balance: Dict[str, Dict[str, float]] = {}
    for posting in gl_posting_lines:
        account = str(posting.get("account") or "")
        if not account:
            continue
        if account not in trial_balance:
            trial_balance[account] = {"debit": 0.0, "credit": 0.0}
        amount = float(posting.get("amount", 0) or 0)
        if posting.get("side") == "Nợ":
            trial_balance[account]["debit"] += amount
        else:
            trial_balance[account]["credit"] += amount

    for account, values in trial_balance.items():
        values["balance"] = float(values.get("debit", 0) - values.get("credit", 0))

    def prefix_balance(prefixes: list[str]) -> float:
        total = 0.0
        for account, values in trial_balance.items():
            if any(str(account).startswith(prefix) for prefix in prefixes):
                total += float(values.get("balance", 0) or 0)
        return total

    def positive_asset(prefixes: list[str]) -> float:
        return max(prefix_balance(prefixes), 0.0)

    def positive_liability_or_equity(prefixes: list[str]) -> float:
        return max(-prefix_balance(prefixes), 0.0)

    def revenue_amount(prefixes: list[str]) -> float:
        return max(-prefix_balance(prefixes), 0.0)

    def expense_amount(prefixes: list[str]) -> float:
        return max(prefix_balance(prefixes), 0.0)

    trial_balance_items = [
        {
            "account": account,
            "account_name": account_name_map.get(account, "Chưa gắn tên tài khoản TT133"),
            "opening_debit": 0,
            "opening_credit": 0,
            "debit": values.get("debit", 0),
            "credit": values.get("credit", 0),
            "balance": values.get("balance", 0),
            "ending_debit": values.get("balance", 0) if float(values.get("balance", 0) or 0) > 0 else 0,
            "ending_credit": abs(float(values.get("balance", 0) or 0)) if float(values.get("balance", 0) or 0) < 0 else 0,
        }
        for account, values in sorted(trial_balance.items(), key=lambda item: item[0])
    ]

    bs = financial_report.get("bang_can_doi_ke_toan", {})
    pl = financial_report.get("ket_qua_hoat_dong_kinh_doanh", {})
    cf = financial_report.get("luu_chuyen_tien_te", {})

    current_assets = positive_asset(["111", "112", "121", "128", "131", "133", "136", "138", "141", "151", "152", "153", "154", "155", "156", "157"])
    non_current_assets = positive_asset(["211", "212", "213", "214", "217", "228", "242", "244"])
    short_term_liabilities = positive_liability_or_equity(["311", "315", "331", "333", "334", "335", "336", "338", "3411", "3412"])
    long_term_liabilities = positive_liability_or_equity(["341", "343", "344", "347"])
    owner_equity = positive_liability_or_equity(["411", "414", "418", "421"])

    tt133_bs_rows = [
        {"code": "100", "item": "A. TÀI SẢN NGẮN HẠN", "amount": current_assets},
        {"code": "110", "item": "I. Tiền và các khoản tương đương tiền", "amount": positive_asset(["111", "112", "1281"])},
        {"code": "120", "item": "II. Các khoản đầu tư tài chính ngắn hạn", "amount": positive_asset(["121", "128"])},
        {"code": "130", "item": "III. Các khoản phải thu ngắn hạn", "amount": positive_asset(["131", "136", "138", "141"])},
        {"code": "140", "item": "IV. Hàng tồn kho", "amount": positive_asset(["151", "152", "153", "154", "155", "156", "157"])},
        {"code": "150", "item": "V. Tài sản ngắn hạn khác", "amount": positive_asset(["133"])},
        {"code": "200", "item": "B. TÀI SẢN DÀI HẠN", "amount": non_current_assets},
        {"code": "210", "item": "I. Các khoản phải thu dài hạn", "amount": positive_asset(["136", "1388"])},
        {"code": "220", "item": "II. Tài sản cố định", "amount": positive_asset(["211", "212", "213", "214"])},
        {"code": "230", "item": "III. Bất động sản đầu tư", "amount": positive_asset(["217"])},
        {"code": "240", "item": "IV. Tài sản dở dang dài hạn", "amount": positive_asset(["241"])},
        {"code": "250", "item": "V. Đầu tư tài chính dài hạn", "amount": positive_asset(["228"])},
        {"code": "260", "item": "VI. Tài sản dài hạn khác", "amount": positive_asset(["242", "244"])},
        {"code": "270", "item": "TỔNG CỘNG TÀI SẢN", "amount": float(bs.get("tong_tai_san", 0) or 0)},
        {"code": "300", "item": "C. NỢ PHẢI TRẢ", "amount": float(bs.get("tong_no_phai_tra", 0) or 0)},
        {"code": "310", "item": "I. Nợ ngắn hạn", "amount": short_term_liabilities},
        {"code": "330", "item": "II. Nợ dài hạn", "amount": long_term_liabilities},
        {"code": "400", "item": "D. VỐN CHỦ SỞ HỮU", "amount": float(bs.get("von_chu_so_huu", 0) or 0)},
        {"code": "410", "item": "I. Vốn chủ sở hữu", "amount": owner_equity},
        {"code": "430", "item": "II. Nguồn kinh phí và quỹ khác", "amount": positive_liability_or_equity(["353", "356"])},
        {"code": "440", "item": "TỔNG CỘNG NGUỒN VỐN", "amount": float(bs.get("tong_tai_san", 0) or 0)},
    ]

    gross_revenue = revenue_amount(["511"])
    sales_deductions = expense_amount(["521"])
    net_revenue = max(gross_revenue - sales_deductions, 0.0)
    cost_of_goods_sold = expense_amount(["632"])
    gross_profit = net_revenue - cost_of_goods_sold
    financial_income = revenue_amount(["515"])
    financial_expense = expense_amount(["635"])
    selling_expense = expense_amount(["641"])
    admin_expense = expense_amount(["642"])
    operating_profit = gross_profit + financial_income - financial_expense - selling_expense - admin_expense
    other_income = revenue_amount(["711"])
    other_expense = expense_amount(["811"])
    other_profit = other_income - other_expense
    accounting_profit_before_tax = operating_profit + other_profit
    current_cit_expense = expense_amount(["8211"])
    deferred_cit_expense = expense_amount(["8212"])
    total_cit_expense = current_cit_expense + deferred_cit_expense
    profit_after_tax = accounting_profit_before_tax - total_cit_expense

    tt133_pl_rows = [
        {"code": "01", "item": "Doanh thu bán hàng và cung cấp dịch vụ", "amount": gross_revenue},
        {"code": "02", "item": "Các khoản giảm trừ doanh thu", "amount": sales_deductions},
        {"code": "10", "item": "Doanh thu thuần về bán hàng và cung cấp dịch vụ", "amount": net_revenue},
        {"code": "11", "item": "Giá vốn hàng bán", "amount": cost_of_goods_sold},
        {"code": "20", "item": "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "amount": gross_profit},
        {"code": "21", "item": "Doanh thu hoạt động tài chính", "amount": financial_income},
        {"code": "22", "item": "Chi phí tài chính", "amount": financial_expense},
        {"code": "25", "item": "Chi phí bán hàng", "amount": selling_expense},
        {"code": "26", "item": "Chi phí quản lý doanh nghiệp", "amount": admin_expense},
        {"code": "30", "item": "Lợi nhuận thuần từ hoạt động kinh doanh", "amount": operating_profit},
        {"code": "31", "item": "Thu nhập khác", "amount": other_income},
        {"code": "32", "item": "Chi phí khác", "amount": other_expense},
        {"code": "40", "item": "Lợi nhuận khác", "amount": other_profit},
        {"code": "50", "item": "Tổng lợi nhuận kế toán trước thuế", "amount": accounting_profit_before_tax},
        {"code": "51", "item": "Chi phí thuế TNDN hiện hành", "amount": current_cit_expense},
        {"code": "52", "item": "Chi phí thuế TNDN hoãn lại", "amount": deferred_cit_expense},
        {"code": "60", "item": "Lợi nhuận sau thuế thu nhập doanh nghiệp", "amount": profit_after_tax},
    ]

    cash_by_event_type: Dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        event_type = str(entry.get("event_type") or "khac")
        cash_delta = 0.0
        for line in entry.get("lines", []):
            account = str(line.get("account") or "")
            if not (account.startswith("111") or account.startswith("112")):
                continue
            amount = float(line.get("amount", 0) or 0)
            side = str(line.get("side") or "")
            if side == "debit":
                cash_delta += amount
            elif side == "credit":
                cash_delta -= amount
        cash_by_event_type[event_type] = cash_by_event_type.get(event_type, 0.0) + cash_delta

    operating_cash_in = max(cash_by_event_type.get("ban_hang_dich_vu", 0.0), 0.0)
    operating_cash_out = (
        abs(min(cash_by_event_type.get("mua_dich_vu", 0.0), 0.0))
        + abs(min(cash_by_event_type.get("mua_hang_dung_noi_bo", 0.0), 0.0))
        + abs(min(cash_by_event_type.get("nop_thue", 0.0), 0.0))
        + abs(min(cash_by_event_type.get("tam_ung", 0.0), 0.0))
    )
    investing_cash_out = abs(min(cash_by_event_type.get("mua_tscd", 0.0), 0.0))
    financing_cash_in = max(cash_by_event_type.get("gop_von", 0.0), 0.0)

    operating_net = operating_cash_in - operating_cash_out
    investing_net = -investing_cash_out
    financing_net = financing_cash_in

    tt133_cf_rows = [
        {"code": "I", "item": "Lưu chuyển tiền từ hoạt động kinh doanh", "amount": operating_net},
        {"code": "01", "item": "Tiền thu từ bán hàng, cung cấp dịch vụ", "amount": operating_cash_in},
        {"code": "02", "item": "Tiền chi trả cho người cung cấp hàng hóa, dịch vụ", "amount": abs(min(cash_by_event_type.get("mua_dich_vu", 0.0), 0.0)) + abs(min(cash_by_event_type.get("mua_hang_dung_noi_bo", 0.0), 0.0))},
        {"code": "05", "item": "Tiền chi nộp thuế thu nhập doanh nghiệp", "amount": abs(min(cash_by_event_type.get("nop_thue", 0.0), 0.0))},
        {"code": "06", "item": "Tiền thu khác từ hoạt động kinh doanh", "amount": 0.0},
        {"code": "07", "item": "Tiền chi khác cho hoạt động kinh doanh", "amount": abs(min(cash_by_event_type.get("tam_ung", 0.0), 0.0))},
        {"code": "20", "item": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "amount": operating_net},
        {"code": "II", "item": "Lưu chuyển tiền từ hoạt động đầu tư", "amount": investing_net},
        {"code": "21", "item": "Tiền chi để mua sắm, xây dựng TSCĐ", "amount": investing_cash_out},
        {"code": "30", "item": "Lưu chuyển tiền thuần từ hoạt động đầu tư", "amount": investing_net},
        {"code": "III", "item": "Lưu chuyển tiền từ hoạt động tài chính", "amount": financing_net},
        {"code": "33", "item": "Tiền thu từ đi vay, phát hành cổ phiếu, nhận vốn góp", "amount": financing_cash_in},
        {"code": "40", "item": "Lưu chuyển tiền thuần từ hoạt động tài chính", "amount": financing_net},
        {"code": "50", "item": "Lưu chuyển tiền thuần trong kỳ", "amount": float(cf.get("luu_chuyen_thuan", 0) or 0)},
        {"code": "70", "item": "Tiền và tương đương tiền cuối kỳ", "amount": positive_asset(["111", "112", "1281"])},
    ]

    return {
        "email": normalized_email,
        "company_id": resolved_company_id,
        "as_of_date": format_date_for_display(derived_as_of_date),
        "as_of_date_iso": derived_as_of_date,
        "gl": {
            "items": gl_items,
            "total": len(gl_items),
        },
        "tb": {
            "items": trial_balance_items,
            "total": len(trial_balance_items),
        },
        "bs": bs,
        "pl": pl,
        "cf": cf,
        "tt133": {
            "basis": "Thông tư 133/2016/TT-BTC",
            "tb_rows": trial_balance_items,
            "bs_rows": tt133_bs_rows,
            "pl_rows": tt133_pl_rows,
            "cf_rows": tt133_cf_rows,
        },
    }


@app.post("/api/auth/login-demo")
def login_demo(payload: LoginPayload, request: Request) -> Dict[str, Any]:
    normalized_email = payload.email.lower().strip()
    _check_login_rate_limit(normalized_email, request)
    token = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    if not storage.get_user(normalized_email):
        is_mock_user = normalized_email in MOCK_USER_EMAILS
        storage.upsert_user(
            normalized_email,
            {
                "email": normalized_email,
                "full_name": normalized_email.split("@")[0],
                "role": "staff",
                "status": "active",
                "company_id": MOCK_COMPANY_ID if is_mock_user else "",
            },
            now,
            now,
        )
        if is_mock_user:
            storage.upsert_user_company_membership(
                email=normalized_email,
                company_id=MOCK_COMPANY_ID,
                role="staff",
                is_default=True,
                payload={"company_name": MOCK_COMPANY_PROFILE["company_name"], "scope": "accounting"},
                updated_at=now,
            )

    storage.save_session(token, normalized_email, now)
    _clear_login_rate_limit(normalized_email, request)
    company_items, default_company_id = _build_accessible_company_items(normalized_email)
    default_company = next((item for item in company_items if str(item.get("company_id") or "") == default_company_id), None)
    has_company = bool(default_company and _profile_complete(default_company))
    return {
        "token": token,
        "email": normalized_email,
        "has_company_profile": has_company,
        "company_id": str(default_company.get("company_id") or "") if default_company else "",
        "company_name": str(default_company.get("company_name") or "") if default_company else "",
        "ui_hints": build_ui_hints(has_company, "login"),
    }


@app.get("/api/company/profile")
def get_company_profile(email: str = Depends(get_current_email)) -> Dict[str, Any]:
    company_items, default_company_id = _build_accessible_company_items(email)
    profile = next((item for item in company_items if str(item.get("company_id") or "") == default_company_id), None)
    if not profile:
        profile = storage.get_default_onboarding_company(email) or storage.get_company_profile(email)
    if not profile:
        return {
            "exists": False,
            "profile": None,
            "ui_hints": build_ui_hints(False, "fetch_company_profile"),
        }
    return {
        "exists": True,
        "profile": profile,
        "ui_hints": build_ui_hints(True, "fetch_company_profile"),
    }


@app.post("/api/company/profile")
def upsert_company_profile(payload: CompanyProfilePayload, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat() + "Z"
    profile_data = payload.model_dump()
    normalized_tax = _normalize_tax_code(profile_data.get("tax_code") or "")
    company_id = str(profile_data.get("company_id") or f"COMP-{normalized_tax or uuid.uuid4().hex[:8].upper()}").strip()
    profile_data["company_id"] = company_id
    profile_data["tax_code"] = normalized_tax

    storage.upsert_company_profile(email, profile_data, now)
    storage.upsert_onboarding_company(
        email=email,
        company_id=company_id,
        tax_code=normalized_tax,
        payload=profile_data,
        is_default=True,
        updated_at=now,
    )
    storage.upsert_company(
        company_id,
        {
            "company_id": company_id,
            "company_name": profile_data.get("company_name"),
            "tax_code": normalized_tax,
            "address": profile_data.get("address"),
            "legal_representative": profile_data.get("legal_representative"),
            "tax_office_code": profile_data.get("tax_office_code"),
            "tax_office_name": profile_data.get("tax_office_name"),
            "province_code": profile_data.get("province_code"),
            "province_name": profile_data.get("province_name"),
        },
        now,
        now,
    )
    storage.upsert_user_company_membership(
        email=email,
        company_id=company_id,
        role="owner",
        is_default=True,
        payload={
            "company_name": profile_data.get("company_name"),
            "tax_code": normalized_tax,
            "scope": "accounting",
        },
        updated_at=now,
    )
    return {
        "saved": True,
        "profile": profile_data,
        "ui_hints": build_ui_hints(_profile_complete(profile_data), "upsert_company_profile"),
    }


@app.get("/api/onboard/company-lookup")
def lookup_company_by_tax_code(tax_code: str, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    normalized_tax = _normalize_tax_code(tax_code)
    if not normalized_tax or len(normalized_tax) < 8:
        raise HTTPException(status_code=400, detail="INVALID_TAX_CODE")

    existing = storage.find_onboarding_company_by_tax_code(email, normalized_tax)
    if existing:
        return {
            "found": True,
            "source": "local_db",
            "profile": existing,
        }

    for company in storage.list_companies():
        if str(company.get("company_id") or "").strip() == MOCK_COMPANY_ID:
            continue
        if _normalize_tax_code(str(company.get("tax_code") or "")) == normalized_tax:
            merged = dict(company)
            merged["tax_code"] = normalized_tax
            return {
                "found": True,
                "source": "company_db",
                "profile": merged,
            }

    external = _lookup_company_by_tax_code_external(normalized_tax)
    return external


@app.get("/api/onboard/companies")
def list_onboard_companies(email: str = Depends(get_current_email)) -> Dict[str, Any]:
    companies, default_company_id = _build_accessible_company_items(email)
    return {
        "items": companies,
        "default_company_id": default_company_id,
    }


@app.post("/api/onboard/select-company")
def select_onboard_company(payload: SelectCompanyPayload, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    company_items, _ = _build_accessible_company_items(email)
    company = next((item for item in company_items if str(item.get("company_id") or "") == payload.company_id), None)
    if not company:
        raise HTTPException(status_code=404, detail="COMPANY_NOT_FOUND")

    role = str(company.get("role") or "owner")
    membership_payload = {
        "company_name": str(company.get("company_name") or payload.company_id),
        "tax_code": str(company.get("tax_code") or ""),
        "scope": str(company.get("scope") or "accounting"),
    }
    now = datetime.utcnow().isoformat() + "Z"
    storage.upsert_user_company_membership(
        email=email,
        company_id=payload.company_id,
        role=role,
        is_default=True,
        payload=membership_payload,
        updated_at=now,
    )
    storage.set_default_onboarding_company(email, payload.company_id, now)
    return {
        "selected": True,
        "company_id": payload.company_id,
        "profile": company,
        "is_complete": _profile_complete(company),
    }


@app.post("/api/onboard/companies")
def create_or_update_onboard_company(payload: CompanyProfilePayload, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat() + "Z"
    profile_data = payload.model_dump()
    normalized_tax = _normalize_tax_code(profile_data.get("tax_code") or "")
    if not normalized_tax:
        raise HTTPException(status_code=400, detail="INVALID_TAX_CODE")

    requested_company_id = str(profile_data.get("company_id") or "").strip()
    existing_company = storage.get_company(requested_company_id) if requested_company_id else None

    if not existing_company:
        for company in storage.list_companies():
            if str(company.get("company_id") or "").strip() == MOCK_COMPANY_ID:
                continue
            if _normalize_tax_code(str(company.get("tax_code") or "")) == normalized_tax:
                existing_company = company
                break

    existing_company_id = str((existing_company or {}).get("company_id") or "").strip()
    company_id = str(existing_company_id or requested_company_id or f"COMP-{normalized_tax}").strip()

    existing_tax_code = _normalize_tax_code(str(existing_company.get("tax_code") or "")) if existing_company else ""
    if existing_tax_code and existing_tax_code != normalized_tax:
        raise HTTPException(status_code=400, detail="TAX_CODE_IMMUTABLE")

    profile_data["company_id"] = company_id
    profile_data["tax_code"] = normalized_tax

    storage.upsert_onboarding_company(
        email=email,
        company_id=company_id,
        tax_code=normalized_tax,
        payload=profile_data,
        is_default=True,
        updated_at=now,
    )
    storage.upsert_company_profile(email, profile_data, now)
    storage.upsert_company(
        company_id,
        {
            "company_id": company_id,
            "company_name": profile_data.get("company_name"),
            "tax_code": normalized_tax,
            "address": profile_data.get("address"),
            "legal_representative": profile_data.get("legal_representative"),
            "established_date": profile_data.get("established_date"),
            "accounting_software_start_date": profile_data.get("accounting_software_start_date"),
            "fiscal_year_start": profile_data.get("fiscal_year_start"),
            "tax_declaration_cycle": profile_data.get("tax_declaration_cycle"),
            "default_bank_account": profile_data.get("default_bank_account"),
            "accountant_email": profile_data.get("accountant_email"),
        },
        now,
        now,
    )
    storage.upsert_user_company_membership(
        email=email,
        company_id=company_id,
        role="owner",
        is_default=True,
        payload={
            "company_name": profile_data.get("company_name"),
            "tax_code": normalized_tax,
            "scope": "accounting",
        },
        updated_at=now,
    )

    return {
        "saved": True,
        "profile": profile_data,
        "is_complete": _profile_complete(profile_data),
        "ui_hints": build_ui_hints(_profile_complete(profile_data), "upsert_onboarding_company"),
    }


@app.post("/api/events/post")
def post_event(payload: EventPayload, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    profile = storage.get_company_profile(email)
    if not profile:
        raise HTTPException(status_code=400, detail="COMPANY_PROFILE_REQUIRED")

    event = dict(payload.data)
    event["source_id"] = payload.source_id
    event["event_type"] = payload.event_type

    result = posting_engine.post(event)
    if not result.accepted or not result.journal_entry:
        return {
            "accepted": False,
            "reason": result.reason,
            "journal_entry": None,
            "ui_hints": {
                "next_actions": ["review_event_context"],
                "available_actions": ["retry_post_event"],
                "blocked_actions": ["lock_period"],
                "context": "validation_failed",
            },
        }

    now = datetime.utcnow().isoformat() + "Z"
    case_id = str(payload.data.get("case_id") or f"API-{uuid.uuid4().hex[:8].upper()}")
    truth_event = dict(event)
    truth_event["case_id"] = case_id
    truth_event["event_date"] = str(
        truth_event.get("statement_date")
        or truth_event.get("issue_date")
        or truth_event.get("event_date")
        or datetime.utcnow().date().isoformat()
    )
    storage.upsert_case_event(email, case_id, truth_event, now)
    return {
        "accepted": True,
        "reason": None,
        "journal_entry": result.journal_entry,
        "ui_hints": {
            "next_actions": ["view_journal", "open_reports"],
            "available_actions": ["post_event", "view_reports", "create_adjustment"],
            "blocked_actions": [],
            "context": "posted",
        },
    }


@app.get("/api/journals")
def list_journals(email: str = Depends(get_current_email)) -> Dict[str, Any]:
    items = _derive_journal_entries_from_truth(email)
    return {"items": items, "total": len(items)}


@app.get("/api/reports/financial")
def get_financial_report(as_of_date: str, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    entries = _derive_journal_entries_from_truth(email, as_of_date)
    report = report_service.generate_financial_statements(entries, as_of_date)
    return {"report": report, "as_of_date": as_of_date}


@app.get("/api/reports/tax")
def get_tax_report(as_of_date: str, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    entries = _derive_journal_entries_from_truth(email, as_of_date)
    report = report_service.generate_tax_reports(entries, as_of_date)
    return {"report": report, "as_of_date": as_of_date}


@app.post("/api/adjustments/request")
def create_adjustment(payload: AdjustmentPayload, email: str = Depends(get_current_email)) -> Dict[str, Any]:
    req = adjustment_service.create_adjustment_request(
        {
            "maker_id": email,
            "checker_id": payload.checker_id,
            "target_entry_id": payload.target_entry_id,
            "edit_mode": "adjustment_entry",
            "reason": payload.reason,
        }
    )
    now = datetime.utcnow().isoformat() + "Z"
    storage.add_adjustment_request(email, req["request_id"], req, now)
    return {"request": req}


@app.get("/api/adjustments")
def list_adjustments(email: str = Depends(get_current_email)) -> Dict[str, Any]:
    items = storage.list_adjustment_requests(email)
    return {"items": items, "total": len(items)}

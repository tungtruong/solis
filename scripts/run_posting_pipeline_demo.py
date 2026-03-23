import importlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = WORKSPACE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

tt133_mvp = importlib.import_module("tt133_mvp")
RuleStore = tt133_mvp.RuleStore
PostingEngine = tt133_mvp.PostingEngine

reporting_mod = importlib.import_module("tt133_mvp.reporting")
ReportService = reporting_mod.ReportService
storage_mod = importlib.import_module("tt133_mvp.storage")
AppStorage = storage_mod.AppStorage

DEMO_EMAIL = "demo@wssmeas.local"
MOCK_COMPANY_ID = "COMP-WS-001"

MOCK_COMPANY_PROFILE = {
    "company_id": MOCK_COMPANY_ID,
    "company_name": "Công ty TNHH WSSMEAS Mock",
    "tax_code": "0312345678",
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

EVENT_TYPE_LABELS = {
    "gop_von": "Góp vốn",
    "mua_dich_vu": "Mua dịch vụ",
    "mua_hang_dung_noi_bo": "Mua hàng dùng nội bộ",
    "mua_tscd": "Mua tài sản cố định",
    "ban_hang_dich_vu": "Bán hàng dịch vụ",
    "nop_thue": "Nộp thuế",
    "tam_ung": "Tạm ứng",
}

EVIDENCE_LIBRARY = {
    "purchase_invoice": [
        "ABC_invoice.pdf",
        "marketing_contract_signed.pdf",
        "vendor_tax_lookup.png",
    ],
    "sales_invoice": [
        "delivery_note_991.pdf",
        "appendix_scope_work.png",
        "bao_cao_tai_chinh_dummy.docx",
    ],
    "bank_statement": [
        "payment_order_772.pdf",
        "bao_cao_tai_chinh_q1_2026.xml",
        "bao_cao_tai_chinh_dummy.doc",
    ],
    "fixed_asset": [
        "device_invoice_041.pdf",
        "delivery_note_991.pdf",
        "vendor_tax_lookup.png",
    ],
}


def build_mock_case_list() -> List[Dict[str, Any]]:
    base_cases = [
        {
            "case_id": "CASE-2026-0001",
            "step": 1,
            "event_type": "gop_von",
            "source_id": "bank_statement",
            "event_date": "2026-03-01",
            "counterparty_name": "Chủ sở hữu công ty",
            "description": "Góp vốn đợt đầu để vận hành doanh nghiệp",
            "payment_channel": "bank",
            "amount": 300000000,
            "reference_no": "CAP-2026-0001",
            "debit_credit_flag": "credit",
        },
        {
            "case_id": "CASE-2026-0002",
            "step": 2,
            "event_type": "mua_dich_vu",
            "source_id": "purchase_invoice_xml",
            "event_date": "2026-03-06",
            "counterparty_name": "Bright Ads",
            "description": "Hợp đồng marketing 24 tháng",
            "invoice_no": "IN-2026-0101",
            "seller_tax_code": "0109999999",
            "goods_service_type": "service",
            "amount_untaxed": 12000000,
            "vat_amount": 1200000,
            "amount_total": 13200000,
            "service_term_months": 24,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "case_id": "CASE-2026-0003",
            "step": 3,
            "event_type": "mua_dich_vu",
            "source_id": "purchase_invoice_xml",
            "event_date": "2026-03-07",
            "counterparty_name": "Cloud Ops",
            "description": "Phí dịch vụ cloud 1 quý",
            "invoice_no": "IN-2026-0102",
            "seller_tax_code": "0109999998",
            "goods_service_type": "service",
            "amount_untaxed": 2000000,
            "vat_amount": 200000,
            "amount_total": 2200000,
            "service_term_months": 3,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "case_id": "CASE-2026-0004",
            "step": 4,
            "event_type": "mua_hang_dung_noi_bo",
            "source_id": "purchase_invoice_xml",
            "event_date": "2026-03-08",
            "counterparty_name": "Stationery Hub",
            "description": "Mua CCDC dùng nội bộ",
            "invoice_no": "IN-2026-0103",
            "seller_tax_code": "0109999997",
            "goods_service_type": "tools",
            "amount_untaxed": 5909091,
            "vat_amount": 590909,
            "amount_total": 6500000,
            "useful_life_months": 24,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "case_id": "CASE-2026-0005",
            "step": 5,
            "event_type": "mua_hang_dung_noi_bo",
            "source_id": "purchase_invoice_xml",
            "event_date": "2026-03-09",
            "counterparty_name": "Office Mart",
            "description": "Mua vật tư tiêu hao",
            "invoice_no": "IN-2026-0104",
            "seller_tax_code": "0109999996",
            "goods_service_type": "office_supply",
            "amount_untaxed": 1636364,
            "vat_amount": 163636,
            "amount_total": 1800000,
            "useful_life_months": 2,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "case_id": "CASE-2026-0006",
            "step": 6,
            "event_type": "mua_tscd",
            "source_id": "purchase_invoice_xml",
            "event_date": "2026-03-10",
            "counterparty_name": "Viet Infra Tech",
            "description": "Mua máy chủ lưu trữ",
            "invoice_no": "IN-2026-0105",
            "seller_tax_code": "0109999995",
            "goods_service_type": "fixed_asset",
            "amount_untaxed": 180000000,
            "vat_amount": 18000000,
            "amount_total": 198000000,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "case_id": "CASE-2026-0007",
            "step": 7,
            "event_type": "ban_hang_dich_vu",
            "source_id": "sales_invoice_xml",
            "event_date": "2026-03-12",
            "counterparty_name": "An Phuc Trading",
            "description": "Dịch vụ triển khai hệ thống",
            "invoice_no": "OUT-2026-0301",
            "buyer_tax_code": "0310001111",
            "amount_untaxed": 25000000,
            "vat_amount": 2500000,
            "amount_total": 27500000,
            "receipt_account": "131",
            "has_vat": True,
            "payment_status": "unpaid",
        },
        {
            "case_id": "CASE-2026-0008",
            "step": 8,
            "event_type": "nop_thue",
            "source_id": "bank_statement",
            "event_date": "2026-03-20",
            "counterparty_name": "Kho bạc Nhà nước",
            "description": "Nộp thuế GTGT tháng 03/2026",
            "amount": 3500000,
            "reference_no": "STMT-2026-0301",
            "debit_credit_flag": "debit",
            "tax_payable_account": "3331",
            "payment_channel": "bank",
        },
        {
            "case_id": "CASE-2026-0009",
            "step": 9,
            "event_type": "tam_ung",
            "source_id": "bank_statement",
            "event_date": "2026-03-21",
            "counterparty_name": "Nhân viên Nguyễn A",
            "description": "Tạm ứng công tác phí",
            "amount": 5000000,
            "reference_no": "STMT-2026-0302",
            "debit_credit_flag": "debit",
            "payment_channel": "bank",
            "person_name": "Nguyễn A",
        },
    ]

    return base_cases + build_additional_case_list(start_step=len(base_cases) + 1, count=30)


def build_additional_case_list(start_step: int, count: int) -> List[Dict[str, Any]]:
    templates = [
        {
            "event_type": "mua_dich_vu",
            "source_id": "purchase_invoice_xml",
            "description": "Thuê dịch vụ vận hành hệ thống theo tháng",
            "counterparty_name": "Công ty Vận hành Sao Việt",
            "goods_service_type": "service",
            "amount_untaxed": 4800000,
            "vat_amount": 480000,
            "service_term_months": 1,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "event_type": "mua_hang_dung_noi_bo",
            "source_id": "purchase_invoice_xml",
            "description": "Mua vật tư văn phòng định kỳ",
            "counterparty_name": "Siêu thị Văn phòng phẩm Hà Nội",
            "goods_service_type": "office_supply",
            "amount_untaxed": 2100000,
            "vat_amount": 210000,
            "useful_life_months": 1,
            "payment_account": "331",
            "has_vat": True,
        },
        {
            "event_type": "ban_hang_dich_vu",
            "source_id": "sales_invoice_xml",
            "description": "Cung cấp gói dịch vụ tư vấn triển khai",
            "counterparty_name": "Công ty Cổ phần Minh Long",
            "amount_untaxed": 32000000,
            "vat_amount": 3200000,
            "receipt_account": "131",
            "has_vat": True,
            "payment_status": "unpaid",
        },
        {
            "event_type": "nop_thue",
            "source_id": "bank_statement",
            "description": "Nộp thuế GTGT theo tờ khai kỳ gần nhất",
            "counterparty_name": "Kho bạc Nhà nước",
            "amount": 4200000,
            "debit_credit_flag": "debit",
            "tax_payable_account": "3331",
            "payment_channel": "bank",
        },
        {
            "event_type": "tam_ung",
            "source_id": "bank_statement",
            "description": "Tạm ứng chi phí công tác nội bộ",
            "counterparty_name": "Nhân viên phụ trách dự án",
            "amount": 3500000,
            "debit_credit_flag": "debit",
            "payment_channel": "bank",
            "person_name": "Lê Quang Anh",
        },
        {
            "event_type": "gop_von",
            "source_id": "bank_statement",
            "description": "Bổ sung vốn lưu động đợt tiếp theo",
            "counterparty_name": "Thành viên góp vốn",
            "amount": 150000000,
            "debit_credit_flag": "credit",
            "payment_channel": "bank",
        },
        {
            "event_type": "mua_tscd",
            "source_id": "purchase_invoice_xml",
            "description": "Mua mới thiết bị phục vụ vận hành",
            "counterparty_name": "Công ty Thiết bị Kỹ thuật Việt",
            "goods_service_type": "fixed_asset",
            "amount_untaxed": 95000000,
            "vat_amount": 9500000,
            "payment_account": "331",
            "has_vat": True,
        },
    ]

    generated_cases: List[Dict[str, Any]] = []
    start_date = date(2026, 3, 22)

    for offset in range(count):
        step = start_step + offset
        running_no = step
        template = templates[offset % len(templates)]
        event_date = (start_date + timedelta(days=offset)).isoformat()

        case_item: Dict[str, Any] = {
            "case_id": f"CASE-2026-{running_no:04d}",
            "step": step,
            "event_type": template["event_type"],
            "source_id": template["source_id"],
            "event_date": event_date,
            "counterparty_name": str(template.get("counterparty_name", "Đối tác")),
            "description": f"{template['description']} - đợt {offset + 1}",
        }

        if template["source_id"] == "bank_statement":
            case_item.update(
                {
                    "amount": int(template.get("amount", 0)) + (offset * 150000),
                    "reference_no": f"STMT-2026-{running_no:04d}",
                    "debit_credit_flag": template.get("debit_credit_flag", "debit"),
                }
            )
            for key in ["tax_payable_account", "payment_channel", "person_name"]:
                if key in template:
                    case_item[key] = template[key]
        elif template["source_id"] == "purchase_invoice_xml":
            untaxed = int(template.get("amount_untaxed", 0)) + (offset * 120000)
            vat_amount = int(template.get("vat_amount", 0)) + (offset * 12000)
            case_item.update(
                {
                    "invoice_no": f"IN-2026-{running_no:04d}",
                    "seller_tax_code": f"01{(90000000 + running_no):08d}",
                    "goods_service_type": template.get("goods_service_type", "service"),
                    "amount_untaxed": untaxed,
                    "vat_amount": vat_amount,
                    "amount_total": untaxed + vat_amount,
                }
            )
            for key in ["service_term_months", "useful_life_months", "payment_account", "has_vat"]:
                if key in template:
                    case_item[key] = template[key]
        else:
            untaxed = int(template.get("amount_untaxed", 0)) + (offset * 180000)
            vat_amount = int(template.get("vat_amount", 0)) + (offset * 18000)
            case_item.update(
                {
                    "invoice_no": f"OUT-2026-{running_no:04d}",
                    "buyer_tax_code": f"03{(10000000 + running_no):08d}",
                    "amount_untaxed": untaxed,
                    "vat_amount": vat_amount,
                    "amount_total": untaxed + vat_amount,
                    "payment_status": template.get("payment_status", "unpaid"),
                }
            )
            for key in ["receipt_account", "has_vat"]:
                if key in template:
                    case_item[key] = template[key]

        generated_cases.append(case_item)

    return generated_cases


def build_evidence_files(case_item: Dict[str, Any]) -> List[str]:
    source_id = str(case_item.get("source_id") or "")
    event_type = str(case_item.get("event_type") or "")

    if event_type == "mua_tscd":
        library_key = "fixed_asset"
    elif source_id == "purchase_invoice_xml":
        library_key = "purchase_invoice"
    elif source_id == "sales_invoice_xml":
        library_key = "sales_invoice"
    else:
        library_key = "bank_statement"

    base_files = EVIDENCE_LIBRARY[library_key]
    return [
        base_files[0],
        base_files[1],
        base_files[2],
        "bao_cao_tai_chinh_q1_2026.xml",
    ]


def map_case_to_event(case_item: Dict[str, Any]) -> Dict[str, Any]:
    event_date = case_item.get("event_date")
    base_event: Dict[str, Any] = {
        "source_id": case_item["source_id"],
        "event_type": case_item["event_type"],
        "counterparty_name": case_item.get("counterparty_name"),
        "description": case_item.get("description"),
    }

    if case_item["source_id"] == "bank_statement":
        base_event.update(
            {
                "statement_date": event_date,
                "amount": case_item.get("amount", 0),
                "reference_no": case_item.get("reference_no"),
                "debit_credit_flag": case_item.get("debit_credit_flag", "debit"),
            }
        )
        optional_fields = ["tax_payable_account", "payment_channel", "person_name"]
    elif case_item["source_id"] == "purchase_invoice_xml":
        base_event.update(
            {
                "invoice_no": case_item.get("invoice_no"),
                "issue_date": event_date,
                "seller_tax_code": case_item.get("seller_tax_code"),
                "goods_service_type": case_item.get("goods_service_type"),
                "amount_untaxed": case_item.get("amount_untaxed", 0),
                "vat_amount": case_item.get("vat_amount", 0),
                "amount_total": case_item.get("amount_total", 0),
            }
        )
        optional_fields = ["service_term_months", "useful_life_months", "payment_account", "has_vat"]
    else:
        base_event.update(
            {
                "invoice_no": case_item.get("invoice_no"),
                "issue_date": event_date,
                "buyer_tax_code": case_item.get("buyer_tax_code"),
                "amount_untaxed": case_item.get("amount_untaxed", 0),
                "vat_amount": case_item.get("vat_amount", 0),
                "amount_total": case_item.get("amount_total", 0),
                "payment_status": case_item.get("payment_status", "unpaid"),
            }
        )
        optional_fields = ["receipt_account", "has_vat"]

    # Normalize fields used by posting method expressions.
    if "amount_total" in base_event:
        base_event["total_amount"] = base_event["amount_total"]
    if "amount_untaxed" in base_event:
        base_event["untaxed_amount"] = base_event["amount_untaxed"]
        base_event["amount"] = base_event["amount_untaxed"] + base_event.get("vat_amount", 0)

    for field in optional_fields:
        if field in case_item:
            base_event[field] = case_item[field]

    return base_event


def build_ui_case_items(case_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    status_cycle = [
        ("hoan_tat", "Hoàn tất"),
        ("dang_xu_ly", "Đang xử lý"),
        ("cho_duyet", "Chờ duyệt"),
        ("moi", "Mới"),
    ]

    ui_items: List[Dict[str, Any]] = []
    for idx, case_item in enumerate(case_list):
        status, status_label = status_cycle[idx % len(status_cycle)]
        amount = float(case_item.get("amount_total") or case_item.get("amount") or 0)
        event_type = str(case_item.get("event_type") or "")
        event_label = EVENT_TYPE_LABELS.get(event_type, event_type.replace("_", " ").capitalize())
        title = f"{event_label} - {case_item.get('description', '')}"
        event_date = case_item.get("event_date", "2026-03-31")
        timeline = [
            {
                "id": f"{case_item['case_id']}-a1",
                "kind": "analysis",
                "title": "Phân tích AI",
                "body": f"Đã đối chiếu dữ liệu nguồn cho {case_item.get('event_type')} từ {case_item.get('source_id')}.",
                "time": "09:10",
            },
            {
                "id": f"{case_item['case_id']}-e1",
                "kind": "event",
                "title": "Sự kiện kinh tế",
                "body": case_item.get("description", "Đã ghi nhận nghiệp vụ theo rule."),
                "time": "09:12",
            },
            {
                "id": f"{case_item['case_id']}-e2",
                "kind": "event",
                "title": "Định tuyến posting rule",
                "body": f"Ánh xạ event_type={case_item.get('event_type')} theo TT133 MVP rule index.",
                "time": "09:14",
            },
        ]
        evidence = build_evidence_files(case_item)
        reasoning = [
            f"Nghiệp vụ được nhận diện là {event_label.lower()} theo nguồn {case_item.get('source_id')}.",
            "Hệ thống chọn phương pháp định khoản theo rule-file, không hardcode trong UI.",
        ]

        ui_items.append(
            {
                "id": case_item["case_id"],
                "code": case_item["case_id"].replace("CASE", "CS"),
                "title": title,
                "partner": case_item.get("counterparty_name", "Đối tác"),
                "amount": f"{amount:,.0f} VND",
                "updatedAt": event_date,
                "status": status,
                "statusLabel": status_label,
                "event_type": case_item.get("event_type"),
                "source_id": case_item.get("source_id"),
                "reference_no": case_item.get("reference_no") or case_item.get("invoice_no"),
                "timeline": timeline,
                "evidence": evidence,
                "reasoning": reasoning,
            }
        )

    return ui_items


def build_ui_content() -> Dict[str, Any]:
    return {
        "dashboard": {
            "cards": [
                {
                    "title": "Vị thế tiền mặt",
                    "value": "1,842,000,000 VND",
                    "note": "+8.2% so với tuần trước",
                },
                {
                    "title": "Công nợ phải trả mở",
                    "value": "624,000,000 VND",
                    "note": "14 khoản chờ thanh toán",
                },
                {
                    "title": "Công nợ phải thu mở",
                    "value": "1,120,000,000 VND",
                    "note": "7 khách hàng quá hạn dưới 15 ngày",
                },
            ],
            "companion": {
                "title": "Màn phụ Bảng điều khiển",
                "subtitle": "Chi tiết bổ trợ cho KPI và cảnh báo tài chính.",
                "highlights": [
                    "Thời gian duy trì dòng tiền dự kiến: 7.8 tháng với tốc độ chi hiện tại.",
                    "Top 3 khoản chi tăng mạnh trong 14 ngày qua: tiếp thị, điện toán đám mây, vận hành.",
                    "Có 2 nhà cung cấp cần ưu tiên thanh toán trong 3 ngày tới.",
                ],
                "actions": ["Mở chi tiết dòng tiền", "Xem công nợ đến hạn", "Tạo cảnh báo chi phí"],
            },
        },
        "reports": {
            "rows": [
                {
                    "title": "Báo cáo kết quả kinh doanh",
                    "text": "Doanh thu thuần tháng 03 tăng 12.4%.",
                },
                {
                    "title": "Bảng cân đối kế toán",
                    "text": "Tài sản ngắn hạn đang chiếm 61% tổng tài sản.",
                },
                {
                    "title": "Báo cáo lưu chuyển tiền tệ",
                    "text": "Dòng tiền vận hành dương, cần tối ưu dòng tiền đầu tư.",
                },
            ],
            "companion": {
                "title": "Màn phụ Báo cáo",
                "subtitle": "Gợi ý đối soát và các điểm cần chú ý cho báo cáo.",
                "highlights": [
                    "Báo cáo lãi lỗ: biên lợi nhuận gộp giảm 1.9% so với tháng trước.",
                    "Bảng cân đối: khoản phải thu trên 60 ngày đang tăng.",
                    "Lưu chuyển tiền tệ: dòng tiền đầu tư âm do mua sắm thiết bị.",
                ],
                "actions": ["Xuất báo cáo lãi lỗ dạng PDF", "Mở bảng đối chiếu công nợ", "So sánh theo quý"],
            },
        },
        "settings": {
            "mode_toggle": {
                "title": "Chế độ kế toán nâng cao",
                "text": "Cho phép hạch toán chuyên sâu với bút toán nhiều lớp, phân bổ tự động và kiểm soát ràng buộc nâng cao.",
                "cta_on": "Bật Advanced Mode",
                "cta_off": "Tắt Advanced Mode",
            },
            "rows": [
                {
                    "title": "Chính sách kế toán",
                    "text": "Cấu hình phương pháp hạch toán và ánh xạ tài khoản mặc định.",
                },
                {
                    "title": "Vai trò và phân quyền",
                    "text": "Quản lý quyền xem báo cáo, duyệt bút toán và truy cập dữ liệu nhạy cảm.",
                },
                {
                    "title": "Hệ thống tài khoản",
                    "text": "Thiết lập danh mục tài khoản theo TT133 và đồng bộ với bộ máy AI.",
                },
            ],
            "companion": {
                "title": "Màn phụ Cài đặt",
                "subtitle": "Hướng dẫn thao tác cấu hình cho hệ thống kế toán AI.",
                "highlights": [
                    "Chính sách hạch toán đang đặt theo TT133 phiên bản 2026.",
                    "Còn 2 vai trò chưa phân quyền phê duyệt bút toán.",
                    "Hệ thống tài khoản có 4 tài khoản mới chưa ánh xạ với AI.",
                ],
                "actions": ["Mở phân quyền người dùng", "Cập nhật tài khoản ánh xạ AI", "Kiểm tra nhật ký kiểm toán"],
            },
        },
    }


def seed_mock_identities(storage: AppStorage, now: str) -> None:
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

        company_profile = {
            "company_name": MOCK_COMPANY_PROFILE["company_name"],
            "tax_code": MOCK_COMPANY_PROFILE["tax_code"],
            "address": MOCK_COMPANY_PROFILE["address"],
            "fiscal_year_start": MOCK_COMPANY_PROFILE["fiscal_year_start"],
            "tax_declaration_cycle": MOCK_COMPANY_PROFILE["tax_declaration_cycle"],
            "default_bank_account": MOCK_COMPANY_PROFILE["default_bank_account"],
            "accountant_email": "accountant@wssmeas.local",
            "company_id": MOCK_COMPANY_ID,
            "user_role": user.get("role"),
        }
        storage.upsert_company_profile(email, company_profile, now)


def main():
    store = RuleStore.from_workspace(str(WORKSPACE_ROOT))
    posting_engine = PostingEngine(store)
    report_service = ReportService(store)
    storage = AppStorage.from_workspace(str(WORKSPACE_ROOT))
    storage.init_db()

    as_of = date(2026, 3, 31).isoformat()
    case_list = sorted(build_mock_case_list(), key=lambda item: item.get("step", 999))
    events = [map_case_to_event(case_item) for case_item in case_list]
    ui_case_items = build_ui_case_items(case_list)
    ui_content = build_ui_content()
    now = datetime.utcnow().isoformat() + "Z"

    seed_mock_identities(storage, now)

    accepted_entries = []
    rejected_events = []

    for event in events:
        result = posting_engine.post(event)
        if result.accepted and result.journal_entry:
            accepted_entries.append(result.journal_entry)
        else:
            rejected_events.append(
                {
                    "event_type": event.get("event_type"),
                    "source_id": event.get("source_id"),
                    "reason": result.reason,
                }
            )

    storage.replace_case_items(DEMO_EMAIL, ui_case_items, now)
    events_with_case = []
    for case_item, event in zip(case_list, events):
        event_payload = dict(event)
        event_payload["case_id"] = str(case_item.get("case_id") or "")
        event_payload["event_date"] = str(
            event_payload.get("statement_date")
            or event_payload.get("issue_date")
            or case_item.get("event_date")
            or ""
        )
        events_with_case.append(event_payload)
    storage.replace_case_events(DEMO_EMAIL, events_with_case, now)
    storage.upsert_opening_balances(DEMO_EMAIL, {"lines": []}, now)
    storage.upsert_ui_content(DEMO_EMAIL, "main_panels", ui_content, now)
    storage.clear_journal_entries(DEMO_EMAIL)
    for entry in accepted_entries:
        storage.add_journal_entry(
            DEMO_EMAIL,
            entry["entry_id"],
            entry.get("event_type", "unknown"),
            entry,
            now,
        )

    output = {
        "posting_rule_basis": {
            "router": store.posting_router(),
            "classification_rules": store.classification_rules(),
        },
        "demo_email": DEMO_EMAIL,
        "mock_case_list": case_list,
        "ui_case_items": ui_case_items,
        "input_summary": {
            "total_events": len(events),
            "accepted_events": len(accepted_entries),
            "rejected_events": len(rejected_events),
        },
        "rejected_events": rejected_events,
        "journal_entries": accepted_entries,
        "report_request": report_service.build_request(
            report_code="BCTC_BANG_CAN_DOI_KE_TOAN",
            frequency="month",
            as_of_date=as_of,
        ),
        "financial_statements": report_service.generate_financial_statements(accepted_entries, as_of),
        "tax_reports": report_service.generate_tax_reports(accepted_entries, as_of),
    }

    output_path = WORKSPACE_ROOT / "data" / "mock_pipeline_tt133_output.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Pipeline completed")
    print(f"- total_events: {output['input_summary']['total_events']}")
    print(f"- accepted_events: {output['input_summary']['accepted_events']}")
    print(f"- rejected_events: {output['input_summary']['rejected_events']}")
    print(f"- output_file: {output_path}")
    print("\nFinancial statements summary")
    print(json.dumps(output["financial_statements"], ensure_ascii=False, indent=2))
    print("\nTax reports summary")
    print(json.dumps(output["tax_reports"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

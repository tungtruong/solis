# Implementation Plan MVP TT133 (Rule-File First, No Manual Entry)

Mục tiêu: triển khai MVP nhanh nhất nhưng vẫn giữ nguyên DNA kiến trúc của bản gốc: Event -> Rule -> Ledger, ledger bất biến, rule cấu hình dữ liệu, không hardcode định khoản.

## 1) Nguyên tắc cốt lõi giữ nguyên
1. Kiến trúc 3 tầng bắt buộc:
- Tầng 1: Economic Events (nguồn sự thật)
- Tầng 2: Rule Engine (mapping theo cấu hình)
- Tầng 3: General Ledger (Nợ = Có, append-only)
2. Không cho AI quyết định hạch toán. AI/OCR (nếu có) chỉ hỗ trợ bóc tách dữ liệu đầu vào.
3. Không hardcode tài khoản hay bút toán trong code nghiệp vụ. Mọi định khoản nằm trong file rule.
4. Ledger bất biến: không update/delete bút toán đã ghi; điều chỉnh bằng bút toán đảo.

## 2) Phạm vi MVP mới (đã cập nhật)
1. Không nhập liệu thủ công.
2. Chỉ chấp nhận 3 nguồn dữ liệu đầu vào:
- Hóa đơn XML đầu ra của chính công ty (sales invoice XML)
- Hóa đơn XML đầu vào của nhà cung cấp (purchase invoice XML)
- Sao kê ngân hàng (bank statement)
3. Một doanh nghiệp, một tiền tệ VND, local-first.
4. Một sổ kế toán hoạt động (TT133) cho MVP.

## 3) Chuẩn hóa ingestion theo nguồn dữ liệu
1. XML đầu ra công ty:
- Parse các trường bắt buộc: invoice_no, issue_date, buyer, amount_untaxed, vat_amount, amount_total, payment_status.
- Sinh economic events nhóm bán hàng dịch vụ và thu tiền liên quan.
2. XML đầu vào nhà cung cấp:
- Parse các trường bắt buộc: invoice_no, issue_date, seller, amount_untaxed, vat_amount, amount_total, goods_service_type.
- Sinh economic events nhóm mua hàng dùng nội bộ, mua dịch vụ, mua TSCĐ theo phân loại.
3. Sao kê ngân hàng:
- Parse date, amount, debit_credit_flag, counterparty, description, reference_no.
- Sinh economic events nhóm thu/chi tiền ngân hàng (nộp tiền, rút tiền, nộp thuế, hoàn ứng bằng tiền, thanh toán công nợ).
4. Reject sớm file không đúng schema hoặc thiếu trường bắt buộc.

## 4) Danh mục event MVP (13 event)
1. góp_vốn
2. rút_tiền
3. tạm_ứng
4. nộp_tiền
5. hoàn_ứng
6. bán_hàng_dịch_vụ
7. mua_hàng_dùng_nội_bộ
8. mua_dịch_vụ
9. mua_TSCĐ
10. khấu_hao
11. nộp_thuế
12. phân_bổ_CCDC
13. phân_bổ_chi_phí_trả_trước

## 5) Rule files (mapping theo event_type)
1. event_rule_map.json:
- Ánh xạ event_type -> rule_id.
2. posting_templates.json:
- Định nghĩa dòng Nợ/Có theo rule_id.
3. classification_rules.json:
- CCDC nếu amount > 3.000.000 và useful_life_months > 12.
- Chi phí trả trước dịch vụ nếu amount > 3.000.000 và service_term_months > 12.
4. validation_rules.json:
- Ràng buộc dữ liệu, ví dụ hoàn_ứng chỉ bằng tiền (cash/bank).

## 6) Quy tắc nghiệp vụ đã chốt
1. Hoàn ứng chỉ bằng tiền: Nợ 111/112, Có 141.
2. Mua hàng dùng nội bộ:
- Nếu đạt ngưỡng CCDC: ghi nhận theo nhánh CCDC.
- Nếu không đạt ngưỡng: ghi nhận thẳng chi phí 642.
3. Mua dịch vụ:
- Nếu đạt ngưỡng trả trước: vào 242 rồi phân bổ.
- Nếu không đạt ngưỡng: ghi nhận thẳng 642.
4. Phân bổ:
- phân_bổ_CCDC và phân_bổ_chi_phí_trả_trước đều kết chuyển dần về 642 theo rule định kỳ.

## 7) Posting engine data-driven
1. Nhận economic event đã chuẩn hóa từ pipeline ingestion.
2. Lookup rule_id qua event_rule_map.
3. Evaluate classification_rules để chọn nhánh template.
4. Render journal lines từ posting_templates.
5. Validate theo validation_rules.
6. Ghi sổ nếu cân Nợ/Có.

## 8) Vận hành MVP
1. Lưu trữ SQLite local.
2. Lưu liên kết file nguồn (XML/sao kê) với event_id và journal_id để truy vết.
3. Chức năng khóa kỳ cơ bản để ngăn sửa dữ liệu kỳ đã chốt.
4. Báo cáo kế toán lõi: nhật ký chung, sổ cái, cân đối phát sinh, export CSV/PDF.

## 9) Đầu ra báo cáo bắt buộc (mục tiêu cuối)
1. Kết xuất đủ bộ BCTC theo TT133:
- Bảng cân đối kế toán.
- Báo cáo kết quả hoạt động kinh doanh.
- Báo cáo lưu chuyển tiền tệ.
- Thuyết minh báo cáo tài chính.
2. Kết xuất báo cáo thuế:
- Theo kỳ: tháng, quý, năm.
- Theo thời điểm: chốt số liệu tới ngày bất kỳ (as-of date).
3. Mọi báo cáo phải truy vết ngược được về journal entry và chứng từ nguồn XML/sao kê.

## 10) Kế hoạch triển khai nhanh theo pha
1. Pha 1: Data ingestion
- Parser XML đầu ra, XML đầu vào, parser sao kê ngân hàng.
- Chuẩn hóa về economic event schema.
2. Pha 2: Rule engine + ledger
- Hoàn thiện 4 file rule.
- Hoàn thiện posting engine và ghi sổ bất biến.
3. Pha 3: Đối soát và báo cáo
- Liên kết chứng từ nguồn.
- Báo cáo kế toán lõi, khóa kỳ, UAT.
4. Pha 4: Financial & Tax Reporting
- Build bộ BCTC TT133 đủ 4 báo cáo.
- Build báo cáo thuế theo kỳ và theo thời điểm.
5. Pha 5: Advanced Feature
- Cho phép sửa bút toán bằng tay sau khi hạch toán nhưng bắt buộc qua kiểm soát.
- Cơ chế kiểm soát tối thiểu: maker-checker, lưu vết thay đổi, lý do chỉnh sửa bắt buộc, auto tạo bút toán điều chỉnh/đảo thay vì sửa trực tiếp dòng đã khóa.

## 10.1) Trạng thái thực thi hiện tại
1. Đã bắt đầu implementation theo hướng rule-file first.
2. Đã tạo xong bộ artifact TT133 MVP tại data/regulations:
- tt133_mvp_2026_event_rule_index.json
- tt133_mvp_2026_posting_methods.json
- tt133_mvp_2026_validation_rules.json
- tt133_mvp_2026_classification_rules.json
- tt133_mvp_2026_ingestion_sources.json
- tt133_mvp_2026_posting_router.json
- tt133_mvp_2026_auto_engine_policy.json
- tt133_mvp_2026_report_catalog.json
- tt133_mvp_2026_advanced_feature_controls.json
3. Toàn bộ file JSON trên đã parse hợp lệ.
4. Đã tạo code scaffold engine:
- src/tt133_mvp/rule_store.py
- src/tt133_mvp/ingestion.py
- src/tt133_mvp/posting_engine.py
- src/tt133_mvp/reporting.py
- src/tt133_mvp/advanced_controls.py
- scripts/run_mvp_demo.py
- scripts/run_advanced_demo.py
5. Smoke test pass:
- scripts/run_mvp_demo.py đọc rule và sinh bút toán cân đối thành công.
- scripts/run_advanced_demo.py sinh report request và adjustment request theo control policy thành công.
6. Đã có scaffold kết xuất dữ liệu báo cáo từ journal entries:
- Financial statements: BCDKT, KQHDKD, LCTT, thuyết minh (mức MVP scaffold).
- Tax reports: GTGT, TNCN, TNDN theo as-of date (mức MVP scaffold).

## 11) Tiêu chí nghiệm thu MVP
1. Không còn luồng nhập liệu thủ công.
2. Chỉ nhận đúng 3 nguồn file đầu vào như phạm vi.
3. 13/13 event map rule thành công.
4. Không có hardcode định khoản trong code.
5. 100% journal entries cân Nợ/Có.
6. Có thể truy ngược từ dòng sổ cái về XML/sao kê gốc.
7. Kết xuất được đủ bộ BCTC TT133.
8. Kết xuất được báo cáo thuế theo kỳ và theo thời điểm.

## 12) Advanced Feature: Sửa tay có kiểm soát
1. Cho phép tạo yêu cầu chỉnh sửa bút toán sau hạch toán để xử lý nghiệp vụ ngoại lệ.
2. Không cho sửa trực tiếp entry đã khóa; hệ thống bắt buộc sinh adjustment/reversal entry.
3. Bắt buộc quy trình kiểm soát 2 bước:
- Bước 1: Người lập (maker) tạo đề nghị chỉnh sửa kèm lý do và chứng từ bổ sung.
- Bước 2: Người duyệt (checker) phê duyệt trước khi ghi nhận điều chỉnh vào sổ.
4. Audit trail bắt buộc: ai sửa, sửa khi nào, lý do gì, trước/sau thay đổi.

## 13) Rủi ro và xử lý nhanh
1. Rủi ro định dạng sao kê khác nhau giữa ngân hàng:
- MVP: hỗ trợ trước 1-2 mẫu sao kê chuẩn, thêm adapter theo ngân hàng ở pha sau.
2. Rủi ro XML không đồng nhất:
- MVP: schema validation cứng, file lỗi đưa vào hàng chờ reject để xử lý lại.
3. Rủi ro thiếu mapping rule cho event mới:
- MVP: strict startup, thiếu mapping thì không cho chạy post.
4. Rủi ro chỉnh sửa tay gây sai lệch:
- Advanced Feature bắt buộc maker-checker + immutable adjustment để giữ toàn vẹn sổ sách.

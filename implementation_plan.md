# Kiến trúc Hệ thống Kế toán Tự động (Automated Accounting System)

Hệ thống được thiết kế theo hướng **Domain-Driven Design (DDD)** và **Event-Driven Architecture**, tách biệt hoàn toàn giữa lõi kế toán (Core Ledger) và các nghiệp vụ AI/Ngoại vi. 

## 1. Kiến trúc Tổng thể (System Architecture)

Hệ thống chia làm 4 lớp (Layers) chính để đảm bảo mở rộng không giới hạn:
1. **Client / UI Layer**: Giao diện (Web/Desktop) cho Kế toán viên và CFO Dashboard.
2. **AI & NLP Layer (Cổng giao tiếp)**: Phiên dịch yêu cầu ngôn ngữ tự nhiên thành dữ liệu có cấu trúc.
3. **Business & Rule Layer**: Tiếp nhận dữ liệu, đối chiếu thông tư và tạo bút toán nháp. Các module con (Payroll, Inventory, Costing) nằm ở đây.
4. **Core Ledger (Lõi Kế toán kép)**: Sổ cái bất biến, chỉ nhận các bút toán chuẩn đã cân bằng (Nợ = Có). 

---

## 2. Giải pháp cho từng bài toán phức tạp

### A. Xử lý Bút toán định kỳ, phân bổ, kết chuyển
- Không dùng AI cho các tác vụ mang tính chu kỳ và công thức định sẵn.
- Sử dụng **Workflow Engine (như Celery, Temporal hoặc Cronjobs)**.
- **Ví dụ Trích khấu hao (TK 214)**: Module Tài sản cố định (Fixed Assets) sẽ tự động chạy vào cuối tháng, tính toán theo đường thẳng/số dư giảm dần, và phát sinh một đối tượng `JournalEntryDraft`. Kế toán viên chỉ cần lướt xem và duyệt (Approve) là hệ thống sẽ tự động ghi vào Sổ cái.
- **Bút toán điều chỉnh**: Thiết kế tính năng "Version" cho chứng từ. Hệ thống không cho phép xóa/sửa bút toán của kỳ đã khóa, mà bắt buộc sinh ra bút toán đảo/điều chỉnh theo đúng luật định.

### B. Mở rộng Module (Costing, Payroll) & Luật Kế toán
- **Kiến trúc Modular**: Lõi Kế toán (Core Ledger) là một "hộp đen" cực kỳ cứng nhắc (chỉ biết Nợ, Có, Tài khoản, Số tiền, Dimension quản lý). 
- **Payroll/Costing là các Micro-services độc lập**: Khi module Payroll chấm công và tính xong bảng lương, nó chỉ gọi một API duy nhất vào lõi hệ thống: `POST /api/ledger/entries` kèm theo chứng từ (Bảng lương mẫu). 
- **Decoupled Rule Engine**: Các thông tư, chuẩn mực (VAS 200, 133, luật thuế mới) được lưu cấu hình trong Database dưới dạng JSON/Rules, **tuyệt đối không hard-code đoạn if/else vào mã nguồn gốc**. Khi cơ quan Thuế thay đổi thông tư, ta chỉ cần update thiết lập `Accounting_Rules` mà không cần đập đi xây lại phần mềm.

### C. Đảm bảo Kế toán "Live" (Real-time) nhưng vẫn Tuân thủ (Compliance)
Doanh nghiệp luôn cần 2 góc nhìn, hệ thống sẽ tổ chức cơ sở dữ liệu để phục vụ cả hai một cách mượt mà:
- **Management Book (Sổ quản trị)**: Số liệu Live, ghi nhận ngay lập tức mọi giao dịch (kể cả chưa có hóa đơn đỏ, hóa đơn chứng từ mới nháp xong), phục vụ riêng cho CFO và Giám đốc ra quyết định tức thời.
- **Tax Book (Sổ tài chính/Thuế)**: Chỉ ghi nhận những giao dịch đã được hệ thống "Lock" (Khóa sổ) kèm theo đầy đủ hồ sơ, hóa đơn điện tử hợp lệ (có chữ ký số).

### D. Kiến trúc AI "Siêu nhẹ" & Nhiệm vụ của mô hình ngôn ngữ (LLM Roles)
Để chạy trên các máy tính kế toán phổ thông (không cần GPU 3080 mạnh mẽ), hệ thống AI tuyệt đối không được dùng "end-to-end" để tự suy luận và tự tạo Nợ/Có. 
**Quy trình Phân rã AI (Hybrid Pipeline)**:
1. **Extraction (Trích xuất - Dùng Local AI siêu nhỏ)**: Thay vì Qwen-7B quá nặng, ta dùng các loại mô hình chỉ từ **0.5B đến 1.5B tham số** (như Qwen2.5-1.5B, hoặc mô hình NLP chuyên biệt rút trích thực thể PhoNLP/CRF). Các mô hình này có thể chạy mượt trên CPU RAM 4-8GB. Nó chỉ có một nhiệm vụ: Rút trích `[Ngày tháng]`, `[Số tiền]`, `[Tên đối tượng]`, `[Nhãn nội dung]`.
2. **Rule-Mapping (Không dùng AI)**: Đầu ra của mô hình được đưa vào Rule Engine (Code Logic truyền thống). Code sẽ tìm kiếm trong CSDL: "Nhãn: Chi phí tiếp khách" -> Đối chiếu luật: Tài khoản 642 -> Đưa ra hạch toán chính xác 100% kèm link trích dẫn điều luật. Không có rủi ro "ảo giác" (Hallucination) của AI ở đây.
3. **CFO AI Agent (Hỏi đáp Live)**: Dùng công nghệ **Text-to-SQL**. Người dùng hỏi "Doanh thu tháng này của sản phẩm A là bao nhiêu?". AI sẽ dịch câu hỏi này thành lệnh SQL `SELECT SUM(amount) FROM ledger WHERE account LIKE '511%' AND product='A'` chạy trực tiếp vào CSDL, đảm bảo số liệu trả về là thật từ Database chứ AI không hề tự nghĩ ra số liệu. Lúc này, AI đóng vai trò như một phiên dịch viên cơ sở dữ liệu.

### E. Chiến lược Cập nhật (Offline Updates Strategy)
Một hệ thống lưu trữ dữ liệu tại máy (Local-first) vẫn có thể duy trì sự bảo mật và cập nhật mới nhất thông qua cơ chế Delta Updates:
- **Hot-Reload Luật Kế Toán (Rule Base):** Điểm tự hào nhất của kiến trúc Rule-Engine. Khi Bộ Tài Chính ra chính sách mới, chúng ta phát hành một file Payload JSON (chỉ vài Kilobytes). Phần mềm có thể tự tải ngầm khi có Internet, hoặc kế toán tải file này từ nhà, bỏ vào USB mang tới công ty (không có mạng Internet/Air-gapped) rồi bấm nút **"Import Luật Mới"**.
- **Tính năng Versioning không gãy đổ báo cáo:** Khi Import Luật Mới (ví dụ áp dụng từ T1/2026), Rule Database sẽ cập nhật cột `valid_to` của luật cũ thành 31/12/2025. Báo cáo năm 2025 in ra vẫn giữ đúng luật cũ, trong khi phiếu chi năm 2026 sẽ tự động chạy theo luật mới.
- **Cập nhật Mô hình AI xưng (Weight Updates):** Vì AI (Qwen cỡ siêu nhỏ) của bạn chỉ làm việc `Bóc tách từ ngữ tiếng Việt` chứ không phải nhớ Luật, nên AI rất hiếm khi bị "lỗi thời". Có thể 1-2 năm mới phải tải lại mô hình một lần qua bộ cài Installer (.exe).

---

## 3. Kiến trúc Lõi Kế toán kép: Event-Driven & REA (Resource, Event, Agent) Hybrid

Để đáp ứng được việc bóc tách AI, đảm bảo tĩnh tuân thủ thuế tuyệt đối và có thể mở rộng như các ERP lớn (Odoo, SAP), lõi kế toán của hệ thống **KHÔNG hạch toán Nợ/Có ngay từ đầu**. Thay vào đó, hệ thống áp dụng tiêu chuẩn **Event-Driven Architecture kết hợp mô hình REA**, chia quá trình ghi nhận thành 3 tầng nguyên thủy:

### Tầng 1: Economic Events (Sự kiện Kinh tế - Nguồn Sự thật)
Đây là "Single Source of Truth" (Nguồn chân lý duy nhất). Tầng này lưu trữ **những gì thực sự diễn ra trong thực tế**, bằng ngôn ngữ hoạt động kinh doanh, hoàn toàn không dính dáng đến Nợ/Có hay Tài khoản kế toán.
- **Mô hình REA**: Mỗi giao dịch thực tế sẽ có `Event` (Sự kiện: Mua, Bán, Trả lương) gắn với `Agents` (Ai: Nhân viên, Khách hàng, NCC) và `Resources` (Tài sản gì: Tiền, Hàng tồn kho thiết bị).
- **Ví dụ Database Record**: `Event_Type: Mua_Tai_San | Agent_ID: NCC_PhongVu | Item: Laptop_Dell | Total_Amount: 40_000_000 | Date: 14/03/2026`.
- **Vai trò của AI**: Các mô hình AI nhỏ gọn (Local LLMs/NER) **CHỈ ĐƯỢC PHÉP CHẠY Ở TẦNG NÀY**. AI đọc file hóa đơn / nghe người dùng nói và bóc tách ra các trường thông tin của Economic Event. AI không cần biết Nợ/Có, loại bỏ 100% rủi ro "ảo giác" làm sai lệch sổ sách.

### Tầng 2: Accounting Rule Engine (Công cụ ánh xạ Chuẩn mực)
Nằm giữa Sự kiện thực tế và Sổ kế toán, đây là "Bộ não Tuân thủ". 
- Khi một `Economic Event` được chốt, hệ thống tự động đẩy nó qua bộ Rule Engine. 
- Rule Engine chứa các bảng tham chiếu Luật dưới dạng JSON Rules (Ví dụ: `Rule 12.A: Nếu Event = Mua_Tai_San và Trị_giá > 30tr -> Áp dụng Thông tư 200, kích hoạt Hạch toán Tài sản cố định`).
- Hệ thống hỗ trợ "Version Control" cho luật. Nếu Tổng cục Thuế ra quy định mới, bạn chỉ cần cập nhật bộ Rule, các báo cáo sau ngày áp dụng sẽ đi theo luật mới.

### Tầng 3: General Ledger & Journal Entries (Sổ cái và Bút toán)
Đây là tầng "Kế toán" bảo thủ và khắt khe nhất. Nơi xuất hiện các khái niệm Nợ (Debit) và Có (Credit).
- Hệ quả của Rule Engine ở Tầng 2 là các `Journal Entries` được sinh ra tự động ở Tầng 3.
- Ràng buộc lõi ở Database: `Total_Debit = Total_Credit`.
- Bất biến (Immutable): Không cho phép cập nhật (UPDATE) hay xóa (DELETE) bất cứ dòng nào đã `Locked`. Mọi thay đổi phải là các bút toán đảo (Reversal Entries).
- **Sức mạnh của Multi-Ledger (Đa Sổ sách)**: Từ một gốc `Economic Event` duy nhất ở Tầng 1, bạn có thể thiết lập Rule Engine chạy ra nhiều hệ thống sổ khác nhau. Ví dụ: Sự kiện "Tiếp khách 50 triệu" sẽ sinh ra *Sổ Quản trị (CFO)* là Toàn bộ 50tr chi phí, nhưng đồng thời sinh ra *Sổ Thuế* chỉ chấp nhận 30tr (Theo luật định mức), loại 20tr ra khỏi chi phí hợp lý. Cả hai sổ chạy độc lập, báo cáo không cắn xé nhau.

## 4. Giá trị Chiến lược dành cho Giám đốc (CEO/CFO Dashboard)

Phần lớn các hệ thống kế toán truyền thống thường "bỏ rơi" Cán bộ quản lý cấp cao, chỉ cung cấp các báo cáo bảng biểu khô khan, chậm tiến độ (phải đợi cuối tháng khóa sổ). Hệ thống Auto ERP này thiết kế lấy **Người Ra Quyết Định (Decision Makers)** làm trung tâm với các tính năng:

### A. Real-time Cockpit (Trạm Điều khiển Thời gian thực)
- Nhờ kiến trúc "Nguồn sự thật" (Economic Events), số liệu doanh thu, chi phí, dòng tiền (Cashflow) cập nhật từng giây ngay khi có giao dịch phát sinh.
- **Dự báo Dòng tiền (Cashflow Forecasting):** Kết hợp dữ liệu lịch sử thanh toán của khách hàng với công nợ hiện tại, AI sẽ dự báo: *"Tuần sau công ty có khả năng thâm hụt 500 triệu tiền mặt do khoản phải trả NCC X đến hạn, trong khi khách hàng Y thường xuyên trả trễ"*.

### B. "Hỏi AI như hỏi Kế toán trưởng" (Conversational BI)
- Không cần học cách bấm hàng chục filter trong phần mềm để ra được báo cáo. 
- CEO chỉ cần mở điện thoại và chat/voice: 
  - *"Chi phí Marketing tháng này đang vượt ngân sách bao nhiêu % so với doanh thu?"*
  - *"Liệt kê Top 5 khách hàng nợ dai nhất trong năm qua."*
- Agent AI (Text-to-SQL) sẽ tự động sinh biểu đồ (Charts) ngay lập tức trên màn hình dựa trên dữ liệu thật của Database.

### C. Cơ chế Cảnh báo Bất thường (Anomaly Detection)
- Khi nhân viên phát sinh một khoản chi (ví dụ: Mua laptop 80 triệu) chênh lệch quá lớn so với định mức lịch sử (trung bình 30 triệu). Hệ thống tự động khoanh vùng giao dịch này thành màu Đỏ (High Risk) và đẩy thẳng Notification qua App/Zalo cho CFO duyệt trước khi ghi sổ.
- Cảnh báo rủi ro về Thuế: "Giao dịch chi phí tiếp khách này chiếm tỷ trọng quá lớn, có rủi ro bị loại khi quyết toán thuế".

---

## 5. Chiến lược Thương mại & Bản quyền (Commercial & Licensing Strategy)

Để thuyết phục người dùng "xuống tiền" theo mô hình Thuê bao (Subscription/SaaS) thay vì Mua đứt (One-time purchase) dành cho một phần mềm Local-first, chúng ta cần một chiến lược định giá và khóa bản quyền chặt chẽ.

### A. Mô hình Định giá (Pricing Strategy)

| Tính năng | Bản Free (Mồi câu) | Bản Premium (Subscription) |
| :--- | :--- | :--- |
| **Mục tiêu** | Chiến lấy thị phần, thay thế Excel của các hộ kinh doanh/startup nhỏ. | Tạo ra lợi nhuận từ các SME, Doanh nghiệp lớn cần tự động hóa và quản trị chiến lược. |
| **Giới hạn Giao dịch** | 100 User/tháng (Hoặc giới hạn 50 chứng từ/tháng). | Không giới hạn giao dịch. |
| **Lõi Kế toán (Ledger)** | Các định khoản cơ bản (Thu/Chi tiền mặt). | Đầy đủ hệ thống chuẩn mực VAS 133/200, Đa Tiền tệ. |
| **AI Data Extractor** | Phải tự gõ tay (Thủ công) hoặc chỉ OCR cơ bản hóa đơn. | Upload Batch hàng chục file XML hoá đơn 1 lúc, AI xé nhỏ và tự đưa vào Rule Engine. |
| **CFO Dashboard** | Chỉ có Báo cáo tĩnh theo tháng. | Real-time Dashboard, Truy vấn Text-to-SQL (Hỏi AI trả lời). |
| **Đồng bộ hóa/Backup** | Database nằm chết ở 1 máy Local. Mất máy là mất dữ liệu. | Tính năng Cloud Sync: Mã hóa E2E, đồng bộ qua thiết bị khác hoặc xem báo cáo trên Mobile. |

### B. Kiểm soát Bản quyền Offline (Offline DRM Mechanism)

Vấn đề lớn nhất của app Offline là crack. Nếu họ mua 1 tháng rồi ngắt mạng dùng vĩnh viễn thì sao? Giải pháp **Rolling Token (Mã thông báo cuộn)**:
1. **Heartbeat Check:** App Local bắt buộc phải "Ping" về License Server của chúng ta ít nhất 1 lần mỗi 30 ngày. 
2. **Cấp Token có thời hạn:** Khi app kết nối Internet, Server trả về một file cấu hình JWT Token đã mã hóa, bên trong chứa `valid_until: [Ngày hết hạn gói cước]`. App Local sẽ tự đếm ngược thời gian dựa trên đồng hồ BIOS (hoặc gọi API NTP nếu có mạng).
3. **Cơ chế Khóa (Grace Period):** Nếu sau 30 ngày KHÔNG có mạng, hoặc Token hết hạn, app chuyển sang chế độ **Read-Only (Chỉ Đọc)**. Khách hàng vẫn xem được toàn bộ Sổ cái lịch sử (Tránh vi phạm luật không giam lỏng dữ liệu người dùng), nhưng KHÔNG THỂ tạo/import giao dịch mới. Muốn nhập liệu tiếp -> Phải mua gói tháng mới.

### C. "Key" để Thuyết phục Khách hàng chi tiền

Điểm chốt (Selling Point) mạnh nhất không phải là "Kế toán không phải làm gì", mà là:
1. **"Tiết kiệm 20 triệu/tháng tiền phạt vì sai soát Thuế"**: Tính năng cập nhật Luật Thuế theo thời gian thực (Rule Engine Update) đảm bảo họ luôn làm đúng luật mới nhất mà không cần phụ thuộc trình độ của Kế toán viên.
2. **"Tầm nhìn CFO dành cho CEO"**: Mua phần mềm Premium không phải để giải quyết khâu nhập liệu, mà là mua một **"Giám đốc Tài chính Ảo"**. Tính năng Cashflow Forecasting và Anomaly Detection giúp CEO ngủ ngon vì biết tiền của mình đang chạy đúng hướng.

---

## 6. Chiến lược Chống Thanh tra Thuế & Hồ sơ Số hóa (Audit Trail & Paperless Strategy)

Để giải quyết triệt để nỗi lo "làm sao giải trình với cán bộ Thuế" một cách nhanh gọn và không cần ôm giấy tờ đóng cuốn cồng kềnh, hệ thống áp dụng cơ chế **Văn phòng Không giấy tờ (Paperless Office) đạt chuẩn Lưu trữ điện tử**:

### A. Số hóa Chứng từ 100% (Document Archiving)
Tại Tầng 1 (Economic Events), mọi giao dịch đều bắt buộc phải đính kèm chứng từ vật lý đã số hóa vào bảng `EVENT_ATTACHMENTS`.
- **Hóa đơn điện tử (Bắt buộc):** Hệ thống tự động kéo file XML/PDF từ Tổng cục Thuế (thông qua API hoặc nhận file hàng loạt khách hàng ném vào). File XML được mã hóa và lưu trữ nguyên bản (đủ giá trị pháp lý tuyệt đối để cung cấp cho Thuế).
- **Chứng từ nội bộ (Uyển chuyển):** Giấy đề nghị thanh toán, Hợp đồng, Phiếu thu/chi... Kế toán chỉ cần lấy điện thoại chụp hình (Quét CamScanner qua App) và đẩy thẳng vào giao dịch. Hệ thống lưu thành file PDF không thể sửa đổi.

### B. Liên kết Ngược & Truy xuất Tức thì 1-Click (1-Click Drill Down)
Khủng hoảng lớn nhất khi thanh tra Thuế là: Thuế nhặt 1 dòng 50.000.000VNĐ trên Sổ TNDN và hỏi "Hóa đơn, hợp đồng chứng minh khoản này đâu?". Ở hệ thống cũ, kế toán phải lặn lội lục kho tìm cuốn chứng từ tháng 5.
- Ở hệ thống Auto ERP: Kế toán (hoặc chính cán bộ Thuế) chỉ cần **Double-Click** vào dòng "Nợ 642 - 50.000.000đ" trên màn hình.
- Lập tức một hộp thoại (Modal) hiện ra chứa trọn bộ:
  1. Hóa đơn XML đỏ chót.
  2. Ảnh chụp Hợp đồng PDF có chữ ký.
  3. Ảnh chụp màn hình Internet Banking chuyển khoản.
  4. **Dòng giải trình Auto-Rules:** *"Hạch toán theo Rule VAS200_EXP_02: Trị giá > 20tr đã thanh toán không dùng tiền mặt"*.
- Chỉ mất 2 giây để cán bộ Thuế gật đầu và chuyển sang dòng khác.

### C. Mã băm toàn vẹn dữ liệu (Immutability Hash)
Để chứng minh với Cơ quan Thuế rằng "Số liệu này chúng em không hề xào nấu trước ngày thanh tra", hệ thống áp dụng cơ chế Hash (tương tự Blockchain):
- Mỗi khi một chu kỳ (Tháng/Quý) được **Khóa sổ (Locked)**, hệ thống sẽ gộp toàn bộ `Event`, `Journal Entries` và `Attachments` của tháng đó để chạy qua thuật toán mã hóa SHA-256 sinh ra một chuỗi Hash duy nhất.
- Bất kỳ ai cố tình sửa 1 dấu phẩy trong bill PDF hoặc đổi số tiền trong Database, mã Hash sẽ vỡ. Bản in Sổ kế toán nộp Thuế có in kèm chuỗi Hash này ở cuối trang như một con dấu điện tử đảm bảo tính toàn vẹn 100%.

---

## 7. Kế hoạch triển khai (Next Steps)
1. Thống nhất Mô hình Audit Trail & Document.
2. Setup cấu trúc lõi Backend (FastAPI + PostgreSQL/SQLite).

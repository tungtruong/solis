# Thư mục lưu trữ CSDL Văn bản Pháp luật (Regulations Database)

Xin chào! CFO/Kế toán trưởng hãy đưa toàn văn các văn bản gốc (Thông tư 133, 200, 99/2025, Luật Thuế TNDN...) vào thư mục này.

**Định dạng khuyên dùng để hệ thống xử lý tốt nhất (RAG / Rule Parsing):**
- **`.txt` hoặc `.md`** (Plain Text / Markdown): **TỐT NHẤT CHO AI**. Đọc siêu nhanh và không bị lỗi format.
- **`.json`**: Tốt nhất nếu bạn đã trích xuất sẵn cấu trúc Điều, Khoản.
- **`.pdf` / `.docx`**: Có thể dùng, nhưng hệ thống sẽ cần thêm module OCR/PDF Parser (như `PyPDF2` hoặc `unstructured`) để đọc và bóc tách trước khi đưa cho AI.

**Sau khi bạn đưa dữ liệu vào đây (Ví dụ: `TT200.txt`), chúng ta sẽ có 2 luồng xử lý chính:**
1. **Dùng Script tự động (LLM Script)**: Quét toàn bộ nội dung chữ, yêu cầu AI trích xuất các quy tắc định khoản Nợ/Có thành dạng File JSON chuẩn của hệ thống (Import vào bảng `TaxAccountingRule` làm lõi cứng bảo vệ).
2. **Setup Vector Database (RAG - Retrieval-Augmented Generation)**: Cắt nát các thông tư thành từng đoạn văn bản (chunks) và đưa vào CSDL Vector (như ChromaDB / Qdrant). Khi CFO Chat "Chi phí tiếp khách tối đa là bao nhiêu trước khi bị Thuế loại?", AI sẽ tìm đoạn văn bản đó trong này, đọc lại cho CFO và trích dẫn chuẩn "Theo Điều X thông tư Y".

Sau khi bạn copy xong, hãy phản hồi lại cho tôi nhé!

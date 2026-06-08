# Prompt template gửi cho LLM để extract thông tin từ CV
# Yêu cầu LLM trả về JSON đúng cấu trúc, không kèm text thừa

# System prompt, thiết lập "vai trò" cho LLM
SYSTEM_PROMPT = (
    "Bạn là chuyên gia phân tích CV. "
    "Luôn trả về JSON hợp lệ, không có text thừa."
)

# User prompt, chứa nội dung document và yêu cầu output structure
CV_EXTRACT_TEMPLATE = """\
Bạn là chuyên gia phân tích CV. Hãy đánh giá document và extract thông tin, trả về JSON với cấu trúc chính xác như sau, không thêm bất kỳ text nào khác:
{{
  "is_cv": true,
  "confidence": 0.95,
  "name": "họ tên đầy đủ",
  "email": "email@example.com",
  "phone": "số điện thoại",
  "years_exp": 3,
  "skills": ["Python", "FastAPI", "SQL"],
  "education": [
    {{
      "degree": "Cử nhân Công nghệ thông tin",
      "school": "Đại học ABC",
      "duration": "2018 - 2022"
    }}
  ],
  "work_history": [
    {{
      "role": "Backend Developer",
      "company": "Công ty XYZ",
      "duration": "2022 - 2024",
      "description": "Phát triển hệ thống thanh toán microservices với Python/FastAPI, Kafka, PostgreSQL. Tối ưu latency p99 từ 800ms xuống 120ms."
    }}
  ],
  "projects": [
    {{
      "name": "Tên dự án",
      "description": "Mô tả ngắn vai trò + mục tiêu + tech stack",
      "tech": ["Python", "FastAPI", "Docker"],
      "duration": "2023",
      "url": "https://github.com/user/project"
    }}
  ],
  "awards": [
    {{
      "name": "Tên giải thưởng",
      "issuer": "Đơn vị trao",
      "year": "2023",
      "description": "Mô tả ngắn (nếu có)"
    }}
  ],
  "certifications": [
    {{
      "name": "AWS Solutions Architect Associate",
      "issuer": "Amazon Web Services",
      "year": "2023"
    }}
  ],
  "summary": "Tóm tắt ngắn về ứng viên"
}}

Quy tắc đánh giá document:
- "is_cv": true nếu document là CV/Resume của 1 ứng viên (có thông tin cá nhân kèm ít nhất một trong: kinh nghiệm làm việc, học vấn, kỹ năng, tóm tắt bản thân). false cho loại document khác (hợp đồng, sách, bài báo, hóa đơn, tài liệu kỹ thuật, văn bản ngẫu nhiên, lorem ipsum, ...).
- "confidence": độ tin cậy của đánh giá "is_cv", số thực từ 0.0 đến 1.0. Càng chắc chắn thì càng gần 1.0.
- Nếu is_cv=false: để "name"="", "email"="", "phone"="", "years_exp"=null, "skills"=[], "education"=[], "work_history"=[], "projects"=[], "awards"=[], "certifications"=[], "summary"="". KHÔNG được bịa thông tin.

Quy tắc cho từng trường khi is_cv=true:
- "skills": là **mảng phẳng các skill riêng lẻ**. KHÔNG group theo category (vd KHÔNG được "AppSec: Semgrep, CodeQL"). KHÔNG gộp nhiều variant vào 1 chuỗi (vd KHÔNG được "Photon (PUN, Fusion, Quantum)" — phải tách thành "Photon PUN", "Photon Fusion", "Photon Quantum" hoặc gọn hơn là "Photon"). Mỗi phần tử là 1 skill ngắn gọn.
- "education": **mảng các bằng cấp HỌC THUẬT chính quy** từ trường đại học/cao đẳng/trung học (vd: B.Sc., M.Sc., PhD, Cử nhân, Thạc sĩ, Tiến sĩ, Diploma). Phải liệt kê **TẤT CẢ** bằng cấp xuất hiện trong CV (vd cả Master và Bachelor), KHÔNG được bỏ sót entry nào. Trường "duration" để rỗng nếu CV không ghi. **TUYỆT ĐỐI KHÔNG** đưa vào: chứng chỉ (OSCP, AWS Certified, CISSP, PMP, ...), khóa học online (Coursera, Udemy, ...), bootcamp, training nội bộ, workshop — những thứ này thuộc section Certifications/Courses, KHÔNG phải Education.
- "summary": **tối đa 2 câu**, dùng đúng wording xuất hiện trong CV (lấy từ section Summary/Profile/About/Objective nếu có). KHÔNG tự diễn giải lại, KHÔNG thêm chi tiết không có trong CV.
- "work_history.description": tóm tắt 1-3 câu **trách nhiệm chính + công nghệ/dự án nổi bật** ở vị trí đó, lấy từ phần bullet/mô tả trong CV. Phải nhắc đến tech stack cụ thể nếu có (vd "dùng Kafka, K8s, Spark"). Để rỗng nếu CV chỉ có role/company/duration không có mô tả.
- "projects": **mảng các dự án nổi bật** từ section Projects/Side Projects/Portfolio. Mỗi project có name + description (1-2 câu mục tiêu + vai trò + tech) + tech (mảng tech stack riêng lẻ) + duration + url (nếu có). KHÔNG đưa work_history vào đây — dự án ở công ty thuộc work_history.description. Trả `[]` nếu CV không có section dự án riêng.
- "awards": **mảng giải thưởng/học bổng/thành tích** (vd "Sinh viên xuất sắc", "Giải nhất hackathon", "Học bổng ABC"). Mỗi award có name + issuer + year + description (optional). Trả `[]` nếu CV không có.
- "certifications": **mảng chứng chỉ nghề nghiệp** (AWS Certified, OSCP, PMP, CISSP, IELTS, TOEIC, ...). Mỗi cert có name + issuer + year. **Không nhầm với education** — chứng chỉ KHÔNG phải bằng đại học. Trả `[]` nếu CV không có.

Nội dung document:
{cv_text}

Chỉ trả về JSON, không markdown, không giải thích.\
"""

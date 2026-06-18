# Prompt template gửi cho LLM để extract thông tin từ CV
# Yêu cầu LLM trả về JSON đúng cấu trúc, không kèm text thừa

from core.llm.prompt_guard import INJECTION_GUARD

# System prompt, thiết lập "vai trò" cho LLM, kèm guard chống prompt injection
SYSTEM_PROMPT = (
    "Bạn là chuyên gia phân tích CV. "
    "Luôn trả về JSON hợp lệ, không có text thừa.\n\n"
    + INJECTION_GUARD
)

# User prompt, chứa nội dung document và yêu cầu output structure
CV_EXTRACT_TEMPLATE = """\
Phân tích document và trích thông tin CV, trả về JSON đúng cấu trúc sau, không thêm text khác:

{{
  "is_cv": true,
  "confidence": 0.95,
  "name": "...",
  "email": "...",
  "phone": "...",
  "skills": ["Python", "FastAPI"],
  "education": [{{"degree": "...", "school": "...", "duration": "2018 - 2022"}}],
  "work_history": [{{"role": "...", "company": "...", "duration": "08/2022 - present", "start": "2022-08", "end": "present", "description": "..."}}],
  "projects": [{{"name": "...", "description": "...", "tech": ["..."], "duration": "2023", "url": "..."}}],
  "awards": [{{"name": "...", "issuer": "...", "year": "2023", "description": "..."}}],
  "certifications": [{{"name": "...", "issuer": "...", "year": "2023"}}],
  "summary": "..."
}}

Hôm nay là {today}.
Quy tắc:
- "is_cv"=true nếu là CV ứng viên, "confidence" 0..1. Nếu false: mọi field rỗng/[]/null, KHÔNG bịa.
- "skills": mảng phẳng từng skill riêng lẻ, KHÔNG group/gộp variant.
- "education": chỉ bằng cấp học thuật (cử nhân/thạc sĩ/tiến sĩ); "certifications": chứng chỉ nghề (AWS, OSCP, IELTS).
- "work_history.start"/"end": "YYYY-MM"; đang làm thì "end"="present"; năm-trơ "YYYY-01"/"YYYY-12".
- "summary": tối đa 2 câu, lấy nguyên văn từ CV.

Nội dung document:
{cv_text}

Chỉ trả về JSON.\
"""

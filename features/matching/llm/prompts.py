# Prompt LLM extract yêu cầu từ JD (Job Description) thành JSON structured

from core.llm.prompt_guard import INJECTION_GUARD

JD_SYSTEM_PROMPT = (
    "Bạn là chuyên gia HR/recruiter. "
    "Đọc Job Description và trả về JSON hợp lệ, không text thừa.\n\n"
    + INJECTION_GUARD
)

JD_EXTRACT_TEMPLATE = """\
Đọc Job Description sau và trích các yêu cầu chính, trả về JSON đúng cấu trúc:
{{
  "summary": "1-3 câu mô tả ngắn vị trí tuyển dụng (lấy nguyên văn nếu có)",
  "required_skills": ["Python", "FastAPI", "PostgreSQL"],
  "min_years_exp": 3,
  "max_years_exp": null
}}

Quy tắc:
- "summary": 1-3 câu tóm tắt vị trí + lĩnh vực chính. Dùng wording xuất hiện trong JD, không tự thêm.
- "required_skills": mảng các skill kỹ thuật riêng lẻ. KHÔNG group, mỗi phần tử là 1 skill ngắn.
- "min_years_exp": số năm KN tối thiểu yêu cầu (vd "3+ năm" -> 3, "tối thiểu 5 năm" -> 5). null nếu JD không nói.
- "max_years_exp": số năm KN tối đa (vd "dưới 10 năm" -> 10). null nếu JD không nói (hầu hết JD không có max).

Nội dung JD:
{jd_text}

Chỉ trả về JSON, không markdown, không giải thích.\
"""

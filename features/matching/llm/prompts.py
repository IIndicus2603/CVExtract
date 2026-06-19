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
- "min_years_exp": số NĂM kinh nghiệm làm việc tối thiểu (vd "3+ năm" thành 3, "tối thiểu 5 năm" thành 5). Bỏ qua số buổi/tuần, số giờ, lương, tuổi, năm học. JD thực tập/intern/sinh viên/mới tốt nghiệp thì để null. null nếu JD không nói.
- "max_years_exp": số NĂM kinh nghiệm làm việc tối đa (vd "dưới 10 năm" thành 10). null nếu JD không nói (hầu hết JD không có max).

Nội dung JD:
{jd_text}

Chỉ trả về JSON, không markdown, không giải thích.\
"""


EVAL_SYSTEM_PROMPT = (
    "Bạn là chuyên gia tuyển dụng đánh giá mức độ phù hợp giữa ứng viên và vị trí. "
    "Đọc yêu cầu JD và dữ liệu CV, chấm điểm khách quan và trả về JSON hợp lệ, không text thừa.\n\n"
    + INJECTION_GUARD
)

EVAL_USER_TEMPLATE = """\
Đánh giá mức độ phù hợp của CV với yêu cầu tuyển dụng sau, trả về JSON đúng cấu trúc:
{{
  "score": 0.0,
  "recommendation": "strong | good | weak | reject",
  "reasoning": "2-4 câu giải thích điểm số",
  "matched_skills": ["Python", "FastAPI"],
  "missing_skills": ["Kubernetes"],
  "experience_fit": "1 câu đánh giá kinh nghiệm so với yêu cầu",
  "strengths": ["điểm mạnh 1"],
  "concerns": ["điểm cần lưu ý 1"]
}}

Quy tắc:
- "score": số thực 0..1, 1 là phù hợp hoàn hảo, cân nhắc kỹ năng cộng kinh nghiệm cộng lĩnh vực cộng thành tích liên quan
- "recommendation": 1 trong 4 nhãn strong/good/weak/reject dựa trên score
- "matched_skills": skill trong CV trùng với required_skills của JD
- "missing_skills": required_skills của JD mà CV không thể hiện
- "experience_fit": so kinh nghiệm CV với yêu cầu kinh nghiệm bên dưới. Nếu JD không yêu cầu số năm thì coi là đạt, không trừ điểm ứng viên ít hoặc chưa có kinh nghiệm và không cộng điểm chỉ vì nhiều năm
- giải thưởng/thành tích liên quan tới vị trí hoặc lĩnh vực phải CỘNG THÊM vào "score" (mỗi thành tích nổi bật khoảng +0.05 đến +0.1, tổng không vượt 1.0) và nêu ở "strengths"; thành tích không liên quan thì bỏ qua, không cộng không trừ
- chỉ đánh giá dựa trên dữ liệu được cung cấp, không suy diễn ngoài dữ liệu

Yêu cầu tuyển dụng (JD):
- Tóm tắt: {jd_summary}
- Kỹ năng yêu cầu: {required_skills}
- Yêu cầu kinh nghiệm: {years_req}

Dữ liệu CV (JSON các trường đã trích):
{cv_text}

Bằng chứng từ các đoạn khớp nhất:
{evidence}

Chỉ trả về JSON, không markdown, không giải thích.\
"""

# Answer, dùng context (CV chunks) trả lời câu hỏi

from core.schemas import SearchHit
from features.chat.llm.prompts import ANSWER_SYSTEM, ANSWER_USER_TEMPLATE


def build_answer_messages(context: str, question: str) -> tuple[str, str]:
    """Trả (system, user) prompts để gọi BaseProvider.chat/stream"""
    return ANSWER_SYSTEM, ANSWER_USER_TEMPLATE.format(
        context=context, question=question,
    )


def format_context(hits: list[SearchHit]) -> str:
    """Gộp các đoạn thành '[Section, X]\\n<text>' khối, rỗng thì trả 'Không có thông tin.'"""
    if not hits:
        return "Không có thông tin."
    blocks = [f"[Section: {h.section}]\n{h.chunk_text}" for h in hits]
    return "\n\n".join(blocks)

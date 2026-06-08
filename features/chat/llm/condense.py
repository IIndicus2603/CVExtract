# Condense, viết lại câu follow-up thành câu standalone đầy đủ ngữ cảnh

from features.chat.llm.prompts import CONDENSE_SYSTEM, CONDENSE_USER_TEMPLATE
from features.chat.schemas import ChatMessage


def build_condense_messages(history: str, question: str) -> tuple[str, str]:
    """Trả (system, user) prompts để gọi BaseProvider.chat/stream"""
    return CONDENSE_SYSTEM, CONDENSE_USER_TEMPLATE.format(
        chat_history=history, question=question,
    )


def format_history_for_condense(messages: list[ChatMessage]) -> str:
    """List message thành 'User, ...\\nAssistant, ...' để nhét vào prompt"""
    if not messages:
        return ""
    return "\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in messages
    )

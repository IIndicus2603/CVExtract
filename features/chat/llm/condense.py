# pipeline để viết lại câu hỏi follow-up thành câu đầy đủ
# Ví dụ: "Anh ấy ở công ty nào?" -> "Alex Petrov ở công ty nào?"

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from features.chat.llm.prompts import CONDENSE_PROMPT
from features.chat.schemas import ChatMessage


def build_condense_chain(llm: BaseChatModel) -> Runnable:
    prompt = ChatPromptTemplate.from_template(CONDENSE_PROMPT)
    return prompt | llm | StrOutputParser()


# Biến list message thành chuỗi text "User: ...\nAssistant: ..." để nhét vào prompt
# Trả "" nếu không có message
def format_history_for_condense(messages: list[ChatMessage]) -> str:
    if not messages:
        return ""
    lines = []
    for m in messages:
        prefix = "User" if m.role == "user" else "Assistant"
        lines.append(f"{prefix}: {m.content}")
    return "\n".join(lines)

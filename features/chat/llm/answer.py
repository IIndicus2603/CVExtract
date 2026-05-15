# pipeline để trả lời câu hỏi, dựa trên các đoạn CV đã tìm được

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from features.chat.llm.prompts import ANSWER_PROMPT
from features.retrieval.schemas import SearchHit


def build_answer_chain(llm: BaseChatModel) -> Runnable:
    prompt = ChatPromptTemplate.from_template(ANSWER_PROMPT)
    return prompt | llm | StrOutputParser()


# Gộp các đoạn thành 1 khối text dạng "[Section: <tên>]\n<nội dung>" để llm đọc
# Nếu không có đoạn nào, trả về "không có thông tin" để llm reject
def format_context(hits: list[SearchHit]) -> str:
    if not hits:
        return "Không có thông tin."
    blocks = [f"[Section: {h.section}]\n{h.chunk_text}" for h in hits]
    return "\n\n".join(blocks)

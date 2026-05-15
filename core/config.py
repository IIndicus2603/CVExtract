# Đọc các biến môi trường từ file .env và export thành constants

import os
from dotenv import load_dotenv

load_dotenv()

# API key của Groq (LLM provider)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# API key của Gemini (LLM provider)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# API key của Nvidia (chỉ cần nếu dùng model của Nvidia trên Groq)
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")

# Connection string MySQL, default trỏ tới localhost
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:password@localhost:3306/cvextract",
)

# Qdrant
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "cv_chunks_v1")

# Embedding (bi-encoder, sentence-transformers)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))

# Reranker (cross-encoder)
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# Parsing LLM (gọi khi upload CV để tách thông tin)
PARSING_LLM_PROVIDER: str = os.getenv("PARSING_LLM_PROVIDER", "groq")
PARSING_LLM_MODEL: str = os.getenv("PARSING_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# Chat LLM (gọi khi user chat hỏi đáp với CV); chỉ hỗ trợ Groq
CHAT_LLM_MODEL: str = os.getenv("CHAT_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
CHAT_SESSION_TTL_HOURS: int = int(os.getenv("CHAT_SESSION_TTL_HOURS", "24"))
CHAT_HISTORY_LAST_N: int = int(os.getenv("CHAT_HISTORY_LAST_N", "6"))
CHAT_REFUSAL_SCORE_THRESHOLD: float = float(os.getenv("CHAT_REFUSAL_SCORE_THRESHOLD", "0.3"))

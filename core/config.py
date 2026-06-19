# Constants, biến lấy từ .env dùng os.getenv, còn lại là cố định

import os
from dotenv import load_dotenv

load_dotenv()

# LLM API keys (lấy từ .env)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
ROUTER9_API_KEY: str = os.getenv("ROUTER9_API_KEY", "")

# Database (lấy từ .env, Docker Compose set sẵn DATABASE_URL host=mysql, local dựng từ MYSQL_*)
_MYSQL_PASSWORD = os.getenv("MYSQL_ROOT_PASSWORD", "password")
_MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "cvextract")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"mysql+aiomysql://root:{_MYSQL_PASSWORD}@localhost:3307/{_MYSQL_DATABASE}",
)

# Qdrant (Docker Compose set QDRANT_URL host=qdrant)
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = "cv_chunks_v1"

# Embedding + reranker
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # bi-encoder, text thành vector
EMBEDDING_DIM = 384                                        # Số chiều vector, phải khớp model
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"                 # Cross-encoder chấm lại

# Retrieval pipeline (dùng chung retrieval + matching)
MAX_CHUNKS_PER_CV = 3        # Mỗi CV tối đa N chunks trong kết quả
RERANK_CANDIDATES = 40       # Số kết quả thô lấy từ Qdrant để rerank
UNLIMITED_FETCH_LIMIT = 10000  # Khi top_k=None, limit cứng bảo vệ Qdrant

# Chunker (cắt CV thành đoạn cho vector index)
SKILLS_PER_CHUNK = 10        # Số skill mỗi chunk khi phải chia nhỏ
MAX_SKILLS_SINGLE_CHUNK = 15  # Quá ngưỡng này thì skills tách nhiều chunk

# JD matching, trọng số top-N chunks/CV khi tính điểm aggregated (tổng = 1.0), len() quyết định N chunks mỗi CV
JD_AGG_WEIGHTS = [0.5, 0.3, 0.2]
JD_FALLBACK_SUMMARY_CHARS = 500  # Parse JD fail thì dùng raw JD làm summary
JD_MATCH_DEFAULT_TOP_K = 5       # Số CV trả ra mặc định mỗi JD khi caller không truyền top_k

# JD LLM evaluation, chỉ chạy khi caller bật llm_evaluate
JD_LLM_EVAL_CONCURRENCY = 5        # Số CV chấm song song tối đa, bound API rate
JD_LLM_EVAL_CV_TEXT_CHARS = 6000   # Cắt cv text JSON trước khi đưa vào prompt, chặn prompt phình
JD_LLM_EVAL_EVIDENCE_CHARS = 1500  # Cắt phần matched_chunks evidence trong prompt

# Extraction (Docker Compose set CV_RAW_TEXT_DIR)
CV_RAW_TEXT_DIR: str = os.getenv("CV_RAW_TEXT_DIR", "tests/data/raw_txt")  # Dump raw text sau extract để debug, rỗng để tắt

# Parsing LLM, provider: groq | nvidia | 9router
PARSING_LLM_PROVIDER = "9router"
PARSING_LLM_MODEL = "llm"
CV_CONFIDENCE_THRESHOLD = 0.5  # Min confidence từ LLM để công nhận là CV

# Chat LLM
CHAT_LLM_PROVIDER = "9router"
CHAT_LLM_MODEL = "llm"
CHAT_SESSION_TTL_HOURS = 24        # Phiên chat idle quá N giờ thì task nền tự xoá
CHAT_HISTORY_LAST_N = 10           # Số message gần nhất nạp vào prompt condense
CHAT_REFUSAL_SCORE_THRESHOLD = 0.3  # Top score dưới ngưỡng thì bot từ chối
CHAT_RETRIEVE_TOP_K = 5            # Số đoạn CV lấy ra mỗi câu hỏi chat

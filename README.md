# CVExtract

Hệ thống trích xuất thông tin từ CV (PDF, DOCX). Người dùng upload file, hệ thống đọc nội dung, gọi LLM để bóc tách các trường (họ tên, email, kỹ năng, kinh nghiệm, dự án, giải thưởng, chứng chỉ...) thành JSON có cấu trúc, lưu xuống MySQL + index vào Qdrant để **tìm kiếm ngữ nghĩa**, **match JD <-> CV**, và **chat hỏi đáp với từng CV**.

---

## Run with Docker

```bash
# 1. Tạo file .env từ template (default đã trỏ sẵn provider = 9router)
cp .env.example .env

# 2. Build + chạy 4 service (app + MySQL + Qdrant + 9Router)
docker compose --profile router9 up -d --build

# 3. Xem log app
docker compose logs -f app
```

### LLM setup (required)

App cần **ít nhất 1 LLM provider** để bóc tách CV và trả lời chat. Mặc định app đi qua **9Router** - proxy OpenAI-compatible chạy local, nơi bạn **tự do chọn provider và model nào cũng được** (Groq / NVIDIA / OpenAI...). `config.py` đã đặt sẵn `PARSING_LLM_PROVIDER=9router` / `CHAT_LLM_PROVIDER=9router` + `*_LLM_MODEL=llm`, nên chỉ cần setup model trong dashboard:

1. Bước 2 ở trên đã build + chạy service `router9` (nhờ `--profile router9`).
2. Mở dashboard `http://localhost:20128`, thêm provider + API key (provider nào tuỳ bạn) và tạo combo (tên tuỳ ý), chọn model muốn dùng trong combo đó.
3. Nếu đặt tên combo khác `llm`, sửa `PARSING_LLM_MODEL` / `CHAT_LLM_MODEL` trong [`core/config.py`](core/config.py) cho khớp (đây là hằng số trong code, không đọc từ `.env`), rồi `docker compose up -d --build` để app nạp lại.

> Truy cập:

- Frontend: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Qdrant dashboard: `http://localhost:6333/dashboard`

Dừng & xoá container:

```bash
docker compose down
```

Dừng & xoá cả data (MySQL + Qdrant + cache HuggingFace):

```bash
docker compose down -v
```

---

## Configuration

Cấu hình chia làm **2 nhóm**, khác nhau ở chỗ sửa và thời điểm có hiệu lực:

1. **Biến môi trường (`.env`)** - đọc lúc chạy qua `os.getenv` trong [`core/config.py`](core/config.py). Override được mà **không cần sửa code**, chỉ cần đổi `.env` rồi restart. Đây là những thứ thay đổi theo môi trường (secret, host, đường dẫn).
2. **Hằng số tinh chỉnh (`config.py`)** - gán cứng trong code, **không** đọc từ `.env`. Muốn đổi phải sửa trực tiếp `core/config.py` rồi restart. Đây là các tham số thuật toán (model, ngưỡng, trọng số).

### 1. Environment variables

`config.py` đọc các biến dưới đây qua `os.getenv`, nhưng chia làm 2 mức:

**1a. Variables in `.env.example`** - copy ra `.env` rồi điền. Đây là 5 biến duy nhất bạn cần khai báo. Cột _Default_ là giá trị dùng khi để trống.

| Biến                   | Default       | Ý nghĩa                                                               |
| ----------------------- | ------------- | ----------------------------------------------------------------------- |
| `GROQ_API_KEY`        | _(rỗng)_   | API key Groq, chỉ cần khi provider =`groq`                          |
| `NVIDIA_API_KEY`      | _(rỗng)_   | API key NVIDIA, chỉ cần khi provider =`nvidia`                      |
| `ROUTER9_API_KEY`     | _(rỗng)_   | API key 9Router (provider mặc định)                                  |
| `MYSQL_ROOT_PASSWORD` | `password`  | Mật khẩu root MySQL; Docker Compose dùng để dựng `DATABASE_URL` |
| `MYSQL_DATABASE`      | `cvextract` | Tên database; Docker Compose dùng để dựng `DATABASE_URL`         |

**1b. Optional overrides** - `config.py` (và `providers.py`) có đọc các biến này, nhưng chúng **không nằm trong `.env.example`** vì đã có default hợp lý hoặc do Docker Compose tự set. Chỉ thêm vào `.env` khi muốn đổi.

| Biến                    | Default                                            | Ý nghĩa                                                                  |
| ------------------------ | -------------------------------------------------- | -------------------------------------------------------------------------- |
| `DATABASE_URL`         | `mysql+aiomysql://root:<pw>@localhost:3307/<db>` | Override toàn bộ chuỗi kết nối MySQL; Compose tự set host =`mysql` |
| `QDRANT_URL`           | `http://localhost:6333`                          | Endpoint Qdrant; Compose tự set host =`qdrant`                          |
| `PARSING_LLM_PROVIDER` | `9router`                                        | Provider parse CV + match JD:`groq` / `nvidia` / `9router`           |
| `PARSING_LLM_MODEL`    | _(rỗng = default của provider)_                | Tên model (hoặc combo 9Router) dùng để parse                          |
| `CHAT_LLM_PROVIDER`    | `9router`                                        | Provider cho chat                                                          |
| `CHAT_LLM_MODEL`       | _(rỗng = default của provider)_                | Tên model (hoặc combo 9Router) dùng cho chat                            |
| `CV_RAW_TEXT_DIR`      | `tests/data/raw_txt`                             | Thư mục dump raw text sau extract để debug; để rỗng để tắt       |
| `<PROVIDER>_BASE_URL`  | _(theo provider)_                                | Override base URL endpoint từng provider, vd `ROUTER9_BASE_URL`         |

`<PROVIDER>_BASE_URL` suy ra từ tên `*_API_KEY` (vd `ROUTER9_API_KEY` -> `ROUTER9_BASE_URL`). Default theo provider: `groq` = `https://api.groq.com/openai/v1`, `nvidia` = `https://integrate.api.nvidia.com/v1`, `9router` = `http://localhost:20128/v1`. Trong Docker, `ROUTER9_BASE_URL` mặc định trỏ tới service `router9` (`http://router9:20128/v1`).

### 2. Tuning constants (`config.py`)

Sửa trực tiếp [`core/config.py`](core/config.py), **không** đặt trong `.env`.

**LLM (parsing + chat)** — provider/model đã chuyển sang env (xem mục 1b)

| Hằng số                   | Default | Ý nghĩa                                                                        |
| --------------------------- | ------- | -------------------------------------------------------------------------------- |
| `CV_CONFIDENCE_THRESHOLD` | `0.5` | Confidence tối thiểu từ LLM để công nhận là CV, dưới ngưỡng trả 422 |

**Vector DB + Embedding/Rerank**

| Hằng số             | Default                                   | Ý nghĩa                                                   |
| --------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| `QDRANT_COLLECTION` | `cv_chunks_v1`                          | Tên collection Qdrant                                      |
| `EMBEDDING_MODEL`   | `paraphrase-multilingual-MiniLM-L12-v2` | Bi-encoder, biến text thành vector                        |
| `EMBEDDING_DIM`     | `384`                                   | Số chiều vector,**phải khớp** `EMBEDDING_MODEL` |
| `RERANKER_MODEL`    | `BAAI/bge-reranker-v2-m3`               | Cross-encoder chấm lại; để rỗng để tắt rerank       |

**Retrieval + Chunker**

| Hằng số                   | Default   | Ý nghĩa                                                 |
| --------------------------- | --------- | --------------------------------------------------------- |
| `MAX_CHUNKS_PER_CV`       | `3`     | Mỗi CV tối đa N chunks trong kết quả                 |
| `RERANK_CANDIDATES`       | `40`    | Số kết quả thô lấy từ Qdrant để đưa vào rerank |
| `UNLIMITED_FETCH_LIMIT`   | `10000` | Limit cứng khi `top_k=None` để bảo vệ Qdrant       |
| `SKILLS_PER_CHUNK`        | `10`    | Số skill mỗi chunk khi phải chia nhỏ                  |
| `MAX_SKILLS_SINGLE_CHUNK` | `15`    | Quá ngưỡng này thì skills tách thành nhiều chunk  |

**JD matching**

| Hằng số                     | Default             | Ý nghĩa                                                                                              |
| ----------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------ |
| `JD_AGG_WEIGHTS`            | `[0.5, 0.3, 0.2]` | Trọng số top-N chunks/CV khi tính điểm aggregate;**tổng = 1.0**, `len()` quyết định N |
| `JD_FALLBACK_SUMMARY_CHARS` | `500`             | Parse JD fail thì cắt N ký tự raw JD làm summary                                                  |

**JD LLM evaluation** (chỉ chạy khi request bật `llm_evaluate`)

| Hằng số                      | Default  | Ý nghĩa                                                     |
| ------------------------------ | -------- | ------------------------------------------------------------- |
| `JD_LLM_EVAL_CONCURRENCY`    | `5`    | Số CV chấm song song tối đa, bound API rate               |
| `JD_LLM_EVAL_CV_TEXT_CHARS`  | `6000` | Cắt CV text JSON trước khi đưa vào prompt, chặn phình |
| `JD_LLM_EVAL_EVIDENCE_CHARS` | `1500` | Cắt phần matched_chunks evidence trong prompt               |

**Chat**

| Hằng số                        | Default | Ý nghĩa                                              |
| -------------------------------- | ------- | ------------------------------------------------------ |
| `CHAT_SESSION_TTL_HOURS`       | `24`  | Phiên chat idle quá N giờ thì task nền tự xoá   |
| `CHAT_HISTORY_LAST_N`          | `10`  | Số message gần nhất nạp vào prompt condense       |
| `CHAT_REFUSAL_SCORE_THRESHOLD` | `0.3` | Top score dưới ngưỡng thì bot từ chối trả lời |
| `CHAT_RETRIEVE_TOP_K`          | `5`   | Số đoạn CV lấy ra mỗi câu hỏi chat              |

---

## Endpoints

| Method     | Endpoint                                | Mô tả                                      |
| ---------- | --------------------------------------- | -------------------------------------------- |
| `GET`    | `/`                                   | Frontend SPA                                 |
| `POST`   | `/UploadCV`                           | Upload 1 file CV                             |
| `POST`   | `/UploadMultipleCVs`                  | Upload batch nhiều file (từ folder picker) |
| `GET`    | `/Storage`                            | List tất cả CV đã lưu                   |
| `GET`    | `/Storage/{cv_key}`                   | Chi tiết 1 CV                               |
| `PATCH`  | `/Storage/{cv_key}`                   | Update CV + re-index Qdrant                  |
| `DELETE` | `/Storage/{cv_key}`                   | Xoá CV (MySQL + Qdrant + registry)          |
| `POST`   | `/Search/Semantic`                    | Tìm CV theo ngữ nghĩa (vector + rerank)   |
| `POST`   | `/Match/JD`                           | Match JD text -> top-K CV phù hợp          |
| `POST`   | `/Match/JD/Upload`                    | Match JD file PDF/DOCX -> top-K CV           |
| `POST`   | `/Chat/Sessions`                      | Tạo phiên chat gắn với 1 CV              |
| `POST`   | `/Chat/Sessions/{id}/Messages`        | Gửi message (non-streaming)                 |
| `POST`   | `/Chat/Sessions/{id}/Messages/Stream` | Gửi message, stream từng token             |
| `GET`    | `/Chat/Sessions/{id}`                 | Full history của session                    |
| `DELETE` | `/Chat/Sessions/{id}`                 | Xoá session (CASCADE messages)              |

---

## Example responses

### Upload CV

```json
{
  "message": "CV uploaded successfully",
  "results": {
    "file_name": "nguyen_van_a.pdf",
    "extension": ".pdf",
    "status": "success",
    "text": "{\n  \"name\": \"Nguyễn Văn A\",\n  \"email\": \"nguyenvana@example.com\",\n  ... \n}"
  }
}
```

`text` là JSON string đã escape (`json.dumps(parsed, ensure_ascii=False, indent=2)`). Nội dung sau khi decode, đầy đủ các trường:

```json
{
  "name": "Nguyễn Văn A",
  "email": "nguyenvana@example.com",
  "phone": "0901234567",
  "years_exp": 3,
  "skills": ["Python", "FastAPI", "SQL", "PostgreSQL", "Docker", "Kafka"],
  "education": [
    {
      "degree": "Cử nhân Công nghệ thông tin",
      "school": "Đại học Bách Khoa Hà Nội",
      "duration": "2018 - 2022"
    }
  ],
  "work_history": [
    {
      "role": "Backend Developer",
      "company": "Công ty XYZ",
      "duration": "2022 - 2024",
      "description": "Phát triển hệ thống thanh toán microservices với Python/FastAPI, Kafka, PostgreSQL. Tối ưu latency p99 từ 800ms xuống 120ms."
    }
  ],
  "projects": [
    {
      "name": "Hệ thống gợi ý sản phẩm",
      "description": "Xây dựng recommendation engine cho sàn thương mại điện tử, vai trò backend lead",
      "tech": ["Python", "FastAPI", "Docker"],
      "duration": "2023",
      "url": "https://github.com/nguyenvana/recsys"
    }
  ],
  "awards": [
    {
      "name": "Giải nhất Hackathon",
      "issuer": "FPT Software",
      "year": "2021",
      "description": "Giải pháp tối ưu logistics"
    }
  ],
  "certifications": [
    {
      "name": "AWS Solutions Architect Associate",
      "issuer": "Amazon Web Services",
      "year": "2023"
    }
  ],
  "summary": "Backend developer 3 năm kinh nghiệm Python, FastAPI, microservices"
}
```

`years_exp` được tính tất định từ `start`/`end` của work_history (gộp khoảng chồng lấn rồi floor về số năm), `null` nếu không mục nào có mốc thời gian hợp lệ. Các trường mảng (`skills`, `education`, `work_history`, `projects`, `awards`, `certifications`) trả `[]` khi CV không có thông tin tương ứng.

### Match JD

```json
{
  "parsed_jd": {
    "summary": "Backend Engineer 3+ năm Python, FastAPI",
    "required_skills": ["Python", "FastAPI", "PostgreSQL"],
    "min_years_exp": 3,
    "max_years_exp": null
  },
  "total_cvs": 5,
  "results": [
    {
      "cv_key": "nguyen_van_a",
      "cv": { /* full CV dict */ },
      "score": 0.873,
      "matched_chunks": [
        { "section": "work_history", "text": "...", "score": 0.91 },
        { "section": "skills", "text": "...", "score": 0.85 }
      ],
      "llm_evaluation": {
        "score": 0.86,
        "recommendation": "good",
        "reasoning": "Ứng viên đáp ứng tốt yêu cầu backend Python/FastAPI, thiếu Kubernetes.",
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": ["Kubernetes"],
        "experience_fit": "3 năm kinh nghiệm đạt mức tối thiểu JD yêu cầu",
        "strengths": ["Kinh nghiệm microservices thanh toán"],
        "concerns": ["Chưa thể hiện Kubernetes"]
      }
    }
  ]
}
```

`llm_evaluation` chỉ có khi request bật `llm_evaluate=true`, ngược lại là `null`. Khi bật, `results` được **re-rank theo `llm_evaluation.score`** (vector `score` vẫn giữ để tham chiếu), CV nào eval thất bại thì `llm_evaluation=null` và tụt xuống dùng vector score làm fallback.

---

## Architecture

Project tổ chức theo **feature based** + **shared core layer**. Code dùng chung (LLM client, vector store, embeddings, schemas) nằm ở `core/`, mỗi feature có `service.py` + `schemas.py`.

```
├── main.py                       # Endpoints + lifespan; điều phối services
├── core/                         # Shared layer
│   ├── config.py                 #   - Đọc env vars
│   ├── database.py               #   - SQLAlchemy async engine
│   ├── models.py                 #   - ORM: cv_data, chat_sessions, chat_messages
│   ├── logger.py                 #   - Logging config (file rotate)
│   ├── schemas.py                #   - Chunk, SearchHit (shared retrieval/matching/chat)
│   ├── registries.py             #   - NameRegistry + SkillRegistry (in-memory filter)
│   ├── retrieval_utils.py        #   - cap_per_cv
│   ├── vector_store.py           #   - Qdrant async wrapper
│   ├── llm/                      #   - LLM client (retry + JSON repair)
│   │   ├── client.py             #     - LLMClient.extract_json
│   │   └── providers.py          #     - Groq / NVIDIA / 9Router adapters (OpenAI-compatible)
│   └── embeddings/               #   - Sentence-transformers
│       ├── embedder.py           #     - Bi-encoder (text -> vector)
│       └── reranker.py           #     - Cross-encoder (rerank)
├── features/
│   ├── extraction/               # 1. Đọc text từ PDF/DOCX
│   │   ├── service.py
│   │   ├── extractors/           #   - PdfExtractor, DocxExtractor
│   │   └── schemas.py
│   ├── parsing/                  # 2. LLM parse text -> JSON
│   │   ├── service.py
│   │   ├── llm/                  #   - prompts.py (system + extract) + experience.py (years_exp tất định)
│   │   └── schemas.py
│   ├── storage/                  # 3. CRUD MySQL cv_data
│   │   ├── service.py
│   │   └── schemas.py
│   ├── retrieval/                # 4. Chunk + embed + search + rerank
│   │   ├── service.py
│   │   ├── pipeline/             #   - chunker.py + filters.py (query parser)
│   │   └── schemas.py
│   ├── matching/                 # 5. JD <-> CV matching
│   │   ├── service.py            #   - parse JD -> search -> aggregate top-N -> score
│   │   ├── llm/prompts.py
│   │   └── schemas.py
│   └── chat/                     # 6. Conversational RAG (1 CV)
│       ├── service.py            #   - condense + answer; streaming
│       ├── llm/                  #   - answer.py, condense.py, prompts.py
│       ├── memory/store.py       #   - SessionStore (DB-backed) + cleanup task
│       └── schemas.py
└── static/                       # Frontend (vanilla JS, no build)
    ├── index.html                #   - Tabs: Upload file / Folder / Hồ sơ / JD Match
    ├── css/style.css
    └── js/{common,upload,storage,modal,jd_match,chat}.js
```

**Lý do tách core/:** LLM client, vector store, embeddings dùng bởi 3 feature (retrieval, matching, chat). Tách ra để tránh duplicate + import vòng giữa features.

---

## Processing flow

### Upload CV

`POST /UploadCV` qua 4 bước:

1. **Extraction** - `CVExtractorService` dùng `PdfExtractor` (pdfplumber, hỗ trợ bảng) hoặc `DocxExtractor` (python-docx). Chạy trong `asyncio.to_thread` tránh block event loop.
2. **Parsing** - `ParsingService` gọi LLM (9Router mặc định) trả về JSON đúng schema. Response làm sạch (bỏ markdown fence, `<think>`...) rồi parse. Có cơ chế repair JSON cho trailing comma, mismatched quote. `years_exp` không tin số LLM mà tính tất định từ `start`/`end` (YYYY-MM) của work_history, gộp khoảng chồng lấn rồi floor.
3. **Classify** - Check `is_cv` + `confidence` từ LLM, dưới `CV_CONFIDENCE_THRESHOLD` thì trả 422 "Not a CV". Pop 2 field meta khỏi parsed trước khi lưu.
4. **Storage + index** - `StorageService` upsert MySQL (key = filename lowercase, no ext); `RetrievalService.index_cv` cắt thành chunks theo section (header, summary, skills, education, work_history, projects, awards, certifications), embed, upsert Qdrant. Đồng thời cập nhật `NameRegistry` + `SkillRegistry` (in-memory) để query filter thấy CV mới. Lỗi index không fail request (MySQL là nguồn chính).

**Batch upload** (`/UploadMultipleCVs`): browser dùng `webkitdirectory` enumerate file, POST multipart; backend lọc `.pdf/.docx`, extract + parse song song bằng `asyncio.gather`, file unsupported báo lỗi cùng response.

### Semantic Search

`POST /Search/Semantic` qua 5 bước:

1. **Parse query** - `parse_query()` tách filter ra khỏi câu hỏi: years (vi/en: "tối thiểu 5 năm", "5+ năm", "dưới 10 năm", "at least 3 yrs"), skills (lấy động từ `SkillRegistry` - chỉ skill đã từng xuất hiện trong DB).
2. **Match tên** - `NameRegistry.match()` tìm cv_keys có MỌI token tên xuất hiện trong query (vd "Nguyễn Văn A có Python?" -> match CV tên "Nguyễn Văn A").
3. **Embed + Qdrant search** - `Embedder` biến query -> vector; Qdrant search với hard filter (years/skills/cv_keys).
4. **Rerank** - Cross-encoder chấm lại điểm; sigmoid về 0..1 cho đồng nhất với cosine.
5. **Cap + group** - `cap_per_cv(MAX_CHUNKS_PER_CV)` đảm bảo mỗi CV ≤ 3 chunks. Group theo `cv_key`, fetch full CV từ MySQL, sort theo score giảm dần.

`top_k=null` (unlimited): skip rerank vì pool có thể lớn, chỉ trả raw Qdrant cosine.

### JD Matching

`POST /Match/JD` (text) hoặc `/Match/JD/Upload` (PDF/DOCX) qua 8 bước (bước 8 tuỳ chọn):

1. **Parse JD** - LLM extract `summary`, `required_skills`, `min/max_years_exp`. Fail thì fallback dùng raw JD làm summary.
2. **Embed summary** - biến summary thành query vector.
3. **Search Qdrant** - lấy tối đa `UNLIMITED_FETCH_LIMIT` chunks; hard filter years/skills tuỳ `strict_*_filter` flag.
4. **Cap chunks/CV** - mỗi CV tối đa `MAX_CHUNKS_PER_CV` chunks.
5. **Rerank** (nếu có reranker) - chấm lại pool đã cap, cap lần 2 idempotent.
6. **Aggregate** - mỗi CV lấy top-N chunks (N = len(`JD_AGG_WEIGHTS`)), tính weighted avg score; CV có < N chunks thì renormalize weights theo n thực dùng.
7. **Fetch CV + slice top_k** - lấy CV detail từ MySQL, skip CV bị xoá khỏi DB nhưng còn trong Qdrant.
8. **LLM evaluate** (tuỳ chọn, khi `llm_evaluate=true`) - chấm song song từng CV (tối đa `JD_LLM_EVAL_CONCURRENCY`) độ phù hợp với JD: score, recommendation, skill khớp/thiếu, experience_fit, điểm mạnh/lưu ý. Re-rank `results` theo điểm LLM; CV eval fail tụt xuống dùng vector score làm fallback.

### Conversational Chat

`POST /Chat/Sessions/{id}/Messages[/Stream]` qua 5 bước:

1. **Load session + history** - `SessionStore.get()` lấy session info (`cv_key` đã lock). `get_history()` lấy `CHAT_HISTORY_LAST_N` message gần nhất.
2. **Condense** - lượt đầu (no history) bỏ qua. Sau đó LLM viết lại câu hỏi follow-up thành standalone (vd "anh ấy có dùng React?" -> "Nguyễn Văn A có dùng React?").
3. **Retrieve** - `RetrievalService.search_within_cv()` lấy top `CHAT_RETRIEVE_TOP_K` chunks trong đúng 1 CV (filter cứng `cv_key`).
4. **Guardrail** - top score < `CHAT_REFUSAL_SCORE_THRESHOLD` (0.3) -> trả reject ngay, không gọi answer LLM. Refusal vẫn được lưu vào DB.
5. **Answer + persist** - Answer LLM dùng context chunks, prompt cấm bịa. `append_pair()` lưu user + assistant message trong 1 transaction. LLM trả rỗng (lỗi/rate-limit) thì thay bằng `LLM_ERROR_MESSAGE` thân thiện và bỏ sources, tránh lưu message rỗng.

**Streaming** (`/Stream`): bước 5 dùng `astream_events` yield từng text chunk. Cuối stream gửi `\n__SOURCES__\n` sentinel + JSON sources để frontend tách. Tin nhắn chỉ lưu sau khi stream xong (client đóng giữa chừng -> không lưu phần dở).

**Persistence**: `chat_sessions` + `chat_messages` lưu MySQL với FK CASCADE. Task nền xoá phiên quá `CHAT_SESSION_TTL_HOURS` chạy mỗi 1h (UTC clock, đồng bộ với `UTC_TIMESTAMP()` của DB). Frontend lưu `{cv_key: session_id}` trong localStorage để giữ chat qua reload trang.

---

## UI

Frontend SPA 4 tab:

- **Upload file** - upload 1 CV (drag-drop hoặc click chọn file)
- **Upload Folder** - chọn 1 folder, browser enumerate file, gửi multipart batch
- **Hồ sơ** - list CV + search semantic. Click CV -> modal:
  - Mode **view**: hiện đầy đủ thông tin
  - Mode **edit**: sửa từng field/entry, save -> re-index Qdrant
  - Mode **chat**: chat với CV trong modal - session lưu localStorage, reset/xoá session bằng nút Reset
  - Xoá CV
- **JD Match** - paste JD text hoặc upload PDF/DOCX, hệ thống extract yêu cầu, embed, match top-K CV với score bar. Tick **Chấm điểm bằng LLM** để re-rank theo điểm LLM + hiện badge recommendation, nhận xét, skill khớp/thiếu, điểm mạnh/lưu ý từng CV

---

## Testing with curl

### Upload & CRUD

```bash
# Upload 1 file
curl -X POST http://localhost:8000/UploadCV -F "file=@/path/to/cv.pdf"

# Upload batch (browser folder picker - qua API gửi nhiều file)
curl -X POST http://localhost:8000/UploadMultipleCVs \
  -F "files=@cv1.pdf" -F "files=@cv2.pdf" -F "files=@cv3.docx"

# List tất cả
curl http://localhost:8000/Storage

# Chi tiết 1 CV
curl http://localhost:8000/Storage/nguyen_van_a

# Update (gửi parsed dict đầy đủ)
curl -X PATCH http://localhost:8000/Storage/nguyen_van_a \
  -H "Content-Type: application/json" \
  -d '{"parsed": {"name": "Nguyễn Văn A", "email": "...", "skills": ["Python"], ...}}'

# Xoá
curl -X DELETE http://localhost:8000/Storage/nguyen_van_a
```

### Semantic search

```bash
# Top-K mặc định (top_k=null = unlimited, skip rerank)
curl -X POST http://localhost:8000/Search/Semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "kỹ sư Python 3 năm FastAPI", "top_k": 5}'

# Filter qua câu hỏi tự nhiên
curl -X POST http://localhost:8000/Search/Semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "Nguyễn Văn A có biết Docker?", "top_k": 10}'
```

### JD Matching

```bash
# Paste JD text (llm_evaluate=true để LLM chấm điểm + re-rank)
curl -X POST http://localhost:8000/Match/JD \
  -H "Content-Type: application/json" \
  -d '{
    "jd_text": "Tuyển Backend Engineer 3+ năm Python, FastAPI, PostgreSQL. Đã làm với Docker, Kafka.",
    "top_k": 5,
    "strict_skills_filter": false,
    "strict_years_filter": true,
    "llm_evaluate": true
  }'

# Upload JD file
curl -X POST http://localhost:8000/Match/JD/Upload \
  -F "file=@jd.pdf" -F "top_k=5" -F "strict_years_filter=true" -F "llm_evaluate=true"
```

### Chatbot

```bash
# 1. Tạo session (cv_key = filename lowercase, no ext)
curl -X POST http://localhost:8000/Chat/Sessions \
  -H "Content-Type: application/json" \
  -d '{"cv_key": "alex_petrov"}'
# Response: {"session_id":"1f82537c-006d-...","cv_key":"alex_petrov"}

session_id=<session_id từ bước 1>

# 2. Non-streaming
curl -X POST http://localhost:8000/Chat/Sessions/session_id/Messages \
  -H "Content-Type: application/json" \
  -d '{"message": "Ứng viên có biết Python?"}'

# 3. Streaming (curl -N để xem token chảy realtime)
curl -N -X POST http://localhost:8000/Chat/Sessions/session_id/Messages/Stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Anh ấy đã làm ở công ty nào?"}'

# 4. Full history
curl http://localhost:8000/Chat/Sessions/session_id

# 5. Xoá session
curl -X DELETE http://localhost:8000/Chat/Sessions/session_id
```

---

# CVExtract

Hệ thống trích xuất thông tin từ CV (PDF, DOCX). Người dùng upload file, hệ thống đọc nội dung, gọi LLM để bóc tách các trường (họ tên, email, kỹ năng, kinh nghiệm, dự án, giải thưởng, chứng chỉ...) thành JSON có cấu trúc, lưu xuống MySQL + index vào Qdrant để tìm kiếm ngữ nghĩa và chat hỏi đáp với từng CV.

---

## Chạy bằng Docker

```bash
# 1. Tạo file .env từ template, điền API key (Groq / Gemini / NVIDIA)
cp .env.example .env

# 2. Build + chạy 3 service (app + MySQL + Qdrant)
docker compose up -d --build

# 3. Xem log app
docker compose logs -f app
```

Truy cập:

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

## Cấu hình

Tất cả biến môi trường nằm trong `.env` (copy từ `.env.example`). Chia thành 6 nhóm:

### LLM API keys

Điền key của provider sẽ dùng. Chỉ cần ít nhất 1 key (Groq mặc định).

| Biến              | Mô tả                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| `GROQ_API_KEY`   | API key Groq, lấy ở [console.groq.com](https://console.groq.com). Dùng cho cả parsing và chat |
| `GEMINI_API_KEY` | API key Google Gemini, lấy ở[aistudio.google.com](https://aistudio.google.com)                    |
| `NVIDIA_API_KEY` | API key NVIDIA NIM, lấy ở[build.nvidia.com](https://build.nvidia.com)                             |

### MySQL (chỉ dùng khi chạy Docker Compose)

Docker Compose dùng 2 biến này để khởi tạo container MySQL. Khi chạy local thì chỉ cần `DATABASE_URL`.

| Biến                   | Default       | Mô tả                                        |
| ----------------------- | ------------- | ---------------------------------------------- |
| `MYSQL_ROOT_PASSWORD` | `password`  | Mật khẩu root MySQL trong container          |
| `MYSQL_DATABASE`      | `cvextract` | Tên database được tạo khi container start |

### Database URL

| Biến            | Default                                                 | Mô tả                                                                                                            |
| ---------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `DATABASE_URL` | `mysql+aiomysql://root:password@mysql:3306/cvextract` | Connection string MySQL. Docker Compose dùng host =`mysql` (tên service); chạy local đổi sang `localhost` |

### Qdrant (vector database)

| Biến                 | Default                | Mô tả                                                                                 |
| --------------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| `QDRANT_URL`        | `http://qdrant:6333` | URL Qdrant. Docker Compose dùng host =`qdrant`; chạy local đổi sang `localhost` |
| `QDRANT_COLLECTION` | `cv_chunks_v1`       | Tên collection đang dùng:`cv_chunks_v1` (default, 384d)                            |

### Embedding & Reranker (cho semantic search + chat)

| Biến               | Default                                   | Mô tả                                                                                                                                     |
| ------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Model sentence-transformers dùng để biến text thành vector. Phải match với `QDRANT_COLLECTION` về dim                             |
| `EMBEDDING_DIM`   | `384`                                   | Số chiều của vector. Phải khớp với model, đổi sai sẽ báo lỗi lúc khởi động                                                   |
| `RERANKER_MODEL`  | `BAAI/bge-reranker-v2-m3`               | Model cross-encoder để chấm điểm lại lần 2. Để rỗng (`RERANKER_MODEL=`) để tắt rerank cho nhanh nhưng chính xác kém hơn |

### Conversational Chat

| Biến                            | Default                                       | Mô tả                                                                                                                                                                                                                                                     |
| -------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CHAT_LLM_MODEL`               | `meta-llama/llama-4-scout-17b-16e-instruct` | Model Groq dùng cho cả 2 bước: viết lại câu hỏi (condense) và trả lời (answer)                                                                                                                                                                   |
| `CHAT_SESSION_TTL_HOURS`       | `24`                                        | Phiên chat không hoạt động quá số giờ này thì task nền tự xoá                                                                                                                                                                                  |
| `CHAT_HISTORY_LAST_N`          | `10`                                        | Số tin nhắn gần nhất load vào prompt khi viết lại câu hỏi. Tăng để nhớ lâu hơn nhưng tốn token, giảm để tiết kiệm                                                                                                                     |
| `CHAT_REFUSAL_SCORE_THRESHOLD` | `0.3`                                       | Điểm cao nhất của đoạn CV tìm được dưới ngưỡng này thì bot từ chối luôn, không gọi AI trả lời. Score đã sigmoid về 0..1 cho cả khi có/không reranker. Log có `top_score=X.XXX` cho mọi query để tham khảo điều chỉnh |

---

## Endpoints

| Method     | Endpoint                                | Mô tả                                    |
| ---------- | --------------------------------------- | ------------------------------------------ |
| `GET`    | `/`                                   | Frontend                                   |
| `POST`   | `/UploadCV`                           | Upload 1 file CV                           |
| `POST`   | `/UploadMultipleCVs`                  | Upload cả thư mục                       |
| `GET`    | `/Storage`                            | Xem tất cả CV đã lưu                  |
| `POST`   | `/Search/Semantic`                    | Tìm CV theo ngữ nghĩa (vector + rerank) |
| `POST`   | `/Chat/Sessions`                      | Tạo phiên chat lock vào 1 CV            |
| `POST`   | `/Chat/Sessions/{id}/Messages`        | Gửi message (non-streaming)               |
| `POST`   | `/Chat/Sessions/{id}/Messages/Stream` | Gửi message, stream từng token           |
| `GET`    | `/Chat/Sessions/{id}`                 | Xem full history của session              |
| `DELETE` | `/Chat/Sessions/{id}`                 | Xoá session (CASCADE messages)            |

---

## Ví dụ response

```json
{
  "message": "CV uploaded successfully",
  "results": {
    "file_name": "nguyen_van_a.pdf",
    "extension": ".pdf",
    "status": "success",
    "text": {
      "name": "Nguyễn Văn A",
      "email": "nguyenvana@gmail.com",
      "phone": "0901234567",
      "years_exp": 3,
      "skills": ["Python", "FastAPI", "MySQL", "Docker"],
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
          "description": "Phát triển hệ thống thanh toán microservices với Python/FastAPI, Kafka, PostgreSQL."
        }
      ],
      "projects": [
        {
          "name": "CVExtract",
          "description": "Hệ thống trích xuất CV với RAG",
          "tech": ["Python", "FastAPI", "Qdrant"],
          "duration": "2024",
          "url": "https://github.com/user/cvextract"
        }
      ],
      "awards": [
        {
          "name": "Giải nhất hackathon ABC",
          "issuer": "Công ty ABC",
          "year": "2023",
          "description": ""
        }
      ],
      "certifications": [
        {
          "name": "AWS Solutions Architect Associate",
          "issuer": "Amazon Web Services",
          "year": "2023"
        }
      ],
      "summary": "Backend developer với 3 năm kinh nghiệm Python..."
    }
  }
}
```

3 trường `projects`, `awards`, `certifications` đều optional — nếu CV không có thì trả mảng rỗng.

---

## Kiến trúc

Project tổ chức theo **feature based**. Mỗi feature có `service.py` + `schemas.py` ở gốc, các file phụ chia vào subfolder theo trách nhiệm.

```
├── main.py                  # Điều phối services, định nghĩa endpoints
├── core/                    # Hạ tầng dùng chung
│   ├── config.py            #   - Đọc biến môi trường
│   ├── database.py          #   - SQLAlchemy engine + session
│   ├── models.py            #   - cv_data, chat_sessions, chat_messages
│   └── logger.py            #   - Cấu hình logging
├── features/
│   ├── extraction/          # 1. Đọc text từ PDF/DOCX
│   │   ├── service.py
│   │   ├── extractors/      #   - PdfExtractor (pdfplumber), DocxExtractor (python-docx)
│   │   └── schemas.py
│   ├── parsing/             # 2. Gọi LLM parse text thành JSON
│   │   ├── service.py
│   │   ├── llm/             #   - Client + providers (Groq, Gemini, NVIDIA) + prompt
│   │   └── schemas.py
│   ├── storage/             # 3. Lưu/đọc CV trong MySQL
│   │   ├── service.py
│   │   └── schemas.py
│   ├── retrieval/           # 4. Chunk + embed + Qdrant vector search + rerank
│   │   ├── service.py    
│   │   ├── models/          #   - Embedder + Reranker (sentence-transformers)
│   │   ├── pipeline/        #   - Chunker + VectorStore + query parser
│   │   └── schemas.py
│   └── chat/                # 5. Conversational RAG (chat với 1 CV)
│       ├── service.py    
│       ├── llm/             #   - 2 pipeline (condense, answer) + prompts
│       ├── memory/          #   - SessionStore (lưu session + message vào MySQL)
│       └── schemas.py
└── static/index.html        # Frontend
```

**Lý do chọn feature based:** thêm tính năng mới chỉ đụng 1 folder duy nhất, không sửa nhiều chỗ.

---

## Flow xử lý

### Upload

Khi user upload 1 file CV qua `POST /UploadCV`, request đi qua 4 bước:

1. **Extraction** - `CVExtractorService` chọn extractor phù hợp theo extension (`PdfExtractor` dùng pdfplumber, `DocxExtractor` dùng python-docx). Việc đọc file chạy trong thread riêng (`asyncio.to_thread`) để không block event loop.
2. **Parsing** - `ParsingService` gửi text cho LLM (Groq Llama 4 Scout mặc định) kèm prompt yêu cầu trả về JSON đúng schema (name, email, skills, work_history, projects, awards, certifications, ...). Response được làm sạch (bỏ markdown fence, bỏ thẻ `<think>` nếu có) rồi parse thành dict.
3. **Storage** - `StorageService` upsert vào MySQL: nếu `key` (= tên file viết thường, không đuôi) đã tồn tại thì update, không thì insert mới. Vừa lưu raw JSON vừa tách ra các cột riêng (name, email, phone, skills, projects, awards, certifications...) để query nhanh.
4. **Index vector** - `RetrievalService.index_cv` cắt CV thành các chunk theo từng section (header, summary, skills, education, work_history, projects, awards, certifications), biến mỗi đoạn thành vector và upsert vào Qdrant. Lỗi ở bước này không làm fail request (MySQL là nguồn chính, Qdrant có thể rebuild).

**Với batch upload (`/UploadMultipleCVs`):** cả extraction và parsing chạy song song bằng `asyncio.gather`.

### Search

Khi user gửi câu truy vấn qua `POST /Search/Semantic`, request đi qua 5 bước:

1. **Parse query** - `parse_query()` tách các filter ra khỏi câu hỏi: số năm kinh nghiệm (vd "5 năm"), skill (vd "Python", "FastAPI"), role (vd "data engineer", "developer"). Phần text còn lại vẫn dùng để embed.
2. **Embed** - `Embedder` biến câu hỏi thành vector (chuẩn hoá độ dài để so sánh nhanh). Chạy trong thread riêng vì là phép tính nặng CPU.
3. **Vector search + filter** — Qdrant tìm top-20 đoạn CV gần nhất với vector câu hỏi, áp filter cứng theo `years_exp`/`skills` nếu có. Nếu filter ra 0 kết quả thì tự bỏ filter, search lại.
4. **Rerank** - `Reranker` (cross-encoder bge-reranker-v2-m3) chấm lại điểm từng cặp (câu hỏi, đoạn CV), sắp xếp giảm dần. Điểm sigmoid về 0..1 cho đồng nhất.
5. **Role boost** - đoạn nào chứa role khớp với câu hỏi được kéo lên đầu (sort ổn định, giữ thứ tự rerank trong cùng nhóm). Cuối cùng cắt top-K, gom theo `cv_key`, fetch full CV từ MySQL trả về.

### Conversational Chat

Khi user gửi 1 tin nhắn qua `POST /Chat/Sessions/{id}/Messages`, request đi qua 5 bước:

1. **Load session + history** - `SessionStore.get()` lấy thông tin phiên (kèm `cv_key` đã lock). `get_history()` lấy N tin nhắn gần nhất (mặc định 10) làm ngữ cảnh cho bước viết lại câu hỏi. Không có session → trả 404.
2. **Condense** - nếu có lịch sử, gọi AI viết lại câu hỏi follow-up thành câu đầy đủ (vd "anh ấy có dùng React?" -> "Nguyễn Văn A có dùng React?"). Lượt đầu (chưa có lịch sử) thì bỏ qua bước này, dùng nguyên câu hỏi gốc.
3. **Retrieve** - `RetrievalService.search_within_cv()` tìm top-5 đoạn CV liên quan, lọc bắt buộc theo `cv_key` của session (không fallback). Không apply role boost vì chỉ có 1 CV trong pool.
4. **Guardrail** - nếu không tìm được đoạn nào hoặc điểm cao nhất dưới `CHAT_REFUSAL_SCORE_THRESHOLD` (mặc định 0.3), trả ngay reject, không gọi llm trả lời (tiết kiệm token). Câu Reject vẫn được lưu vào DB.
5. **Answer + persist** - `Answer AI` (ChatGroq llama-4-scout) sinh câu trả lời dựa trên các đoạn CV, prompt cấm bịa. Sau khi AI trả lời xong, `append_pair()` lưu cả tin nhắn user và bot vào DB trong 1 lần ghi (nếu lỗi giữa chừng thì không cái nào lưu, tránh bỏ rớt lẻ tin user).

**Bản streaming** (`/Stream`) chạy y hệt 5 bước trên nhưng bước 5 dùng `astream()` gửi từng token text về client. Cuối stream gửi kèm ký hiệu `\n__SOURCES__\n` + JSON sources để frontend cắt chuỗi tách phần trả lời và phần nguồn. Tin nhắn chỉ được lưu sau khi stream xong; nếu client đóng tab giữa chừng thì không lưu phần dở.

**Persistence** - phiên chat + tin nhắn lưu vào MySQL (`chat_sessions`, `chat_messages` với FK CASCADE). Sống qua restart server. Task nền xoá phiên quá `CHAT_SESSION_TTL_HOURS` chạy mỗi 1h. Frontend lưu map `{cv_key: session_id}` trong localStorage để giữ chat khi refresh trang; mỗi CV có nút "Bắt đầu lại" để xoá session cũ và tạo mới.

---

## Test bằng curl

### Upload & Storage

```bash
# Upload 1 file
curl -X POST http://localhost:8000/UploadCV \
  -F "file=@/path/to/cv.pdf"

# Upload cả thư mục
curl -X POST http://localhost:8000/UploadMultipleCVs \
  -F "folder_path=/path/to/cv_folder"

# Xem tất cả CV đã lưu
curl http://localhost:8000/Storage
```

### Tìm kiếm ngữ nghĩa

```bash
curl -X POST http://localhost:8000/Search/Semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "kỹ sư Python có kinh nghiệm FastAPI", "top_k": 5}'
```

### Chat bot

```bash
# 1. Tạo session (cv_key = tên file không đuôi, lowercase)
curl -X POST http://localhost:8000/Chat/Sessions \
  -H "Content-Type: application/json" \
  -d '{"cv_key": "alex_petrov"}'
# Trả về: {"session_id":"1f82537c-006d-...","cv_key":"alex_petrov"}

# 2. Chat non-streaming
SID=1f82537c-006d-469b-8159-803d760543d1
curl -X POST http://localhost:8000/Chat/Sessions/<session_id>/Messages \
  -H "Content-Type: application/json" \
  -d '{"message": "Ứng viên có biết Python?"}'

# 3. Chat streaming (curl -N để xem token chảy realtime)
curl -N -X POST http://localhost:8000/Chat/Sessions/<session_id>/Messages/Stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Anh ấy đã làm ở đâu?"}'

# 4. Xem full history
curl http://localhost:8000/Chat/Sessions/<session_id>

# 5. Xoá session (CASCADE xoá luôn messages)
curl -X DELETE http://localhost:8000/Chat/Sessions/<session_id>
```

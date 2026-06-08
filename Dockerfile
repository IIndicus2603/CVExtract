# Stage `app`: FastAPI Python service
FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu torch==2.4.1 && \
    pip install -r requirements.txt

COPY . .

RUN mkdir -p logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/docs > /dev/null || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


# Stage `router9`: 9Router (Node + better-sqlite3)
FROM node:20-slim AS router9

# Build tools cho native binding của better-sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

# 9router chạy từ app/ subdir; require resolve trong app/node_modules.
# Cài better-sqlite3 đúng vào app/ để require tìm thấy.
RUN npm install -g 9router && \
    cd "$(npm root -g)/9router/app" && \
    npm install better-sqlite3

EXPOSE 20128
VOLUME ["/data"]

ENV DATA_DIR=/data \
    NEXT_PUBLIC_BASE_URL=http://localhost:20128

# Bind 0.0.0.0 để các container khác trong docker network gọi được;
# -n: không mở browser; --skip-update: không tự update; -l: in log ra stdout
CMD ["9router", "-H", "0.0.0.0", "-p", "20128", "-n", "--skip-update", "-l"]

# Rerank lại lần 2 các kết quả tìm vector để chính xác hơn (cross-encoder)

import logging
import math
import time
from typing import Sequence

from sentence_transformers import CrossEncoder

from features.retrieval.schemas import SearchHit

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str):
        logger.info("Loading cross-encoder reranker: %s", model_name)
        t0 = time.perf_counter()
        self._model = CrossEncoder(model_name)
        logger.info("Reranker loaded in %.2fs", time.perf_counter() - t0)

    # Rerank lại từng cặp (câu hỏi, chunk CV), sắp xếp giảm dần, lấy top_k
    # Điểm mới đè lên điểm cũ trong SearchHit
    def rerank(self, query: str, hits: Sequence[SearchHit], top_k: int) -> list[SearchHit]:
        if not hits:
            return []

        pairs = [(query, h.chunk_text) for h in hits]
        scores = self._model.predict(pairs, show_progress_bar=False)

        # Ép điểm thô về khoảng 0..1 (hàm sigmoid) để đồng nhất với điểm cosine
        # Hàm này không đổi thứ tự sắp xếp, ngưỡng từ chối dùng chung được cho cả 2 trường hợp
        scored = [
            h.model_copy(update={"score": 1.0 / (1.0 + math.exp(-float(s)))})
            for h, s in zip(hits, scores)
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

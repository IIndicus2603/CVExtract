# Cross-encoder rerank, chính xác hơn cosine vector search

import logging
import math
import time
from typing import Sequence

from sentence_transformers import CrossEncoder

from core.schemas import SearchHit

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str):
        """Load cross-encoder model"""
        logger.info("Loading cross-encoder reranker: %s", model_name)
        t0 = time.perf_counter()
        self._model = CrossEncoder(model_name)
        logger.info("Reranker loaded in %.2fs", time.perf_counter() - t0)

    def rerank(self, query: str, hits: Sequence[SearchHit], top_k: int) -> list[SearchHit]:
        """Score lại từng (query, chunk), sigmoid về 0..1 cho đồng nhất với cosine, sort giảm dần, lấy top_k"""
        if not hits:
            return []

        pairs = [(query, h.chunk_text) for h in hits]
        scores = self._model.predict(pairs, show_progress_bar=False)

        scored = [
            h.model_copy(update={"score": 1.0 / (1.0 + math.exp(-float(s)))})
            for h, s in zip(hits, scores)
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

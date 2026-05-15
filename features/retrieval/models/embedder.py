# sentence-transformers: biến text thành vector số

import logging
import time
from typing import Sequence

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str, expected_dim: int):
        logger.info("Loading embedding model: %s", model_name)
        t0 = time.perf_counter()
        self._model = SentenceTransformer(model_name)
        elapsed = time.perf_counter() - t0

        # Báo lỗi sớm nếu đổi model mà quên cập nhật EMBEDDING_DIM trong config
        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim != expected_dim:
            raise ValueError(
                f"Model dim mismatch: expected {expected_dim}, got {actual_dim}. "
                f"Update EMBEDDING_DIM in config or change model."
            )

        logger.info("Model loaded in %.2fs | dim=%d", elapsed, actual_dim)
        self._dim = actual_dim

    @property
    def dim(self) -> int:
        return self._dim

    # Biến 1 hoặc nhiều text thành vector số; chuẩn hoá độ dài để so sánh nhanh hơn
    def encode(self, texts: str | Sequence[str]) -> list[list[float]]:
        items = [texts] if isinstance(texts, str) else list(texts)
        if not items:
            return []

        return self._model.encode(
            items,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

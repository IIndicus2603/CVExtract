# sentence-transformers bi-encoder, text thành vector

import logging
import time
from typing import Sequence

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str, expected_dim: int):
        """Load model + verify dim khớp config"""
        logger.info("Loading embedding model: %s", model_name)
        t0 = time.perf_counter()
        self._model = SentenceTransformer(model_name)
        elapsed = time.perf_counter() - t0

        # Đổi model mà quên cập nhật EMBEDDING_DIM thì báo lỗi sớm
        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim != expected_dim:
            raise ValueError(
                f"Model dim mismatch: expected {expected_dim}, got {actual_dim}. "
                f"Update EMBEDDING_DIM in config or change model."
            )

        logger.info("Model loaded in %.2fs | dim=%d", elapsed, actual_dim)

    def encode(self, texts: str | Sequence[str]) -> list[list[float]]:
        """Normalize_embeddings=True để cosine = dot product"""
        items = [texts] if isinstance(texts, str) else list(texts)
        if not items:
            return []
        return self._model.encode(
            items,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

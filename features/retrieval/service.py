# Điều phối retrieval, chunk rồi embed rồi upsert Qdrant, search + rerank

import asyncio
import logging
import time

from core.config import MAX_CHUNKS_PER_CV, RERANK_CANDIDATES, UNLIMITED_FETCH_LIMIT
from core.embeddings.embedder import Embedder
from core.embeddings.reranker import Reranker
from core.registries import NameRegistry, SkillRegistry
from core.retrieval_utils import cap_per_cv
from core.schemas import SearchHit
from core.vector_store import VectorStore

from features.retrieval.pipeline.chunker import CVChunker
from features.retrieval.pipeline.filters import parse_query

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, embedder: Embedder, vector_store: VectorStore, reranker: Reranker | None = None, name_registry: NameRegistry | None = None, skill_registry: SkillRegistry | None = None):
        """Compose embedder + vector_store + (optional) reranker + registries"""
        self._embedder = embedder
        self._vector_store = vector_store
        self._reranker = reranker
        self._chunker = CVChunker()
        self._name_registry = name_registry
        self._skill_registry = skill_registry

    async def index_cv(self, cv_key: str, parsed: dict) -> int:
        """Chunk + embed + upsert Qdrant, cập nhật registries"""
        if not parsed:
            logger.warning("Skip indexing '%s': empty parsed data", cv_key)
            return 0

        chunks = self._chunker.chunk(cv_key, parsed)
        if not chunks:
            logger.warning("Skip indexing '%s': no chunks generated", cv_key)
            return 0

        # Encode chạy CPU-bound nên thread riêng tránh block event loop
        t0 = time.perf_counter()
        vectors = await asyncio.to_thread(
            self._embedder.encode,
            [c.text for c in chunks],
        )
        encode_time = time.perf_counter() - t0

        await self._vector_store.delete_by_cv_key(cv_key)
        await self._vector_store.upsert_chunks(chunks, vectors)

        if self._name_registry is not None:
            await self._name_registry.add(cv_key, parsed.get("name"))
        if self._skill_registry is not None:
            await self._skill_registry.add(parsed.get("skills"))

        logger.info(
            "Indexed '%s': %d chunks (encode=%.2fs)",
            cv_key, len(chunks), encode_time,
        )
        return len(chunks)

    async def remove_cv(self, cv_key: str) -> None:
        """Xoá Qdrant chunks + NameRegistry, SkillRegistry không track per-cv nên skip"""
        await self._vector_store.delete_by_cv_key(cv_key)
        if self._name_registry is not None:
            await self._name_registry.remove(cv_key)

    async def _search_common(
        self,
        *,
        query_vector: list[float],
        rerank_query: str,
        top_k: int,
        cv_key: str | None = None,
        cv_keys: list[str] | None = None,
        min_years_exp: int | None = None,
        max_years_exp: int | None = None,
        required_skills: list[str] | None = None,
        keep_pool_after_rerank: bool = False,
    ) -> tuple[list[SearchHit], int, float]:
        """Vector search + (optional) rerank, keep_pool_after_rerank giữ toàn pool cho cap_per_cv caller chạy, ngược lại cắt top_k luôn"""
        fetch_k = RERANK_CANDIDATES if self._reranker else top_k

        hits = await self._vector_store.search(
            query_vector, top_k=fetch_k, cv_key=cv_key, cv_keys=cv_keys,
            min_years_exp=min_years_exp, max_years_exp=max_years_exp,
            required_skills=required_skills,
        )

        rerank_time = 0.0
        if self._reranker and hits:
            rerank_top = len(hits) if keep_pool_after_rerank else top_k
            t_rr = time.perf_counter()
            hits = await asyncio.to_thread(self._reranker.rerank, rerank_query, hits, rerank_top)
            rerank_time = time.perf_counter() - t_rr
        elif not self._reranker:
            hits = hits[:top_k]

        return hits, fetch_k, rerank_time

    async def search(self, query: str, top_k: int | None = None) -> list[SearchHit]:
        """Search toàn bộ CV, top_k=None, unlimited (skip rerank vì pool lớn)"""
        t0 = time.perf_counter()

        pq = parse_query(query, self._skill_registry)
        matched_cv_keys = self._name_registry.match(query) if self._name_registry else []

        vectors = await asyncio.to_thread(self._embedder.encode, pq.text)
        query_vector = vectors[0]

        rerank_time = 0.0
        if top_k is None:
            hits = await self._vector_store.search(
                query_vector, top_k=UNLIMITED_FETCH_LIMIT,
                cv_keys=matched_cv_keys or None,
                min_years_exp=pq.min_years_exp,
                max_years_exp=pq.max_years_exp,
                required_skills=pq.required_skills,
            )
        else:
            hits, _, rerank_time = await self._search_common(
                query_vector=query_vector,
                rerank_query=pq.text,
                top_k=top_k,
                cv_keys=matched_cv_keys or None,
                min_years_exp=pq.min_years_exp,
                max_years_exp=pq.max_years_exp,
                required_skills=pq.required_skills,
                keep_pool_after_rerank=True,
            )

        hits = cap_per_cv(hits, MAX_CHUNKS_PER_CV)
        if top_k is not None:
            hits = hits[:top_k]

        unique_cvs = len({h.cv_key for h in hits})
        elapsed = time.perf_counter() - t0
        logger.info(
            "Search '%s' | filters=(years>=%s, years<=%s, skills=%s, names=%d) | top_k=%s chunks=%d cvs=%d (cap=%d/cv) | %.3fs (rerank=%.3fs)",
            query[:50], pq.min_years_exp, pq.max_years_exp, pq.required_skills,
            len(matched_cv_keys), top_k, len(hits), unique_cvs, MAX_CHUNKS_PER_CV, elapsed, rerank_time,
        )
        return hits

    async def search_within_cv(self, query: str, cv_key: str, top_k: int = 5) -> list[SearchHit]:
        """Search trong đúng 1 CV (dùng cho chatbot)"""
        t0 = time.perf_counter()

        vectors = await asyncio.to_thread(self._embedder.encode, query)
        query_vector = vectors[0]

        hits, fetch_k, rerank_time = await self._search_common(
            query_vector=query_vector,
            rerank_query=query,
            top_k=top_k,
            cv_key=cv_key,
        )

        elapsed = time.perf_counter() - t0
        logger.info(
            "SearchWithinCV cv_key=%s | query='%s' | candidates=%d top_k=%d | %.3fs (rerank=%.3fs)",
            cv_key, query[:50], fetch_k, len(hits), elapsed, rerank_time,
        )
        return hits

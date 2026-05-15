# điều phối tìm kiếm CV: cắt nhỏ CV, biến text thành vector, lưu/tìm trong Qdrant, rerank

import asyncio
import logging
import time

from features.retrieval.models.embedder import Embedder
from features.retrieval.models.reranker import Reranker
from features.retrieval.pipeline.chunker import CVChunker
from features.retrieval.pipeline.query_parser import parse_query, text_matches_role
from features.retrieval.pipeline.vector_store import VectorStore
from features.retrieval.schemas import SearchHit


# Số kết quả thô lấy ra để rerank
RERANK_CANDIDATES = 20

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, embedder: Embedder, vector_store: VectorStore, reranker: Reranker | None = None):
        self._embedder = embedder
        self._vector_store = vector_store
        self._reranker = reranker
        self._chunker = CVChunker()

    # Lưu 1 CV vào Qdrant: cắt nhỏ, biến text thành vector, ghi vào DB
    async def index_cv(self, cv_key: str, parsed: dict) -> int:
        if not parsed:
            logger.warning("Skip indexing '%s': empty parsed data", cv_key)
            return 0

        chunks = self._chunker.chunk(cv_key, parsed)
        if not chunks:
            logger.warning("Skip indexing '%s': no chunks generated", cv_key)
            return 0

        # Biến text thành vector chạy nặng CPU, đưa ra thread riêng để không đứng app
        t0 = time.perf_counter()
        vectors = await asyncio.to_thread(
            self._embedder.encode,
            [c.text for c in chunks],
        )
        encode_time = time.perf_counter() - t0

        await self._vector_store.delete_by_cv_key(cv_key)
        await self._vector_store.upsert_chunks(chunks, vectors)

        logger.info(
            "Indexed '%s': %d chunks (encode=%.2fs)",
            cv_key, len(chunks), encode_time,
        )
        return len(chunks)

    # Helper chung: vector search Qdrant + rerank
    # fallback_no_filter: 0 hit thì search lại bỏ years/skills (giữ cv_key)
    # keep_pool_after_rerank: rerank giữ toàn bộ hits (cho role boost) hay cắt top_k luôn
    async def _search_common(
        self,
        *,
        query_vector: list[float],
        rerank_query: str,
        top_k: int,
        cv_key: str | None = None,
        min_years_exp: int | None = None,
        required_skills: list[str] | None = None,
        fallback_no_filter: bool = False,
        keep_pool_after_rerank: bool = False,
    ) -> tuple[list[SearchHit], int, float]:
        # Lấy nhiều kết quả thô hơn nếu có lớp rerank
        fetch_k = RERANK_CANDIDATES if self._reranker else top_k

        hits = await self._vector_store.search(
            query_vector, top_k=fetch_k, cv_key=cv_key,
            min_years_exp=min_years_exp, required_skills=required_skills,
        )

        # Nếu lọc ra 0 kết quả thì tìm lại không lọc (giữ cv_key nếu có)
        if fallback_no_filter and not hits and (min_years_exp or required_skills):
            logger.info("Lọc quá chặt, tìm lại không lọc")
            hits = await self._vector_store.search(query_vector, top_k=fetch_k, cv_key=cv_key)

        rerank_time = 0.0
        if self._reranker and hits:
            rerank_top = len(hits) if keep_pool_after_rerank else top_k
            t_rr = time.perf_counter()
            hits = await asyncio.to_thread(self._reranker.rerank, rerank_query, hits, rerank_top)
            rerank_time = time.perf_counter() - t_rr
        elif not self._reranker:
            hits = hits[:top_k]

        return hits, fetch_k, rerank_time

    # Quy trình tìm kiếm: tách filter từ câu hỏi, search + rerank, ưu tiên role, lấy top-K
    async def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        t0 = time.perf_counter()

        # Tách filter ("5 năm", "Python", role,...) ra khỏi câu hỏi
        pq = parse_query(query)

        vectors = await asyncio.to_thread(self._embedder.encode, pq.text)
        query_vector = vectors[0]

        hits, fetch_k, rerank_time = await self._search_common(
            query_vector=query_vector,
            rerank_query=pq.text,
            top_k=top_k,
            min_years_exp=pq.min_years_exp,
            required_skills=pq.required_skills,
            fallback_no_filter=True,
            keep_pool_after_rerank=True,
        )

        # Ưu tiên role: đoạn nào khớp role thì boost lên đầu (sort ổn định, giữ thứ tự rerank trong cùng nhóm)
        roles_boosted = 0
        if pq.required_roles and hits:
            def _role_match(text: str) -> bool:
                return any(text_matches_role(text, r) for r in pq.required_roles)
            hits = sorted(hits, key=lambda h: (not _role_match(h.chunk_text), -h.score))
            roles_boosted = sum(1 for h in hits if _role_match(h.chunk_text))

        hits = hits[:top_k]

        elapsed = time.perf_counter() - t0
        logger.info(
            "Search '%s' | filters=(years>=%s, skills=%s, roles=%s) | candidates=%d top_k=%d | role_boost=%d | %.3fs (rerank=%.3fs)",
            query[:50], pq.min_years_exp, pq.required_skills, pq.required_roles,
            fetch_k, len(hits), roles_boosted, elapsed, rerank_time,
        )
        return hits

    # Tìm kiếm trong đúng 1 CV (dùng cho chatbot); lọc cv_key bắt buộc, không role boost
    async def search_within_cv(self, query: str, cv_key: str, top_k: int = 5) -> list[SearchHit]:
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

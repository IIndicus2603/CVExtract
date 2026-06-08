# JD và CV matching pipeline,
#   1. LLM extract yêu cầu từ JD
#   2. embed summary, search Qdrant (optional hard filter years/skills)
#   3. cap chunks/CV, optional rerank
#   4. aggregate top-N chunks/CV theo JD_AGG_WEIGHTS
#   5. fetch CV full, sort, slice top_k

import asyncio
import logging
import time
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import (
    JD_AGG_WEIGHTS,
    JD_FALLBACK_SUMMARY_CHARS,
    MAX_CHUNKS_PER_CV,
    UNLIMITED_FETCH_LIMIT,
)
from core.embeddings.embedder import Embedder
from core.embeddings.reranker import Reranker
from core.llm.client import build_llm_client
from core.registries import SkillRegistry
from core.retrieval_utils import cap_per_cv
from core.schemas import SearchHit, to_int_or_none
from core.vector_store import VectorStore

from features.matching.llm.prompts import JD_EXTRACT_TEMPLATE, JD_SYSTEM_PROMPT
from features.matching.schemas import CVMatch, MatchResponse, ParsedJD

logger = logging.getLogger(__name__)


_AGG_TOP_N = len(JD_AGG_WEIGHTS)


GetCVMetaFn = Callable[[AsyncSession, str], Awaitable[dict | None]]


class MatchingService:
    def __init__(
        self,
        provider: str,
        model: str | None,
        embedder: Embedder,
        vector_store: VectorStore,
        skill_registry: SkillRegistry,
        get_cv_meta_fn: GetCVMetaFn,
        reranker: Reranker | None = None,
    ):
        """Init LLM + reuse embedder/vector_store/reranker từ retrieval layer"""
        self._llm = build_llm_client(provider=provider, model=model)
        self._embedder = embedder
        self._vs = vector_store
        self._skills = skill_registry
        self._get_cv = get_cv_meta_fn
        self._reranker = reranker

    async def match(
        self,
        db: AsyncSession,
        jd_text: str,
        top_k: int,
        *,
        strict_skills_filter: bool,
        strict_years_filter: bool,
    ) -> MatchResponse:
        """Pipeline match JD với top-K CV (xem docstring module)"""
        t_total = time.perf_counter()

        # 1. Parse JD bằng LLM
        parsed_dict, usage = await self._llm.extract_json(
            JD_SYSTEM_PROMPT, JD_EXTRACT_TEMPLATE.format(jd_text=jd_text),
        )
        if parsed_dict:
            parsed_jd = ParsedJD(
                summary=str(parsed_dict.get("summary") or "")[:JD_FALLBACK_SUMMARY_CHARS],
                required_skills=[s for s in (parsed_dict.get("required_skills") or []) if isinstance(s, str)],
                min_years_exp=to_int_or_none(parsed_dict.get("min_years_exp")),
                max_years_exp=to_int_or_none(parsed_dict.get("max_years_exp")),
            )
        else:
            # LLM fail thì fallback dùng raw JD làm summary
            parsed_jd = ParsedJD(summary=jd_text[:JD_FALLBACK_SUMMARY_CHARS])

        # 2. Embed summary
        embed_text = parsed_jd.summary or jd_text[:JD_FALLBACK_SUMMARY_CHARS]
        vectors = await asyncio.to_thread(self._embedder.encode, embed_text)
        query_vector = vectors[0]

        # 3. Search Qdrant - hard filter tuỳ flag
        skills_filter = parsed_jd.required_skills if strict_skills_filter else None
        min_y = parsed_jd.min_years_exp if strict_years_filter else None
        max_y = parsed_jd.max_years_exp if strict_years_filter else None

        hits = await self._vs.search(
            query_vector,
            top_k=UNLIMITED_FETCH_LIMIT,
            required_skills=skills_filter,
            min_years_exp=min_y,
            max_years_exp=max_y,
        )

        # 4. Cap chunks/CV
        hits = cap_per_cv(hits, MAX_CHUNKS_PER_CV)

        # 5. (Optional) rerank trên pool đã cap
        rerank_time = 0.0
        if self._reranker and hits:
            t_rr = time.perf_counter()
            hits = await asyncio.to_thread(
                self._reranker.rerank, parsed_jd.summary or jd_text[:200], hits, len(hits),
            )
            rerank_time = time.perf_counter() - t_rr
            # Sau rerank order toàn cục có thể đổi nên cap lại idempotent
            hits = cap_per_cv(hits, MAX_CHUNKS_PER_CV)

        # 6. Aggregate per CV, top-N chunks, weighted avg
        per_cv: dict[str, list[SearchHit]] = {}
        for h in hits:
            per_cv.setdefault(h.cv_key, []).append(h)

        scored: list[tuple[str, float, list[SearchHit]]] = []
        for cv_key, chunks in per_cv.items():
            chunks_sorted = sorted(chunks, key=lambda x: -x.score)[:_AGG_TOP_N]
            scored.append((cv_key, _aggregate(chunks_sorted), chunks_sorted))

        scored.sort(key=lambda x: -x[1])

        # 7. Fetch full CV, skip CV đã xoá khỏi MySQL nhưng còn Qdrant
        results: list[CVMatch] = []
        for cv_key, score, chunks in scored:
            if len(results) >= top_k:
                break
            cv = await self._get_cv(db, cv_key)
            if cv is None:
                continue
            results.append(CVMatch(
                cv_key=cv_key,
                cv=cv,
                score=score,
                matched_chunks=[
                    {"section": h.section, "text": h.chunk_text, "score": h.score}
                    for h in chunks
                ],
            ))

        elapsed = time.perf_counter() - t_total
        logger.info(
            "MatchJD | jd_len=%d skills=%s years=(%s,%s) | strict=(skills=%s,years=%s) "
            "| chunks=%d cvs=%d returned=%d | %.3fs (rerank=%.3fs) | tokens=p%d/c%d/t%d",
            len(jd_text), parsed_jd.required_skills,
            parsed_jd.min_years_exp, parsed_jd.max_years_exp,
            strict_skills_filter, strict_years_filter,
            len(hits), len(per_cv), len(results), elapsed, rerank_time,
            usage.prompt, usage.completion, usage.total,
        )

        return MatchResponse(
            parsed_jd=parsed_jd,
            total_cvs=len(results),
            results=results,
        )


def _aggregate(chunks: list[SearchHit]) -> float:
    """Weighted avg score top-N chunks, renormalize weights nếu < N chunks"""
    if not chunks:
        return 0.0
    n = min(len(chunks), _AGG_TOP_N)
    weights = JD_AGG_WEIGHTS[:n]
    wsum = sum(weights)
    if wsum <= 0:
        return 0.0
    return sum(w * chunks[i].score for i, w in enumerate(weights)) / wsum

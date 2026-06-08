# Qdrant, tạo collection, upsert/delete chunks, vector search có filter

import logging
import uuid
from typing import Sequence

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from core.schemas import Chunk, SearchHit

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, url: str, collection: str, vector_dim: int):
        """Init Qdrant async client"""
        self._client = AsyncQdrantClient(url=url)
        self._collection = collection
        self._dim = vector_dim

    async def ensure_collection(self, *, log_ready: bool = True) -> None:
        """Tạo collection + payload indexes nếu chưa có"""
        exists = await self._client.collection_exists(self._collection)
        if exists:
            if log_ready:
                logger.info("Qdrant collection ready: %s", self._collection)
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qm.VectorParams(size=self._dim, distance=qm.Distance.COSINE),
        )

        # Index các field hay dùng filter, thiếu index thì Qdrant full-scan
        indexes = [
            ("cv_key", qm.PayloadSchemaType.KEYWORD),
            ("section", qm.PayloadSchemaType.KEYWORD),
            ("years_exp", qm.PayloadSchemaType.INTEGER),
            ("skills", qm.PayloadSchemaType.KEYWORD),
        ]
        for field, schema in indexes:
            await self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema=schema,
            )

        logger.info(
            "Created Qdrant collection: %s (dim=%d, %d payload indexes)",
            self._collection, self._dim, len(indexes),
        )

    async def delete_by_cv_key(self, cv_key: str) -> None:
        """Xoá toàn bộ chunks của 1 CV (dùng khi re-index hoặc delete CV)"""
        await self.ensure_collection(log_ready=False)
        await self._client.delete(
            collection_name=self._collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="cv_key", match=qm.MatchValue(value=cv_key))]
                )
            ),
        )
        logger.debug("Deleted Qdrant chunks for cv_key=%s", cv_key)

    async def upsert_chunks(self, chunks: Sequence[Chunk], vectors: Sequence[list[float]]) -> None:
        """Thêm/cập nhật nhiều chunks, cần len(chunks)==len(vectors)"""
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks ({len(chunks)}) and vectors ({len(vectors)}) length mismatch"
            )
        if not chunks:
            return

        await self.ensure_collection(log_ready=False)

        points = [
            qm.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "cv_key": chunk.cv_key,
                    "section": chunk.section,
                    "chunk_text": chunk.text,
                    "section_index": chunk.section_index,
                    "name": chunk.name,
                    "years_exp": chunk.years_exp,
                    "skills": chunk.skills,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]

        await self._client.upsert(collection_name=self._collection, points=points)
        logger.debug("Upserted %d chunks to Qdrant", len(points))

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        *,
        cv_key: str | None = None,
        cv_keys: list[str] | None = None,
        min_years_exp: int | None = None,
        max_years_exp: int | None = None,
        required_skills: list[str] | None = None,
    ) -> list[SearchHit]:
        """Top-K chunks, cv_key (1 CV) ưu tiên cv_keys (nhiều CV)"""
        must: list[qm.FieldCondition] = []

        if cv_key is not None:
            must.append(qm.FieldCondition(key="cv_key", match=qm.MatchValue(value=cv_key)))
        elif cv_keys:
            must.append(qm.FieldCondition(key="cv_key", match=qm.MatchAny(any=cv_keys)))

        if min_years_exp is not None or max_years_exp is not None:
            must.append(qm.FieldCondition(
                key="years_exp",
                range=qm.Range(gte=min_years_exp, lte=max_years_exp),
            ))

        # Mảng skills, MatchValue = "mảng chứa giá trị này", mỗi skill là 1 AND condition
        for skill in (required_skills or []):
            must.append(qm.FieldCondition(key="skills", match=qm.MatchValue(value=skill)))

        query_filter = qm.Filter(must=must) if must else None

        results = await self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        return [
            SearchHit(
                cv_key=p.payload["cv_key"],
                section=p.payload["section"],
                chunk_text=p.payload["chunk_text"],
                score=p.score,
            )
            for p in results.points
        ]

    async def close(self) -> None:
        """Đóng connection (gọi khi shutdown)"""
        await self._client.close()

# StorageService, CRUD bảng cv_data

import json
import logging

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import CVData
from features.storage.schemas import CVSaveData

logger = logging.getLogger(__name__)


# Structured fields mapped 1-1 với cột DB (không gồm key/file_name/extension/status)
_PARSED_FIELDS: tuple[str, ...] = (
    "name", "email", "phone", "years_exp", "skills", "education",
    "work_history", "projects", "awards", "certifications", "summary",
)


class StorageService:
    async def save(self, db: AsyncSession, data: CVSaveData) -> None:
        """Upsert 1 CV, parse JSON từ text để tách ra cột riêng"""
        cv = self._parse_cv_fields(data.text)
        row = {
            "key": data.key,
            "file_name": data.file_name,
            "extension": data.extension,
            "status": data.status,
            "error_message": data.error_message,
            **self._parsed_to_row(cv),
        }
        stmt = insert(CVData).values(**row).on_duplicate_key_update(
            **{k: v for k, v in row.items() if k != "key"}
        )
        await db.execute(stmt)
        await db.commit()

    async def get_all(self, db: AsyncSession) -> dict:
        """Lấy tất cả CV trong DB, trả {key, cv_dict}"""
        rows = (await db.execute(select(CVData))).scalars().all()
        return {r.key: self._row_to_dict(r) for r in rows}

    async def get_by_key(self, db: AsyncSession, key: str) -> dict | None:
        """Tìm 1 CV theo key, None nếu không có"""
        row = await db.scalar(select(CVData).where(CVData.key == key))
        return self._row_to_dict(row) if row else None

    async def delete(self, db: AsyncSession, key: str) -> bool:
        """Xoá 1 CV, True nếu có xoá"""
        result = await db.execute(delete(CVData).where(CVData.key == key))
        await db.commit()
        return result.rowcount > 0

    async def update(self, db: AsyncSession, key: str, parsed: dict) -> bool:
        """Replace structured fields cho 1 CV, True nếu có update"""
        result = await db.execute(
            update(CVData).where(CVData.key == key).values(**self._parsed_to_row(parsed))
        )
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    def _parsed_to_row(parsed: dict) -> dict:
        """Build dict cột structured từ parsed dict (chung cho save/update)"""
        return {f: (parsed.get(f) or None) if f != "years_exp" else parsed.get(f)
                for f in _PARSED_FIELDS}

    @staticmethod
    def _parse_cv_fields(text: str) -> dict:
        """Parse JSON text thành dict, trả {} nếu lỗi format hoặc empty"""
        try:
            return json.loads(text) if text else {}
        except (json.JSONDecodeError, ValueError) as e:
            # Text không phải JSON (vd raw-text fallback khi LLM parse fail) thì lưu không structured fields
            logger.warning("Skip structured fields: text not valid JSON (%s) | preview=%r", e, text[:120])
            return {}

    @staticmethod
    def _reconstruct_text(row: CVData) -> str:
        """Rebuild JSON string từ structured columns (thay cho raw_json đã bỏ), frontend parse field 'text' như JSON để render"""
        return json.dumps(
            {f: getattr(row, f) for f in _PARSED_FIELDS},
            ensure_ascii=False, indent=2,
        )

    @classmethod
    def _row_to_dict(cls, row: CVData) -> dict:
        """ORM row thành response dict (gồm text reconstruct cho frontend)"""
        out = {
            "file_name": row.file_name,
            "extension": row.extension,
            "status": row.status,
            "text": cls._reconstruct_text(row),
            "error_message": row.error_message,
        }
        out.update({f: getattr(row, f) for f in _PARSED_FIELDS})
        return out

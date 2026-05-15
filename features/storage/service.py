# Service làm việc với bảng cv_data trong DB

import json

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import CVData
from features.storage.schemas import CVSaveData


class StorageService:
    # Lưu hoặc update 1 CV vào DB
    # Tự parse JSON từ text để tách ra các cột riêng (name, email, skills...).
    async def save(self, db: AsyncSession, data: CVSaveData) -> None:
        cv = self._parse_cv_fields(data.text)
        row = dict(
            key=data.key,
            file_name=data.file_name,
            extension=data.extension,
            status=data.status,
            name=cv.get("name") or None,
            email=cv.get("email") or None,
            phone=cv.get("phone") or None,
            years_exp=cv.get("years_exp"),
            skills=cv.get("skills") or None,
            education=cv.get("education") or None,
            work_history=cv.get("work_history") or None,
            projects=cv.get("projects") or None,
            awards=cv.get("awards") or None,
            certifications=cv.get("certifications") or None,
            summary=cv.get("summary") or None,
            raw_json=data.text,
            error_message=data.error_message,
        )
        # MySQL upsert: nếu "key" đã tồn tại thì update, không thì insert mới
        stmt = insert(CVData).values(**row).on_duplicate_key_update(
            **{k: v for k, v in row.items() if k != "key"}
        )
        await db.execute(stmt)
        await db.commit()

    # Lấy tất cả CV trong DB, trả về dict {key: cv_dict}
    async def get_all(self, db: AsyncSession) -> dict:
        rows = (await db.execute(select(CVData))).scalars().all()
        return {r.key: self._row_to_dict(r) for r in rows}

    # Tìm 1 CV theo key
    async def get_by_key(self, db: AsyncSession, key: str) -> dict | None:
        row = await db.scalar(select(CVData).where(CVData.key == key))
        return self._row_to_dict(row) if row else None

    # Parse string JSON thành dict. Nếu lỗi thì trả {}
    @staticmethod
    def _parse_cv_fields(text: str) -> dict:
        try:
            return json.loads(text) if text else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    # Convert ORM row thành dict cho response API
    @staticmethod
    def _row_to_dict(row: CVData) -> dict:
        return {
            "file_name": row.file_name,
            "extension": row.extension,
            "status": row.status,
            "name": row.name,
            "email": row.email,
            "phone": row.phone,
            "years_exp": row.years_exp,
            "skills": row.skills,
            "education": row.education,
            "work_history": row.work_history,
            "projects": row.projects,
            "awards": row.awards,
            "certifications": row.certifications,
            "summary": row.summary,
            "text": row.raw_json,
            "error_message": row.error_message,
        }

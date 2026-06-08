# Cắt CV parsed thành các chunk nhỏ theo section, sẵn sàng embed

import logging

from core.config import MAX_SKILLS_SINGLE_CHUNK, SKILLS_PER_CHUNK
from core.schemas import Chunk

logger = logging.getLogger(__name__)


class CVChunker:

    def chunk(self, cv_key: str, parsed: dict) -> list[Chunk]:
        """Cắt parsed CV thành nhiều chunks theo section"""
        meta = self._extract_meta(parsed)
        ident = self._build_identity(parsed)  # "Nguyễn Văn A (5 năm kinh nghiệm)"

        chunks: list[Chunk] = []

        # Header, gộp tên + role hiện tại + top skills (chunk dày)
        profile_text = self._build_profile(parsed, ident)
        if profile_text:
            chunks.append(Chunk(
                cv_key=cv_key, section="header", text=profile_text,
                section_index=0, **meta,
            ))

        # Summary
        summary = (parsed.get("summary") or "").strip()
        if summary:
            text = f"{ident} - tóm tắt: {summary}" if ident else f"Tóm tắt: {summary}"
            chunks.append(Chunk(
                cv_key=cv_key, section="summary", text=text,
                section_index=0, **meta,
            ))

        # Skills (split nếu nhiều)
        skills = [str(s).strip() for s in (parsed.get("skills") or []) if s and str(s).strip()]
        if skills:
            for i, group in enumerate(self._group_skills(skills)):
                text = (f"{ident} - kỹ năng: " if ident else "Kỹ năng: ") + ", ".join(group)
                chunks.append(Chunk(
                    cv_key=cv_key, section="skills", text=text,
                    section_index=i, **meta,
                ))

        # Education / work_history
        for i, edu in enumerate(parsed.get("education") or []):
            text = self._format_education(edu, ident)
            if text:
                chunks.append(Chunk(
                    cv_key=cv_key, section="education", text=text,
                    section_index=i, **meta,
                ))

        for i, work in enumerate(parsed.get("work_history") or []):
            text = self._format_work(work, ident)
            if text:
                chunks.append(Chunk(
                    cv_key=cv_key, section="work_history", text=text,
                    section_index=i, **meta,
                ))

        # Mỗi project 1 chunk vì có mô tả chi tiết riêng
        for i, proj in enumerate(parsed.get("projects") or []):
            text = self._format_project(proj, ident)
            if text:
                chunks.append(Chunk(
                    cv_key=cv_key, section="projects", text=text,
                    section_index=i, **meta,
                ))

        # Awards / certifications, gộp tất cả vào 1 chunk
        awards_text = self._format_awards(parsed.get("awards") or [], ident)
        if awards_text:
            chunks.append(Chunk(
                cv_key=cv_key, section="awards", text=awards_text,
                section_index=0, **meta,
            ))

        certs_text = self._format_certifications(parsed.get("certifications") or [], ident)
        if certs_text:
            chunks.append(Chunk(
                cv_key=cv_key, section="certifications", text=certs_text,
                section_index=0, **meta,
            ))

        logger.info("Chunked '%s' into %d chunks", cv_key, len(chunks))
        return chunks

    @staticmethod
    def _extract_meta(parsed: dict) -> dict:
        """Meta gắn vào MỌI chunk cho Qdrant payload filter"""
        return {
            "name": parsed.get("name") or None,
            "years_exp": parsed.get("years_exp"),
            "skills": parsed.get("skills") or [],
        }

    @staticmethod
    def _build_identity(parsed: dict) -> str:
        """'<Name> (<years> năm kinh nghiệm)' - empty nếu thiếu name"""
        name = (parsed.get("name") or "").strip()
        years = parsed.get("years_exp")
        if name and years is not None:
            return f"{name} ({years} năm kinh nghiệm)"
        return name or ""

    @staticmethod
    def _build_profile(parsed: dict, ident: str) -> str:
        """Header chunk, identity + role hiện tại + top 5 skills"""
        if not ident:
            return ""

        parts = [ident]

        # Role hiện tại lấy entry đầu (CV thường sắp mới nhất trước)
        works = parsed.get("work_history") or []
        if works:
            current = works[0]
            role = (current.get("role") or "").strip()
            company = (current.get("company") or "").strip()
            if role and company:
                parts.append(f"hiện tại {role} tại {company}")
            elif role:
                parts.append(f"hiện tại {role}")

        skills = [str(s).strip() for s in (parsed.get("skills") or [])[:5] if s]
        if skills:
            parts.append(f"chuyên môn: {', '.join(skills)}")

        return ". ".join(parts) + "."

    @staticmethod
    def _group_skills(skills: list[str]) -> list[list[str]]:
        """1 chunk nếu ít, split SKILLS_PER_CHUNK/chunk nếu nhiều"""
        if len(skills) <= MAX_SKILLS_SINGLE_CHUNK:
            return [skills]
        return [
            skills[i:i + SKILLS_PER_CHUNK]
            for i in range(0, len(skills), SKILLS_PER_CHUNK)
        ]

    @staticmethod
    def _format_education(edu: dict, ident: str) -> str:
        """Format 1 entry education thành text chunk"""
        parts = [
            (edu.get("degree") or "").strip(),
            (edu.get("school") or "").strip(),
            (edu.get("duration") or "").strip(),
        ]
        body = " — ".join(p for p in parts if p)
        if not body:
            return ""
        return f"{ident} - học vấn: {body}" if ident else f"Học vấn: {body}"

    @staticmethod
    def _format_project(proj: dict, ident: str) -> str:
        """Format 1 entry project thành text chunk"""
        name = (proj.get("name") or "").strip()
        description = (proj.get("description") or "").strip()
        tech = [str(t).strip() for t in (proj.get("tech") or []) if t]
        duration = (proj.get("duration") or "").strip()

        if not name and not description:
            return ""

        head_parts = []
        if name:
            head_parts.append(name)
        if duration:
            head_parts.append(f"({duration})")
        head = " ".join(head_parts)

        body_parts = []
        if description:
            body_parts.append(description)
        if tech:
            body_parts.append(f"Tech: {', '.join(tech)}")
        body = ". ".join(body_parts)

        prefix = f"{ident} - dự án: " if ident else "Dự án: "
        return f"{prefix}{head}. {body}" if head and body else f"{prefix}{head or body}"

    @staticmethod
    def _format_awards(awards: list, ident: str) -> str:
        """Gộp tất cả awards thành 1 text chunk"""
        items = []
        for a in awards:
            name = (a.get("name") or "").strip()
            issuer = (a.get("issuer") or "").strip()
            year = (a.get("year") or "").strip()
            parts = [name]
            if issuer:
                parts.append(issuer)
            if year:
                parts.append(year)
            line = " — ".join(p for p in parts if p)
            if line:
                items.append(line)
        if not items:
            return ""
        prefix = f"{ident} - giải thưởng: " if ident else "Giải thưởng: "
        return prefix + "; ".join(items)

    @staticmethod
    def _format_certifications(certs: list, ident: str) -> str:
        """Gộp tất cả certifications thành 1 text chunk"""
        items = []
        for c in certs:
            name = (c.get("name") or "").strip()
            issuer = (c.get("issuer") or "").strip()
            year = (c.get("year") or "").strip()
            parts = [name]
            if issuer:
                parts.append(issuer)
            if year:
                parts.append(year)
            line = " — ".join(p for p in parts if p)
            if line:
                items.append(line)
        if not items:
            return ""
        prefix = f"{ident} - chứng chỉ: " if ident else "Chứng chỉ: "
        return prefix + "; ".join(items)

    @staticmethod
    def _format_work(work: dict, ident: str) -> str:
        """Format 1 entry work_history thành text chunk"""
        role = (work.get("role") or "").strip()
        company = (work.get("company") or "").strip()
        duration = (work.get("duration") or "").strip()
        description = (work.get("description") or "").strip()

        head_parts = []
        if role:
            head_parts.append(role)
        if company:
            head_parts.append(f"tại {company}")
        if duration:
            head_parts.append(f"({duration})")
        head = " ".join(head_parts)

        if not head and not description:
            return ""

        prefix = f"{ident} - kinh nghiệm: " if ident else "Kinh nghiệm: "
        if description:
            return f"{prefix}{head}. {description}" if head else f"{prefix}{description}"
        return f"{prefix}{head}"

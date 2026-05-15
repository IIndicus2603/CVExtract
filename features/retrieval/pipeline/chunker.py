# Cắt CV thành nhiều chunk nhỏ theo từng phần để biến thành vector

import logging

from features.retrieval.schemas import Chunk

logger = logging.getLogger(__name__)


# Danh sách kỹ năng dài quá làm vector bị "loãng", chia nhóm ~10 kỹ năng / chunk
SKILLS_PER_CHUNK = 10
MAX_SKILLS_SINGLE_CHUNK = 15


class CVChunker:

    def chunk(self, cv_key: str, parsed: dict) -> list[Chunk]:
        meta = self._extract_meta(parsed)

        # Thông tin nhận dạng để vector biết "ai làm gì", vd "Nguyễn Văn A (5 năm kinh nghiệm)"
        ident = self._build_identity(parsed)

        chunks: list[Chunk] = []

        # Chunk hồ sơ: gộp tên + công việc hiện tại + top kỹ năng vào 1 chunk dày
        profile_text = self._build_profile(parsed, ident)
        if profile_text:
            chunks.append(Chunk(
                cv_key=cv_key, section="header", text=profile_text,
                section_index=0, **meta,
            ))

        summary = (parsed.get("summary") or "").strip()
        if summary:
            text = f"{ident} - tóm tắt: {summary}" if ident else f"Tóm tắt: {summary}"
            chunks.append(Chunk(
                cv_key=cv_key, section="summary", text=text,
                section_index=0, **meta,
            ))

        skills = [str(s).strip() for s in (parsed.get("skills") or []) if s and str(s).strip()]
        if skills:
            for i, group in enumerate(self._group_skills(skills)):
                text = (
                    f"{ident} - kỹ năng: " if ident else "Kỹ năng: "
                ) + ", ".join(group)
                chunks.append(Chunk(
                    cv_key=cv_key, section="skills", text=text,
                    section_index=i, **meta,
                ))

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

        # Mỗi dự án 1 đoạn vì có mô tả chi tiết, đáng tách riêng
        for i, proj in enumerate(parsed.get("projects") or []):
            text = self._format_project(proj, ident)
            if text:
                chunks.append(Chunk(
                    cv_key=cv_key, section="projects", text=text,
                    section_index=i, **meta,
                ))

        # Giải thưởng và chứng chỉ gộp 1 chunk vì mỗi cái thường ngắn
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
        return {
            "name": parsed.get("name") or None,
            "years_exp": parsed.get("years_exp"),
            "skills": parsed.get("skills") or [],
        }

    @staticmethod
    def _build_identity(parsed: dict) -> str:
        name = (parsed.get("name") or "").strip()
        years = parsed.get("years_exp")
        if name and years is not None:
            return f"{name} ({years} năm kinh nghiệm)"
        return name or ""

    @staticmethod
    def _build_profile(parsed: dict, ident: str) -> str:
        if not ident:
            return ""

        parts = [ident]

        # Công việc hiện tại lấy từ entry đầu tiên (CV thường sắp mới nhất trước)
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
        if len(skills) <= MAX_SKILLS_SINGLE_CHUNK:
            return [skills]
        return [
            skills[i:i + SKILLS_PER_CHUNK]
            for i in range(0, len(skills), SKILLS_PER_CHUNK)
        ]

    @staticmethod
    def _format_education(edu: dict, ident: str) -> str:
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

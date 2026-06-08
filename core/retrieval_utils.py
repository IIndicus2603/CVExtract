# Helpers dùng chung retrieval + matching

from core.schemas import SearchHit


def cap_per_cv(hits: list[SearchHit], cap: int) -> list[SearchHit]:
    """Mỗi cv_key tối đa cap hits, giữ thứ tự gốc để preserve rerank ranking"""
    if cap <= 0:
        return list(hits)
    counts: dict[str, int] = {}
    out: list[SearchHit] = []
    for h in hits:
        n = counts.get(h.cv_key, 0)
        if n < cap:
            out.append(h)
            counts[h.cv_key] = n + 1
    return out

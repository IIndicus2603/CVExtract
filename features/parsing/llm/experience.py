# Tính số năm kinh nghiệm tất định từ start/end work_history (LLM chuẩn hoá về YYYY-MM)

import datetime as _dt
import re


def _parse_month(token, today_idx: int) -> int | None:
    """Token YYYY-MM thành chỉ số tháng tuyệt đối year*12+month, 'present' thành nay, None nếu không hợp lệ"""
    s = str(token or "").strip().lower()
    if s == "present":                             # LLM chuẩn hoá việc đang làm về đúng chữ này
        return today_idx
    m = re.match(r"(\d{4})[-/.](\d{1,2})\b", s)    # YYYY-MM, định dạng chuẩn LLM trả về
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)) * 12 + int(m.group(2))
    return None


def _entry_interval(entry, today_idx: int) -> tuple[int, int] | None:
    """1 mục work_history thành khoảng (start, end) theo tháng, None nếu thiếu start hợp lệ"""
    if not isinstance(entry, dict):
        return None
    start = _parse_month(entry.get("start"), today_idx)
    if start is None:
        return None
    end = _parse_month(entry.get("end"), today_idx)
    end = min(end if end is not None else today_idx, today_idx)  # end rỗng hoặc không rõ coi như hiện tại
    return (start, end) if end >= start else None


def compute_years_exp(work_history, today: _dt.date | None = None) -> int | None:
    """Tổng số năm KN, gộp khoảng chồng lấn rồi floor, None nếu không mục nào tính được"""
    today = today or _dt.date.today()
    today_idx = today.year * 12 + today.month
    intervals = sorted(
        iv for e in (work_history or []) if (iv := _entry_interval(e, today_idx))
    )
    if not intervals:
        return None
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))   # chồng lấn thì gộp, tránh đếm trùng job song song
        else:
            merged.append((s, e))
    total_months = sum(e - s for s, e in merged)
    return total_months // 12               # floor

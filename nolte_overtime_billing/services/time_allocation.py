"""Shared, pure time-allocation rules for CSV and mobile reports.

The caller supplies chronological work/travel intervals and optional pause
intervals. The result separates the first 8 hours, hours 8–10, and all later
hours while preserving whether time was work or travel.
"""


def _clip(segment_start, segment_end, clip_start, clip_end):
    start = max(segment_start, clip_start)
    end = min(segment_end, clip_end)
    return (start, end) if end > start else None


def _subtract_pauses(start, end, pauses):
    segments = [(start, end)]
    for pause_start, pause_end in pauses:
        remaining = []
        for segment_start, segment_end in segments:
            overlap = _clip(segment_start, segment_end, pause_start, pause_end)
            if not overlap:
                remaining.append((segment_start, segment_end))
                continue
            overlap_start, overlap_end = overlap
            if overlap_start > segment_start:
                remaining.append((segment_start, overlap_start))
            if overlap_end < segment_end:
                remaining.append((overlap_end, segment_end))
        segments = remaining
    return segments


def allocate_timeline(segments):
    result = {
        "work": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0},
        "travel": {"normal": 0.0, "ot30": 0.0, "ot50": 0.0},
    }
    consumed = 0.0
    for start, end, kind in sorted(segments, key=lambda item: item[0]):
        hours = (end - start).total_seconds() / 3600.0
        if hours <= 0:
            continue
        remaining = hours
        while remaining > 1e-9:
            if consumed < 8.0:
                limit, bucket = 8.0, "normal"
            elif consumed < 10.0:
                limit, bucket = 10.0, "ot30"
            else:
                limit, bucket = float("inf"), "ot50"
            amount = remaining if limit == float("inf") else min(remaining, max(limit - consumed, 0.0))
            result[kind][bucket] += amount
            consumed += amount
            remaining -= amount
    return result


def allocate_with_pauses(segments, pauses=()):
    """Remove pauses from every overlapping work/travel segment, then allocate."""
    effective = []
    for start, end, kind in segments:
        effective.extend((part_start, part_end, kind) for part_start, part_end in _subtract_pauses(start, end, pauses))
    return allocate_timeline(effective)

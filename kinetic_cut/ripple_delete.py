"""A single, order-preserving clock for a batch ripple deletion."""
from bisect import bisect_right

from .timeline_actions import merge_ranges


def deletion_clock(deleted, occupied):
    """Close deleted time once, without shortening any surviving unlocked item.

    A surviving item crossing a deleted span protects its occupied time. This
    keeps global ripple synchronized without overlapping or trimming that item.
    Locked lanes neither move nor participate in the editable clock.
    """
    occupied = merge_ranges(occupied)
    gaps = []
    index = 0
    for start, end in merge_ranges(deleted):
        while index < len(occupied) and occupied[index][1] <= start:
            index += 1
        cursor = start
        scan = index
        while scan < len(occupied) and occupied[scan][0] < end:
            left, right = occupied[scan]
            if left > cursor:
                gaps.append((cursor, min(left, end)))
            cursor = max(cursor, right)
            if cursor >= end:
                break
            scan += 1
        if cursor < end:
            gaps.append((cursor, end))
    starts = [start for start, _ in gaps]
    totals = [0.0]
    for start, end in gaps:
        totals.append(totals[-1] + end - start)

    def map_time(value):
        index = bisect_right(starts, value) - 1
        if index < 0:
            return value
        start, end = gaps[index]
        return value - totals[index] - min(value - start, end - start)

    return map_time

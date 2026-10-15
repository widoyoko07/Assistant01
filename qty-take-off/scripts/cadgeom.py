#!/usr/bin/env python3
"""Pure geometry helpers for CAD take-off. Coordinates are in metres."""
import collections
import math


def p3(point):
    point = tuple(float(coord) for coord in point)
    return point + (0.0,) * (3 - len(point)) if len(point) < 3 else point[:3]


def seg_len(start, end):
    return math.dist(p3(start), p3(end))


def _unit(start, end):
    delta = tuple(end[i] - start[i] for i in range(3))
    length = math.sqrt(sum(component * component for component in delta))
    if length < 1e-9:
        return None
    direction = [component / length for component in delta]
    for component in direction:
        if abs(component) > 1e-6:
            if component < 0:
                direction = [-value for value in direction]
            break
    return tuple(direction)


def _dot(left, right):
    return sum(left[i] * right[i] for i in range(3))


def _perpendicular(point, direction):
    projection = _dot(point, direction)
    return tuple(point[i] - projection * direction[i] for i in range(3))


def merge_collinear(segments, tol=0.002):
    """Merge collinear overlaps without filling gaps; keep separate parallel lines.

    ``tol`` is the maximum perpendicular offset in metres. Exact duplicates,
    reversed segments, partial overlaps, and touching segments count once.
    """
    if tol <= 0:
        raise ValueError("tol must be positive")
    groups = collections.defaultdict(list)
    for start, end in segments:
        start, end = p3(start), p3(end)
        direction = _unit(start, end)
        if direction is not None:
            key = tuple(round(component, 3) for component in direction)
            groups[key].append((start, end))

    merged = []
    for items in groups.values():
        direction = _unit(*items[0])
        records = []
        for start, end in items:
            s0, s1 = _dot(start, direction), _dot(end, direction)
            records.append((
                _perpendicular(start, direction),
                _perpendicular(end, direction),
                min(s0, s1),
                max(s0, s1),
            ))

        parent = list(range(len(records)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        cells = {}
        for index, (perp_start, perp_end, _, _) in enumerate(records):
            cell = tuple(math.floor(coord / tol) for coord in perp_start)
            matched = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nearby = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                        for other in cells.get(nearby, ()):
                            other_start, other_end = records[other][:2]
                            if (math.dist(perp_start, other_start) <= tol
                                    and math.dist(perp_end, other_end) <= tol):
                                parent[find(index)] = find(other)
                                matched = True
            if not matched:
                cells.setdefault(cell, []).append(index)

        clusters = collections.defaultdict(list)
        for index in range(len(records)):
            clusters[find(index)].append(index)
        for indexes in clusters.values():
            indexes.sort(key=lambda index: records[index][2])
            base = records[indexes[0]][0]
            start_t, end_t = records[indexes[0]][2:]

            def emit(first, last):
                merged.append((
                    tuple(base[i] + first * direction[i] for i in range(3)),
                    tuple(base[i] + last * direction[i] for i in range(3)),
                ))

            for index in indexes[1:]:
                next_start, next_end = records[index][2:]
                if next_start <= end_t + 1e-9:
                    end_t = max(end_t, next_end)
                else:
                    emit(start_t, end_t)
                    start_t, end_t = next_start, next_end
            emit(start_t, end_t)
    return merged


def orient_split(segments):
    """Return horizontal, vertical, and sloped lengths in metres."""
    lengths = {"h": 0.0, "v": 0.0, "d": 0.0}
    for start, end in segments:
        start, end = p3(start), p3(end)
        horizontal = math.hypot(end[0] - start[0], end[1] - start[1])
        vertical = abs(end[2] - start[2])
        length = math.hypot(horizontal, vertical)
        if length < 1e-9:
            continue
        angle = math.degrees(math.atan2(vertical, horizontal))
        category = "h" if angle < 3 else "v" if angle > 87 else "d"
        lengths[category] += length
    return lengths


def cluster_runs(segments, link_tol=0.05):
    """Group segments whose endpoints are within ``link_tol`` metres."""
    if link_tol <= 0:
        raise ValueError("link_tol must be positive")
    parent = list(range(len(segments)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    cells = {}
    for index, (start, end) in enumerate(segments):
        for point in (p3(start), p3(end)):
            cell = tuple(math.floor(coord / link_tol) for coord in point)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nearby = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                        for other, other_point in cells.get(nearby, ()):
                            if math.dist(point, other_point) <= link_tol:
                                parent[find(index)] = find(other)
            cells.setdefault(cell, []).append((index, point))

    groups = collections.defaultdict(list)
    for index in range(len(segments)):
        groups[find(index)].append(index)

    runs = []
    for indexes in groups.values():
        points = [p3(point) for index in indexes for point in segments[index]]
        orientation = orient_split([segments[index] for index in indexes])
        runs.append({
            "n": len(indexes),
            "length_m": sum(seg_len(*segments[index]) for index in indexes),
            "bbox": [
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            ],
            "h_m": orientation["h"],
            "v_m": orientation["v"],
            "d_m": orientation["d"],
        })
    return sorted(runs, key=lambda run: -run["length_m"])

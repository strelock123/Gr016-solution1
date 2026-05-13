from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from utils import normalize_point


# Set to False to disable side/top/font highlight export quickly while debugging.
ENABLE_WAY_HIGHLIGHT_EXPORT = False
CONSTRAINT_GEOMETRY_FIELDS = (
    "dim_type",
    "angle",
    "start",
    "end",
    "dimension_point",
    "center",
    "point_on_circle",
    "defpoint",
    "defpoint2",
    "defpoint3",
    "defpoint4",
    "defpoint5",
    "text_midpoint",
)


def analyze_interpolate_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    try:
        return _analyze_interpolate_payload(payload, precision=precision)
    except Exception as exc:
        return {"error": f"interpolate failed: {exc}"}


def _analyze_interpolate_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    line_entities = payload.get("line_entities") or []
    arc_entities = payload.get("arc_entities") or []
    circle_entities = payload.get("circle_entities") or []
    endpoint_board = payload.get("endpoint_board") or []

    point_to_names = build_point_name_map(endpoint_board, precision)

    all_entities = build_entity_records(line_entities, arc_entities, circle_entities, precision)
    side_interval = choose_side_interval(all_entities, axis="x")
    side_way, remaining_after_side = split_entities_by_interval(all_entities, side_interval, axis="x")

    side_points = select_points_in_interval(endpoint_board, side_interval, axis="x", precision=precision)
    side_point_names = point_names_from_points(side_points, point_to_names, precision)
    side_constraints = select_constraints_by_names(payload, side_point_names, precision)

    top_interval = choose_top_interval(remaining_after_side, axis="y")
    top_way, font_way_candidates = split_entities_by_interval(remaining_after_side, top_interval, axis="y")

    used_point_names = set(side_point_names)
    top_points = select_points_in_interval(
        endpoint_board,
        top_interval,
        axis="y",
        precision=precision,
        exclude_names=used_point_names,
    )
    top_point_names = point_names_from_points(top_points, point_to_names, precision)
    top_constraints = select_constraints_by_names(payload, top_point_names, precision, exclude_names=used_point_names)

    font_points = [
        item for item in endpoint_board
        if normalize_point(item.get("point"), precision) is not None
        and item.get("name", "") not in used_point_names
        and item.get("name", "") not in set(top_point_names)
    ]
    font_point_names = [
        item.get("name", "")
        for item in font_points
        if item.get("name", "")
    ]
    font_constraints = select_remaining_constraints(
        payload,
        used_names=used_point_names.union(set(top_point_names)),
        precision=precision,
    )

    side_way = annotate_way_records(side_way, "side_way", precision)
    top_way = annotate_way_records(top_way, "top_way", precision)
    font_way = annotate_way_records(font_way_candidates, "font_way", precision)

    highlight_groups = {}
    if ENABLE_WAY_HIGHLIGHT_EXPORT:
        highlight_groups = {
            "side_way": build_way_highlights(side_way, precision),
            "top_way": build_way_highlights(top_way, precision),
            "font_way": build_way_highlights(font_way, precision),
        }
    else:
        compact_way_records(side_way)
        compact_way_records(top_way)
        compact_way_records(font_way)

    return {
        "side_interval": side_interval,
        "top_interval": top_interval,
        "side_way": side_way,
        "side_points": side_points,
        "side_constraints": side_constraints,
        "top_way": top_way,
        "top_points": top_points,
        "top_constraints": top_constraints,
        "font_way": font_way,
        "font_points": font_points,
        "font_constraints": font_constraints,
        "highlight_groups": highlight_groups,
    }


def build_entity_records(
    line_entities: list[dict[str, Any]],
    arc_entities: list[dict[str, Any]],
    circle_entities: list[dict[str, Any]],
    precision: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for item in line_entities:
        start = normalize_point(item.get("start"), precision)
        end = normalize_point(item.get("end"), precision)
        if start is None or end is None:
            continue
        records.append(
            {
                "points": [list(start), list(end)],
                "interval_x": [min(start[0], end[0]), max(start[0], end[0])],
                "interval_y": [min(start[1], end[1]), max(start[1], end[1])],
            }
        )

    for item in arc_entities:
        center = normalize_point(item.get("center"), precision)
        radius = num(item.get("radius", 0.0), precision)
        if center is None:
            continue
        arc_points = sample_arc_points(
            center,
            radius,
            num(item.get("start_angle", 0.0), precision),
            num(item.get("end_angle", 0.0), precision),
            precision,
        )
        records.append(
            {
                "center": [center[0], center[1]],
                "radius": radius,
                "points": arc_points,
                "interval_x": interval_from_points(arc_points, axis=0, precision=precision),
                "interval_y": interval_from_points(arc_points, axis=1, precision=precision),
            }
        )

    for item in circle_entities:
        center = normalize_point(item.get("center"), precision)
        radius = num(item.get("radius", 0.0), precision)
        if center is None:
            continue
        circle_points = sample_circle_points(center, radius, precision)
        records.append(
            {
                "center": [center[0], center[1]],
                "radius": radius,
                "points": circle_points,
                "interval_x": [round(center[0] - radius, precision), round(center[0] + radius, precision)],
                "interval_y": [round(center[1] - radius, precision), round(center[1] + radius, precision)],
            }
        )

    return records


def choose_side_interval(entities: list[dict[str, Any]], axis: str) -> list[float] | None:
    intervals = [entity.get(f"interval_{axis}") for entity in entities if entity.get(f"interval_{axis}")]
    merged = merge_overlapping_intervals(intervals)
    if not merged:
        return None
    return max(merged, key=lambda interval: (interval[1], interval[0] - interval[1]))


def choose_top_interval(entities: list[dict[str, Any]], axis: str) -> list[float] | None:
    intervals = [entity.get(f"interval_{axis}") for entity in entities if entity.get(f"interval_{axis}")]
    merged = merge_overlapping_intervals(intervals)
    if not merged:
        return None
    return min(merged, key=lambda interval: (interval[0], interval[1] - interval[0]))


def split_entities_by_interval(
    entities: list[dict[str, Any]],
    target_interval: list[float] | None,
    axis: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if target_interval is None:
        return [], list(entities)

    selected: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for entity in entities:
        interval = entity.get(f"interval_{axis}")
        if interval and intervals_overlap(interval, target_interval):
            selected.append(entity)
        else:
            remaining.append(entity)
    return selected, remaining


def merge_overlapping_intervals(intervals: list[list[float]]) -> list[list[float]]:
    cleaned = sorted(
        ([min(num(interval[0]), num(interval[1])), max(num(interval[0]), num(interval[1]))] for interval in intervals if interval and len(interval) >= 2),
        key=lambda item: (item[0], item[1]),
    )
    if not cleaned:
        return []

    merged: list[list[float]] = [cleaned[0]]
    for start, end in cleaned[1:]:
        current = merged[-1]
        if start <= current[1]:
            current[1] = max(current[1], end)
        else:
            merged.append([start, end])
    return merged


def intervals_overlap(a: list[float], b: list[float], tolerance: float = 1e-9) -> bool:
    return not (a[1] < b[0] - tolerance or b[1] < a[0] - tolerance)


def select_points_in_interval(
    endpoint_board: list[dict[str, Any]],
    interval: list[float] | None,
    axis: str,
    precision: int,
    exclude_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    if interval is None:
        return []

    exclude_names = exclude_names or set()
    selected: list[dict[str, Any]] = []
    for item in endpoint_board:
        point = normalize_point(item.get("point"), precision)
        if point is None:
            continue
        if item.get("name", "") in exclude_names:
            continue
        value = point[0] if axis == "x" else point[1]
        if interval[0] - 1e-9 <= value <= interval[1] + 1e-9:
            selected.append(
                {
                    "name": item.get("name", ""),
                    "point": [point[0], point[1]],
                }
            )
    return selected


def point_names_from_points(
    points: list[dict[str, Any]],
    point_to_names: dict[tuple[float, float], list[str]],
    precision: int,
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in points:
        point = normalize_point(item.get("point"), precision)
        if point is None:
            continue
        for name in point_to_names.get(point, []):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def build_point_name_map(endpoint_board: list[dict[str, Any]], precision: int) -> dict[tuple[float, float], list[str]]:
    mapping: dict[tuple[float, float], list[str]] = {}
    for item in endpoint_board:
        point = normalize_point(item.get("point"), precision)
        name = item.get("name", "")
        if point is None or not name:
            continue
        mapping.setdefault(point, []).append(str(name))
    return mapping


def select_constraints_by_names(
    payload: dict[str, Any],
    point_names: list[str],
    precision: int,
    exclude_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    exclude_names = exclude_names or set()
    target_names = set(point_names)
    result: list[dict[str, Any]] = []

    for group_name in ("distance_x", "distance_y", "distance_radius", "distance_angle", "distance_edge", "distance_other"):
        for item in payload.get(group_name) or []:
            entry = {"kind": group_name}
            names = collect_constraint_endpoint_names(item, payload, precision)
            entry["endpoint_names"] = names
            if not target_names.intersection(names):
                continue
            if exclude_names and exclude_names.intersection(names):
                continue
            copy_constraint_geometry(entry, item)
            result.append(entry)
    return result


def select_remaining_constraints(
    payload: dict[str, Any],
    used_names: set[str],
    precision: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for group_name in ("distance_x", "distance_y", "distance_radius", "distance_angle", "distance_edge", "distance_other"):
        for item in payload.get(group_name) or []:
            entry = {"kind": group_name}
            names = collect_constraint_endpoint_names(item, payload, precision)
            entry["endpoint_names"] = names
            if not used_names.intersection(names):
                copy_constraint_geometry(entry, item)
                result.append(entry)
    return result


def collect_constraint_endpoint_names(
    entry: dict[str, Any],
    payload: dict[str, Any],
    precision: int,
) -> list[str]:
    endpoint_board = payload.get("endpoint_board") or []
    point_map = build_point_name_map(endpoint_board, precision)
    names: list[str] = []
    seen: set[str] = set()
    for point in iter_constraint_points(entry, precision):
        for name in point_map.get(point, []):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def iter_constraint_points(entry: dict[str, Any], precision: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for field in ("start", "end", "dimension_point", "center", "point_on_circle", "defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint", "point"):
        point = normalize_point(entry.get(field), precision)
        if point is not None:
            points.append(point)
    for item in entry.get("points") or []:
        point = normalize_point(item, precision)
        if point is not None:
            points.append(point)
    return unique_points(points)


def annotate_way_records(records: list[dict[str, Any]], kind: str, precision: int) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for item in records:
        annotated.append({"kind": kind, "points": item.get("points") or [], "interval_x": item.get("interval_x"), "interval_y": item.get("interval_y"), "center": item.get("center"), "radius": item.get("radius")})
    return annotated


def compact_way_records(records: list[dict[str, Any]]) -> None:
    for item in records:
        item.pop("points", None)


def build_way_highlights(records: list[dict[str, Any]], precision: int) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for item in records:
        points = []
        for point in item.get("points") or []:
            normalized = normalize_point(point, precision)
            if normalized is not None:
                points.append([normalized[0], normalized[1]])
        if not points:
            continue
        highlights.append(
            {
                "kind": item.get("kind", ""),
                "points": points,
            }
        )
    return highlights


def copy_constraint_geometry(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field in CONSTRAINT_GEOMETRY_FIELDS:
        if field in source:
            target[field] = source[field]


def sample_circle_points(center: tuple[float, float], radius: float, precision: int, segments: int = 16) -> list[list[float]]:
    points: list[list[float]] = []
    if radius <= 0:
        return [[round(center[0], precision), round(center[1], precision)]]
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        x = round(center[0] + math.cos(angle) * radius, precision)
        y = round(center[1] + math.sin(angle) * radius, precision)
        points.append([x, y])
    return points


def sample_arc_points(
    center: tuple[float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    precision: int,
    segments: int = 12,
) -> list[list[float]]:
    if radius <= 0:
        return [[round(center[0], precision), round(center[1], precision)]]

    start = normalize_angle(start_angle)
    end = normalize_angle(end_angle)
    sweep = compute_ccw_sweep(start, end)
    step_count = max(3, min(segments, int(max(sweep, 1.0) / 15.0) + 1))
    points: list[list[float]] = []
    for index in range(step_count + 1):
        t = index / step_count
        angle = math.radians(start + sweep * t)
        x = round(center[0] + math.cos(angle) * radius, precision)
        y = round(center[1] + math.sin(angle) * radius, precision)
        points.append([x, y])
    return points


def normalize_angle(angle: float) -> float:
    return float(angle) % 360.0


def compute_ccw_sweep(start: float, end: float) -> float:
    if end >= start:
        return end - start
    return 360.0 - (start - end)


def interval_from_points(points: list[list[float]], axis: int, precision: int) -> list[float] | None:
    values = [round(float(point[axis]), precision) for point in points if point is not None and len(point) >= 2]
    if not values:
        return None
    return [min(values), max(values)]


def num(value: Any, precision: int = 4) -> float:
    return round(float(value), precision)


def unique_points(points: list[tuple[float, float] | None]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    result: list[tuple[float, float]] = []
    for point in points:
        if point is None or point in seen:
            continue
        seen.add(point)
        result.append(point)
    return result





def analyze_interpolate_file(payload_path: str, precision: int = 4) -> dict[str, Any]:
    text = Path(payload_path).read_text(encoding="utf-8")
    payload = json.loads(text)
    return analyze_interpolate_payload(payload, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload_file", nargs="?", help="Path to JSON payload file")
    args = parser.parse_args()

    if not args.payload_file:
        raise SystemExit("Missing payload file")

    result = analyze_interpolate_file(args.payload_file)
    print_report(result)


if __name__ == "__main__":
    main()

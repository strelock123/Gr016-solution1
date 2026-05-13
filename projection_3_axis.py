from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from utils import normalize_point


def analyze_projection_3_axis_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    try:
        return _analyze_projection_3_axis_payload(payload, precision=precision)
    except Exception as exc:
        return {"error": f"projection_3_axis failed: {exc}"}


def _analyze_projection_3_axis_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    top_points = payload.get("top_points") or []
    font_points = payload.get("font_points") or payload.get("front_points") or []
    side_points = payload.get("side_points") or []

    top_constraints = payload.get("top_constraints") or []
    font_constraints = payload.get("font_constraints") or []
    side_constraints = payload.get("side_constraints") or []

    ox_projection = unique_axis_points(top_points, axis="x", precision=precision)
    oy_projection = unique_axis_points(font_points, axis="y", precision=precision)
    oz_projection = unique_axis_points(side_points, axis="x", precision=precision)

    x_side_max = axis_max(side_points, axis="x", precision=precision)
    y_top_min = axis_min(top_points, axis="y", precision=precision)
    delta_oz = round(x_side_max + y_top_min, precision)

    ox_projection_constraints = merge_projection_triplets(
        project_constraints(font_constraints + top_constraints, axis="x", precision=precision),
        precision=precision,
    )
    oy_projection_constraints = merge_projection_triplets(
        project_constraints(font_constraints + side_constraints, axis="y", precision=precision),
        precision=precision,
    )

    oz_projection_constraints = merge_projection_triplets(
        project_constraints(side_constraints, axis="x", precision=precision),
        precision=precision,
    )
    oz_projection_merge = project_constraints(top_constraints, axis="y", precision=precision)
    oz_projection_merge = map_oz_projection_merge(oz_projection_merge, delta_oz, precision)
    oz_projection_constraints = merge_projection_triplets(oz_projection_constraints + oz_projection_merge, precision=precision)

    return {
        "ox_projection": ox_projection,
        "oy_projection": oy_projection,
        "oz_projection": oz_projection,
        "delta_oz": delta_oz,
        "ox_projection_constraints": ox_projection_constraints,
        "oy_projection_constraints": oy_projection_constraints,
        "oz_projection_constraints": oz_projection_constraints,
        "oz_projection_merge": oz_projection_merge,
    }


def project_constraints(constraints: list[dict[str, Any]], axis: str, precision: int) -> list[list[float]]:
    projected: list[list[float]] = []
    for entry in constraints:
        projected.extend(project_constraint_entry(entry, axis=axis, precision=precision))
    return projected


def project_constraint_entry(entry: dict[str, Any], axis: str, precision: int) -> list[list[float]]:
    kind = str(entry.get("kind", "")).lower()
    points = extract_points(entry, precision)
    center = get_point(entry, "center", precision)
    point_on_circle = get_point(entry, "point_on_circle", precision)
    point_count = len(points)

    if is_circle_like(kind, center, point_on_circle, points):
        radius = resolve_radius(center, point_on_circle, entry, precision)
        if center is None or radius is None:
            return []
        axis_value = center[0] if axis == "x" else center[1]
        return [
            [round(axis_value - radius, precision), round(axis_value, precision), 1.0],
            [round(axis_value, precision), round(axis_value + radius, precision), 1.0],
        ]

    if is_arc_like(kind, center, points, point_on_circle):
        end_points = [point for point in points if center is None or point != center]
        if center is None or len(end_points) < 2:
            return []
        axis_index = 0 if axis == "x" else 1
        axis_center = round(center[axis_index], precision)
        p1 = round(end_points[0][axis_index], precision)
        p2 = round(end_points[1][axis_index], precision)
        return [
            canonical_triplet([p1, axis_center, 0.7], precision),
            canonical_triplet([p2, axis_center, 0.7], precision),
        ]

    values = [round(point[0 if axis == "x" else 1], precision) for point in points]
    if not values:
        return []

    if kind == "distance_x":
        if axis == "x":
            return [canonical_triplet([values[0], values[min(1, len(values) - 1)], 1.0], precision)]
        return [canonical_triplet([values[0], values[0], 0.3], precision)]

    if kind == "distance_y":
        if axis == "x":
            return [canonical_triplet([values[0], values[0], 0.3], precision)]
        return [canonical_triplet([values[0], values[min(1, len(values) - 1)], 1.0], precision)]

    if kind in ("distance_edge", "distance_angle"):
        if len(values) >= 2:
            return [canonical_triplet([values[0], values[1], 0.7], precision)]
        return [canonical_triplet([values[0], values[0], 0.7], precision)]

    if point_count >= 2:
        if len(values) >= 2:
            return [canonical_triplet([values[0], values[1], 0.7], precision)]
        return [canonical_triplet([values[0], values[0], 0.7], precision)]

    return []


def is_circle_like(kind: str, center: tuple[float, float] | None, point_on_circle: tuple[float, float] | None, points: list[tuple[float, float]]) -> bool:
    if center is None:
        return False
    if point_on_circle is not None:
        return True
    return kind in ("distance_radius", "distance_other") and len(points) <= 2


def is_arc_like(kind: str, center: tuple[float, float] | None, points: list[tuple[float, float]], point_on_circle: tuple[float, float] | None) -> bool:
    if center is None:
        return False
    if point_on_circle is not None and kind == "distance_other":
        return False
    return kind in ("distance_other", "distance_angle") and len(points) >= 3


def resolve_radius(
    center: tuple[float, float] | None,
    point_on_circle: tuple[float, float] | None,
    entry: dict[str, Any],
    precision: int,
) -> float | None:
    if center is not None and point_on_circle is not None:
        return round(math.hypot(point_on_circle[0] - center[0], point_on_circle[1] - center[1]), precision)

    radius = entry.get("radius")
    if radius is None:
        return None
    try:
        return round(float(radius), precision)
    except Exception:
        return None


def unique_axis_points(items: list[dict[str, Any]], axis: str, precision: int) -> list[list[float]]:
    seen: set[float] = set()
    result: list[list[float]] = []
    axis_index = 0 if axis == "x" else 1
    for item in items:
        point = normalize_point(item.get("point"), precision)
        if point is None:
            continue
        value = round(point[axis_index], precision)
        if value in seen:
            continue
        seen.add(value)
        result.append([value, 0.0])
    return sorted(result, key=lambda pair: pair[0])


def axis_max(items: list[dict[str, Any]], axis: str, precision: int) -> float:
    values = []
    axis_index = 0 if axis == "x" else 1
    for item in items:
        point = normalize_point(item.get("point"), precision)
        if point is not None:
            values.append(point[axis_index])
    return round(max(values) if values else 0.0, precision)


def axis_min(items: list[dict[str, Any]], axis: str, precision: int) -> float:
    values = []
    axis_index = 0 if axis == "x" else 1
    for item in items:
        point = normalize_point(item.get("point"), precision)
        if point is not None:
            values.append(point[axis_index])
    return round(min(values) if values else 0.0, precision)


def map_oz_projection_merge(items: list[list[float]], delta_oz: float, precision: int) -> list[list[float]]:
    mapped: list[list[float]] = []
    for item in items:
        if len(item) < 3:
            continue
        y1, y2, a = item[0], item[1], item[2]
        mapped.append([round(-y1 + delta_oz, precision), round(-y2 + delta_oz, precision), round(a, precision)])
    return mapped


def merge_projection_triplets(items: list[list[float]], precision: int) -> list[list[float]]:
    seen: set[tuple[float, float, float]] = set()
    result: list[list[float]] = []
    for item in items:
        if len(item) < 3:
            continue
        canonical = canonical_triplet(item, precision)
        key = triplet_key(canonical, precision)
        if key in seen:
            continue
        seen.add(key)
        result.append(canonical)
    return result


def canonical_triplet(item: list[float], precision: int) -> list[float]:
    a = round(float(item[0]), precision)
    b = round(float(item[1]), precision)
    c = round(float(item[2]), precision)
    if a > b:
        a, b = b, a
    return [a, b, c]


def triplet_key(item: list[float], precision: int) -> tuple[float, float, float]:
    a, b, c = item[0], item[1], item[2]
    if a > b:
        a, b = b, a
    return (round(a, precision), round(b, precision), round(c, precision))


def extract_points(entry: dict[str, Any], precision: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for field in ("start", "end", "dimension_point", "center", "point_on_circle", "defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
        point = get_point(entry, field, precision)
        if point is not None:
            points.append(point)

    unique: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for point in points:
        if point in seen:
            continue
        seen.add(point)
        unique.append(point)
    return unique


def get_point(entry: dict[str, Any], field: str, precision: int) -> tuple[float, float] | None:
    value = entry.get(field)
    return normalize_point(value, precision)





def analyze_projection_3_axis_file(payload_path: str, precision: int = 4) -> dict[str, Any]:
    text = Path(payload_path).read_text(encoding="utf-8")
    payload = json.loads(text)
    return analyze_projection_3_axis_payload(payload, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload_file", nargs="?", help="Path to JSON payload file")
    args = parser.parse_args()

    if not args.payload_file:
        raise SystemExit("Missing payload file")

    result = analyze_projection_3_axis_file(args.payload_file)
    print_report(result)


if __name__ == "__main__":
    main()

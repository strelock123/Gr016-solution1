from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from utils import normalize_point


def analyze_lack_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    try:
        return _analyze_lack_payload(payload, precision=precision)
    except Exception as exc:
        return {"error": f"lack_print failed: {exc}"}


def _analyze_lack_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    ox_projection = payload.get("ox_projection") or []
    oy_projection = payload.get("oy_projection") or []
    oz_projection = payload.get("oz_projection") or []

    ox_projection_constraints = payload.get("ox_projection_constraints") or []
    oy_projection_constraints = payload.get("oy_projection_constraints") or []
    oz_projection_constraints = payload.get("oz_projection_constraints") or []

    ox_offset = compute_projection_offset(ox_projection, ox_projection_constraints, precision)
    oy_offset = compute_projection_offset(oy_projection, oy_projection_constraints, precision)
    oz_offset = compute_projection_offset(oz_projection, oz_projection_constraints, precision)

    ox_lack = find_lack_constraints(ox_projection, ox_projection_constraints, precision)
    oy_lack = find_lack_constraints(oy_projection, oy_projection_constraints, precision)
    oz_lack = find_lack_constraints(oz_projection, oz_projection_constraints, precision)

    distance_radius = payload.get("distance_radius") or []
    distance_other = payload.get("distance_other") or []
    circle_board = payload.get("circle_board") or []
    lack_distance_other = build_missing_radius_records(circle_board, distance_radius, distance_other, precision)

    return {
        "ox_projection_offset": ox_offset,
        "oy_projection_offset": oy_offset,
        "oz_projection_offset": oz_offset,
        "ox_lack_constraints": ox_lack,
        "oy_lack_constraints": oy_lack,
        "oz_lack_constraints": oz_lack,
        "lack_distance_other": lack_distance_other,
        "highlight_groups": {
            "lack_distance_other": build_missing_radius_highlights(lack_distance_other),
        },
    }


# ---------------------------------------------------------------------------
# Floyd-Warshall based projection analysis
# ---------------------------------------------------------------------------

INF = float("inf")


def compute_projection_offset(
    projection: list[list[float]],
    constraints: list[list[float]],
    precision: int,
) -> list[list[float]]:
    """For each node in *projection*, sum up the offset `o` from every
    constraint `[x1, x2, o]` where the node appears as x1 or x2.

    Input:  ox_projection = [[coord, 0], ...]
            ox_projection_constraints = [[x1, x2, o], ...]
    Output: [[coord, accumulated_o], ...]  (same order as projection)
    """
    # Build a map: coordinate -> accumulated offset.
    offset_map: dict[float, float] = {}
    for item in projection:
        if not item:
            continue
        coord = round(float(item[0]), precision)
        offset_map.setdefault(coord, 0.0)

    for item in constraints:
        if len(item) < 3:
            continue
        x1 = round(float(item[0]), precision)
        x2 = round(float(item[1]), precision)
        o = round(float(item[2]), precision)
        if x1 in offset_map:
            offset_map[x1] = round(offset_map[x1] + o, precision)
        if x2 in offset_map:
            offset_map[x2] = round(offset_map[x2] + o, precision)

    # Rebuild in original order.
    result: list[list[float]] = []
    seen: set[float] = set()
    for item in projection:
        if not item:
            continue
        coord = round(float(item[0]), precision)
        if coord in seen:
            continue
        seen.add(coord)
        result.append([coord, offset_map.get(coord, 0.0)])
    return result


def find_lack_constraints(
    projection: list[list[float]],
    constraints: list[list[float]],
    precision: int,
) -> list[list[float]]:
    """Find pairs of projection nodes that are NOT yet connected even after
    Floyd-Warshall transitivity.  These are the constraints that must be added
    so that every node relates to every other node."""
    nodes = collect_projection_nodes(projection, precision)
    if len(nodes) <= 1:
        return []

    index_map = {v: i for i, v in enumerate(nodes)}
    size = len(nodes)
    dist = [[INF] * size for _ in range(size)]

    for i in range(size):
        dist[i][i] = 0.0

    for item in constraints:
        if len(item) < 3:
            continue
        a = round(float(item[0]), precision)
        b = round(float(item[1]), precision)
        if a > b:
            a, b = b, a
        ia = index_map.get(a)
        ib = index_map.get(b)
        if ia is None or ib is None:
            continue
        edge_w = round(b - a, precision)
        if edge_w < dist[ia][ib]:
            dist[ia][ib] = edge_w
            dist[ib][ia] = edge_w

    # Floyd-Warshall.
    for k in range(size):
        for i in range(size):
            dik = dist[i][k]
            if dik == INF:
                continue
            for j in range(size):
                alt = dik + dist[k][j]
                if alt < dist[i][j]:
                    dist[i][j] = alt

    # Find connected components via reachability.
    component_id = [-1] * size
    current_component = 0
    for i in range(size):
        if component_id[i] >= 0:
            continue
        component_id[i] = current_component
        for j in range(i + 1, size):
            if dist[i][j] < INF:
                component_id[j] = current_component
        current_component += 1

    if current_component <= 1:
        return []

    # Group nodes by component (already sorted by coordinate).
    components: list[list[int]] = [[] for _ in range(current_component)]
    for i in range(size):
        components[component_id[i]].append(i)

    # Bridge adjacent components: connect the last node of component k
    # to the first node of component k+1.  This gives exactly
    # (num_components - 1) edges — the minimum to make everything
    # transitively connected.
    lack: list[list[float]] = []
    for k in range(current_component - 1):
        tail = components[k][-1]
        head = components[k + 1][0]
        lack.append([nodes[tail], nodes[head]])
    return lack


def collect_projection_nodes(
    projection: list[list[float]],
    precision: int,
) -> list[float]:
    """Extract unique sorted first-axis coordinate values from the projection."""
    seen: set[float] = set()
    result: list[float] = []
    for item in projection:
        if not item:
            continue
        coord = round(float(item[0]), precision)
        if coord in seen:
            continue
        seen.add(coord)
        result.append(coord)
    result.sort()
    return result


# ---------------------------------------------------------------------------
# Missing radius / circle detection (unchanged logic)
# ---------------------------------------------------------------------------


def build_missing_radius_records(
    circle_board: list[dict[str, Any]],
    distance_radius: list[dict[str, Any]],
    distance_other: list[dict[str, Any]],
    precision: int,
) -> list[dict[str, Any]]:
    existing_centers = collect_record_centers(distance_radius + distance_other, precision)
    results: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()

    for circle in circle_board:
        center = normalize_point(circle.get("center"), precision)
        if center is None or center in seen:
            continue
        if center in existing_centers:
            continue
        radius = round(float(circle.get("radius", 0.0)), precision)
        point_on_circle = [round(center[0] + radius, precision), round(center[1], precision)]
        results.append(
            {
                "kind": "distance_other",
                "center": [center[0], center[1]],
                "point_on_circle": point_on_circle,
                "radius": radius,
                "points": [[center[0], center[1]], point_on_circle],
            }
        )
        seen.add(center)
    return results


def build_missing_radius_highlights(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "lack_distance_other",
            "points": item.get("points") or [],
        }
        for item in records
        if item.get("points")
    ]


def collect_record_centers(records: list[dict[str, Any]], precision: int) -> set[tuple[float, float]]:
    centers: set[tuple[float, float]] = set()
    for record in records:
        center = normalize_point(record.get("center"), precision)
        if center is None and record.get("kind") == "distance_other":
            center = normalize_point(record.get("defpoint"), precision)
        if center is not None:
            centers.add(center)
    return centers


def collect_record_points(records: list[dict[str, Any]], precision: int) -> set[tuple[float, float]]:
    points: set[tuple[float, float]] = set()
    for record in records:
        for point in extract_record_points(record, precision):
            points.add(point)
    return points


def extract_record_points(record: dict[str, Any], precision: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for field in ("point", "center", "start", "end", "dimension_point", "point_on_circle"):
        point = normalize_point(record.get(field), precision)
        if point is not None:
            points.append(point)
    for item in record.get("points") or []:
        point = normalize_point(item, precision)
        if point is not None:
            points.append(point)
    return unique_points(points)


def unique_points(points: list[tuple[float, float] | None]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    result: list[tuple[float, float]] = []
    for point in points:
        if point is None or point in seen:
            continue
        seen.add(point)
        result.append(point)
    return result





def analyze_lack_file(payload_path: str, precision: int = 4) -> dict[str, Any]:
    text = Path(payload_path).read_text(encoding="utf-8")
    payload = json.loads(text)
    return analyze_lack_payload(payload, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload_file", nargs="?", help="Path to JSON payload file")
    args = parser.parse_args()

    if not args.payload_file:
        raise SystemExit("Missing payload file")

    result = analyze_lack_file(args.payload_file)
    print_report(result)


if __name__ == "__main__":
    main()

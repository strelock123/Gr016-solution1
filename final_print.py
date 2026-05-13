from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from utils import normalize_point


def analyze_final_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    try:
        return _analyze_final_payload(payload, precision=precision)
    except Exception as exc:
        return {"error": f"final_print failed: {exc}"}


def _analyze_final_payload(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    ox_lack = payload.get("ox_lack_constraints") or []
    oy_lack = payload.get("oy_lack_constraints") or []
    oz_lack = payload.get("oz_lack_constraints") or []

    ox_projection_offset = payload.get("ox_projection_offset") or []
    oy_projection_offset = payload.get("oy_projection_offset") or []
    oz_projection_offset = payload.get("oz_projection_offset") or []

    font_points = payload.get("font_points") or []
    side_points = payload.get("side_points") or []

    # ox: lack constraints → distance_x between font endpoints matched by x-axis
    final_distance_x = build_final_from_lack(
        ox_lack, ox_projection_offset, font_points,
        axis="x", kind="distance_x", precision=precision,
    )
    # oy: lack constraints → distance_y between font endpoints matched by y-axis
    final_distance_y = build_final_from_lack(
        oy_lack, oy_projection_offset, font_points,
        axis="y", kind="distance_y", precision=precision,
    )
    # oz: lack constraints → distance_x between side endpoints matched by x-axis
    final_distance_oz = build_final_from_lack(
        oz_lack, oz_projection_offset, side_points,
        axis="x", kind="distance_x", precision=precision,
    )

    return {
        "final_distance_x": final_distance_x,
        "final_distance_y": final_distance_y,
        "final_distance_oz": final_distance_oz,
        "highlight_groups": {
            "final_distance_x": build_highlights(final_distance_x),
            "final_distance_y": build_highlights(final_distance_y),
            "final_distance_oz": build_highlights(final_distance_oz),
        },
    }


def build_final_from_lack(
    lack_constraints: list[list[float]],
    projection_offset: list[list[float]],
    points: list[dict[str, Any]],
    axis: str,
    kind: str,
    precision: int,
) -> list[dict[str, Any]]:
    """For each [x1, x2] in *lack_constraints*, check if the offset value
    of x1 or x2 in *projection_offset* is < 1.  If so, create a constraint
    of the given *kind* between the two endpoints in *points* whose coordinate
    on *axis* matches x1 and x2."""

    # Build offset map: coord -> offset value.
    offset_map: dict[float, float] = {}
    for item in projection_offset:
        if not item or len(item) < 2:
            continue
        coord = round(float(item[0]), precision)
        offset_map[coord] = round(float(item[1]), precision)

    # Build point map: coord (on the specified axis) -> [x, y].
    axis_index = 0 if axis == "x" else 1
    point_map: dict[float, list[float]] = {}
    for item in points:
        point = normalize_point(item.get("point"), precision)
        if point is None:
            continue
        coord = round(point[axis_index], precision)
        if coord not in point_map:
            point_map[coord] = [point[0], point[1]]

    results: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()

    for lack in lack_constraints:
        if len(lack) < 2:
            continue
        x1 = round(float(lack[0]), precision)
        x2 = round(float(lack[1]), precision)

        # Check: at least one of x1, x2 must have offset < 1.
        e1 = offset_map.get(x1, 0.0)
        e2 = offset_map.get(x2, 0.0)
        if e1 >= 1 and e2 >= 1:
            continue

        # Find matching endpoints.
        p1 = point_map.get(x1)
        p2 = point_map.get(x2)
        if p1 is None or p2 is None:
            continue

        # Deduplicate.
        key = (min(x1, x2), max(x1, x2))
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "kind": kind,
            "points": [list(p1), list(p2)],
        })

    return results


def build_highlights(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for item in records:
        points = item.get("points") or []
        if len(points) < 2:
            continue
        highlights.append({"kind": item.get("kind", ""), "points": points})
    return highlights





def analyze_final_file(payload_path: str, precision: int = 4) -> dict[str, Any]:
    text = Path(payload_path).read_text(encoding="utf-8")
    payload = json.loads(text)
    return analyze_final_payload(payload, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload_file", nargs="?", help="Path to JSON payload file")
    args = parser.parse_args()

    if not args.payload_file:
        raise SystemExit("Missing payload file")

    result = analyze_final_file(args.payload_file)
    print_report(result)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import recover

from utils import classify_axis_dimension, vec_to_xy


# Set to False to disable highlight metadata export to the frontend quickly.
ENABLE_HIGHLIGHT_EXPORT = False


def analyze_dxf_text(dxf_text: str, precision: int = 4) -> dict[str, Any]:
    try:
        doc = ezdxf.read(io.StringIO(dxf_text))
    except Exception as exc:
        return {"error": f"Invalid or corrupt DXF file: {exc}"}

    return analyze_document(doc, precision=precision)


def analyze_dxf_bytes(dxf_bytes: bytes, precision: int = 4) -> dict[str, Any]:
    try:
        doc, _auditor = recover.read(io.BytesIO(dxf_bytes))
    except Exception as exc:
        return {"error": f"Invalid or corrupt DXF file: {exc}"}

    return analyze_document(doc, precision=precision)


def analyze_dxf_base64(payload: str, precision: int = 4) -> dict[str, Any]:
    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:
        return {"error": f"Invalid base64 DXF payload: {exc}"}
    return analyze_dxf_bytes(data, precision=precision)


def analyze_document(doc, precision: int = 4) -> dict[str, Any]:
    msp = doc.modelspace()
    distance_x: list[dict[str, Any]] = []
    distance_y: list[dict[str, Any]] = []
    distance_radius: list[dict[str, Any]] = []
    distance_angle: list[dict[str, Any]] = []
    distance_edge: list[dict[str, Any]] = []
    distance_other: list[dict[str, Any]] = []
    line_entities: list[dict[str, Any]] = []
    arc_entities: list[dict[str, Any]] = []
    circle_entities: list[dict[str, Any]] = []

    for index, entity in enumerate(msp):
        etype = entity.dxftype().upper()
        if etype == "LINE":
            start = vec_to_xy(getattr(entity.dxf, "start", None), precision)
            end = vec_to_xy(getattr(entity.dxf, "end", None), precision)
            if start is not None and end is not None:
                line_entities.append(
                    {
                        "start": start,
                        "end": end,
                    }
                )
            continue

        if etype == "ARC":
            center = vec_to_xy(getattr(entity.dxf, "center", None), precision)
            radius = round(float(getattr(entity.dxf, "radius", 0.0)), precision)
            arc_entities.append(
                {
                    "center": center,
                    "radius": radius,
                    "start_angle": round(float(getattr(entity.dxf, "start_angle", 0.0)), precision),
                    "end_angle": round(float(getattr(entity.dxf, "end_angle", 0.0)), precision),
                }
            )
            continue

        if etype == "CIRCLE":
            center = vec_to_xy(getattr(entity.dxf, "center", None), precision)
            radius = round(float(getattr(entity.dxf, "radius", 0.0)), precision)
            circle_entities.append(
                {
                    "center": center,
                    "radius": radius,
                }
            )
            continue

    for index, dim in enumerate(msp.query("DIMENSION")):
        entry = extract_dimension(dim, index, precision)
        kind = entry.get("kind", "other")
        if kind == "distance_x":
            distance_x.append(entry)
        elif kind == "distance_y":
            distance_y.append(entry)
        elif kind == "distance_radius":
            distance_radius.append(entry)
        elif kind == "distance_angle":
            distance_angle.append(entry)
        elif kind == "distance_edge":
            distance_edge.append(entry)
        else:
            distance_other.append(entry)

    full_distance_xy = build_full_distance_xy(distance_x, distance_y, precision)
    if ENABLE_HIGHLIGHT_EXPORT:
        highlight_groups = build_highlight_groups(
            {
                "distance_x": distance_x,
                "distance_y": distance_y,
                "distance_edge": distance_edge,
                "distance_angle": distance_angle,
                "distance_radius": distance_radius,
                "distance_other": distance_other,
            },
            precision,
        )
    else:
        highlight_groups = {}
        strip_dimension_points(distance_x)
        strip_dimension_points(distance_y)
        strip_dimension_points(distance_radius)
        strip_dimension_points(distance_angle)
        strip_dimension_points(distance_edge)
        strip_dimension_points(distance_other)

    return {
        "distance_x": distance_x,
        "distance_y": distance_y,
        "distance_radius": distance_radius,
        "distance_angle": distance_angle,
        "distance_edge": distance_edge,
        "distance_other": distance_other,
        "line_entities": line_entities,
        "arc_entities": arc_entities,
        "circle_entities": circle_entities,
        "highlight_groups": highlight_groups,
    }


def extract_dimension(dim, index: int, precision: int) -> dict[str, Any]:
    dim_type = int(getattr(dim, "dimtype", getattr(dim.dxf, "dimtype", 0))) & 7
    entry: dict[str, Any] = {"dim_type": dim_type, "kind": "other"}

    if dim_type == 0:
        p2 = vec_to_xy(getattr(dim.dxf, "defpoint2", None), precision)
        p3 = vec_to_xy(getattr(dim.dxf, "defpoint3", None), precision)
        p_dim = vec_to_xy(getattr(dim.dxf, "defpoint", None), precision)
        angle = round(float(getattr(dim.dxf, "angle", 0.0)), precision)

        if p2 is not None:
            entry["start"] = p2
        if p3 is not None:
            entry["end"] = p3
        if p_dim is not None:
            entry["dimension_point"] = p_dim
        entry["angle"] = angle

        entry["kind"] = classify_axis_dimension(angle, precision)

    elif dim_type == 1:
        entry["kind"] = "distance_edge"
        for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    elif dim_type == 2:
        entry["kind"] = "distance_angle"
        for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    elif dim_type == 3:
        center = vec_to_xy(getattr(dim.dxf, "defpoint", None), precision)
        point_on_circle = vec_to_xy(getattr(dim.dxf, "defpoint4", None), precision)
        if center is not None:
            entry["center"] = center
        if point_on_circle is not None:
            entry["point_on_circle"] = point_on_circle
        entry["kind"] = "distance_radius"

    elif dim_type == 4:
        entry["kind"] = "distance_other"
        for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    elif dim_type == 5:
        entry["kind"] = "distance_other"
        for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    elif dim_type == 6:
        entry["kind"] = "distance_other"
        for name in ("defpoint", "defpoint2", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    elif dim_type == 8:
        entry["kind"] = "distance_other"
        for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
            point = vec_to_xy(getattr(dim.dxf, name, None), precision)
            if point is not None:
                entry[name] = point

    return entry





def build_full_distance_xy(
    distance_x: list[dict[str, Any]],
    distance_y: list[dict[str, Any]],
    precision: int,
) -> list[dict[str, Any]]:
    x_points = index_dimension_points(distance_x, precision)
    y_points = index_dimension_points(distance_y, precision)

    common_keys = sorted(set(x_points).intersection(y_points))
    result: list[dict[str, Any]] = []
    for key in common_keys:
        x_entry = x_points[key]
        y_entry = y_points[key]
        result.append(
            {
                "point": x_entry["point"],
                "distance_x_refs": x_entry["refs"],
                "distance_y_refs": y_entry["refs"],
            }
        )
    return result


def index_dimension_points(dimensions: list[dict[str, Any]], precision: int) -> dict[tuple[float, float], dict[str, Any]]:
    indexed: dict[tuple[float, float], dict[str, Any]] = {}
    for entry in dimensions:
        for ref in iter_entry_points(entry, precision):
            point = ref["point"]
            if point is None:
                continue
            key = (point[0], point[1])
            bucket = indexed.setdefault(key, {"point": point, "refs": []})
            bucket["refs"].append({"field": ref["field"], "point": point})
    return indexed


def iter_entry_points(entry: dict[str, Any], precision: int) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for field in ("start", "end", "dimension_point", "center", "point_on_circle"):
        point = vec_to_xy(entry.get(field), precision)
        if point is not None:
            points.append({"field": field, "point": point})

    for item in entry.get("points") or []:
        point = vec_to_xy(item.get("coords"), precision)
        if point is not None:
            points.append({"field": item.get("name", "points"), "point": point})

    return points


def build_highlight_groups(groups: dict[str, list[dict[str, Any]]], precision: int) -> dict[str, list[dict[str, Any]]]:
    highlight_groups: dict[str, list[dict[str, Any]]] = {}
    for group_name, entries in groups.items():
        items: list[dict[str, Any]] = []
        for entry in entries:
            points = extract_highlight_points(entry, group_name, precision)
            if not points:
                continue
            items.append({"kind": group_name, "points": points})
        highlight_groups[group_name] = items
    return highlight_groups


def strip_dimension_points(dimensions: list[dict[str, Any]]) -> None:
    for entry in dimensions:
        entry.pop("points", None)


def attach_endpoint_names(payload: dict[str, Any], precision: int = 4) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return payload

    endpoint_board = payload.get("endpoint_board") or []
    if not endpoint_board:
        return payload

    name_map = build_endpoint_name_map(endpoint_board, precision)
    for group_name in ("distance_x", "distance_y", "distance_radius", "distance_angle", "distance_edge", "distance_other"):
        items = payload.get(group_name)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            names = collect_endpoint_names(item, name_map, precision)
            if names:
                item["endpoint_names"] = names
    return payload


def build_endpoint_name_map(endpoint_board: list[dict[str, Any]], precision: int) -> dict[tuple[float, float], str]:
    name_map: dict[tuple[float, float], str] = {}
    for item in endpoint_board:
        point = vec_to_xy(item.get("point"), precision)
        name = item.get("name")
        if point is None or not name:
            continue
        name_map[(point[0], point[1])] = str(name)
    return name_map


def collect_endpoint_names(item: dict[str, Any], name_map: dict[tuple[float, float], str], precision: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for field in ("start", "end", "dimension_point", "center", "point_on_circle", "defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
        point = vec_to_xy(item.get(field), precision)
        if point is None:
            continue
        name = name_map.get((point[0], point[1]))
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    for ref in item.get("points") or []:
        point = vec_to_xy(ref.get("coords"), precision)
        if point is None:
            continue
        name = name_map.get((point[0], point[1]))
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    return names


def extract_highlight_points(entry: dict[str, Any], group_name: str, precision: int) -> list[list[float]]:
    field_map = {
        "distance_x": ("start", "end", "dimension_point"),
        "distance_y": ("start", "end", "dimension_point"),
        "distance_edge": ("start", "end", "dimension_point", "defpoint", "defpoint2", "defpoint3", "defpoint4", "text_midpoint"),
        "distance_angle": ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"),
        "distance_radius": ("center", "point_on_circle"),
        "distance_other": ("start", "end", "dimension_point", "center", "point_on_circle", "defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"),
    }
    points: list[list[float]] = []
    seen: set[tuple[float, float]] = set()

    for field in field_map.get(group_name, ()):
        point = vec_to_xy(entry.get(field), precision)
        if point is None:
            continue
        key = (point[0], point[1])
        if key in seen:
            continue
        seen.add(key)
        points.append(point)

    if group_name in ("distance_x", "distance_y", "distance_radius", "distance_other") and len(points) < 2:
        for point_entry in entry.get("points") or []:
            point = vec_to_xy(point_entry.get("coords"), precision)
            if point is None:
                continue
            key = (point[0], point[1])
            if key in seen:
                continue
            seen.add(key)
            points.append(point)

    return points


def capture_points(dim) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
        if not dim.dxf.hasattr(name):
            continue
        point = vec_to_xy(getattr(dim.dxf, name, None))
        if point is not None:
            points.append({"name": name, "coords": point})
    return points





def analyze_dxf_file(dxf_path: str, precision: int = 4) -> dict[str, Any]:
    data = Path(dxf_path).read_bytes()
    return analyze_dxf_bytes(data, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", nargs="?", help="Path to DXF file")
    args = parser.parse_args()

    if not args.dxf_file:
        raise SystemExit("Missing DXF file path")

    result = analyze_dxf_file(args.dxf_file)
    print_report(result)


if __name__ == "__main__":
    main()

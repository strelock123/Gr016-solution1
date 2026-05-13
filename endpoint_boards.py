from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import recover

from utils import (
    add_circle,
    add_endpoint,
    angle_point,
    iter_polyline_points,
    vec_to_xy,
)


# Set to False to disable highlight metadata export for endpoint/circle boards.
ENABLE_ENDPOINT_HIGHLIGHT_EXPORT = False


def analyze_endpoint_boards_text(dxf_text: str, precision: int = 4) -> dict[str, Any]:
    try:
        doc = ezdxf.read(io.StringIO(dxf_text))
    except Exception as exc:
        return {"error": f"Invalid or corrupt DXF file: {exc}"}
    return analyze_document(doc, precision=precision)


def analyze_endpoint_boards_bytes(dxf_bytes: bytes, precision: int = 4) -> dict[str, Any]:
    try:
        doc, _auditor = recover.read(io.BytesIO(dxf_bytes))
    except Exception as exc:
        return {"error": f"Invalid or corrupt DXF file: {exc}"}
    return analyze_document(doc, precision=precision)


def analyze_endpoint_boards_base64(payload: str, precision: int = 4) -> dict[str, Any]:
    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:
        return {"error": f"Invalid base64 DXF payload: {exc}"}
    return analyze_endpoint_boards_bytes(data, precision=precision)


def analyze_document(doc, precision: int = 4) -> dict[str, Any]:
    msp = doc.modelspace()
    endpoint_board: list[dict[str, Any]] = []
    circle_board: list[dict[str, Any]] = []

    for index, entity in enumerate(msp):
        etype = entity.dxftype().upper()

        if etype == "LINE":
            start = vec_to_xy(getattr(entity.dxf, "start", None), precision)
            end = vec_to_xy(getattr(entity.dxf, "end", None), precision)
            add_endpoint(endpoint_board, start)
            add_endpoint(endpoint_board, end)
            continue

        if etype in ("LWPOLYLINE", "POLYLINE"):
            for point in iter_polyline_points(entity, precision):
                add_endpoint(endpoint_board, point)
            continue

        if etype == "ARC":
            center = vec_to_xy(getattr(entity.dxf, "center", None), precision)
            radius = round(float(getattr(entity.dxf, "radius", 0.0)), precision)
            start_angle = float(getattr(entity.dxf, "start_angle", 0.0))
            end_angle = float(getattr(entity.dxf, "end_angle", 0.0))
            start = angle_point(center, radius, start_angle, precision)
            end = angle_point(center, radius, end_angle, precision)
            add_endpoint(endpoint_board, start)
            add_endpoint(endpoint_board, end)
            add_circle(circle_board, center, radius)
            continue

        if etype == "CIRCLE":
            center = vec_to_xy(getattr(entity.dxf, "center", None), precision)
            radius = round(float(getattr(entity.dxf, "radius", 0.0)), precision)
            add_circle(circle_board, center, radius)
            continue

        if etype == "POINT":
            location = vec_to_xy(getattr(entity.dxf, "location", None), precision)
            add_endpoint(endpoint_board, location)

    for idx, item in enumerate(endpoint_board, start=1):
        item["name"] = f"P{idx}"

    result = {
        "endpoint_board": endpoint_board,
        "circle_board": circle_board,
    }

    if ENABLE_ENDPOINT_HIGHLIGHT_EXPORT:
        result["highlight_groups"] = build_highlight_groups(endpoint_board, circle_board, precision)

    return result





def build_highlight_groups(
    endpoint_board: list[dict[str, Any]],
    circle_board: list[dict[str, Any]],
    precision: int,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "endpoint_board": build_endpoint_highlights(endpoint_board, precision),
        "circle_board": build_circle_highlights(circle_board, precision),
    }


def build_endpoint_highlights(endpoint_board: list[dict[str, Any]], precision: int) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for item in endpoint_board:
        point = vec_to_xy(item.get("point"), precision)
        if point is None:
            continue
        highlights.append(
            {
                "point": point,
                "name": item.get("name", ""),
            }
        )
    return highlights


def build_circle_highlights(circle_board: list[dict[str, Any]], precision: int) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for item in circle_board:
        center = vec_to_xy(item.get("center"), precision)
        if center is None:
            continue
        highlights.append(
            {
                "center": center,
                "radius": round(float(item.get("radius", 0.0)), precision),
            }
        )
    return highlights


def analyze_endpoint_boards_file(dxf_path: str, precision: int = 4) -> dict[str, Any]:
    data = Path(dxf_path).read_bytes()
    return analyze_endpoint_boards_bytes(data, precision=precision)


def print_report(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", nargs="?", help="Path to DXF file")
    args = parser.parse_args()

    if not args.dxf_file:
        raise SystemExit("Missing DXF file path")

    result = analyze_endpoint_boards_file(args.dxf_file)
    print_report(result)


if __name__ == "__main__":
    main()

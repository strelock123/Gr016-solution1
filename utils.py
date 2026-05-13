"""
Shared utility functions for the DXF inspection pipeline.

This module consolidates duplicated helper functions that were previously
defined independently across multiple pipeline stages.

Functions:
    vec_to_xy         — Convert a 2D/3D vector to a [x, y] list with rounding.
    normalize_point   — Convert a point value to a (x, y) tuple with rounding.
    angle_point       — Compute a point on a circle/arc at a given angle.
    add_endpoint      — Add a deduplicated endpoint to a board.
    add_circle        — Add a circle record to a board.
    iter_polyline_points — Extract all vertices from LWPOLYLINE / POLYLINE entities.
    classify_axis_dimension — Classify a DXF angle as 'x' or 'y' axis dimension.
"""

from __future__ import annotations

import math
from typing import Any


DEFAULT_PRECISION = 4
"""Default number of decimal places for coordinate rounding."""

FLOAT_TOLERANCE = 10 ** (-DEFAULT_PRECISION)
"""Tolerance used for floating-point comparisons."""

MAX_INTERPOLATION_ITERATIONS = 64
"""Maximum iterations for coordinate propagation in interpolate.py."""


# ---------------------------------------------------------------------------
# Vector / point conversion helpers
# ---------------------------------------------------------------------------


def vec_to_xy(value, precision: int = DEFAULT_PRECISION) -> list[float] | None:
    """Convert a DXF vector (3D or 2D) to a rounded [x, y] list.

    Accepts a tuple, list, or an object with ``.x`` / ``.y`` attributes.
    Returns ``None`` when the input is ``None`` or cannot be converted.
    """
    if value is None:
        return None
    try:
        x = round(float(value[0]), precision)
        y = round(float(value[1]), precision)
    except Exception:
        try:
            x = round(float(value.x), precision)
            y = round(float(value.y), precision)
        except Exception:
            return None
    return [x, y]


def normalize_point(value, precision: int = DEFAULT_PRECISION) -> tuple[float, float] | None:
    """Convert a point value to a rounded ``(x, y)`` tuple.

    Accepts the same input types as :func:`vec_to_xy` but returns a tuple
    instead of a list (hashable — useful as a dict key).
    """
    if value is None:
        return None
    try:
        x = round(float(value[0]), precision)
        y = round(float(value[1]), precision)
    except Exception:
        try:
            x = round(float(value.x), precision)
            y = round(float(value.y), precision)
        except Exception:
            return None
    return (x, y)


def angle_point(
    center: list[float] | None,
    radius: float,
    degrees: float,
    precision: int = DEFAULT_PRECISION,
) -> list[float] | None:
    """Compute a point on a circle/arc given *center*, *radius* and *degrees*.

    Uses standard trigonometry::

        x = cx + cos(radians) * radius
        y = cy + sin(radians) * radius
    """
    if center is None:
        return None
    radians = degrees * math.pi / 180.0
    x = round(center[0] + math.cos(radians) * radius, precision)
    y = round(center[1] + math.sin(radians) * radius, precision)
    return [x, y]


# ---------------------------------------------------------------------------
# Endpoint / circle board helpers
# ---------------------------------------------------------------------------


def add_endpoint(target: list[dict[str, Any]], point: list[float] | None) -> None:
    """Append *point* to *target* if it is not ``None`` and not a duplicate."""
    if point is None:
        return
    for existing in target:
        if existing.get("point") == point:
            return
    target.append({"point": point})


def add_circle(
    target: list[dict[str, Any]],
    center: list[float] | None,
    radius: float,
) -> None:
    """Append a circle record to *target*."""
    if center is None:
        return
    target.append({"center": center, "radius": radius})


def iter_polyline_points(entity, precision: int = DEFAULT_PRECISION) -> list[list[float] | None]:
    """Extract all vertices from an LWPOLYLINE or POLYLINE entity.

    Returns a list of ``[x, y]`` coordinates (or ``None`` for bad vertices).
    """
    points: list[list[float] | None] = []

    if entity.dxftype().upper() == "LWPOLYLINE":
        for point in entity.get_points("xy"):
            points.append(vec_to_xy(point, precision))
        return points

    if entity.dxftype().upper() == "POLYLINE":
        for vertex in entity.vertices():
            location = getattr(vertex.dxf, "location", None)
            points.append(vec_to_xy(location, precision))
        return points

    return points


# ---------------------------------------------------------------------------
# Dimension classification helpers
# ---------------------------------------------------------------------------


def classify_axis_dimension(angle: float, precision: int = DEFAULT_PRECISION) -> str:
    """Classify a DXF dimension angle as belonging to the X or Y axis.

    Rules
    -----
    * angle ≈ 0° or 180°   → ``'x'`` (horizontal dimension)
    * angle ≈ 90°           → ``'y'`` (vertical dimension)
    """
    tol = 10 ** (-precision)
    normalised = angle % 360.0
    if normalised > 180.0:
        normalised -= 360.0
    if abs(normalised) < tol or abs(abs(normalised) - 180.0) < tol:
        return "x"
    if abs(abs(normalised) - 90.0) < tol:
        return "y"
    return "x"  # fallback

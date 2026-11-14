"""Small deterministic L-system canopy atlas; Python standard library only.

This is a geometric toy, not a model of living plant physiology.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

RULE = "F[+F]F[-F]F"
ANGLES = (12.0, 20.0, 30.0, 42.0, 60.0)
MAX_SEGMENTS = 15625


def grammar(iterations: int) -> str:
    """Expand a balanced context-free turtle word with a known segment bound."""
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 0 <= iterations <= 6:
        raise ValueError("iterations must be an integer from 0 to 6")
    word = "F"
    for _ in range(iterations):
        word = "".join(RULE if c == "F" else c for c in word)
    assert word.count("F") == 5**iterations <= MAX_SEGMENTS
    return word


def trace(word: str, angle_degrees: float) -> list[tuple[float, float, float, float]]:
    """Interpret F, +, -, [, ] into ordered line segments; reject malformed input."""
    if not math.isfinite(angle_degrees) or not 0 < angle_degrees < 90:
        raise ValueError("angle must be finite and strictly between 0 and 90 degrees")
    turn = math.radians(angle_degrees)
    x = y = 0.0
    heading = -math.pi / 2
    stack: list[tuple[float, float, float]] = []
    segments: list[tuple[float, float, float, float]] = []
    for token in word:
        if token == "F":
            if len(segments) >= MAX_SEGMENTS:
                raise ValueError("segment budget exceeded")
            nx, ny = x + math.cos(heading), y + math.sin(heading)
            segments.append((x, y, nx, ny))
            x, y = nx, ny
        elif token == "+":
            heading += turn
        elif token == "-":
            heading -= turn
        elif token == "[":
            stack.append((x, y, heading))
        elif token == "]":
            if not stack:
                raise ValueError("unmatched closing bracket")
            x, y, heading = stack.pop()
        else:
            raise ValueError(f"invalid turtle instruction {token!r}")
    if stack:
        raise ValueError("unmatched opening bracket")
    return segments


def hull_area(points: list[tuple[float, float]]) -> float:
    """Convex hull area of all segment endpoints (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    polygon = lower[:-1] + upper[:-1]
    return abs(sum(p[0] * q[1] - q[0] * p[1]
                   for p, q in zip(polygon, polygon[1:] + polygon[:1]))) / 2


def metrics(segments: list[tuple[float, float, float, float]]) -> dict[str, float | int]:
    """Report raw geometry; no biological or statistical interpretation."""
    if not segments:
        raise ValueError("at least one segment required")
    points = [(x1, y1) for x1, y1, _, _ in segments] + [
        (x2, y2) for _, _, x2, y2 in segments
    ]
    xs, ys = zip(*points)
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    area = hull_area(points)
    return {
        "segments": len(segments),
        "width": round(width, 6),
        "height": round(height, 6),
        "aspect_width_over_height": round(width / height, 6) if height else None,
        "hull_area": round(area, 6),
        "hull_fraction_of_bbox": round(area / (width * height), 6) if width and height else None,
    }


def atlas(iterations: int = 4, angles: tuple[float, ...] = ANGLES) -> tuple[str, dict]:
    """Return an SVG and a portable result record for one controlled sweep."""
    if not angles:
        raise ValueError("at least one angle required")
    word = grammar(iterations)
    panel_width, panel_height = 270, 355
    colors = ("#456b43", "#467b71", "#517b93", "#836c9a", "#a36f53")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{panel_width * len(angles)}" '
        f'height="{panel_height}" viewBox="0 0 {panel_width * len(angles)} {panel_height}">',
        '<rect width="100%" height="100%" fill="#f8f6f0"/>',
    ]
    records = []
    for index, angle in enumerate(angles):
        segments = trace(word, angle)
        values = metrics(segments)
        records.append({"angle_degrees": angle, **values})
        endpoints = [(x, y) for x1, y1, x2, y2 in segments for x, y in ((x1, y1), (x2, y2))]
        xs, ys = zip(*endpoints)
        minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
        scale = min(224 / max(maxx - minx, 1e-9), 250 / max(maxy - miny, 1e-9))
        # Each canopy is fitted independently; aspect ratios must be read from metrics.
        cx = index * panel_width + panel_width / 2
        def px(x: float) -> float:
            return cx + (x - (minx + maxx) / 2) * scale
        def py(y: float) -> float:
            return 172 + (y - (miny + maxy) / 2) * scale
        commands = " ".join(
            f"M{px(x1):.2f},{py(y1):.2f}L{px(x2):.2f},{py(y2):.2f}"
            for x1, y1, x2, y2 in segments
        )
        color = colors[index % len(colors)]
        parts.append(f'<g><rect x="{index * panel_width + 6}" y="6" width="258" height="343" '
                     'rx="8" fill="#fffdf8" stroke="#ddd9cc"/>')
        parts.append(f'<path d="{commands}" fill="none" stroke="{color}" '
                     'stroke-width="1.1" stroke-linecap="round"/>')
        parts.append(f'<text x="{cx:.1f}" y="30" text-anchor="middle" '
                     'font-family="sans-serif" font-size="15" fill="#25332a">'
                     f'{escape(f"angle {angle:g}°")}</text>')
        parts.append(f'<text x="{cx:.1f}" y="324" text-anchor="middle" '
                     'font-family="monospace" font-size="11" fill="#4c5952">'
                     f'aspect {values["aspect_width_over_height"]:.3f}</text></g>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n", {
        "experiment": "same-grammar-different-canopies",
        "rule": RULE,
        "axiom": "F",
        "iterations": iterations,
        "segment_length": 1,
        "note": "Independent panel fit; raw geometry in records, no biological validation",
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--angles", nargs="+", type=float, default=ANGLES)
    parser.add_argument("--svg", type=Path, default=Path("canopies.svg"))
    parser.add_argument("--json", type=Path, default=Path("measurements.json"))
    args = parser.parse_args()
    try:
        svg, record = atlas(args.iterations, tuple(args.angles))
    except ValueError as exc:
        parser.error(str(exc))
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(svg, encoding="utf-8")
    args.json.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

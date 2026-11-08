#!/usr/bin/env python3
"""Simplifica GeoJSON para visualización web sin dependencias externas.

Uso:
  python3 scripts/simplify_geojson.py entrada.geojson salida.geojson 0.01

Implementa Douglas-Peucker sobre anillos y líneas, redondea coordenadas y
elimina puntos duplicados. Es una simplificación de presentación: no sustituye
la geometría oficial para análisis legal o catastral.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def sq_dist(p, q):
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def point_segment_dist(p, a, b):
    if a == b:
        return math.sqrt(sq_dist(p, a))
    t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / sq_dist(a, b)
    t = max(0.0, min(1.0, t))
    proj = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return math.sqrt(sq_dist(p, proj))


def dp(points, tol):
    if len(points) <= 2:
        return points
    a, b = points[0], points[-1]
    max_d, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        d = point_segment_dist(points[i], a, b)
        if d > max_d:
            max_d, idx = d, i
    if max_d > tol:
        left = dp(points[: idx + 1], tol)
        right = dp(points[idx:], tol)
        return left[:-1] + right
    return [a, b]


def clean_ring(ring, tol):
    if not ring:
        return ring
    # Cierra el anillo si hace falta.
    closed = ring[0] == ring[-1]
    pts = [tuple(p[:2]) for p in ring]
    if not closed:
        pts.append(pts[0])
    out = dp(pts, tol)
    # Deduplicar puntos consecutivos.
    dedup = []
    for p in out:
        if not dedup or p != dedup[-1]:
            dedup.append(p)
    if len(dedup) < 4:
        return [tuple(p[:2]) for p in ring]
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    return dedup


def simplify_geometry(geom, tol):
    if not geom:
        return geom
    t = geom.get("type")
    if t == "Polygon":
        rings = [clean_ring(r, tol) for r in geom.get("coordinates", [])]
        return {"type": "Polygon", "coordinates": rings}
    if t == "MultiPolygon":
        polys = []
        for poly in geom.get("coordinates", []):
            rings = [clean_ring(r, tol) for r in poly]
            polys.append(rings)
        return {"type": "MultiPolygon", "coordinates": polys}
    if t == "LineString":
        pts = [tuple(p[:2]) for p in geom.get("coordinates", [])]
        return {"type": "LineString", "coordinates": dp(pts, tol)}
    if t == "MultiLineString":
        return {
            "type": "MultiLineString",
            "coordinates": [dp([tuple(p[:2]) for p in line], tol) for line in geom.get("coordinates", [])],
        }
    return geom


def round_coords(value, decimals=4):
    if isinstance(value, (int, float)):
        return round(value, decimals)
    if isinstance(value, list):
        return [round_coords(v, decimals) for v in value]
    return value


def main():
    if len(sys.argv) < 4:
        raise SystemExit("Uso: simplify_geojson.py entrada.geojson salida.geojson tolerancia")
    src, dst, tol = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3])
    data = json.loads(src.read_text())
    for feature in data.get("features", []):
        feature["geometry"] = simplify_geometry(feature.get("geometry"), tol)
        if feature.get("geometry"):
            feature["geometry"]["coordinates"] = round_coords(feature["geometry"].get("coordinates", []))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{src} -> {dst} ({dst.stat().st_size / 1e6:.1f} MB, {len(data.get('features', []))} features, tol={tol})")


if __name__ == "__main__":
    main()

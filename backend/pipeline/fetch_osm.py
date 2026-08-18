#!/usr/bin/env python3
"""
Fetch OSM building footprints + heights for the Umbra bbox and cache them
locally as GeoJSON (WGS84) for the frontend's 3D building layer.

Usage:
  python fetch_osm.py            # use cached file if present
  python fetch_osm.py --refresh  # re-fetch from Overpass even if cached
"""

import argparse
import json
from pathlib import Path

BBOX = dict(north=44.4340, south=44.4280, east=26.1060, west=26.0960)
METERS_PER_LEVEL = 3.0

# Fallback height by building type when neither height nor levels tag exists.
TYPE_HEIGHT_M = {
    "apartments": 10 * METERS_PER_LEVEL,
    "residential": 2 * METERS_PER_LEVEL,
    "house": 2 * METERS_PER_LEVEL,
    "church": 15.0,
    "retail": 4 * METERS_PER_LEVEL,
    "commercial": 4 * METERS_PER_LEVEL,
}
DEFAULT_HEIGHT_M = 8.0

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = DATA_DIR / "buildings.geojson"


def resolve_height(raw_h, raw_l, building_type):
    """height tag -> levels * 3.0 -> fallback by building type -> default."""
    if raw_h is not None and str(raw_h) != "nan":
        try:
            return float(str(raw_h).replace("m", "").strip()), "height"
        except ValueError:
            pass
    if raw_l is not None and str(raw_l) != "nan":
        try:
            return float(raw_l) * METERS_PER_LEVEL, "levels"
        except ValueError:
            pass
    if building_type in TYPE_HEIGHT_M:
        return TYPE_HEIGHT_M[building_type], "type_fallback"
    return DEFAULT_HEIGHT_M, "default"


def fetch_buildings():
    """Fetch buildings from Overpass via osmnx. Returns a GeoJSON dict
    (WGS84) with height_m / height_source properties per feature."""
    import osmnx as ox

    gdf = ox.features_from_bbox(
        bbox=(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]),
        tags={"building": True},
    )

    features = []
    stats = {"height": 0, "levels": 0, "type_fallback": 0, "default": 0}
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue

        btype = row.get("building")
        btype = btype if isinstance(btype, str) else None
        h, source = resolve_height(row.get("height"), row.get("building:levels"), btype)
        stats[source] += 1

        features.append({
            "type": "Feature",
            "properties": {
                "height_m": round(h, 1),
                "height_source": source,
                "building_type": btype or "unknown",
            },
            "geometry": geom.__geo_interface__,
        })

    total = sum(stats.values()) or 1
    print(f"OSM buildings in bbox: {total}")
    for k, v in stats.items():
        print(f"  {k:14s}: {v:5d} ({100*v/total:.1f}%)")

    return {"type": "FeatureCollection", "features": features}


def load_buildings(refresh=False):
    """Cache-first accessor: read CACHE_FILE unless missing or --refresh."""
    if CACHE_FILE.exists() and not refresh:
        print(f"Using cached buildings: {CACHE_FILE}")
        return json.loads(CACHE_FILE.read_text())

    fc = fetch_buildings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(fc))
    print(f"Wrote {CACHE_FILE} ({len(fc['features'])} features)")
    return fc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="bypass cache, re-fetch from Overpass")
    args = ap.parse_args()
    load_buildings(refresh=args.refresh)


if __name__ == "__main__":
    main()

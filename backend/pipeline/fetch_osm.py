#!/usr/bin/env python3
"""
Fetch OSM building footprints + heights and the walking street network for
the Umbra bbox. Caches everything to backend/data/ so Overpass is never hit
twice for the same bbox.

Usage:
  python fetch_osm.py            # use cached files if present
  python fetch_osm.py --refresh  # re-fetch from Overpass even if cached
"""

import argparse
import json
from pathlib import Path

from heights import resolve_height, build_buildings_parquet

BBOX = dict(north=44.4340, south=44.4280, east=26.1060, west=26.0960)

PIPELINE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BUILDINGS_GEOJSON = DATA_DIR / "buildings.geojson"
BUILDINGS_PARQUET = DATA_DIR / "buildings.parquet"
STREET_NETWORK_GRAPHML = DATA_DIR / "street_network.graphml"


def _fetch_buildings_gdf():
    import osmnx as ox

    ox.settings.cache_folder = str(PIPELINE_DIR / "cache")
    return ox.features_from_bbox(
        bbox=(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]),
        tags={"building": True},
    )


def _buildings_gdf_to_geojson(gdf):
    """WGS84 GeoJSON FeatureCollection for the frontend's 3D building layer."""
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


def fetch_buildings():
    """Fetch buildings once from Overpass and write both artifacts:
    buildings.geojson (WGS84, for the frontend) and buildings.parquet
    (UTM 32635, for the shadow/routing pipeline)."""
    gdf = _fetch_buildings_gdf()
    fc = _buildings_gdf_to_geojson(gdf)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    build_buildings_parquet(gdf, BUILDINGS_PARQUET)
    return fc


def fetch_street_network(refresh=False):
    """Fetch (or load cached) walking street network graph for the bbox."""
    import osmnx as ox

    ox.settings.cache_folder = str(PIPELINE_DIR / "cache")
    if STREET_NETWORK_GRAPHML.exists() and not refresh:
        print(f"Using cached street network: {STREET_NETWORK_GRAPHML}")
        return ox.load_graphml(STREET_NETWORK_GRAPHML)

    g = ox.graph_from_bbox(
        bbox=(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]),
        network_type="walk",
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(g, STREET_NETWORK_GRAPHML)
    print(f"Wrote {STREET_NETWORK_GRAPHML} ({len(g.nodes)} nodes, {len(g.edges)} edges)")
    return g


def load_buildings(refresh=False):
    """Cache-first accessor for the frontend: read buildings.geojson unless
    missing, buildings.parquet missing, or --refresh."""
    if BUILDINGS_GEOJSON.exists() and BUILDINGS_PARQUET.exists() and not refresh:
        print(f"Using cached buildings: {BUILDINGS_GEOJSON}")
        return json.loads(BUILDINGS_GEOJSON.read_text())

    fc = fetch_buildings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BUILDINGS_GEOJSON.write_text(json.dumps(fc))
    print(f"Wrote {BUILDINGS_GEOJSON} ({len(fc['features'])} features)")
    return fc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="bypass cache, re-fetch from Overpass")
    args = ap.parse_args()
    load_buildings(refresh=args.refresh)
    fetch_street_network(refresh=args.refresh)


if __name__ == "__main__":
    main()

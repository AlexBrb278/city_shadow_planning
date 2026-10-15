#!/usr/bin/env python3
"""
Download every building in Bucharest from OpenStreetMap, give each one a
height, and cache the result as GeoParquet for the API. Also downloads and
caches the walking street network, which routing runs on.

Usage:
  python fetch_osm.py            # use the cached files if present
  python fetch_osm.py --refresh  # re-download (a city-sized download takes several minutes)
"""

import argparse
from pathlib import Path

import geopandas as gpd

from heights import print_height_coverage, resolve_heights

# Nominatim resolves this to the municipality boundary (sectors 1-6).
PLACE = "Bucharest, Romania"

# Overpass times out on one city-sized query, so osmnx splits the area into
# sub-queries no larger than this (5 km x 5 km) and merges the results.
MAX_QUERY_AREA_M2 = 25_000_000
REQUEST_TIMEOUT_S = 300

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = DATA_DIR / "buildings.parquet"
STREETS_FILE = DATA_DIR / "streets.graphml"


def _configure_osmnx():
    import osmnx as ox

    ox.settings.max_query_area_size = MAX_QUERY_AREA_M2
    ox.settings.requests_timeout = REQUEST_TIMEOUT_S
    return ox


def polygons_only(gdf):
    """Repair invalid footprints and split multipolygons, leaving one plain
    Polygon per row (each part keeps its building's attributes)."""
    gdf = gdf.set_geometry(gdf.make_valid())
    # make_valid can return a collection that itself holds a MultiPolygon,
    # so explode twice to be sure only single parts remain.
    gdf = gdf.explode(index_parts=False).explode(index_parts=False)
    return gdf[gdf.geom_type == "Polygon"].reset_index(drop=True)


def fetch_buildings(place=PLACE):
    """Download the buildings of `place` from Overpass. Returns a
    GeoDataFrame (WGS84) with height_m, height_source, building_type, osm_id."""
    ox = _configure_osmnx()

    osm = ox.features_from_place(place, tags={"building": True})
    osm = osm[osm.geom_type.isin(["Polygon", "MultiPolygon"])]

    heights, sources = resolve_heights(osm)
    print_height_coverage(sources)

    buildings = gpd.GeoDataFrame(
        {
            "osm_id": [f"{element}/{osm_id}" for element, osm_id in osm.index],
            "building_type": osm["building"].fillna("unknown").astype(str).to_numpy(),
            "height_m": heights.round(1).to_numpy(),
            "height_source": sources.to_numpy(),
        },
        geometry=osm.geometry.to_numpy(),
        crs=osm.crs,
    )
    return polygons_only(buildings)


def load_buildings(refresh=False):
    """Cache-first accessor: read CACHE_FILE unless it's missing or `refresh`."""
    if CACHE_FILE.exists() and not refresh:
        print(f"Using cached buildings: {CACHE_FILE}")
        return gpd.read_parquet(CACHE_FILE)

    buildings = fetch_buildings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    buildings.to_parquet(CACHE_FILE)
    print(f"Wrote {CACHE_FILE} ({len(buildings)} footprints)")
    return buildings


def load_streets(refresh=False, place=PLACE):
    """Cache-first accessor for the walking network (an osmnx MultiDiGraph in
    WGS84, edge lengths in metres)."""
    ox = _configure_osmnx()
    if STREETS_FILE.exists() and not refresh:
        print(f"Using cached streets: {STREETS_FILE}")
        return ox.load_graphml(STREETS_FILE)

    graph = ox.graph_from_place(place, network_type="walk")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, STREETS_FILE)
    print(f"Wrote {STREETS_FILE} ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
    return graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass even if cached")
    args = ap.parse_args()
    load_buildings(refresh=args.refresh)
    load_streets(refresh=args.refresh)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Download every building in Bucharest from OpenStreetMap, give each one a
height, and cache the result as GeoParquet for the API.

Usage:
  python fetch_osm.py            # use the cached file if present
  python fetch_osm.py --refresh  # re-download (a city-sized download takes several minutes)
"""

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

# Nominatim resolves this to the municipality boundary (sectors 1-6).
PLACE = "Bucharest, Romania"

# Overpass times out on one city-sized query, so osmnx splits the area into
# sub-queries no larger than this (5 km x 5 km) and merges the results.
MAX_QUERY_AREA_M2 = 25_000_000
REQUEST_TIMEOUT_S = 300

METERS_PER_LEVEL = 3.0
# Typical height by building type, for buildings with no height or levels tag.
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
CACHE_FILE = DATA_DIR / "buildings.parquet"


def positive_number(values):
    """Parse OSM tag values like '12', '12 m', '12m' or '3' to floats.
    Anything unparseable ('12 ft', '3;4') or not above zero becomes NaN."""
    cleaned = values.astype("string").str.removesuffix("m").str.strip()
    numbers = pd.to_numeric(cleaned, errors="coerce")
    return numbers.where(numbers > 0)


def resolve_heights(tags):
    """Height in metres for each row of OSM `tags`, and where it came from.

    Takes the first of: the height tag, building:levels x 3 m, a typical
    height for the building type, or 8 m. Returns (heights, sources)."""
    missing = pd.Series(np.nan, index=tags.index)
    explicit = positive_number(tags.get("height", missing))
    from_levels = positive_number(tags.get("building:levels", missing)) * METERS_PER_LEVEL
    by_type = tags.get("building", missing).map(TYPE_HEIGHT_M)

    heights = explicit.fillna(from_levels).fillna(by_type).fillna(DEFAULT_HEIGHT_M)
    sources = np.select(
        [explicit.notna(), from_levels.notna(), by_type.notna()],
        ["height", "levels", "type_fallback"],
        default="default",
    )
    return heights.astype(float), pd.Series(sources, index=tags.index)


def polygons_only(gdf):
    """Repair invalid footprints and split multipolygons, leaving one plain
    Polygon per row (each part keeps its building's attributes)."""
    gdf = gdf.set_geometry(gdf.make_valid())
    # make_valid can return a collection that itself holds a MultiPolygon,
    # so explode twice to be sure only single parts remain.
    gdf = gdf.explode(index_parts=False).explode(index_parts=False)
    return gdf[gdf.geom_type == "Polygon"].reset_index(drop=True)


def print_height_coverage(sources):
    counts = sources.value_counts()
    total = len(sources) or 1
    print(f"OSM buildings: {len(sources)}")
    for source in ["height", "levels", "type_fallback", "default"]:
        n = counts.get(source, 0)
        print(f"  {source:14s}: {n:7d} ({100 * n / total:.1f}%)")


def fetch_buildings(place=PLACE):
    """Download the buildings of `place` from Overpass. Returns a
    GeoDataFrame (WGS84) with height_m, height_source, building_type, osm_id."""
    import osmnx as ox

    ox.settings.max_query_area_size = MAX_QUERY_AREA_M2
    ox.settings.requests_timeout = REQUEST_TIMEOUT_S

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass even if cached")
    args = ap.parse_args()
    load_buildings(refresh=args.refresh)


if __name__ == "__main__":
    main()

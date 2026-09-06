#!/usr/bin/env python3
"""
Height resolution ladder for OSM building footprints, shared by the fetch
pipeline and its tests: explicit height tag -> building:levels * 3.0m ->
fallback by building type -> default 8m.
"""

import geopandas as gpd

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


def _parse_float(raw):
    """Best-effort float parse for messy OSM tag values ('12 m', '~4',
    '2.5', '12;14'). Returns None if nothing usable is found."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = s.split(";")[0]  # some tags carry multiple values, e.g. "12;14"
    s = s.replace("m", "").replace("~", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def resolve_height(raw_height, raw_levels, building_type):
    """Returns (height_m, source); source is one of 'height', 'levels',
    'type_fallback', 'default'."""
    h = _parse_float(raw_height)
    if h is not None and h > 0:
        return h, "height"

    levels = _parse_float(raw_levels)
    if levels is not None and levels > 0:
        return levels * METERS_PER_LEVEL, "levels"

    if building_type in TYPE_HEIGHT_M:
        return TYPE_HEIGHT_M[building_type], "type_fallback"

    return DEFAULT_HEIGHT_M, "default"


def build_buildings_parquet(gdf, out_path):
    """Resolve heights for every row of a WGS84 buildings GeoDataFrame (as
    returned by osmnx.features_from_bbox) and write geometry (UTM 32635) +
    height_m + height_source to a GeoParquet file. Returns per-source counts."""
    utm_geom = gdf.to_crs(epsg=32635).geometry.values

    heights, sources = [], []
    for _, row in gdf.iterrows():
        btype = row.get("building")
        btype = btype if isinstance(btype, str) else None
        h, source = resolve_height(row.get("height"), row.get("building:levels"), btype)
        heights.append(round(h, 1))
        sources.append(source)

    out = gpd.GeoDataFrame(
        {"height_m": heights, "height_source": sources},
        geometry=utm_geom,
        crs="EPSG:32635",
    )
    out = out[out.geometry.notnull() & out.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    out.to_parquet(out_path)

    counts = out["height_source"].value_counts().to_dict()
    print(f"buildings.parquet: {len(out)} features -> {out_path}")
    for k, v in counts.items():
        print(f"  {k:14s}: {v:5d} ({100*v/len(out):.1f}%)")
    return counts

#!/usr/bin/env python3
"""
Ground-shade polygons for the Umbra bbox at a given moment.

Projects the cached OSM buildings (fetch_osm.py) to UTM 35N, sweeps each
footprint away from the sun by its shadow length, and returns the shaded
ground (shadow union minus footprints, clipped to the bbox) as WGS84 GeoJSON
for the map layer and, later, the router.

Usage:
  python shadows.py                                # today, 14:00 Bucharest time
  python shadows.py --date 2026-07-15 --time 18:30
"""

import argparse
import math
import warnings
from datetime import date as Date, datetime
from functools import cache, lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pyproj
import shapely
from shapely.affinity import translate
from shapely.geometry import box, mapping, shape
from pysolar.solar import get_altitude, get_azimuth

from fetch_osm import BBOX, load_buildings

# pysolar warns on every call for years past its leap-second table; the
# sub-second error is irrelevant at this scale.
warnings.filterwarnings("ignore", message="Leap seconds for year", category=UserWarning)

CENTER_LAT = (BBOX["north"] + BBOX["south"]) / 2
CENTER_LON = (BBOX["east"] + BBOX["west"]) / 2

# Europe/Bucharest switches between EET (+2) and EEST (+3); a fixed offset
# puts winter shadows an hour off.
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")
UTM_CRS = "EPSG:32635"
WGS84_TO_UTM = pyproj.Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)
UTM_TO_WGS84 = pyproj.Transformer.from_crs(UTM_CRS, "EPSG:4326", always_xy=True)

# Near sunrise/sunset shadows run for kilometres; cap them so the union stays
# cheap. Anything this long crosses the whole bbox and is clipped anyway.
MAX_SHADOW_M = 500.0
# ~0.1 m at this latitude: plenty for display, keeps the payload small.
OUTPUT_PRECISION_DEG = 1e-6


def _reproject(geom, transformer):
    return shapely.transform(
        geom, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1]))
    )


# --- Time & sun -------------------------------------------------------------

def local_datetime(date_str, time_str):
    """'YYYY-MM-DD', 'HH:MM' in Bucharest local time -> aware datetime.
    Raises ValueError on malformed input."""
    d = Date.fromisoformat(date_str)
    t = datetime.strptime(time_str, "%H:%M").time()
    return datetime.combine(d, t, tzinfo=BUCHAREST_TZ)


def sun_position(when):
    """(elevation_deg, azimuth_deg) at the bbox centre. Azimuth is clockwise
    from north, so 90 = east, 180 = south."""
    # pysolar returns numpy scalars; comparisons on them yield np.bool_,
    # which the JSON encoder rejects.
    return (
        float(get_altitude(CENTER_LAT, CENTER_LON, when)),
        float(get_azimuth(CENTER_LAT, CENTER_LON, when)),
    )


# --- Shadow math ------------------------------------------------------------

def shadow_offset(height_m, azimuth_deg, elevation_deg):
    """(dx, dy) in metres from a roof edge to its shadow on the ground.
    Shadows point away from the sun (azimuth + 180)."""
    length = min(height_m / math.tan(math.radians(elevation_deg)), MAX_SHADOW_M)
    theta = math.radians((azimuth_deg + 180) % 360)
    return math.sin(theta) * length, math.cos(theta) * length


def building_shadow(footprint, offset):
    """Ground shadow of an extruded footprint: the footprint swept along
    `offset`, i.e. footprint ∪ translated footprint ∪ the parallelogram swept
    by every edge. Interior-ring edges are swept too, so courtyards get the
    shade their walls cast into them. Handles concave footprints."""
    dx, dy = offset
    d = np.array([dx, dy])
    quads = []
    for ring in (footprint.exterior, *footprint.interiors):
        c = np.asarray(ring.coords)[:, :2]
        a, b = c[:-1], c[1:]
        quads.append(np.stack([a, b, b + d, a + d, a], axis=1))
    quads = shapely.polygons(np.concatenate(quads))
    # Edges parallel to the sun direction sweep zero-area slivers.
    quads = quads[shapely.area(quads) > 1e-9]
    moved = translate(footprint, dx, dy)
    return shapely.union_all([footprint, moved, *quads])


def ground_shade(buildings, azimuth_deg, elevation_deg, clip=None):
    """Shaded open ground (UTM) for `buildings` = [(Polygon, height_m)] with
    the sun at the given position. Footprints themselves are excluded: they
    are roofs, not walkable ground. Returns an empty geometry when the sun is
    at or below the horizon - the caller decides what "night" means."""
    if elevation_deg <= 0 or not buildings:
        return shapely.Polygon()
    shadows = [
        building_shadow(poly, shadow_offset(h, azimuth_deg, elevation_deg))
        for poly, h in buildings
    ]
    shade = shapely.union_all(shadows).difference(shapely.union_all([p for p, _ in buildings]))
    if clip is not None:
        shade = shade.intersection(clip)
    return shade


# --- Data -------------------------------------------------------------------

def _polygons(geom):
    """Every non-empty Polygon in `geom`, recursing into multi-geometries and
    collections (make_valid can nest a MultiPolygon in a collection)."""
    for part in shapely.get_parts(geom):
        if part.geom_type == "Polygon":
            if not part.is_empty:
                yield part
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            yield from _polygons(part)


@cache
def projected_buildings():
    """Cached buildings as [(Polygon in UTM, height_m)]. Invalid OSM
    footprints are repaired and multipolygons exploded into their parts."""
    out = []
    for f in load_buildings()["features"]:
        geom = shapely.make_valid(_reproject(shape(f["geometry"]), WGS84_TO_UTM))
        h = f["properties"]["height_m"]
        out.extend((p, h) for p in _polygons(geom))
    return out


@cache
def bbox_utm():
    return _reproject(box(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]), WGS84_TO_UTM)


def to_feature_collection(shade_utm):
    """UTM shade geometry -> WGS84 GeoJSON FeatureCollection dict, one
    feature per polygon (holes preserved)."""
    wgs = shapely.set_precision(_reproject(shade_utm, UTM_TO_WGS84), OUTPUT_PRECISION_DEG)
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": mapping(p)}
            for p in shapely.get_parts(wgs)
            if p.geom_type == "Polygon" and not p.is_empty
        ],
    }


@lru_cache(maxsize=256)
def shadows_geojson(date_str, time_str):
    """Ground shade for the cached bbox buildings at local Bucharest
    date/time, as a GeoJSON FeatureCollection with the moment and sun
    position attached as foreign members (map clients ignore them)."""
    when = local_datetime(date_str, time_str)
    elev, az = sun_position(when)
    shade = ground_shade(projected_buildings(), az, elev, clip=bbox_utm())
    fc = to_feature_collection(shade)
    fc["time"] = when.isoformat()
    fc["sun"] = {
        "elevation_deg": round(elev, 2),
        "azimuth_deg": round(az, 2),
        "is_up": elev > 0,
    }
    return fc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(BUCHAREST_TZ).date().isoformat(), help="YYYY-MM-DD")
    ap.add_argument("--time", default="14:00", help="HH:MM, Bucharest local time")
    args = ap.parse_args()

    fc = shadows_geojson(args.date, args.time)
    sun = fc["sun"]
    print(f"{fc['time']}: sun elevation {sun['elevation_deg']} deg, azimuth {sun['azimuth_deg']} deg")
    print(f"{len(fc['features'])} shade polygons")


if __name__ == "__main__":
    main()

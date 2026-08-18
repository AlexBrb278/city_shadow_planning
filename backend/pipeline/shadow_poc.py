#!/usr/bin/env python3
"""
Umbra PoC - shadow map for central Bucharest.

Usage:
  python shadow_poc.py            # fetch real OSM data (needs internet + osmnx)
  python shadow_poc.py --demo     # synthetic city block, no network needed
  python shadow_poc.py --time 18  # hour of day (EEST), default 14

Outputs:
  shadow_map.png   - rendered buildings + shadows
  shadows.geojson  - shadow polygons (WGS84) for the map layer
  stdout           - OSM height-tag coverage stats (the go/no-go number)
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone, timedelta

from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union
from shapely.affinity import translate
from pysolar.solar import get_altitude, get_azimuth
import pyproj

# --- Config -----------------------------------------------------------------

# Chunk of central Bucharest (Lipscani / Old Town area)
BBOX = dict(north=44.4340, south=44.4280, east=26.1060, west=26.0960)
CENTER_LAT = (BBOX["north"] + BBOX["south"]) / 2
CENTER_LON = (BBOX["east"] + BBOX["west"]) / 2

EEST = timezone(timedelta(hours=3))
METERS_PER_LEVEL = 3.0
DEFAULT_HEIGHT_M = 8.0          # fallback when no height/levels tag exists
WGS84_TO_UTM = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
UTM_TO_WGS84 = pyproj.Transformer.from_crs("EPSG:32635", "EPSG:4326", always_xy=True)


# --- Data loading -----------------------------------------------------------

def load_osm_buildings():
    """Fetch building footprints + height info from OSM. Returns list of
    (polygon_utm, height_m, height_source)."""
    import osmnx as ox  # imported here so --demo works without it

    gdf = ox.features_from_bbox(bbox=(BBOX["west"], BBOX["south"],
                                      BBOX["east"], BBOX["north"]),
                                tags={"building": True})
    buildings = []
    stats = {"height": 0, "levels": 0, "none": 0}
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)

        h, source = None, "none"
        raw_h = row.get("height")
        raw_l = row.get("building:levels")
        if raw_h is not None and str(raw_h) != "nan":
            try:
                h = float(str(raw_h).replace("m", "").strip())
                source = "height"
            except ValueError:
                pass
        if h is None and raw_l is not None and str(raw_l) != "nan":
            try:
                h = float(raw_l) * METERS_PER_LEVEL
                source = "levels"
            except ValueError:
                pass
        if h is None:
            h = DEFAULT_HEIGHT_M
        stats[source] += 1

        for p in polys:
            xs, ys = zip(*p.exterior.coords)
            ux, uy = WGS84_TO_UTM.transform(xs, ys)
            buildings.append((Polygon(zip(ux, uy)), h, source))

    total = sum(stats.values()) or 1
    print(f"OSM buildings in bbox: {total}")
    print(f"  explicit height tag : {stats['height']:5d} ({100*stats['height']/total:.1f}%)")
    print(f"  building:levels tag : {stats['levels']:5d} ({100*stats['levels']/total:.1f}%)")
    print(f"  no height info      : {stats['none']:5d} ({100*stats['none']/total:.1f}%)  <- default {DEFAULT_HEIGHT_M} m used")
    print("GO/NO-GO: if (height+levels) < ~40%, plan a height-estimation fallback before routing work.\n")
    return buildings


def demo_buildings():
    """Synthetic city block in UTM coords near the real Bucharest center,
    so solar geometry is identical to the real run."""
    cx, cy = WGS84_TO_UTM.transform(CENTER_LON, CENTER_LAT)
    specs = [
        # (dx, dy, w, d, height_m)
        (-120, -80, 40, 25, 12), (-60, -80, 35, 25, 21), (0, -80, 50, 30, 9),
        (70, -80, 30, 25, 33),  (-120, 0, 45, 35, 15),  (-50, 10, 30, 30, 27),
        (10, 0, 55, 20, 6),     (80, 0, 25, 40, 45),    (-110, 70, 35, 25, 18),
        (-50, 80, 40, 20, 10),  (10, 70, 30, 35, 24),   (60, 75, 45, 25, 14),
    ]
    out = []
    for dx, dy, w, d, h in specs:
        x0, y0 = cx + dx, cy + dy
        out.append((Polygon([(x0, y0), (x0 + w, y0), (x0 + w, y0 + d), (x0, y0 + d)]), h, "demo"))
    return out


# --- Shadow math ------------------------------------------------------------

def sun_vector(when_utc):
    """Returns (dx, dy) unit shadow direction in UTM meters, elevation deg."""
    elev = get_altitude(CENTER_LAT, CENTER_LON, when_utc)
    az = get_azimuth(CENTER_LAT, CENTER_LON, when_utc)  # deg from N, clockwise
    if elev <= 0:
        return None, elev
    # Shadow points away from the sun: azimuth + 180
    theta = math.radians((az + 180) % 360)
    return (math.sin(theta), math.cos(theta)), elev


def building_shadow(poly, height_m, shadow_dir, elev_deg):
    """Ground shadow = union of footprint, translated footprint, and the
    swept quad of every exterior edge. Handles concave footprints."""
    L = height_m / math.tan(math.radians(elev_deg))
    dx, dy = shadow_dir[0] * L, shadow_dir[1] * L
    moved = translate(poly, dx, dy)
    pieces = [poly, moved]
    coords = list(poly.exterior.coords)
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        quad = Polygon([(x1, y1), (x2, y2), (x2 + dx, y2 + dy), (x1 + dx, y1 + dy)])
        if quad.is_valid and quad.area > 0:
            pieces.append(quad)
    return unary_union(pieces)


# --- Main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="synthetic block, no network")
    ap.add_argument("--time", type=int, default=14, help="hour of day, EEST")
    ap.add_argument("--date", default="2026-07-15", help="YYYY-MM-DD")
    args = ap.parse_args()

    y, m, d = map(int, args.date.split("-"))
    when_local = datetime(y, m, d, args.time, 0, tzinfo=EEST)
    when_utc = when_local.astimezone(timezone.utc)

    shadow_dir, elev = sun_vector(when_utc)
    print(f"Sun @ {when_local:%Y-%m-%d %H:%M} EEST, Bucharest: elevation {elev:.1f} deg")
    if shadow_dir is None:
        sys.exit("Sun below horizon - everything is shade. Pick a daytime hour.")

    buildings = demo_buildings() if args.demo else load_osm_buildings()
    print(f"Computing shadows for {len(buildings)} footprints...")

    shadows = [building_shadow(p, h, shadow_dir, elev) for p, h, _ in buildings]
    shadow_union = unary_union(shadows)
    footprint_union = unary_union([p for p, _, _ in buildings])
    ground_shade = shadow_union.difference(footprint_union)

    # GeoJSON export (back to WGS84) for the future MapLibre layer
    def utm_geom_to_wgs(geom):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        feats = []
        for p in polys:
            xs, ys = zip(*p.exterior.coords)
            lon, lat = UTM_TO_WGS84.transform(xs, ys)
            feats.append({"type": "Feature", "properties": {},
                          "geometry": mapping(Polygon(zip(lon, lat)))})
        return feats

    fc = {"type": "FeatureCollection", "features": utm_geom_to_wgs(ground_shade)}
    with open("shadows.geojson", "w") as f:
        json.dump(fc, f)
    print("Wrote shadows.geojson")

    # Render
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 10))
    for geom, color, alpha, z in [(ground_shade, "#4a5568", 0.55, 1),
                                  (footprint_union, "#1a202c", 1.0, 2)]:
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for p in polys:
            ax.fill(*p.exterior.xy, color=color, alpha=alpha, zorder=z)
    ax.set_aspect("equal")
    ax.set_title(f"Bucharest shadow map - {when_local:%d %b %Y, %H:%M} EEST "
                 f"(sun elev {elev:.0f} deg)")
    ax.set_xlabel("UTM 35N east (m)"); ax.set_ylabel("UTM 35N north (m)")
    plt.tight_layout()
    plt.savefig("shadow_map.png", dpi=150)
    print("Wrote shadow_map.png")


if __name__ == "__main__":
    main()

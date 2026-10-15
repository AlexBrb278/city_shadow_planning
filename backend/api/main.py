#!/usr/bin/env python3
"""Umbra API - serves Bucharest's buildings and their shade as map tiles, and
shade-aware walking routes.

Buildings and streets load once, at startup (see fetch_osm.py for the cache).
Shade is built per tile on demand and kept in memory, so each tile is
computed once per moment - for the map and for routing alike.

Run: uvicorn main:app --reload --app-dir backend/api
"""

import sys
from contextlib import asynccontextmanager
from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import shapely
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

import tiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import routing  # noqa: E402  (uses pipeline modules)
from buildings import WEB_MERCATOR, Buildings  # noqa: E402
from edge_shade import shaded_lengths_in_tile  # noqa: E402
from shadows import shade_near  # noqa: E402
from streets import Streets  # noqa: E402
from sun import local_datetime, sun_at  # noqa: E402

# Buildings and shade are served as zoom-15 tiles (~870 m across in
# Bucharest); MapLibre stretches them for closer zooms. Keep in sync with
# TILE_ZOOM in frontend/src/lib/api.ts.
TILE_ZOOM = 15
TILE_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
# A tile's content only changes when the building data is refreshed. Being
# cacheable also lets the browser merge MapLibre's duplicate requests: it
# asks for a tile once per zoom level it stretches it to.
TILE_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}

DATE = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD, Bucharest")
TIME = Query(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM, Bucharest local time")


@cache
def city():
    return Buildings.load()


@cache
def streets():
    return Streets.load()


@cache
def to_mercator():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", WEB_MERCATOR, always_xy=True)


@asynccontextmanager
async def lifespan(app):
    # Load before serving: MapLibre asks for a dozen tiles at once, and each
    # would otherwise start loading the whole city in parallel.
    city()
    streets()
    yield


app = FastAPI(title="Umbra API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def moment(date, time):
    """The query's date and time as a Bucharest datetime, or a 422."""
    try:
        return local_datetime(date, time)
    except ValueError as e:  # well-formed but not a real moment, e.g. 2026-02-30
        raise HTTPException(status_code=422, detail=str(e))


def check_tile(z, x, y):
    if z != TILE_ZOOM:
        raise HTTPException(status_code=404, detail=f"tiles exist at zoom {TILE_ZOOM} only")
    if not (0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(status_code=404, detail="no such tile")


def tile_response(content):
    if not content:
        return Response(status_code=204)  # MapLibre reads this as an empty tile
    return Response(content, media_type=TILE_MEDIA_TYPE, headers=TILE_CACHE_HEADERS)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sun")
def sun(date: str = DATE, time: str = TIME):
    """Sun position over Bucharest at a local moment."""
    when = moment(date, time)
    position = sun_at(when)
    return {
        "time": when.isoformat(),
        "elevation_deg": round(position.elevation_deg, 2),
        "azimuth_deg": round(position.azimuth_deg, 2),
        "is_up": position.is_up,
    }


@app.get("/tiles/buildings/{z}/{x}/{y}.pbf")
def building_tile(z: int, x: int, y: int):
    """Building footprints with height_m and height_source, for 3D extrusion."""
    check_tile(z, x, y)
    return tile_response(building_tile_bytes(z, x, y))


@app.get("/tiles/shade/{z}/{x}/{y}.pbf")
def shade_tile(z: int, x: int, y: int, date: str = DATE, time: str = TIME):
    """Ground shade at a local Bucharest moment; empty while the sun is down."""
    check_tile(z, x, y)
    moment(date, time)  # reject impossible moments before touching the cache
    return tile_response(shade_tile_bytes(z, x, y, date, time))


@lru_cache(maxsize=1024)
def building_tile_bytes(z, x, y):
    bounds = tiles.tile_bounds(z, x, y)
    area = tiles.buffered(bounds)
    buildings = city()
    found = buildings.within(area)
    if len(found) == 0:
        return b""
    properties = [
        {"height_m": float(height), "height_source": str(source)}
        for height, source in zip(buildings.heights_m[found], buildings.height_sources[found])
    ]
    footprints = shapely.clip_by_rect(buildings.footprints[found], *area)
    return tiles.encode("buildings", footprints, bounds, properties)


@lru_cache(maxsize=4096)
def shade_tile_geometry(z, x, y, date, time):
    """The shade over tile z/x/y (a little beyond it, see tiles.BUFFER)."""
    position = sun_at(local_datetime(date, time))
    return shade_near(city(), position, tiles.buffered(tiles.tile_bounds(z, x, y)))


@lru_cache(maxsize=4096)
def shade_tile_bytes(z, x, y, date, time):
    shade = shade_tile_geometry(z, x, y, date, time)
    if shade.is_empty:
        return b""
    return tiles.encode("shade", shapely.get_parts(shade), tiles.tile_bounds(z, x, y))


@lru_cache(maxsize=4096)
def edge_shade_tile(z, x, y, date, time):
    """Shaded lengths of the street edges in tile z/x/y (see edge_shade.py)."""
    shade = shade_tile_geometry(z, x, y, date, time)
    return shaded_lengths_in_tile(streets(), shade, tiles.tile_bounds(z, x, y))


@app.get("/route")
def route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
    date: str = DATE,
    time: str = TIME,
    shade: float = Query(0.75, ge=0, le=1, description="0 = fastest, 1 = strongly prefer shade"),
):
    """The fastest walking route and the shade-preferring one, as GeoJSON
    Features with distance_m, duration_min and shade_pct, plus their delta."""
    when = moment(date, time)
    sun_up = sun_at(when).is_up
    start = to_mercator().transform(from_lon, from_lat)
    end = to_mercator().transform(to_lon, to_lat)

    def fractions_for(start_xy, end_xy):
        if not sun_up:  # the whole city is in shade
            return np.ones(len(streets()))
        corridor = routing.corridor_tiles(start_xy, end_xy, TILE_ZOOM)
        return routing.corridor_fractions(
            streets(), corridor, lambda x, y: edge_shade_tile(TILE_ZOOM, x, y, date, time)
        )

    try:
        result = routing.plan(streets(), start, end, shade, fractions_for)
    except routing.RouteError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"time": when.isoformat(), "sun_up": sun_up, **result}

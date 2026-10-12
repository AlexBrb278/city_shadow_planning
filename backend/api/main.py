#!/usr/bin/env python3
"""Umbra API - serves precomputed/cached data to the frontend.

Run: uvicorn main:app --reload --app-dir backend/api
"""

import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from fetch_osm import BBOX, load_buildings  # noqa: E402
from shadows import BUCHAREST_TZ, shadows_geojson  # noqa: E402

app = FastAPI(title="Umbra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_buildings_cache = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/bbox")
def bbox():
    return BBOX


@app.get("/buildings")
def buildings():
    global _buildings_cache
    if _buildings_cache is None:
        _buildings_cache = load_buildings()
    return JSONResponse(_buildings_cache)


@app.get("/shadows")
def shadows(
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD, default today"),
    time: str | None = Query(None, pattern=r"^\d{2}:\d{2}$", description="HH:MM Bucharest time, default now"),
):
    """Shaded ground in the bbox at a local Bucharest moment, as GeoJSON.
    Also carries `time` (ISO 8601) and `sun` {elevation_deg, azimuth_deg,
    is_up}; when the sun is down there are no features."""
    now = datetime.now(BUCHAREST_TZ)
    try:
        fc = shadows_geojson(date or now.date().isoformat(), time or now.strftime("%H:%M"))
    except ValueError as e:  # e.g. 2026-02-30 or 25:00 - well-formed but not a real moment
        raise HTTPException(status_code=422, detail=str(e))
    return JSONResponse(fc)

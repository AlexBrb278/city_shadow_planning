#!/usr/bin/env python3
"""Umbra API - serves precomputed/cached data to the frontend.

Run: uvicorn main:app --reload --app-dir backend/api
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from fetch_osm import BBOX, load_buildings  # noqa: E402

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

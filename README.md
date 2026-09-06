# Umbra — shade-aware walking routes for Bucharest

Mobile app + Python backend computing walking routes through Bucharest that
prefer shaded streets, using OSM building footprints/heights and sun
position. 

## Current state

- `backend/pipeline/fetch_osm.py` — fetches OSM buildings AND the walking
  street network for the bbox (central Bucharest), caches to `backend/data/`:
  `buildings.geojson` (WGS84, frontend), `buildings.parquet` (UTM 32635,
  height_m + height_source, pipeline), `street_network.graphml`. Never hits
  Overpass if cached files exist; `--refresh` bypasses the cache.
- `backend/pipeline/heights.py` — the height resolution ladder (height tag →
  levels × 3m → type fallback → 8m default), shared by the fetch pipeline
  and its unit tests. Tolerates malformed tags (`"12 m"`, `"~4"`, `"12;14"`,
  non-numeric levels).
- `backend/api/main.py` — FastAPI serving `/buildings`, `/bbox`, `/health`.
- `frontend/` — SvelteKit + MapLibre GL, renders buildings as 3D
  fill-extrusions over an OSM raster basemap.
- `backend/pipeline/shadow_poc.py` — reference shadow-math implementation
  (not yet wired into the pipeline/API).
- `backend/tests/test_heights.py` — 13 unit tests covering every branch of
  the height ladder, `pytest backend/tests` green.

### OSM height-tag coverage (central Bucharest bbox, 787 buildings)

| source          | count | %     |
|------------------|------:|------:|
| explicit height  |    21 |  2.7% |
| building:levels  |    59 |  7.5% |
| type fallback    |    29 |  3.7% |
| default (8m)     |   678 | 86.1% |

Height+levels coverage is ~10%, well below the 40% go/no-go threshold —
building heights in the 3D view (and the shadow computation in Phase 2)
are mostly estimates, not survey data.

## Running locally

```bash
# backend
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend/api --port 8000

# frontend (separate terminal)
npm --prefix frontend run dev -- --port 5173
```

Open http://localhost:5173.

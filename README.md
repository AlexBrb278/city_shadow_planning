# Umbra — shade-aware walking routes for Bucharest

Mobile app + Python backend computing walking routes through Bucharest that
prefer shaded streets, using OSM building footprints/heights and sun
position. 

## Current state

- `backend/pipeline/fetch_osm.py` — fetches OSM buildings for the bbox
  (central Bucharest / Lipscani), resolves a height per building
  (height tag → levels × 3m → type fallback → 8m default), caches to
  `backend/data/buildings.geojson`.
- `backend/api/main.py` — FastAPI serving `/buildings`, `/bbox`, `/health`.
- `frontend/` — SvelteKit + MapLibre GL, renders buildings as 3D
  fill-extrusions over an OSM raster basemap.
- `backend/pipeline/shadow_poc.py` — reference shadow-math implementation
  (not yet wired into the pipeline/API).

### OSM height-tag coverage (Lipscani bbox, 787 buildings)

| source          | count | %     |
|------------------|------:|------:|
| explicit height  |    21 |  2.7% |
| building:levels  |    59 |  7.5% |
| type fallback    |    29 |  3.7% |
| default (8m)     |   678 | 86.1% |

Height+levels coverage is ~10%, well below the 40% go/no-go threshold —
building heights in the 3D view are mostly estimates, not survey data.

## Running locally

```bash
# backend
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend/api --port 8000

# frontend (separate terminal)
npm --prefix frontend run dev -- --port 5173
```

Open http://localhost:5173.

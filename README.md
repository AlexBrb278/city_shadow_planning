# Umbra — shade-aware walking routes for Bucharest

Mobile app + Python backend computing walking routes through Bucharest that
prefer shaded streets, using OSM building footprints/heights and sun
position. 

## Current state

- `backend/pipeline/fetch_osm.py` — fetches OSM buildings for the bbox
  (central Bucharest / Lipscani), resolves a height per building
  (height tag → levels × 3m → type fallback → 8m default), caches to
  `backend/data/buildings.geojson`.
- `backend/pipeline/shadows.py` — ground shade for any moment: sun position
  (pysolar, `Europe/Bucharest` time so EET/EEST are both right), each
  footprint swept away from the sun by `height / tan(elevation)`, union
  minus footprints, clipped to the bbox. Concave footprints and courtyards
  are handled exactly. Results are cached per moment.
- `backend/api/main.py` — FastAPI serving `/buildings`, `/bbox`, `/health`,
  and `/shadows?date=YYYY-MM-DD&time=HH:MM` (Bucharest local time, defaults
  to now). `/shadows` returns a GeoJSON FeatureCollection plus `time` and
  `sun` {`elevation_deg`, `azimuth_deg`, `is_up`}; no features when the sun
  is down.
- `frontend/` — SvelteKit + MapLibre GL: buildings as 3D fill-extrusions
  over an OSM raster basemap, a shade layer under them, and a date +
  time-of-day slider. The extrusion lighting follows the sun.
- `backend/pipeline/shadow_poc.py` — the original shadow-math proof of
  concept, superseded by `shadows.py`; kept for its matplotlib rendering.

### OSM height-tag coverage (Lipscani bbox, 787 buildings)

| source          | count | %     |
|------------------|------:|------:|
| explicit height  |    21 |  2.7% |
| building:levels  |    59 |  7.5% |
| type fallback    |    29 |  3.7% |
| default (8m)     |   678 | 86.1% |

Height+levels coverage is ~10%, well below the 40% go/no-go threshold —
building heights in the 3D view are mostly estimates, not survey data.

### Shade model limitations

- Shade comes from buildings only — no trees, awnings or terrain.
- Only buildings fetched for the bbox cast shade, so ground near the bbox
  edge can miss shade from buildings just outside it.
- Shade lengths inherit the height estimates above; with 86% of buildings
  at the 8m default, treat the shade map as indicative.

## Running locally

```bash
# one-time setup
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend install

# backend
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend/api --port 8000

# frontend (separate terminal)
npm --prefix frontend run dev -- --port 5173
```

Open http://localhost:5173.

```bash
# backend tests (no network or cached data needed)
.venv/Scripts/python.exe -m pytest backend

# frontend type check
npm --prefix frontend run check

# shade for one moment from the command line
.venv/Scripts/python.exe backend/pipeline/shadows.py --date 2026-07-15 --time 18:30
```

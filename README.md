# Umbra — shade-aware walking routes for Bucharest

Mobile app + Python backend computing walking routes through Bucharest that
prefer shaded streets, using OSM building footprints/heights and sun
position. 

## How it works

```
OpenStreetMap ──fetch_osm.py──▶ buildings.parquet ──▶ API (tiles on demand) ──▶ MapLibre
   (once)          heights      streets.graphml        buildings + shade         3D map
                                  (whole city)         shade-aware /route        A→B routes
```

1. **`fetch_osm.py`** downloads every building in Bucharest once, gives each
   a height (height tag → levels × 3 m → typical height for its type → 8 m)
   and caches them as GeoParquet.
2. **The API** loads them at startup and serves two kinds of map tile:
   buildings (for the 3D view) and shade for a given date and time. Tiles are
   computed when first asked for, then kept in memory, so the phone only ever
   downloads the few tiles on screen.
3. **The shade** inside a tile: every wall facing away from the sun throws a
   parallelogram-shaped shadow (`height / tan(sun elevation)` long); the
   shade is their union. Only buildings whose shadow can reach the tile are
   looked at. `backend/pipeline/shadows.py` explains this in more detail.
4. **Routing** runs A* over the OSM walking network. Each street edge's
   *shaded fraction* is measured on three lines: the centreline and both
   sidewalks (offset 4 m), keeping the shadiest, because a pedestrian can
   cross to the shady side. Only the zoom-15 tiles in a corridor around the
   trip are measured, and each tile's result is cached per moment, shared
   with the map's shade tiles. Edge cost:

   ```
   cost = length × (1 + α × (1 − shaded_fraction))      α = 4 × shade preference
   ```

   α = 0 is the shortest route; at α = 4 a sunny metre costs as much as five
   shady ones. Every request returns both the shortest and the preferred
   route, so the app can show what the shade costs: *"+1 min, 98% shade vs 81%"*.

### Backend layout

| file                         | what it does                                              |
|------------------------------|-----------------------------------------------------------|
| `pipeline/fetch_osm.py`      | download buildings + walking network, cache (run once)    |
| `pipeline/heights.py`        | height ladder; tolerates `12 m`, `~4`, `12;14`, `2.5`     |
| `pipeline/buildings.py`      | load the cache, project to Web Mercator, spatial index    |
| `pipeline/sun.py`            | Bucharest local time → sun elevation and direction        |
| `pipeline/shadows.py`        | the shade geometry                                        |
| `pipeline/streets.py`        | walking graph → edge lines, sidewalks, spatial index      |
| `pipeline/edge_shade.py`     | shaded fraction of each street edge, per tile             |
| `api/tiles.py`               | tile coordinates and vector-tile encoding                 |
| `api/routing.py`             | corridor, edge cost, A*, fastest vs shady comparison      |
| `api/main.py`                | HTTP endpoints                                            |

### API

| endpoint                                        | returns                                   |
|-------------------------------------------------|-------------------------------------------|
| `/sun?date=YYYY-MM-DD&time=HH:MM`               | sun elevation/azimuth, Bucharest time     |
| `/tiles/buildings/15/{x}/{y}.pbf`               | footprints with `height_m`, `height_source` |
| `/tiles/shade/15/{x}/{y}.pbf?date=…&time=…`     | shade polygons (empty while sun is down)  |
| `/route?from_lat&from_lon&to_lat&to_lon&date&time&shade=0..1` | fastest + shady routes (GeoJSON) with `distance_m`, `duration_min` (4.8 km/h), `shade_pct`, and their `delta` |

`/route` answers 422 when the points are more than 7 km apart, more than
250 m from any walkable street, or the same place. At night every street
counts as shaded, so both routes are the shortest one.

```bash
curl "http://localhost:8000/route?from_lat=44.4268&from_lon=26.1000&to_lat=44.4335&to_lon=26.1040&date=2026-10-15&time=17:00&shade=0.75"
# fastest 971 m, 84.6% shade · shady 973 m, 89.4% shade   (Lipscani data)
```

Tiles exist at zoom 15 only (~870 m across here); MapLibre stretches them for
closer zooms, and the app asks you to zoom in below that.

### Performance (measured on synthetic data)

Real OSM data couldn't be downloaded where this was built, so these numbers
come from a synthetic city of 215k–425k non-overlapping buildings, up to
~2,000 per tile. Re-measure on the real data.

- Startup: ~2–4 s to load and index all buildings; ~600–850 MB RAM.
- First request for a shade tile: ~150–300 ms. Tiles compute in parallel, so
  a full screen (9 tiles) takes ~0.5–0.9 s; after that ~20 ms from memory.
- Tile size: ~10–20 KB gzipped.

Routing, measured on the real Lipscani data (787 buildings, 862 edges):
first route in an area ~300 ms (computing its shade tiles), then ~4 ms.
At full shade preference, old-town trips of ~0.8–0.9 km found +8 to +16
points of shade for 10–70 m of detour.

### OSM height-tag coverage (Lipscani, 787 buildings)

| source          | count | %     |
|------------------|------:|------:|
| explicit height  |    21 |  2.7% |
| building:levels  |    59 |  7.5% |
| type fallback    |    29 |  3.7% |
| default (8m)     |   678 | 86.1% |

Height+levels coverage is ~10%, well below the 40% go/no-go threshold —
building heights are mostly estimates. `fetch_osm.py` prints the same table
for the whole city.

### Shade model limitations

- Shade comes from buildings only — no trees, awnings or terrain.
- Shade lengths inherit the height estimates above; treat the map as
  indicative until heights improve.
- Shadows are capped at 500 m; at the very low sun where that matters, the
  street is in shade anyway.

## Running locally

```bash
# one-time setup
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend install

# download Bucharest's buildings + walking network (can take 30+ min: Overpass
# is split into sub-queries, retried on 502/504 and cached in backend/data/,
# so an interrupted run resumes; --refresh re-downloads)
.venv/Scripts/python.exe backend/pipeline/fetch_osm.py

# UMBRA_DATA_DIR points the pipeline and API at another data folder, e.g. a
# small test area: UMBRA_DATA_DIR=backend/data/lipscani

# backend
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend/api --port 8000

# frontend (separate terminal)
npm --prefix frontend run dev -- --port 5173
```

Open http://localhost:5173. Tap the map once for the start and again for
the destination (drag the pins to adjust); the shade slider sets how much a
detour is worth.

```bash
# backend tests (no network or downloaded data needed)
.venv/Scripts/python.exe -m pytest backend

# frontend type check
npm --prefix frontend run check
```

# Umbra — shade-aware walking routes for Bucharest

Mobile app + Python backend computing walking routes through Bucharest that
prefer shaded streets, using OSM building footprints/heights and sun
position. 

## How it works

```
OpenStreetMap ──fetch_osm.py──▶ buildings.parquet ──▶ API (tiles on demand) ──▶ MapLibre
   (once)          heights         (whole city)          buildings + shade         3D map
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

### Backend layout

| file                         | what it does                                              |
|------------------------------|-----------------------------------------------------------|
| `pipeline/fetch_osm.py`      | download + height resolution + cache (run once)           |
| `pipeline/buildings.py`      | load the cache, project to Web Mercator, spatial index    |
| `pipeline/sun.py`            | Bucharest local time → sun elevation and direction        |
| `pipeline/shadows.py`        | the shade geometry                                        |
| `api/tiles.py`               | tile coordinates and vector-tile encoding                 |
| `api/main.py`                | HTTP endpoints                                            |

### API

| endpoint                                        | returns                                   |
|-------------------------------------------------|-------------------------------------------|
| `/sun?date=YYYY-MM-DD&time=HH:MM`               | sun elevation/azimuth, Bucharest time     |
| `/tiles/buildings/15/{x}/{y}.pbf`               | footprints with `height_m`, `height_source` |
| `/tiles/shade/15/{x}/{y}.pbf?date=…&time=…`     | shade polygons (empty while sun is down)  |

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

# download Bucharest's buildings (several minutes; re-run with --refresh to update)
.venv/Scripts/python.exe backend/pipeline/fetch_osm.py

# backend
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend/api --port 8000

# frontend (separate terminal)
npm --prefix frontend run dev -- --port 5173
```

Open http://localhost:5173.

```bash
# backend tests (no network or downloaded data needed)
.venv/Scripts/python.exe -m pytest backend

# frontend type check
npm --prefix frontend run check
```

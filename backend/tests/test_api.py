import math

import mapbox_vector_tile
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

import main
from buildings import Buildings
from tiles import tile_bounds

# The zoom-15 tile over Piața Unirii, and a 20 m, 15 m tall building in it.
Z, X, Y = 15, 18759, 11860


def lonlat_to_tile(lon, lat, z):
    n = 2**z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


@pytest.fixture
def client(monkeypatch):
    minx, miny, maxx, maxy = tile_bounds(Z, X, Y)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    footprint = box(cx - 14, cy - 14, cx + 14, cy + 14)  # ~20 m in Web Mercator units
    monkeypatch.setattr(main, "city", lambda: Buildings([footprint], [15.0], ["levels"]))
    for cached in (main.building_tile_bytes, main.shade_tile_bytes):
        cached.cache_clear()
    yield TestClient(main.app)  # not as a context manager: skips loading the real city
    for cached in (main.building_tile_bytes, main.shade_tile_bytes):
        cached.cache_clear()


def test_tile_fixture_is_over_bucharest():
    assert lonlat_to_tile(26.1025, 44.4268, Z) == (X, Y)


def test_sun(client):
    r = client.get("/sun", params={"date": "2026-07-15", "time": "13:15"})
    assert r.status_code == 200
    body = r.json()
    assert body["time"] == "2026-07-15T13:15:00+03:00"
    assert body["is_up"] is True
    assert body["azimuth_deg"] == pytest.approx(180, abs=5)


def test_building_tile(client):
    r = client.get(f"/tiles/buildings/{Z}/{X}/{Y}.pbf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert "max-age" in r.headers["cache-control"]
    features = mapbox_vector_tile.decode(r.content)["buildings"]["features"]
    assert [f["properties"] for f in features] == [{"height_m": 15.0, "height_source": "levels"}]


def test_shade_tile_by_day(client):
    r = client.get(f"/tiles/shade/{Z}/{X}/{Y}.pbf", params={"date": "2026-07-15", "time": "13:15"})
    assert r.status_code == 200
    assert mapbox_vector_tile.decode(r.content)["shade"]["features"]


def test_shade_tile_at_night_is_empty(client):
    r = client.get(f"/tiles/shade/{Z}/{X}/{Y}.pbf", params={"date": "2026-07-15", "time": "23:00"})
    assert r.status_code == 204


def test_empty_area_gives_an_empty_tile(client):
    assert client.get(f"/tiles/buildings/{Z}/{X + 5}/{Y}.pbf").status_code == 204


@pytest.mark.parametrize("path", [f"/tiles/buildings/{Z - 1}/{X // 2}/{Y // 2}.pbf", f"/tiles/buildings/{Z}/{2**Z}/0.pbf"])
def test_tiles_outside_the_grid_do_not_exist(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026-7-15", "time": "13:15"},  # malformed
        {"date": "2026-07-15", "time": "1pm"},  # malformed
        {"date": "2026-02-30", "time": "13:15"},  # well-formed, not a real date
        {"date": "2026-07-15", "time": "24:30"},  # well-formed, not a real time
        {"date": "2026-07-15"},  # missing
    ],
)
def test_rejects_bad_moments(client, params):
    assert client.get("/sun", params=params).status_code == 422
    assert client.get(f"/tiles/shade/{Z}/{X}/{Y}.pbf", params=params).status_code == 422

"""
Routing on a hand-drawn neighbourhood near Piața Unirii:

        B ───── D          A→B direct: 200 m up an open street (sunny).
        │    ▓▓ │          A→C→D→B: 320 m, but C–D runs right beside a
        │    ▓▓ │          row of 20 m buildings (▓) whose evening shadow,
        │    ▓▓ │          thrown east, covers it.
        A ───── C          (north is up)

Coordinates are metres east/north of the tile centre: A (0, 0), B (0, 200),
C (60, 0), D (60, 200); the buildings fill x 35..55, y 10..190.
"""

import networkx as nx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer
from shapely.geometry import box

import main
import routing
from buildings import Buildings, units_per_metre
from streets import Streets
from tiles import tile_bounds

Z, X, Y = 15, 18759, 11860
EVENING = {"date": "2026-07-15", "time": "18:30"}  # sun low in the west
NOON = {"date": "2026-07-15", "time": "13:15"}
NIGHT = {"date": "2026-07-15", "time": "23:00"}

minx, miny, maxx, maxy = tile_bounds(Z, X, Y)
CX, CY = (minx + maxx) / 2, (miny + maxy) / 2
SCALE = units_per_metre(CY)
TO_LONLAT = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

POINTS_M = {"A": (0, 0), "B": (0, 200), "C": (60, 0), "D": (60, 200)}
STREETS_M = [("A", "B", 200), ("A", "C", 60), ("C", "D", 200), ("D", "B", 60)]


def merc(x_m, y_m):
    return CX + x_m * SCALE, CY + y_m * SCALE


def lonlat(name):
    return TO_LONLAT.transform(*merc(*POINTS_M[name]))


def neighbourhood():
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for i, name in enumerate(POINTS_M):
        lon, lat = lonlat(name)
        graph.add_node(i, x=lon, y=lat, name=name)
    ids = {name: i for i, name in enumerate(POINTS_M)}
    for a, b, length in STREETS_M:
        graph.add_edge(ids[a], ids[b], length=float(length))
        graph.add_edge(ids[b], ids[a], length=float(length))
    return Streets(graph)


def buildings():
    row = box(*merc(35, 10), *merc(55, 190))
    return Buildings([row], [20.0], ["height"])


@pytest.fixture
def client(monkeypatch):
    city, streets = buildings(), neighbourhood()
    monkeypatch.setattr(main, "city", lambda: city)
    monkeypatch.setattr(main, "streets", lambda: streets)
    caches = (main.shade_tile_geometry, main.shade_tile_bytes, main.edge_shade_tile)
    for cached in caches:
        cached.cache_clear()
    yield TestClient(main.app)
    for cached in caches:
        cached.cache_clear()


def get_route(client, start="A", end="B", shade=1.0, when=EVENING):
    (flon, flat), (tlon, tlat) = lonlat(start), lonlat(end)
    params = {"from_lat": flat, "from_lon": flon, "to_lat": tlat, "to_lon": tlon, "shade": shade, **when}
    return client.get("/route", params=params)


def test_no_shade_preference_takes_the_direct_street(client):
    body = get_route(client, shade=0).json()
    assert body["fastest"]["properties"]["distance_m"] == 200
    assert body["shady"]["geometry"] == body["fastest"]["geometry"]
    assert body["delta"] == {"distance_m": 0, "duration_min": 0, "shade_pct": 0}


def test_shade_preference_detours_through_the_shadow(client):
    r = get_route(client, shade=1)
    assert r.status_code == 200
    body = r.json()
    fastest, shady = body["fastest"]["properties"], body["shady"]["properties"]

    assert body["sun_up"] is True
    assert fastest["distance_m"] == 200 and fastest["shade_pct"] == 0
    assert shady["distance_m"] == 320
    assert shady["shade_pct"] > 50
    assert body["delta"]["duration_min"] == pytest.approx(120 / routing.WALKING_SPEED_M_PER_MIN, abs=0.1)
    assert body["shady"]["geometry"] != body["fastest"]["geometry"]


def test_route_geometry_runs_from_start_to_finish(client):
    coords = np.array(get_route(client, shade=1).json()["shady"]["geometry"]["coordinates"])
    assert coords[0] == pytest.approx(lonlat("A"))
    assert coords[-1] == pytest.approx(lonlat("B"))
    assert len(coords) == 4  # A, C, D, B


def test_at_noon_the_shadow_misses_the_street(client):
    # The sun is high in the south; the buildings' short shadow points north,
    # away from the street, so there's nothing worth a detour.
    body = get_route(client, shade=1, when=NOON).json()
    assert body["shady"]["properties"]["distance_m"] == 200


def test_at_night_everything_is_shade(client):
    body = get_route(client, shade=1, when=NIGHT).json()
    assert body["sun_up"] is False
    assert body["shady"]["properties"]["distance_m"] == 200
    assert body["shady"]["properties"]["shade_pct"] == 100


@pytest.mark.parametrize(
    "start, end, reason",
    [("A", "A", "same place"), ("A", "far", "km apart"), ("A", "off_map", "walkable street")],
)
def test_unroutable_requests_are_422(client, start, end, reason):
    POINTS_M.setdefault("far", (0, 9000))
    POINTS_M.setdefault("off_map", (0, 1000))
    try:
        r = get_route(client, start, end)
    finally:
        POINTS_M.pop("far"), POINTS_M.pop("off_map")
    assert r.status_code == 422
    assert reason in r.json()["detail"]


def test_corridor_covers_the_straight_line():
    start, end = merc(0, 0), merc(2000, 1500)
    found = set(routing.corridor_tiles(start, end, Z))
    for t in np.linspace(0, 1, 50):
        x, y = start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])
        assert routing.tile_of(x, y, Z) in found

import math

import pytest
from shapely.geometry import Polygon, box, shape

import shadows
from shadows import (
    MAX_SHADOW_M,
    building_shadow,
    ground_shade,
    local_datetime,
    shadow_offset,
    sun_position,
)

# Sun due south at 45 deg: a building's shadow points due north and is as
# long as the building is tall, so expected shapes can be drawn by hand.
SOUTH, ELEV_45 = 180.0, 45.0


def same_shape(a, b):
    return a.symmetric_difference(b).area < 1e-6


class TestTime:
    def test_summer_is_eest(self):
        assert local_datetime("2026-07-15", "14:00").utcoffset().total_seconds() == 3 * 3600

    def test_winter_is_eet(self):
        assert local_datetime("2026-01-15", "14:00").utcoffset().total_seconds() == 2 * 3600

    @pytest.mark.parametrize("d, t", [("2026-02-30", "12:00"), ("2026-07-15", "25:00"), ("15/07/2026", "12:00")])
    def test_rejects_invalid(self, d, t):
        with pytest.raises(ValueError):
            local_datetime(d, t)


class TestSun:
    def test_summer_solstice_solar_noon(self):
        # Solar noon in Bucharest is ~13:15 EEST; elevation = 90 - 44.43 + 23.44.
        elev, az = sun_position(local_datetime("2026-06-21", "13:15"))
        assert elev == pytest.approx(69.0, abs=0.5)
        assert az == pytest.approx(180, abs=3)

    def test_morning_sun_is_in_the_east(self):
        elev, az = sun_position(local_datetime("2026-06-21", "08:00"))
        assert elev > 0
        assert 60 < az < 100

    def test_night(self):
        elev, _ = sun_position(local_datetime("2026-06-21", "23:00"))
        assert elev < 0


class TestShadowOffset:
    def test_points_away_from_sun(self):
        dx, dy = shadow_offset(10, SOUTH, ELEV_45)
        assert dx == pytest.approx(0, abs=1e-9)
        assert dy == pytest.approx(10)

    def test_sun_in_the_east_casts_west(self):
        dx, dy = shadow_offset(10, 90, ELEV_45)
        assert dx == pytest.approx(-10)
        assert dy == pytest.approx(0, abs=1e-9)

    def test_low_sun_is_capped(self):
        assert math.hypot(*shadow_offset(50, SOUTH, 0.1)) == pytest.approx(MAX_SHADOW_M)


class TestBuildingShadow:
    def test_square(self):
        s = building_shadow(box(0, 0, 10, 10), shadow_offset(10, SOUTH, ELEV_45))
        assert same_shape(s, box(0, 0, 10, 20))

    def test_concave_footprint_keeps_notch_lit(self):
        # L-shape with its notch at the top right. A convex-hull shortcut
        # would wrongly shade the area north of the notch.
        ell = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
        s = building_shadow(ell, shadow_offset(10, SOUTH, ELEV_45))
        assert same_shape(s, box(0, 0, 10, 30).union(box(10, 0, 20, 20)))

    def test_courtyard_gets_shade_from_its_south_wall(self):
        courtyard = box(10, 10, 20, 20)
        block = box(0, 0, 30, 30).difference(courtyard)
        s = building_shadow(block, shadow_offset(5, SOUTH, ELEV_45))
        assert same_shape(s.intersection(courtyard), box(10, 10, 20, 15))


class TestGroundShade:
    def test_excludes_footprint(self):
        shade = ground_shade([(box(0, 0, 10, 10), 10)], SOUTH, ELEV_45)
        assert same_shape(shade, box(0, 10, 10, 20))

    def test_shadow_falling_on_another_building_is_not_ground(self):
        north_neighbour = box(0, 15, 10, 25)
        shade = ground_shade([(box(0, 0, 10, 10), 10), (north_neighbour, 1)], SOUTH, ELEV_45)
        assert shade.intersection(north_neighbour).area == pytest.approx(0, abs=1e-9)
        assert same_shape(shade, box(0, 10, 10, 15).union(box(0, 25, 10, 26)))

    def test_clip(self):
        shade = ground_shade([(box(0, 0, 10, 10), 10)], SOUTH, ELEV_45, clip=box(-5, -5, 15, 15))
        assert same_shape(shade, box(0, 10, 10, 15))

    @pytest.mark.parametrize("elev", [0.0, -10.0])
    def test_sun_down_means_no_shadow_geometry(self, elev):
        assert ground_shade([(box(0, 0, 10, 10), 10)], SOUTH, elev).is_empty


class TestProjectedBuildings:
    def test_repairs_and_explodes_osm_geometry(self, monkeypatch):
        lon, lat, e = shadows.CENTER_LON, shadows.CENTER_LAT, 1e-4  # e ~ 8-11 m
        square = [[lon, lat], [lon + e, lat], [lon + e, lat + e], [lon, lat + e], [lon, lat]]
        # Self-intersecting with a spike: make_valid returns a collection
        # holding a MultiPolygon (two triangles) and a LineString (the spike).
        bowtie = [[lon, lat], [lon + e, lat + e], [lon + e, lat], [lon, lat + e], [lon, lat], [lon - e / 2, lat], [lon, lat]]
        far = [[x + 3 * e, y] for x, y in square]
        features = [
            {"geometry": {"type": "Polygon", "coordinates": [bowtie]}, "properties": {"height_m": 9.0}},
            {"geometry": {"type": "MultiPolygon", "coordinates": [[square], [far]]}, "properties": {"height_m": 12.0}},
        ]
        monkeypatch.setattr(shadows, "load_buildings", lambda: {"type": "FeatureCollection", "features": features})
        shadows.projected_buildings.cache_clear()
        try:
            result = shadows.projected_buildings()
        finally:
            shadows.projected_buildings.cache_clear()

        assert sorted(h for _, h in result) == [9.0, 9.0, 12.0, 12.0]
        assert all(p.geom_type == "Polygon" and p.is_valid and p.area > 0 for p, _ in result)
        # Projected to metres: a ~8 x 11 m square.
        assert 50 < max(p.area for p, h in result if h == 12.0) < 150


@pytest.fixture
def one_building(monkeypatch):
    """A 20 m square, 15 m tall, at the bbox centre - stands in for the
    cached OSM buildings so tests need neither network nor cache file."""
    cx, cy = shadows.WGS84_TO_UTM.transform(shadows.CENTER_LON, shadows.CENTER_LAT)
    footprint = box(cx - 10, cy - 10, cx + 10, cy + 10)
    monkeypatch.setattr(shadows, "projected_buildings", lambda: [(footprint, 15.0)])
    shadows.shadows_geojson.cache_clear()
    yield footprint
    shadows.shadows_geojson.cache_clear()


class TestShadowsGeojson:
    def test_daytime(self, one_building):
        fc = shadows.shadows_geojson("2026-07-15", "13:15")
        assert fc["type"] == "FeatureCollection"
        assert fc["time"] == "2026-07-15T13:15:00+03:00"
        assert fc["sun"]["is_up"]
        assert len(fc["features"]) == 1

        geom = shape(fc["features"][0]["geometry"])
        bb = shadows.BBOX
        assert box(bb["west"], bb["south"], bb["east"], bb["north"]).buffer(1e-6).contains(geom)
        # Midday sun is in the south, so the shade lies north of the building.
        assert geom.centroid.y > shadows.CENTER_LAT

    def test_night(self, one_building):
        fc = shadows.shadows_geojson("2026-07-15", "23:00")
        assert fc["sun"]["is_up"] is False
        assert fc["features"] == []


class TestApi:
    @pytest.fixture
    def client(self, one_building):
        from fastapi.testclient import TestClient

        import main

        return TestClient(main.app)

    def test_shadows(self, client):
        r = client.get("/shadows", params={"date": "2026-07-15", "time": "13:15"})
        assert r.status_code == 200
        body = r.json()
        assert body["sun"]["is_up"]
        assert body["features"]

    def test_defaults_to_now(self, client):
        r = client.get("/shadows")
        assert r.status_code == 200
        assert {"time", "sun", "features"} <= r.json().keys()

    @pytest.mark.parametrize(
        "params",
        [
            {"date": "2026-7-15", "time": "13:15"},  # malformed
            {"date": "2026-07-15", "time": "1pm"},  # malformed
            {"date": "2026-02-30", "time": "13:15"},  # well-formed, not a real date
            {"date": "2026-07-15", "time": "24:30"},  # well-formed, not a real time
        ],
    )
    def test_rejects_bad_moment(self, client, params):
        assert client.get("/shadows", params=params).status_code == 422

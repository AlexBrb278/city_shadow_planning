import math
import random

import numpy as np
import pytest
import shapely
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box

from buildings import Buildings, units_per_metre
from conftest import SOUTH_45, same_shape
from shadows import MAX_SHADOW_M, shade, shade_near, shadow_direction, shadow_length_m, wall_shadows
from sun import Sun


def oriented(*polygons):
    """Footprints as Buildings stores them: building on the left of each wall."""
    return shapely.orient_polygons(np.array(polygons, dtype=object))


def shade_of(polygon, height, sun=SOUTH_45, bounds=(-1000, -1000, 1000, 1000)):
    return shade(oriented(polygon), np.array([height], dtype=float), sun, bounds)


class TestShadowLengthAndDirection:
    def test_length_at_45_degrees_equals_height(self):
        assert shadow_length_m(10.0, 45.0) == pytest.approx(10.0)

    def test_length_is_capped_near_the_horizon(self):
        assert shadow_length_m(50.0, 0.1) == pytest.approx(MAX_SHADOW_M)

    def test_direction_points_away_from_the_sun(self):
        assert shadow_direction(180.0) == pytest.approx([0.0, 1.0])  # sun south -> north
        assert shadow_direction(90.0) == pytest.approx([-1.0, 0.0])  # sun east -> west


class TestWallShadows:
    def test_only_walls_facing_away_cast_shadows(self):
        # Sun due south: of a square's four walls only the north one faces
        # away; east and west run parallel to the sun and cast nothing.
        shadows = wall_shadows(oriented(box(0, 0, 10, 10)), np.array([10.0]), SOUTH_45)
        assert len(shadows) == 1
        assert same_shape(shadows[0], box(0, 10, 10, 20))

    def test_none_at_night(self):
        night = Sun(elevation_deg=-5.0, azimuth_deg=0.0)
        assert len(wall_shadows(oriented(box(0, 0, 10, 10)), np.array([10.0]), night)) == 0

    def test_scale_converts_metres_to_coordinate_units(self):
        shadows = wall_shadows(oriented(box(0, 0, 10, 10)), np.array([10.0]), SOUTH_45, scale=2.0)
        assert same_shape(shadows[0], box(0, 10, 10, 30))


class TestShade:
    def test_square(self):
        assert same_shape(shade_of(box(0, 0, 10, 10), 10), box(0, 10, 10, 20))

    def test_concave_footprint_keeps_its_notch_lit(self):
        # L-shape with its notch at the top right, sun from the south.
        ell = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
        expected = box(0, 20, 10, 30).union(box(10, 10, 20, 20))
        assert same_shape(shade_of(ell, 10), expected)

    def test_courtyard_gets_shade_from_its_south_wall(self):
        courtyard = box(10, 10, 20, 20)
        block = box(0, 0, 30, 30).difference(courtyard)
        assert same_shape(shade_of(block, 5).intersection(courtyard), box(10, 10, 20, 15))

    def test_is_clipped_to_bounds(self):
        assert same_shape(shade_of(box(0, 0, 10, 10), 10, bounds=(-5, -5, 15, 15)), box(0, 10, 10, 15))

    def test_overlapping_shadows_merge(self):
        footprints = oriented(box(0, 0, 10, 10), box(5, 0, 15, 10))
        result = shade(footprints, np.array([10.0, 10.0]), SOUTH_45, (-100, -100, 100, 100))
        assert result.geom_type == "Polygon"
        assert same_shape(result, box(0, 10, 15, 20))

    def test_empty_at_night(self):
        night = Sun(elevation_deg=-1.0, azimuth_deg=0.0)
        assert shade_of(box(0, 0, 10, 10), 10, sun=night).is_empty


def exact_sweep(polygon, offset):
    """Reference: the full shadow volume of an extruded footprint - the
    footprint, its shifted copy, and the parallelogram of every wall."""
    dx, dy = offset
    pieces = [polygon, translate(polygon, dx, dy)]
    for ring in (polygon.exterior, *polygon.interiors):
        c = list(ring.coords)
        for (x1, y1), (x2, y2) in zip(c, c[1:]):
            quad = Polygon([(x1, y1), (x2, y2), (x2 + dx, y2 + dy), (x1 + dx, y1 + dy)])
            if quad.area > 0:
                pieces.append(quad)
    return shapely.union_all(pieces)


def random_footprint(rng):
    w, d = rng.uniform(5, 30), rng.uniform(5, 30)
    shape_ = box(0, 0, w, d)
    if rng.random() < 0.5:  # L-shape
        shape_ = shape_.difference(box(w * rng.uniform(0.3, 0.7), d * rng.uniform(0.3, 0.7), w, d))
    if rng.random() < 0.3 and shape_.geom_type == "Polygon":  # courtyard
        shape_ = shape_.difference(box(w * 0.2, d * 0.2, w * 0.4, d * 0.4))
    assert shape_.geom_type == "Polygon"
    return rotate(shape_, rng.uniform(0, 360), origin="centroid")


@pytest.mark.parametrize("seed", range(40))
def test_matches_exact_sweep_outside_the_footprint(seed):
    """The core claim: walls facing away from the sun are enough. With the
    footprint added back, their parallelograms equal the full shadow volume."""
    rng = random.Random(seed)
    footprint = random_footprint(rng)
    height = rng.uniform(3, 60)
    sun = Sun(elevation_deg=rng.uniform(5, 85), azimuth_deg=rng.uniform(0, 360))

    ours = shade_of(footprint, height, sun=sun).union(footprint)
    length = shadow_length_m(height, sun.elevation_deg)
    reference = exact_sweep(footprint, shadow_direction(sun.azimuth_deg) * length)
    assert ours.symmetric_difference(reference).area < 1e-6 * reference.area


class TestShadeNear:
    # Web Mercator coordinates of central Bucharest.
    X, Y = 2_905_000.0, 5_533_000.0
    SCALE = units_per_metre(Y)

    def city(self, *buildings):
        return Buildings([footprint for footprint, _ in buildings], [h for _, h in buildings], ["height"] * len(buildings))

    def test_scales_metres_for_web_mercator(self):
        assert self.SCALE == pytest.approx(1 / math.cos(math.radians(44.43)), rel=1e-3)
        size = 10 * self.SCALE
        city = self.city((box(self.X, self.Y, self.X + size, self.Y + size), 10.0))
        result = shade_near(city, SOUTH_45, (self.X - 100, self.Y - 100, self.X + 100, self.Y + 100))
        # A 10 m tall building casts a 10 m shadow, i.e. 10 * SCALE units.
        assert result.bounds[3] == pytest.approx(self.Y + 2 * size, rel=1e-9)

    def test_includes_buildings_outside_the_area_whose_shadow_reaches_in(self):
        # Area starts 20 m north of a 30 m building: its 30 m shadow reaches in.
        s = self.SCALE
        city = self.city((box(self.X, self.Y, self.X + 10 * s, self.Y + 10 * s), 30.0))
        area = (self.X - 50 * s, self.Y + 30 * s, self.X + 50 * s, self.Y + 100 * s)
        # rel: the area's centre is ~90 m north, where Mercator stretches a hair more.
        assert shade_near(city, SOUTH_45, area).area == pytest.approx(10 * s * 10 * s, rel=1e-3)

    def test_ignores_buildings_whose_shadow_falls_short(self):
        s = self.SCALE
        city = self.city((box(self.X, self.Y, self.X + 10 * s, self.Y + 10 * s), 5.0))
        area = (self.X - 50 * s, self.Y + 30 * s, self.X + 50 * s, self.Y + 100 * s)
        assert shade_near(city, SOUTH_45, area).is_empty

import mapbox_vector_tile
import pytest
from shapely.geometry import Polygon, box

from tiles import EXTENT, HALF_WORLD, buffered, encode, tile_bounds


def test_zoom_zero_is_the_whole_world():
    assert tile_bounds(0, 0, 0) == pytest.approx((-HALF_WORLD, -HALF_WORLD, HALF_WORLD, HALF_WORLD))


def test_tiles_count_east_and_south():
    west, south, east, north = tile_bounds(1, 1, 1)  # bottom-right quarter
    assert (west, north) == pytest.approx((0, 0))
    assert (east, south) == pytest.approx((HALF_WORLD, -HALF_WORLD))


def test_buffered():
    assert buffered((0, 0, 100, 100), 0.1) == pytest.approx((-10, -10, 110, 110))


def signed_area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2


@pytest.mark.parametrize("polygon", [
    box(10, 10, 50, 50),  # counter-clockwise
    Polygon([(10, 10), (10, 50), (50, 50), (50, 10)]),  # clockwise
    box(0, 0, 80, 80).difference(box(20, 20, 60, 60)),  # with a hole
])
def test_encode_writes_rings_the_way_the_mvt_spec_wants(polygon):
    """Outer rings positive area and holes negative, in tile coordinates
    (y down) - whatever orientation the input had."""
    bounds = (0, 0, 100, 100)
    tile = mapbox_vector_tile.decode(encode("layer", [polygon], bounds), default_options={"y_coord_down": True})
    rings = tile["layer"]["features"][0]["geometry"]["coordinates"]
    assert signed_area([tuple(p) for p in rings[0]]) > 0
    assert all(signed_area([tuple(p) for p in hole]) < 0 for hole in rings[1:])
    # Scaled into the tile's 0..EXTENT grid with y flipped.
    xs = [x for x, _ in rings[0]]
    assert min(xs) == round(polygon.bounds[0] / 100 * EXTENT)


def test_encode_keeps_properties():
    tile = mapbox_vector_tile.decode(encode("b", [box(1, 1, 2, 2)], (0, 0, 10, 10), [{"height_m": 12.5}]))
    assert tile["b"]["features"][0]["properties"] == {"height_m": 12.5}

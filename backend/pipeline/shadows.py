"""
Where buildings cast shade, for a given sun position.

The idea: a wall that faces away from the sun throws a shadow on the ground
shaped like a parallelogram. One side is the wall's base; the opposite side
is the same line moved away from the sun by the shadow length,
height / tan(sun elevation). The shade is the union of those parallelograms.

Walls facing the sun need no parallelogram: any ground they shade is already
covered by a wall further back facing away. This holds for any footprint,
L-shapes and courtyards included. Some shade lands under the building's own
footprint, which is left in: on the map the 3D building hides it, and no
walking route goes through a building.

Geometry is in Web Mercator (see buildings.py), so metre lengths are
multiplied by `units_per_metre` before they meet coordinates.
"""

import math

import numpy as np
import shapely

from buildings import units_per_metre

# Near sunrise and sunset shadows run for kilometres; cap them so tiles stay
# cheap. At the elevations where this applies, the street is in shade anyway.
MAX_SHADOW_M = 500.0


def shadow_length_m(heights_m, elevation_deg):
    """How far from its wall a roof edge's shadow lands, in metres."""
    return np.minimum(np.asarray(heights_m) / math.tan(math.radians(elevation_deg)), MAX_SHADOW_M)


def shadow_direction(azimuth_deg):
    """Unit vector (east, north) pointing away from the sun."""
    away = math.radians(azimuth_deg + 180)
    return np.array([math.sin(away), math.cos(away)])


def walls(footprints):
    """Every wall of every footprint, as arrays (starts, ends, building index).

    Footprints must be oriented as in buildings.py - building on the left of
    each wall, walking from start to end."""
    rings, ring_building = shapely.get_rings(footprints, return_index=True)
    points, point_ring = shapely.get_coordinates(rings, return_index=True)
    # Consecutive points on the same ring form a wall.
    same_ring = point_ring[:-1] == point_ring[1:]
    starts, ends = points[:-1][same_ring], points[1:][same_ring]
    return starts, ends, ring_building[point_ring[:-1][same_ring]]


def wall_shadows(footprints, heights_m, sun, scale=1.0):
    """One shadow parallelogram per wall that faces away from the sun.
    `scale` converts metres to coordinate units."""
    if not sun.is_up or len(footprints) == 0:
        return np.array([], dtype=object)

    starts, ends, building = walls(footprints)

    # The building is on each wall's left, so turning the wall a quarter
    # clockwise gives the direction it faces (its outward normal).
    along = ends - starts
    facing = np.column_stack([along[:, 1], -along[:, 0]])
    direction = shadow_direction(sun.azimuth_deg)
    # A hair above zero rather than zero: walls parallel to the sun cast
    # nothing, and float rounding mustn't turn them into zero-width slivers.
    faces_away = facing @ direction > 1e-9 * np.hypot(along[:, 0], along[:, 1])
    starts, ends, building = starts[faces_away], ends[faces_away], building[faces_away]

    length = shadow_length_m(heights_m, sun.elevation_deg)[building] * scale
    offset = direction * length[:, np.newaxis]
    corners = np.stack([starts, ends, ends + offset, starts + offset, starts], axis=1)
    return shapely.polygons(corners)


def shade(footprints, heights_m, sun, bounds, scale=1.0):
    """The ground shade inside `bounds` (minx, miny, maxx, maxy) cast by these
    buildings, as a single (Multi)Polygon - empty while the sun is down."""
    shadows = wall_shadows(footprints, heights_m, sun, scale)
    shadows = shadows[shapely.intersects(shadows, shapely.box(*bounds))]
    # Trimming each parallelogram first leaves the union less to do.
    return shapely.union_all(shapely.clip_by_rect(shadows, *bounds))


def shade_near(buildings, sun, bounds):
    """The ground shade inside `bounds`, cast by every building in the city
    whose shadow is long enough to reach it."""
    if not sun.is_up:
        return shapely.Polygon()

    centre_y = (bounds[1] + bounds[3]) / 2
    scale = units_per_metre(centre_y)

    # Only buildings within the longest possible shadow of the area can matter...
    reach = shadow_length_m(buildings.tallest_m, sun.elevation_deg) * scale
    minx, miny, maxx, maxy = bounds
    nearby = buildings.within((minx - reach, miny - reach, maxx + reach, maxy + reach))
    footprints, heights = buildings.footprints[nearby], buildings.heights_m[nearby]

    # ...and of those, only the ones whose own shadow is long enough.
    distance = shapely.distance(shapely.box(*bounds), footprints)
    reaches = distance <= shadow_length_m(heights, sun.elevation_deg) * scale

    return shade(footprints[reaches], heights[reaches], sun, bounds, scale)

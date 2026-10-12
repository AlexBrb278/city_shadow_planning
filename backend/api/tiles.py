"""
Map tiles: which square of the world a z/x/y tile covers, and how to pack
geometries into a Mapbox Vector Tile, the binary format MapLibre reads.

Tiles follow the usual web-map scheme: at zoom z the world is a 2^z x 2^z
grid of squares in Web Mercator, x counting east and y counting south.
"""

import mapbox_vector_tile
import numpy as np
import shapely

# Web Mercator x and y both run from -HALF_WORLD to +HALF_WORLD.
HALF_WORLD = 20_037_508.342789244
EXTENT = 4096  # MVT coordinate resolution along one tile side
# Geometry is clipped slightly outside each tile. MapLibre skips extrusion
# walls that lie outside the tile, so cut buildings don't grow a wall at the
# tile edge; for flat fills it avoids hairline seams.
BUFFER = 64 / EXTENT


def tile_bounds(z, x, y):
    """(minx, miny, maxx, maxy) of tile z/x/y in Web Mercator."""
    size = 2 * HALF_WORLD / 2**z
    minx = -HALF_WORLD + x * size
    maxy = HALF_WORLD - y * size
    return minx, maxy - size, minx + size, maxy


def buffered(bounds, fraction=BUFFER):
    """`bounds` grown on every side by `fraction` of their width."""
    minx, miny, maxx, maxy = bounds
    pad = (maxx - minx) * fraction
    return minx - pad, miny - pad, maxx + pad, maxy + pad


def encode(layer, geometries, bounds, properties=None):
    """Pack `geometries` (Web Mercator) into a one-layer vector tile covering
    `bounds`. `properties` is an optional list of dicts, one per geometry."""
    # The MVT spec wants outer rings to have positive area in tile coordinates,
    # where y points down. The encoder flips y, so here (y up) they must run
    # clockwise. Orienting them ourselves lets the encoder skip its slow
    # per-polygon winding check.
    geometries = shapely.orient_polygons(np.asarray(geometries), exterior_cw=True)

    # Scale into the tile's 0..EXTENT grid in one vectorised step; the
    # encoder's own `quantize_bounds` does the same polygon by polygon in
    # Python, 3-4x slower.
    minx, miny, maxx, maxy = bounds
    to_tile = np.array([EXTENT / (maxx - minx), EXTENT / (maxy - miny)])
    geometries = shapely.transform(geometries, lambda xy: (xy - [minx, miny]) * to_tile)

    properties = properties or [{}] * len(geometries)
    features = [
        {"geometry": geometry, "properties": props}
        for geometry, props in zip(geometries, properties)
        if not geometry.is_empty
    ]
    return mapbox_vector_tile.encode(
        [{"name": layer, "features": features}],
        default_options={"extents": EXTENT, "check_winding_order": False},
    )

"""
How much of each street edge lies in shade.

Measured on three lines per edge: the centreline and the two sidewalks (see
streets.py). Each gives a fraction of its length that is shaded; the edge's
shaded fraction is the best of the three, since you can walk on the shady side.

Work is split by map tile: each tile measures only the part of each edge
inside it, so the shaded lengths from neighbouring tiles simply add up.
"""

import numpy as np
import shapely

VARIANTS = 3  # centreline, left sidewalk, right sidewalk


def variant_lines(streets, edges):
    """(VARIANTS, len(edges)) array of the lines measured for these edges."""
    return np.stack([streets.lines[edges], streets.sidewalks[0][edges], streets.sidewalks[1][edges]])


def shaded_lengths_in_tile(streets, shade, tile_bounds):
    """The edges overlapping the tile, and for each of their three lines the
    length (Web Mercator units) that is both inside the tile and in `shade`.
    Returns (edge indices, (VARIANTS, n) array)."""
    edges = streets.within(tile_bounds)
    lengths = np.zeros((VARIANTS, len(edges)))
    if len(edges) == 0 or shade.is_empty:
        return edges, lengths

    tile_shade = shapely.clip_by_rect(shade, *tile_bounds)
    if tile_shade.is_empty:
        return edges, lengths
    shapely.prepare(tile_shade)

    lines = variant_lines(streets, edges)
    in_tile = shapely.clip_by_rect(lines, *tile_bounds)
    # Most lines are entirely sunny or entirely shaded; only intersect the rest.
    touches = shapely.intersects(tile_shade, in_tile)
    inside = shapely.contains(tile_shade, in_tile)
    partial = touches & ~inside
    lengths[inside] = shapely.length(in_tile[inside])
    lengths[partial] = shapely.length(shapely.intersection(in_tile[partial], tile_shade))
    return edges, lengths


def shaded_fraction(streets, edges, shaded_lengths):
    """Combine per-variant shaded lengths (VARIANTS, n) into one fraction in
    [0, 1] per edge: the shadiest of its three lines."""
    totals = streets.variant_length[:, edges]
    with np.errstate(invalid="ignore", divide="ignore"):
        fractions = np.where(totals > 0, shaded_lengths / totals, 0.0)
    return np.clip(fractions.max(axis=0), 0.0, 1.0)

"""
Shade-aware walking routes.

Every street edge costs  length x (1 + alpha x sun_exposure),  where
sun_exposure = 1 - shaded_fraction (see edge_shade.py) and alpha runs from 0
(shortest route, shade ignored) to MAX_ALPHA (a sunny metre costs five shady
ones). Each request gets two routes: the shortest, and the one for the
walker's shade preference, so the app can show what the shade costs.

Shade is only measured in the zoom-15 tiles along the trip - the corridor
around the straight line from start to finish. Edges outside it count as
fully sunny, which keeps detours out of the unknown honest.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import networkx as nx
import numpy as np
import shapely

from buildings import units_per_metre
from edge_shade import shaded_fraction
from tiles import HALF_WORLD, tile_bounds

MAX_ALPHA = 4.0
WALKING_SPEED_M_PER_MIN = 4800 / 60  # 4.8 km/h
# The corridor reaches this far either side of the straight line, or a
# quarter of the trip if that's more, so reasonable detours are covered.
CORRIDOR_MIN_M = 300.0
CORRIDOR_FRACTION = 0.25
# Beyond this the walk is an hour and a half and the corridor too many tiles.
MAX_TRIP_M = 7000.0
# Taps further than this from any walkable street are not on the map.
MAX_SNAP_M = 250.0

_pool = ThreadPoolExecutor(max_workers=8)


class RouteError(ValueError):
    """The request can't be routed; the message says why."""


@dataclass
class Route:
    edges: np.ndarray  # edge indices into Streets, in walking order
    nodes: list

    def stats(self, streets, fractions):
        length = streets.length_m[self.edges]
        distance = float(length.sum())
        shaded = float((length * fractions[self.edges]).sum())
        return {
            "distance_m": round(distance),
            "duration_min": round(distance / WALKING_SPEED_M_PER_MIN, 1),
            "shade_pct": round(100 * shaded / distance, 1) if distance else 0.0,
        }

    def geometry(self, streets):
        """The route as one WGS84 LineString (lon, lat)."""
        coords = []
        for eid, u in zip(self.edges, self.nodes):
            xy = shapely.get_coordinates(streets.lines_wgs84[eid])
            start = (streets.graph.nodes[u]["x"], streets.graph.nodes[u]["y"])
            # Make each piece run from u to v, whatever way it was stored.
            if np.hypot(*(xy[0] - start)) > np.hypot(*(xy[-1] - start)):
                xy = xy[::-1]
            coords.extend(xy[1:] if coords else xy)
        return shapely.LineString(coords) if len(coords) > 1 else shapely.Point(coords[0])


def tile_of(x, y, z):
    size = 2 * HALF_WORLD / 2**z
    return int((x + HALF_WORLD) // size), int((HALF_WORLD - y) // size)


def corridor_tiles(start_xy, end_xy, z):
    """The z-level tiles that the corridor between two Web Mercator points touches."""
    scale = units_per_metre((start_xy[1] + end_xy[1]) / 2)
    straight = shapely.LineString([start_xy, end_xy])
    trip_m = straight.length / scale
    corridor = straight.buffer(max(CORRIDOR_MIN_M, CORRIDOR_FRACTION * trip_m) * scale)

    minx, miny, maxx, maxy = corridor.bounds
    x0, y0 = tile_of(minx, maxy, z)
    x1, y1 = tile_of(maxx, miny, z)
    candidates = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    boxes = shapely.box(*np.array([tile_bounds(z, x, y) for x, y in candidates]).T)
    return [tile for tile, hit in zip(candidates, shapely.intersects(corridor, boxes)) if hit]


def corridor_fractions(streets, tiles, tile_shaded_lengths):
    """Shaded fraction for every edge in the city: measured inside `tiles`,
    0 outside them. `tile_shaded_lengths(x, y)` -> (edges, (3, n) lengths)."""
    results = list(_pool.map(lambda t: tile_shaded_lengths(*t), tiles))
    lengths = np.zeros((3, len(streets)))
    for edges, tile_lengths in results:
        np.add.at(lengths, (slice(None), edges), tile_lengths)

    touched = np.unique(np.concatenate([edges for edges, _ in results] or [np.array([], int)]))
    fractions = np.zeros(len(streets))
    fractions[touched] = shaded_fraction(streets, touched, lengths[:, touched])
    return fractions


def shortest_route(streets, source, target, cost):
    """A* over the walking graph with per-edge `cost` (indexed by eid)."""
    graph = streets.graph

    def weight(u, v, keyed):
        return min(cost[data["eid"]] for data in keyed.values())

    # Straight-line metres never overestimate: every edge costs at least its length.
    pos = streets.node_pos
    scale = units_per_metre(pos[target][1])

    def heuristic(a, b):
        (ax, ay), (bx, by) = pos[a], pos[b]
        return math.hypot(ax - bx, ay - by) / scale

    try:
        nodes = nx.astar_path(graph, source, target, heuristic=heuristic, weight=weight)
    except nx.NetworkXNoPath:
        raise RouteError("no walking route connects these points")

    edges = [
        min((data["eid"] for data in graph[u][v].values()), key=lambda e: cost[e])
        for u, v in zip(nodes[:-1], nodes[1:])
    ]
    return Route(np.array(edges, dtype=int), nodes[:-1])


def plan(streets, start_xy, end_xy, preference, fractions_for):
    """Fastest and shade-preferring routes between two Web Mercator points.

    `preference` in [0, 1] scales alpha; `fractions_for(start_xy, end_xy)`
    returns every edge's shaded fraction for the trip. Returns a dict ready
    for JSON."""
    scale = units_per_metre((start_xy[1] + end_xy[1]) / 2)
    if np.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1]) / scale > MAX_TRIP_M:
        raise RouteError(f"points are more than {MAX_TRIP_M / 1000:g} km apart")

    source, d_source = streets.nearest_node(*start_xy)
    target, d_target = streets.nearest_node(*end_xy)
    if max(d_source, d_target) / scale > MAX_SNAP_M:
        raise RouteError("a point is too far from any walkable street")
    if source == target:
        raise RouteError("start and finish are the same place")

    fractions = fractions_for(start_xy, end_xy)
    alpha = MAX_ALPHA * preference
    fastest = shortest_route(streets, source, target, streets.length_m)
    shady = shortest_route(streets, source, target, streets.length_m * (1 + alpha * (1 - fractions)))

    def feature(route, kind):
        stats = route.stats(streets, fractions)
        return {
            "type": "Feature",
            "geometry": shapely.geometry.mapping(route.geometry(streets)),
            "properties": {"kind": kind, **stats},
        }

    fast_f, shady_f = feature(fastest, "fastest"), feature(shady, "shady")
    fp, sp = fast_f["properties"], shady_f["properties"]
    return {
        "fastest": fast_f,
        "shady": shady_f,
        "delta": {
            "distance_m": sp["distance_m"] - fp["distance_m"],
            "duration_min": round(sp["duration_min"] - fp["duration_min"], 1),
            "shade_pct": round(sp["shade_pct"] - fp["shade_pct"], 1),
        },
        "alpha": alpha,
    }

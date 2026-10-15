"""
The walking network, ready for shade-aware routing: one row per directed
street edge, with its geometry in Web Mercator (like buildings.py), its true
length in metres, and a spatial index to find the edges in a map tile.

Each edge also carries two sidewalk lines, offset to either side of the
centreline. A pedestrian can cross to whichever side is shaded, so an edge
counts as shaded as its shadier sidewalk (see edge_shade.py).
"""

import numpy as np
import shapely

from buildings import WEB_MERCATOR, units_per_metre
from fetch_osm import load_streets

# How far the sidewalks sit from the centreline: about where you walk on a
# two-lane street. In narrow lanes this lands near the walls, which is still
# where the shade is.
SIDEWALK_OFFSET_M = 4.0


class Streets:
    """Parallel arrays describing every directed edge of the walking graph,
    plus the graph itself (each edge's data holds its row as `eid`)."""

    def __init__(self, graph):
        import osmnx as ox

        nodes, edges = ox.graph_to_gdfs(graph)
        # WGS84 copies are what routes are sent to the app in.
        self.lines_wgs84 = edges.geometry.to_numpy()
        nodes = nodes.to_crs(WEB_MERCATOR)
        edges = edges.to_crs(WEB_MERCATOR)

        self.graph = graph
        self.node_ids = nodes.index.to_numpy()
        self.node_xy = shapely.get_coordinates(nodes.geometry.to_numpy())
        self.node_pos = {n: (float(x), float(y)) for n, (x, y) in zip(self.node_ids, self.node_xy)}

        self.edge_keys = edges.index.to_numpy()  # (u, v, key) tuples
        self.lines = edges.geometry.to_numpy()
        self.length_m = edges["length"].to_numpy(dtype=float)
        for eid, (u, v, k) in enumerate(self.edge_keys):
            graph.edges[u, v, k]["eid"] = eid

        offset = SIDEWALK_OFFSET_M * units_per_metre(float(np.mean(self.node_xy[:, 1])))
        self.sidewalks = np.stack(
            [shapely.offset_curve(self.lines, offset), shapely.offset_curve(self.lines, -offset)]
        )
        # Full length of each measured line (see edge_shade.py), in map units.
        self.variant_length = shapely.length(np.stack([self.lines, *self.sidewalks]))
        self.index = shapely.STRtree(self.lines)

    @classmethod
    def load(cls):
        """The cached city walking network (see fetch_osm.py)."""
        return cls(load_streets())

    def __len__(self):
        return len(self.lines)

    def within(self, bounds):
        """Indices of the edges whose bounding box overlaps `bounds`."""
        return self.index.query(shapely.box(*bounds))

    def nearest_node(self, x, y):
        """(node id, distance in Web Mercator units) of the node nearest x, y."""
        d2 = (self.node_xy[:, 0] - x) ** 2 + (self.node_xy[:, 1] - y) ** 2
        i = int(np.argmin(d2))
        return self.node_ids[i], float(np.sqrt(d2[i]))

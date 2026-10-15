"""
The city's buildings, ready for shadow casting: footprints in Web Mercator,
heights in metres, and a spatial index to find the buildings near a tile.

Web Mercator (EPSG:3857) is the projection map tiles use, so tiles can be cut
without reprojecting anything. It keeps angles true and north straight up,
but stretches every distance by 1 / cos(latitude) - about 1.4x in Bucharest -
so lengths in metres must be scaled with `units_per_metre` before use.
"""

import math

import numpy as np
import shapely

from fetch_osm import load_buildings

WEB_MERCATOR = "EPSG:3857"
EARTH_RADIUS_M = 6_378_137.0  # the sphere Web Mercator is defined on


def units_per_metre(mercator_y):
    """How many Web Mercator units one real metre spans at this y."""
    latitude = 2 * math.atan(math.exp(mercator_y / EARTH_RADIUS_M)) - math.pi / 2
    return 1 / math.cos(latitude)


class Buildings:
    """Footprints, heights and a spatial index, as parallel arrays: entry i
    of each array describes building i."""

    def __init__(self, footprints, heights_m, height_sources):
        # Orient every footprint the same way - outer ring counter-clockwise,
        # courtyard rings clockwise - so walking along any wall, the building
        # is on your left. shadows.py relies on this to tell which way a wall faces.
        self.footprints = shapely.orient_polygons(np.asarray(footprints))
        self.heights_m = np.asarray(heights_m, dtype=float)
        self.height_sources = np.asarray(height_sources)
        self.index = shapely.STRtree(self.footprints)
        self.tallest_m = float(self.heights_m.max(initial=0.0))

    @classmethod
    def from_geodataframe(cls, gdf):
        gdf = gdf.to_crs(WEB_MERCATOR)
        return cls(gdf.geometry.to_numpy(), gdf["height_m"].to_numpy(), gdf["height_source"].to_numpy())

    @classmethod
    def load(cls):
        """The cached city buildings (see fetch_osm.py)."""
        return cls.from_geodataframe(load_buildings())

    def __len__(self):
        return len(self.footprints)

    def within(self, bounds):
        """Indices of the buildings whose bounding box overlaps `bounds`
        (minx, miny, maxx, maxy in Web Mercator)."""
        return self.index.query(shapely.box(*bounds))

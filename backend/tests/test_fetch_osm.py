import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from fetch_osm import DEFAULT_HEIGHT_M, polygons_only, resolve_heights


def test_resolve_heights_takes_the_first_usable_source():
    tags = pd.DataFrame(
        {
            "height": ["12 m", "abc", np.nan, np.nan, "0", np.nan],
            "building:levels": [np.nan, "4", np.nan, np.nan, np.nan, "3;4"],
            "building": ["yes", "yes", "church", "yes", "yes", "house"],
        }
    )
    heights, sources = resolve_heights(tags)
    assert list(heights) == [12.0, 12.0, 15.0, DEFAULT_HEIGHT_M, DEFAULT_HEIGHT_M, 6.0]
    assert list(sources) == ["height", "levels", "type_fallback", "default", "default", "type_fallback"]


def test_resolve_heights_without_height_columns():
    heights, sources = resolve_heights(pd.DataFrame({"building": ["yes"]}))
    assert list(heights) == [DEFAULT_HEIGHT_M]
    assert list(sources) == ["default"]


def test_polygons_only_repairs_and_splits():
    # Self-intersecting with a spike: make_valid returns a collection holding
    # a MultiPolygon (two triangles) and a LineString (the spike).
    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0), (-5, 0), (0, 0)])
    two_parts = MultiPolygon([box(20, 0, 30, 10), box(40, 0, 50, 10)])
    gdf = gpd.GeoDataFrame({"height_m": [9.0, 12.0]}, geometry=[bowtie, two_parts], crs="EPSG:3857")

    result = polygons_only(gdf)

    assert sorted(result["height_m"]) == [9.0, 9.0, 12.0, 12.0]
    assert (result.geom_type == "Polygon").all() and result.is_valid.all()
    assert result.area.sum() == pytest.approx(2 * 25 + 2 * 100)

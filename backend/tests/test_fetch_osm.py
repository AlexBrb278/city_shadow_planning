import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from fetch_osm import polygons_only


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

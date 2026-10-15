import numpy as np
import pandas as pd
import pytest

from heights import DEFAULT_HEIGHT_M, METERS_PER_LEVEL, TYPE_HEIGHT_M, resolve_heights


def resolve_one(height=np.nan, levels=np.nan, building=np.nan):
    tags = pd.DataFrame({"height": [height], "building:levels": [levels], "building": [building]})
    heights, sources = resolve_heights(tags)
    return heights.iloc[0], sources.iloc[0]


@pytest.mark.parametrize(
    "height, levels, building, expected",
    [
        # explicit height tag, in its many spellings
        ("21", "5", "apartments", (21.0, "height")),
        ("12 m", np.nan, np.nan, (12.0, "height")),
        ("12m", np.nan, np.nan, (12.0, "height")),
        ("~4", np.nan, np.nan, (4.0, "height")),
        ("12;14", np.nan, np.nan, (12.0, "height")),
        # levels
        ("not-a-number", "3", np.nan, (3 * METERS_PER_LEVEL, "levels")),
        (np.nan, "4", "residential", (4 * METERS_PER_LEVEL, "levels")),
        (np.nan, "2.5", np.nan, (2.5 * METERS_PER_LEVEL, "levels")),
        (np.nan, "3;4", "house", (3 * METERS_PER_LEVEL, "levels")),
        # type fallback
        (np.nan, "two", "church", (TYPE_HEIGHT_M["church"], "type_fallback")),
        ("0", "0", "house", (TYPE_HEIGHT_M["house"], "type_fallback")),
        (np.nan, np.nan, "commercial", (TYPE_HEIGHT_M["commercial"], "type_fallback")),
        ("nan", "nan", "retail", (TYPE_HEIGHT_M["retail"], "type_fallback")),
        # default
        (np.nan, np.nan, np.nan, (DEFAULT_HEIGHT_M, "default")),
        (np.nan, np.nan, "parking", (DEFAULT_HEIGHT_M, "default")),
        ("12 ft", np.nan, "yes", (DEFAULT_HEIGHT_M, "default")),
    ],
)
def test_height_ladder(height, levels, building, expected):
    assert resolve_one(height, levels, building) == expected


def test_resolve_heights_without_height_columns():
    heights, sources = resolve_heights(pd.DataFrame({"building": ["yes"]}))
    assert list(heights) == [DEFAULT_HEIGHT_M]
    assert list(sources) == ["default"]

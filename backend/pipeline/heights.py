"""
Height resolution ladder for OSM building footprints: explicit height tag ->
building:levels x 3 m -> typical height for the building type -> 8 m.

Vectorised over a whole city's tags at once (a pandas DataFrame with OSM tag
columns, as osmnx returns them).
"""

import numpy as np
import pandas as pd

METERS_PER_LEVEL = 3.0
# Typical height by building type, for buildings with no height or levels tag.
TYPE_HEIGHT_M = {
    "apartments": 10 * METERS_PER_LEVEL,
    "residential": 2 * METERS_PER_LEVEL,
    "house": 2 * METERS_PER_LEVEL,
    "church": 15.0,
    "retail": 4 * METERS_PER_LEVEL,
    "commercial": 4 * METERS_PER_LEVEL,
}
DEFAULT_HEIGHT_M = 8.0

SOURCES = ["height", "levels", "type_fallback", "default"]


def positive_number(values):
    """Parse messy OSM tag values to floats: '12', '12 m', '12m', '~4', '2.5',
    and multi-valued '12;14' (first value wins). Anything else ('12 ft',
    'two') or not above zero becomes NaN."""
    cleaned = (
        values.astype("string")
        .str.split(";").str[0]
        .str.strip()
        .str.removeprefix("~")
        .str.removesuffix("m")
        .str.strip()
    )
    numbers = pd.to_numeric(cleaned, errors="coerce")
    return numbers.where(numbers > 0)


def resolve_heights(tags):
    """Height in metres for each row of OSM `tags`, and where it came from.
    Returns (heights, sources), both Series aligned with `tags`."""
    missing = pd.Series(np.nan, index=tags.index)
    explicit = positive_number(tags.get("height", missing))
    from_levels = positive_number(tags.get("building:levels", missing)) * METERS_PER_LEVEL
    by_type = tags.get("building", missing).map(TYPE_HEIGHT_M)

    heights = explicit.fillna(from_levels).fillna(by_type).fillna(DEFAULT_HEIGHT_M)
    sources = np.select(
        [explicit.notna(), from_levels.notna(), by_type.notna()],
        SOURCES[:3],
        default=SOURCES[3],
    )
    return heights.astype(float), pd.Series(sources, index=tags.index)


def print_height_coverage(sources):
    counts = sources.value_counts()
    total = len(sources) or 1
    print(f"OSM buildings: {len(sources)}")
    for source in SOURCES:
        n = counts.get(source, 0)
        print(f"  {source:14s}: {n:7d} ({100 * n / total:.1f}%)")

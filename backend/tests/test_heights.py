import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from heights import resolve_height, DEFAULT_HEIGHT_M, TYPE_HEIGHT_M, METERS_PER_LEVEL


def test_explicit_height_tag_wins():
    h, source = resolve_height("21", "5", "apartments")
    assert h == 21.0
    assert source == "height"


def test_height_tag_with_unit_suffix():
    h, source = resolve_height("12 m", None, None)
    assert h == 12.0
    assert source == "height"


def test_height_tag_with_approx_prefix():
    h, source = resolve_height("~4", None, None)
    assert h == 4.0
    assert source == "height"


def test_height_tag_multi_value_takes_first():
    h, source = resolve_height("12;14", None, None)
    assert h == 12.0
    assert source == "height"


def test_malformed_height_falls_back_to_levels():
    h, source = resolve_height("not-a-number", "3", None)
    assert h == 3 * METERS_PER_LEVEL
    assert source == "levels"


def test_levels_tag_used_when_no_height():
    h, source = resolve_height(None, "4", "residential")
    assert h == 4 * METERS_PER_LEVEL
    assert source == "levels"


def test_fractional_levels():
    h, source = resolve_height(None, "2.5", None)
    assert h == 2.5 * METERS_PER_LEVEL
    assert source == "levels"


def test_malformed_levels_falls_back_to_type():
    h, source = resolve_height(None, "two", "church")
    assert h == TYPE_HEIGHT_M["church"]
    assert source == "type_fallback"


def test_zero_height_falls_through_ladder():
    h, source = resolve_height("0", "0", "house")
    assert h == TYPE_HEIGHT_M["house"]
    assert source == "type_fallback"


def test_type_fallback_for_known_type():
    h, source = resolve_height(None, None, "commercial")
    assert h == TYPE_HEIGHT_M["commercial"]
    assert source == "type_fallback"


def test_default_when_nothing_resolves():
    h, source = resolve_height(None, None, None)
    assert h == DEFAULT_HEIGHT_M
    assert source == "default"


def test_default_for_unknown_type():
    h, source = resolve_height(None, None, "parking")
    assert h == DEFAULT_HEIGHT_M
    assert source == "default"


def test_nan_string_treated_as_missing():
    h, source = resolve_height("nan", "nan", "retail")
    assert h == TYPE_HEIGHT_M["retail"]
    assert source == "type_fallback"

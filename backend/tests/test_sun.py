import pytest

from sun import Sun, local_datetime, sun_at


def test_summer_is_eest():
    assert local_datetime("2026-07-15", "14:00").utcoffset().total_seconds() == 3 * 3600


def test_winter_is_eet():
    assert local_datetime("2026-01-15", "14:00").utcoffset().total_seconds() == 2 * 3600


@pytest.mark.parametrize("day, clock", [("2026-02-30", "12:00"), ("2026-07-15", "25:00"), ("15/07/2026", "12:00")])
def test_rejects_moments_that_do_not_exist(day, clock):
    with pytest.raises(ValueError):
        local_datetime(day, clock)


def test_summer_solstice_solar_noon():
    # Solar noon in Bucharest is ~13:15 EEST; elevation = 90 - 44.43 + 23.44.
    sun = sun_at(local_datetime("2026-06-21", "13:15"))
    assert sun.elevation_deg == pytest.approx(69.0, abs=0.5)
    assert sun.azimuth_deg == pytest.approx(180, abs=3)


def test_morning_sun_is_in_the_east():
    sun = sun_at(local_datetime("2026-06-21", "08:00"))
    assert sun.is_up
    assert 60 < sun.azimuth_deg < 100


def test_night():
    assert not sun_at(local_datetime("2026-06-21", "23:00")).is_up


def test_values_are_plain_floats():
    # pysolar returns numpy scalars, which JSON encoding rejects.
    sun = sun_at(local_datetime("2026-06-21", "13:15"))
    assert type(sun.elevation_deg) is float and type(sun.azimuth_deg) is float
    assert type(sun.is_up) is bool


def test_is_up_at_the_horizon():
    assert not Sun(elevation_deg=0.0, azimuth_deg=90.0).is_up

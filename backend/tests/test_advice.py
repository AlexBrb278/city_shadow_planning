from advice import advise, sun_minutes
from test_weather import make

STATS = {"duration_min": 30.0, "shade_pct": 20.0}  # 24 min in the open
STRETCH = [{"length_m": 420, "name": "Bulevardul Regina Elisabeta", "geometry": None}]


def ids(tips):
    return [t["id"] for t in tips]


def test_sun_minutes_scale_with_cloud():
    assert sun_minutes(STATS, 1.0) == 24.0
    assert sun_minutes(STATS, 0.5) == 12.0


def test_long_sunny_walk_gets_water_and_a_hat():
    tips = advise(STATS, True, make(), STRETCH)
    assert ids(tips) == ["water", "hat"]
    assert "420 m along Bulevardul Regina Elisabeta" in tips[0]["text"]


def test_high_uv_adds_sunscreen():
    assert "sunscreen" in ids(advise(STATS, True, make(uv_index=8.0), []))


def test_short_shady_walk_needs_nothing():
    assert advise({"duration_min": 10.0, "shade_pct": 80.0}, True, make(), []) == []


def test_heat_lowers_the_water_threshold():
    short = {"duration_min": 10.0, "shade_pct": 40.0}  # 6 sun minutes
    assert ids(advise(short, True, make(), [])) == []
    assert ids(advise(short, True, make(temperature_c=33.0), [])) == ["water"]


def test_overcast_cancels_the_warning():
    assert advise(STATS, True, make(cloud_cover_pct=100.0, weather_code=3), []) == []


def test_rain_means_umbrella_only():
    tips = advise(STATS, True, make(precipitation_mm=2.0, weather_code=63), STRETCH)
    assert ids(tips) == ["umbrella"]
    assert "Rain" in tips[0]["text"]


def test_night_needs_nothing():
    assert advise(STATS, False, make(), STRETCH) == []


def test_unknown_weather_assumes_sun():
    assert ids(advise(STATS, True, None, [])) == ["water", "hat"]

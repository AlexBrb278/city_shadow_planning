from datetime import datetime

import httpx
import pytest

import weather
from sun import BUCHAREST_TZ
from weather import Weather


def hourly(**overrides):
    """One day of Open-Meteo hourly data: dry, clear, 20°C, unless overridden
    as {field: {hour: value}}."""
    data = {
        "time": [f"2026-07-15T{h:02d}:00" for h in range(24)],
        "temperature_2m": [20.0] * 24,
        "precipitation": [0.0] * 24,
        "precipitation_probability": [0] * 24,
        "cloud_cover": [0] * 24,
        "uv_index": [5.0] * 24,
        "weather_code": [0] * 24,
    }
    for field, hours in overrides.items():
        for h, v in hours.items():
            data[field][h] = v
    return data


def at(hh, mm=0):
    return datetime(2026, 7, 15, hh, mm, tzinfo=BUCHAREST_TZ)


def make(**kw):
    base = dict(temperature_c=20.0, precipitation_mm=0.0, precipitation_probability_pct=0,
                cloud_cover_pct=0.0, uv_index=5.0, weather_code=0)
    return Weather(**{**base, **kw})


@pytest.mark.parametrize(
    "kw, raining, strength",
    [
        ({}, False, 1.0),
        ({"cloud_cover_pct": 100.0, "weather_code": 3}, False, 0.1),
        ({"cloud_cover_pct": 50.0}, False, 0.55),
        ({"precipitation_mm": 1.2, "weather_code": 63}, True, 0.0),
        ({"precipitation_probability_pct": 80}, True, 0.0),
        ({"weather_code": 61}, True, 0.0),  # light rain coded, nothing measured yet
    ],
)
def test_rain_and_sun_strength(kw, raining, strength):
    w = make(**kw)
    assert w.is_raining is raining
    assert w.sun_strength == strength


def test_weather_at_picks_the_nearest_hour(monkeypatch):
    monkeypatch.setattr(weather, "fetch_day", lambda d: hourly(cloud_cover={14: 40, 15: 90}))
    assert weather.weather_at(at(14, 20)).cloud_cover_pct == 40
    weather._cache.clear()
    assert weather.weather_at(at(14, 40)).cloud_cover_pct == 90


def test_late_evening_stays_on_the_same_day(monkeypatch):
    monkeypatch.setattr(weather, "fetch_day", lambda d: hourly(temperature_2m={23: 11.0}))
    assert weather.weather_at(at(23, 45)).temperature_c == 11.0


def test_unknown_weather_is_none(monkeypatch):
    assert weather.weather_at(at(12)) is None


def test_days_are_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "fetch_day", lambda d: calls.append(d) or hourly())
    weather.weather_at(at(9))
    weather.weather_at(at(17))
    assert calls == ["2026-07-15"]


def test_missing_fields_from_the_archive(monkeypatch):
    data = hourly()
    del data["uv_index"], data["precipitation_probability"]
    monkeypatch.setattr(weather, "fetch_day", lambda d: data)
    w = weather.weather_at(at(12))
    assert w.uv_index is None and w.precipitation_probability_pct is None
    assert w.to_json()["summary"] == "Clear"


ARCHIVED = {"time": ["x"], "temperature_2m": [21.0]}


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_fetch_day_falls_back_to_the_archive(monkeypatch):
    # Undo the conftest stub: this test exercises the real fetch with fake HTTP.
    monkeypatch.undo()
    urls = []

    def fake_get(url, params, timeout):
        urls.append(url)
        return FakeResponse(400) if url == weather.FORECAST_URL else FakeResponse(200, {"hourly": ARCHIVED})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert weather.fetch_day("2020-07-15") == ARCHIVED
    assert urls == [weather.FORECAST_URL, weather.ARCHIVE_URL]


def test_fetch_day_skips_a_forecast_full_of_nulls(monkeypatch):
    monkeypatch.undo()
    nulls = {"time": ["x"], "temperature_2m": [None]}

    def fake_get(url, params, timeout):
        return FakeResponse(200, {"hourly": nulls if url == weather.FORECAST_URL else ARCHIVED})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert weather.fetch_day("2026-07-15") == ARCHIVED


def test_fetch_day_gives_none_when_nobody_knows(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(httpx, "get", lambda url, params, timeout: FakeResponse(400))
    assert weather.fetch_day("1900-01-01") is None


def test_fetch_day_survives_the_service_being_down(monkeypatch):
    monkeypatch.undo()

    def down(url, params, timeout):
        raise httpx.ConnectTimeout("down")

    monkeypatch.setattr(httpx, "get", down)
    assert weather.fetch_day("2026-07-15") is None

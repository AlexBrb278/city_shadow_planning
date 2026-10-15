"""
The weather over Bucharest at a given moment, from Open-Meteo (free, no key).

Weather changes what shade is worth: under thick cloud there are no shadows
to seek, and in rain the walker wants the quickest way, not the shadiest.
`sun_strength` boils that down to one number that scales the routing's shade
preference.

Open-Meteo's forecast API covers roughly the past three months and the next
16 days; older dates fall back to its archive API. Anything else (or the
service being down) gives None, and routing carries on as if it were sunny.
"""

import threading
import time
from dataclasses import asdict, dataclass

import httpx

LATITUDE, LONGITUDE = 44.4268, 26.1025  # Piața Unirii, as in sun.py
TIMEZONE = "Europe/Bucharest"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = ["temperature_2m", "precipitation", "precipitation_probability", "cloud_cover", "uv_index", "weather_code"]
TIMEOUT_S = 4.0
# A day's forecast is refetched after this long; past days never change.
FORECAST_TTL_S = 30 * 60

# Rain heavier than this (mm in the hour), or this likely, counts as raining.
RAIN_MM = 0.2
RAIN_PROBABILITY_PCT = 60

# WMO weather codes, as Open-Meteo reports them.
WMO_SUMMARY = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}
WET_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


@dataclass(frozen=True)
class Weather:
    temperature_c: float | None
    precipitation_mm: float
    precipitation_probability_pct: float | None  # not in the archive
    cloud_cover_pct: float
    uv_index: float | None  # not in the archive
    weather_code: int | None

    @property
    def summary(self):
        return WMO_SUMMARY.get(self.weather_code, "Unknown")

    @property
    def is_raining(self):
        return (
            self.precipitation_mm >= RAIN_MM
            or (self.precipitation_probability_pct or 0) >= RAIN_PROBABILITY_PCT
            or self.weather_code in WET_CODES
        )

    @property
    def sun_strength(self):
        """How much direct sun reaches the street, 0..1: none in rain, little
        under full overcast (thin cloud still lets some through)."""
        if self.is_raining:
            return 0.0
        return round(1 - 0.9 * self.cloud_cover_pct / 100, 2)

    def to_json(self):
        return {**asdict(self), "summary": self.summary, "is_raining": self.is_raining, "sun_strength": self.sun_strength}


_cache = {}  # date -> (fetched_at, hourly dict or None)
_lock = threading.Lock()


def fetch_day(date_str):
    """Open-Meteo's hourly data for one Bucharest date, or None if neither
    API has it or the service can't be reached."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(HOURLY),
        "timezone": TIMEZONE,
        "start_date": date_str,
        "end_date": date_str,
    }
    for url in (FORECAST_URL, ARCHIVE_URL):
        try:
            # The archive has no probability or UV; ask only for what it has.
            p = params if url == FORECAST_URL else {
                **params, "hourly": "temperature_2m,precipitation,cloud_cover,weather_code"
            }
            r = httpx.get(url, params=p, timeout=TIMEOUT_S)
        except httpx.HTTPError as e:
            print(f"Weather unavailable for {date_str}: {type(e).__name__}")
            return None
        hourly = r.json().get("hourly") if r.status_code == 200 else None
        # At the edge of its range the forecast API answers with rows of
        # nulls rather than an error; 400 means out of range. Either way,
        # try the next API.
        if hourly and any(v is not None for v in hourly.get("temperature_2m") or []):
            return hourly
    return None


def day(date_str, today):
    """Cached fetch_day: forecasts expire, past days are kept for good."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(date_str)
    if hit and (date_str < today or now - hit[0] < FORECAST_TTL_S):
        return hit[1]
    hourly = fetch_day(date_str)
    with _lock:
        _cache[date_str] = (now, hourly)
    return hourly


def _value(hourly, key, i):
    values = hourly.get(key)
    if not values or i >= len(values) or values[i] is None:
        return None
    return float(values[i])


def weather_at(when):
    """The weather at aware Bucharest datetime `when` (nearest hour), or None."""
    hourly = day(when.date().isoformat(), today=time.strftime("%Y-%m-%d"))
    if not hourly or not hourly.get("time"):
        return None
    i = min(round(when.hour + when.minute / 60), len(hourly["time"]) - 1)
    code = _value(hourly, "weather_code", i)
    return Weather(
        temperature_c=_value(hourly, "temperature_2m", i),
        precipitation_mm=_value(hourly, "precipitation", i) or 0.0,
        precipitation_probability_pct=_value(hourly, "precipitation_probability", i),
        cloud_cover_pct=_value(hourly, "cloud_cover", i) or 0.0,
        uv_index=_value(hourly, "uv_index", i),
        weather_code=None if code is None else int(code),
    )

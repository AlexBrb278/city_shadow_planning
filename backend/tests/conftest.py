import sys
from pathlib import Path

import pytest

# Mirror how the API resolves imports: pipeline modules are flat, not a package.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "pipeline"))
sys.path.insert(0, str(BACKEND / "api"))

from sun import Sun  # noqa: E402

# Sun due south at 45 degrees: shadows point due north and are exactly as long
# as the building is tall, so expected shapes can be drawn by hand.
SOUTH_45 = Sun(elevation_deg=45.0, azimuth_deg=180.0)


def same_shape(a, b, tolerance=1e-6):
    return a.symmetric_difference(b).area < tolerance


@pytest.fixture
def south_45():
    return SOUTH_45


@pytest.fixture(autouse=True)
def no_weather_service(monkeypatch):
    """Tests never call Open-Meteo: weather is unknown unless a test says otherwise."""
    import weather

    monkeypatch.setattr(weather, "fetch_day", lambda date_str: None)
    weather._cache.clear()
    yield
    weather._cache.clear()

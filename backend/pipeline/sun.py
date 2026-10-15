"""
Where the sun is over Bucharest at a given local date and time.

One sun position serves the whole city: across Bucharest's ~20 km the sun's
angles differ by a fraction of a degree, far below what the shadows need.
"""

import warnings
from dataclasses import dataclass
from datetime import date as Date, datetime
from zoneinfo import ZoneInfo

from pysolar.solar import get_altitude, get_azimuth

# pysolar warns on every call for years past its leap-second table; the
# sub-second error is irrelevant here.
warnings.filterwarnings("ignore", message="Leap seconds for year", category=UserWarning)

# Europe/Bucharest switches between EET (+2) and EEST (+3); a fixed offset
# would put winter shadows an hour off.
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")
CITY_CENTRE = (26.1025, 44.4268)  # lon, lat - Piața Unirii


@dataclass(frozen=True)
class Sun:
    elevation_deg: float  # above the horizon; negative at night
    azimuth_deg: float  # compass direction, clockwise from north: 90 = east, 180 = south

    @property
    def is_up(self):
        return self.elevation_deg > 0


def local_datetime(date_str, time_str):
    """'YYYY-MM-DD' and 'HH:MM' in Bucharest local time -> aware datetime.
    Raises ValueError if they don't name a real moment."""
    day = Date.fromisoformat(date_str)
    clock = datetime.strptime(time_str, "%H:%M").time()
    return datetime.combine(day, clock, tzinfo=BUCHAREST_TZ)


def sun_at(when):
    """The sun's position over central Bucharest at aware datetime `when`."""
    lon, lat = CITY_CENTRE
    # pysolar returns numpy scalars; plain floats keep JSON encoding happy.
    return Sun(
        elevation_deg=float(get_altitude(lat, lon, when)),
        azimuth_deg=float(get_azimuth(lat, lon, when)),
    )

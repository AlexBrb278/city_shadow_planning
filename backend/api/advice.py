"""
What to bring for a walk, from how much sun (or rain) the chosen route meets.

"Sun minutes" are the minutes walked outside shade, scaled by how strong the
sun is through the cloud (weather.sun_strength): 20 minutes in the open under
thick overcast count as a few.
"""

# Thresholds, in effective sun minutes.
HAT_MIN = 8
WATER_MIN = 15
HOT_C = 27  # from this temperature, water for any real sun at all
HOT_WATER_MIN = 5
SUNSCREEN_UV = 6
SUNSCREEN_MIN = 10


def sun_minutes(stats, sun_strength):
    """Effective minutes in direct sun on a route with `stats` (see routing)."""
    return stats["duration_min"] * (1 - stats["shade_pct"] / 100) * sun_strength


def advise(stats, sun_up, weather, stretches):
    """A list of {id, title, text} tips, most important first; may be empty.
    `stretches` are the route's long sunny stretches (routing.sunny_stretches)."""
    tips = []
    if weather is not None and weather.is_raining:
        tips.append({
            "id": "umbrella",
            "title": "Take an umbrella",
            "text": f"{weather.summary} expected - shade won't help much, so this is the quickest way.",
        })
        return tips
    if not sun_up:
        return tips

    strength = 1.0 if weather is None else weather.sun_strength
    minutes = sun_minutes(stats, strength)
    hot = weather is not None and weather.temperature_c is not None and weather.temperature_c >= HOT_C
    longest = max(stretches, key=lambda s: s["length_m"], default=None)
    where = ""
    if longest:
        name = f" along {longest['name']}" if longest["name"] else ""
        where = f" The longest stretch is {longest['length_m']} m{name}."

    if minutes >= WATER_MIN or (hot and minutes >= HOT_WATER_MIN):
        heat = f" and it's {round(weather.temperature_c)}°C" if hot else ""
        tips.append({
            "id": "water",
            "title": "Bring water",
            "text": f"About {round(minutes)} min of this walk is in direct sun{heat}.{where}",
        })
        where = ""  # said once is enough
    if minutes >= HAT_MIN:
        tips.append({
            "id": "hat",
            "title": "Cover your head",
            "text": f"A hat or cap helps on the sunny parts.{where}".strip(),
        })
    uv = None if weather is None else weather.uv_index
    if uv is not None and uv >= SUNSCREEN_UV and minutes >= SUNSCREEN_MIN:
        tips.append({
            "id": "sunscreen",
            "title": "Sunscreen",
            "text": f"UV index is {round(uv)} - high enough to burn on a walk this sunny.",
        })
    return tips

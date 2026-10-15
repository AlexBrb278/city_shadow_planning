import type { Feature, LineString } from 'geojson';

export const API_BASE = 'http://localhost:8000';

// Buildings and shade come as zoom-15 vector tiles; MapLibre stretches them
// for closer zooms. Keep in sync with TILE_ZOOM in backend/api/main.py.
export const TILE_ZOOM = 15;

/** A moment in Bucharest local time: date YYYY-MM-DD, time HH:MM. */
export interface Moment {
	date: string;
	time: string;
}

export interface Sun {
	/** ISO 8601 with Bucharest offset. */
	time: string;
	elevation_deg: number;
	/** Clockwise from north: 90 = east, 180 = south. */
	azimuth_deg: number;
	is_up: boolean;
}

export async function fetchSun({ date, time }: Moment, signal?: AbortSignal): Promise<Sun> {
	const res = await fetch(`${API_BASE}/sun?${new URLSearchParams({ date, time })}`, { signal });
	if (!res.ok) throw new Error(`/sun -> HTTP ${res.status}`);
	return res.json();
}

export const buildingTilesUrl = `${API_BASE}/tiles/buildings/{z}/{x}/{y}.pbf`;

export function shadeTilesUrl({ date, time }: Moment): string {
	return `${API_BASE}/tiles/shade/{z}/{x}/{y}.pbf?${new URLSearchParams({ date, time })}`;
}

export type LngLat = [number, number];

export interface RouteStats {
	kind: 'fastest' | 'shady';
	distance_m: number;
	duration_min: number;
	/** Length-weighted share of the route in shade, 0-100. */
	shade_pct: number;
}

export interface RouteResult {
	time: string;
	sun_up: boolean;
	fastest: Feature<LineString, RouteStats>;
	shady: Feature<LineString, RouteStats>;
	/** shady minus fastest */
	delta: { distance_m: number; duration_min: number; shade_pct: number };
}

/** Fastest and shade-preferring walks between two points; `shade` in [0, 1]. */
export async function fetchRoute(
	from: LngLat,
	to: LngLat,
	shade: number,
	{ date, time }: Moment,
	signal?: AbortSignal
): Promise<RouteResult> {
	const params = new URLSearchParams({
		from_lon: String(from[0]),
		from_lat: String(from[1]),
		to_lon: String(to[0]),
		to_lat: String(to[1]),
		shade: String(shade),
		date,
		time
	});
	const res = await fetch(`${API_BASE}/route?${params}`, { signal });
	if (res.status === 422) {
		const body = await res.json().catch(() => null);
		throw new Error(typeof body?.detail === 'string' ? body.detail : 'Cannot route between these points');
	}
	if (!res.ok) throw new Error(`/route -> HTTP ${res.status}`);
	return res.json();
}

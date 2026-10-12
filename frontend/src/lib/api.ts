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

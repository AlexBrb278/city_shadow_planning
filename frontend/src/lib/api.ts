import type { FeatureCollection, Polygon } from 'geojson';

export const API_BASE = 'http://localhost:8000';

export interface Sun {
	elevation_deg: number;
	/** Clockwise from north: 90 = east, 180 = south. */
	azimuth_deg: number;
	is_up: boolean;
}

/** GET /shadows - shaded ground at a moment, plus the sun position. */
export interface Shadows extends FeatureCollection<Polygon> {
	/** ISO 8601 with Bucharest offset. */
	time: string;
	sun: Sun;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, { signal });
	if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
	return res.json();
}

export const fetchBuildings = () => get<FeatureCollection>('/buildings');

/** `date` is YYYY-MM-DD, `time` HH:MM, both Bucharest local time. */
export const fetchShadows = (date: string, time: string, signal?: AbortSignal) =>
	get<Shadows>(`/shadows?${new URLSearchParams({ date, time })}`, signal);

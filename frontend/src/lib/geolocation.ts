// Where the walker is and which way they face.
//
// Position comes from the Geolocation API (GPS on phones; Capacitor's web
// view provides the same API). Facing comes from the compass when the device
// has one - that works standing still - and otherwise from the GPS course,
// which only means something while walking.

import type { LngLat } from '$lib/api';

export interface Fix {
	lngLat: LngLat;
	/** Metres, 68% confidence. */
	accuracy: number;
	/** Direction of travel, degrees clockwise from north, or null when still. */
	course: number | null;
}

// GPS course is noise below a slow walk.
const MIN_COURSE_SPEED_M_S = 0.8;

export function geolocationAvailable(): boolean {
	return typeof navigator !== 'undefined' && 'geolocation' in navigator;
}

/** Follow the device's position. Returns a function that stops watching. */
export function watchFix(onFix: (fix: Fix) => void, onError: (message: string) => void): () => void {
	if (!geolocationAvailable()) {
		onError('This device has no location service');
		return () => {};
	}
	const id = navigator.geolocation.watchPosition(
		(p) => {
			const { longitude, latitude, accuracy, heading, speed } = p.coords;
			const moving = speed !== null && speed >= MIN_COURSE_SPEED_M_S;
			onFix({
				lngLat: [longitude, latitude],
				accuracy,
				course: moving && heading !== null && !Number.isNaN(heading) ? heading : null
			});
		},
		(e) =>
			onError(
				e.code === e.PERMISSION_DENIED
					? 'Location permission denied - tap the map to set your start'
					: 'Could not get your location'
			),
		{ enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 }
	);
	return () => navigator.geolocation.clearWatch(id);
}

type CompassEvent = DeviceOrientationEvent & { webkitCompassHeading?: number };
type PermissionRequester = { requestPermission?: () => Promise<'granted' | 'denied'> };

/** iOS asks before sharing the compass, and only from inside a tap handler. */
export async function requestCompass(): Promise<boolean> {
	const request = (globalThis.DeviceOrientationEvent as unknown as PermissionRequester | undefined)
		?.requestPermission;
	if (!request) return true;
	try {
		return (await request()) === 'granted';
	} catch {
		return false;
	}
}

/** Follow the compass heading (degrees clockwise from north). Updates are
 * thinned out to changes of a couple of degrees so the map isn't asked to
 * re-render sixty times a second. Returns a function that stops listening. */
export function watchCompass(onHeading: (heading: number) => void): () => void {
	let last: number | null = null;
	let lastAt = 0;
	const handler = (e: Event) => {
		const ev = e as CompassEvent;
		let heading: number | null = null;
		if (typeof ev.webkitCompassHeading === 'number') heading = ev.webkitCompassHeading; // iOS
		else if (ev.absolute && ev.alpha !== null) heading = 360 - ev.alpha; // alpha turns anticlockwise
		if (heading === null) return;
		// The compass reads relative to the device; turn it to the screen.
		heading = (heading + (screen.orientation?.angle ?? 0) + 360) % 360;

		const now = performance.now();
		const turned = last === null ? 360 : Math.abs(((heading - last + 540) % 360) - 180);
		if (turned < 2 || now - lastAt < 80) return;
		last = heading;
		lastAt = now;
		onHeading(heading);
	};
	window.addEventListener('deviceorientationabsolute', handler);
	window.addEventListener('deviceorientation', handler);
	return () => {
		window.removeEventListener('deviceorientationabsolute', handler);
		window.removeEventListener('deviceorientation', handler);
	};
}

/** Distance in metres between two points (equirectangular; fine at city scale). */
export function metresBetween(a: LngLat, b: LngLat): number {
	const rad = Math.PI / 180;
	const x = (b[0] - a[0]) * rad * Math.cos(((a[1] + b[1]) / 2) * rad);
	const y = (b[1] - a[1]) * rad;
	return Math.hypot(x, y) * 6_371_000;
}

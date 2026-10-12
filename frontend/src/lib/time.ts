// The app is about Bucharest's sun, so all times are Bucharest local time
// regardless of where the browser is.
const TZ = 'Europe/Bucharest';

/** Current Bucharest date (YYYY-MM-DD) and minutes since midnight. */
export function bucharestNow(): { date: string; minutes: number } {
	const parts = Object.fromEntries(
		new Intl.DateTimeFormat('en-CA', {
			timeZone: TZ,
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			hourCycle: 'h23'
		})
			.formatToParts(new Date())
			.map((p) => [p.type, p.value])
	);
	return {
		date: `${parts.year}-${parts.month}-${parts.day}`,
		minutes: Number(parts.hour) * 60 + Number(parts.minute)
	};
}

/** Minutes since midnight -> HH:MM. */
export function formatMinutes(minutes: number): string {
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

/** Azimuth in degrees (clockwise from north) -> 8-point compass label. */
export function compass(azimuthDeg: number): string {
	return COMPASS[Math.round((((azimuthDeg % 360) + 360) % 360) / 45) % 8];
}

// Time slider range: covers Bucharest daylight year-round (earliest sunrise
// ~05:30 EEST in June, latest sunset ~21:05).
export const SLIDER_MIN = 5 * 60;
export const SLIDER_MAX = 21 * 60 + 30;
export const SLIDER_STEP = 15;

/** Snap minutes since midnight onto the slider's range and step. */
export function snapMinutes(minutes: number): number {
	const snapped = Math.round(minutes / SLIDER_STEP) * SLIDER_STEP;
	return Math.min(SLIDER_MAX, Math.max(SLIDER_MIN, snapped));
}

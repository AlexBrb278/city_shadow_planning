<script lang="ts">
	import { onMount } from 'svelte';
	import AdvicePopup from '$lib/AdvicePopup.svelte';
	import Map, { type Basemap } from '$lib/Map.svelte';
	import RoutePanel from '$lib/RoutePanel.svelte';
	import TimeControl from '$lib/TimeControl.svelte';
	import {
		fetchRoute,
		fetchSun,
		fetchWeather,
		type LngLat,
		type Moment,
		type RouteResult,
		type Sun,
		type Weather
	} from '$lib/api';
	import {
		geolocationAvailable,
		metresBetween,
		requestCompass,
		watchCompass,
		watchFix,
		type Fix
	} from '$lib/geolocation';
	import { bucharestNow, formatMinutes, snapMinutes } from '$lib/time';

	const now = bucharestNow();
	// What the controls show, updated on every slider step...
	let date = $state(now.date);
	let minutes = $state(snapMinutes(now.minutes));
	// ...and the moment the map shows, which follows once the slider settles.
	let moment = $state<Moment>({ date: now.date, time: formatMinutes(snapMinutes(now.minutes)) });
	let sun = $state<Sun | null>(null);
	let weather = $state<Weather | null>(null);
	let settling = $state(false);
	let tilesLoading = $state(false);
	let error = $state<string | null>(null);

	// Where the walker is (GPS) and which way they face.
	let me = $state<Fix | null>(null);
	let compass = $state<number | null>(null);
	let heading = $derived(compass ?? me?.course ?? null);
	let locating = $state(false);
	let locationError = $state<string | null>(null);
	let following = $state(false);
	let stopWatching: (() => void)[] = [];

	// The trip. The start is the walker's position while GPS is on, unless
	// they chose a map pin instead; taps set the destination.
	let from = $state<LngLat | null>(null);
	let to = $state<LngLat | null>(null);
	let startFromMe = $state(true);
	// The GPS start only moves on once the walker has really moved, so
	// routes aren't recomputed for every wobble of the fix.
	let meStart = $state<LngLat | null>(null);
	const RESTART_AFTER_M = 25;
	let startIsMe = $derived(startFromMe && meStart !== null);
	let start = $derived(startIsMe ? meStart : from);

	let shade = $state(0.75);
	let route = $state<RouteResult | null>(null);
	let routing = $state(false);
	let routeError = $state<string | null>(null);

	let basemap = $state<Basemap>('satellite');
	const BASEMAP_KEY = 'umbra.basemap';

	// The advice popup shows once per trip and set of tips; "Got it" hides it
	// until either changes.
	let dismissedAdvice = $state('');
	let adviceKey = $derived(
		route && route.advice.length && start && to
			? [start, to].map((p) => p.map((c) => c.toFixed(4)).join(',')).join('|') +
					'|' +
					route.advice.map((a) => a.id).join(',')
			: ''
	);

	onMount(() => {
		try {
			const saved = localStorage.getItem(BASEMAP_KEY);
			if (saved === 'satellite' || saved === 'map') basemap = saved;
		} catch {
			// storage blocked - keep the default
		}
		// Don't pop a permission prompt on load; but if location was allowed
		// before, start right away.
		navigator.permissions
			?.query({ name: 'geolocation' })
			.then((p) => {
				if (p.state === 'granted') startLocation(false);
			})
			.catch(() => {});
		return () => stopWatching.forEach((stop) => stop());
	});

	$effect(() => {
		try {
			localStorage.setItem(BASEMAP_KEY, basemap);
		} catch {
			// storage blocked
		}
	});

	function startLocation(follow: boolean) {
		if (!geolocationAvailable()) {
			locationError = 'This device has no location service';
			return;
		}
		locating = true;
		locationError = null;
		let first = true;
		stopWatching.push(
			watchFix(
				(fix) => {
					me = fix;
					locating = false;
					locationError = null;
					if (!meStart || metresBetween(meStart, fix.lngLat) > RESTART_AFTER_M) meStart = fix.lngLat;
					if (first && follow) following = true;
					first = false;
				},
				(message) => {
					locating = false;
					locationError = message;
				}
			),
			watchCompass((h) => (compass = h))
		);
	}

	async function locate() {
		if (me || locating) {
			following = true; // already tracking: lock the camera on again
			return;
		}
		// iOS only grants the compass from inside this tap.
		await requestCompass();
		startLocation(true);
	}

	function pick(at: LngLat) {
		if (startIsMe) {
			to = at;
			return;
		}
		if (!from) from = at;
		else if (!to) to = at;
		else {
			// A third tap starts a new trip.
			from = at;
			to = null;
		}
	}

	function move(which: 'from' | 'to', at: LngLat) {
		if (which === 'from') from = at;
		else to = at;
	}

	function clear() {
		from = to = route = routeError = null;
	}

	// Debounced so dragging the slider doesn't request a tile set per step;
	// a superseded request is aborted. Weather is a nice-to-have: if it
	// fails, the map still works.
	$effect(() => {
		if (!date) return;
		const next = { date, time: formatMinutes(minutes) };
		const ctrl = new AbortController();
		settling = true;
		const timer = setTimeout(async () => {
			moment = next;
			fetchWeather(next, ctrl.signal)
				.then((w) => (weather = w))
				.catch(() => {
					if (!ctrl.signal.aborted) weather = null;
				});
			try {
				sun = await fetchSun(next, ctrl.signal);
				error = null;
			} catch (e) {
				if (!ctrl.signal.aborted) error = `Could not reach the backend (${(e as Error).message})`;
			} finally {
				if (!ctrl.signal.aborted) settling = false;
			}
		}, 150);
		return () => {
			clearTimeout(timer);
			ctrl.abort();
		};
	});

	// Re-plan when the trip, the preference or the moment changes. Waits for
	// the slider to settle like the shade does; a superseded request is aborted.
	$effect(() => {
		if (!start || !to) {
			route = null;
			return;
		}
		const [a, b, pref, when] = [start, to, shade, moment];
		const ctrl = new AbortController();
		routing = true;
		const timer = setTimeout(async () => {
			try {
				route = await fetchRoute(a, b, pref, when, ctrl.signal);
				routeError = null;
			} catch (e) {
				if (ctrl.signal.aborted) return;
				route = null;
				routeError = (e as Error).message;
			} finally {
				if (!ctrl.signal.aborted) routing = false;
			}
		}, 150);
		return () => {
			clearTimeout(timer);
			ctrl.abort();
		};
	});
</script>

<Map
	{moment}
	{sun}
	{weather}
	bind:loading={tilesLoading}
	from={startIsMe ? null : from}
	{to}
	{route}
	{me}
	{heading}
	{locating}
	bind:following
	bind:basemap
	onpick={pick}
	onmove={move}
	onlocate={locate}
/>
<RoutePanel
	from={start}
	{to}
	bind:shade
	raining={weather?.is_raining ?? false}
	result={route}
	loading={routing}
	error={routeError ?? locationError}
	{startIsMe}
	canUseMe={meStart !== null}
	onclear={clear}
	onusepin={() => {
		startFromMe = false;
		from = null;
	}}
	onuseme={() => {
		startFromMe = true;
		from = null;
	}}
/>
{#if adviceKey && adviceKey !== dismissedAdvice && route}
	<AdvicePopup advice={route.advice} onclose={() => (dismissedAdvice = adviceKey)} />
{/if}
<TimeControl
	bind:date
	bind:minutes
	sun={sun ?? undefined}
	{weather}
	loading={settling || tilesLoading}
	{error}
/>

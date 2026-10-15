<script lang="ts">
	import Map from '$lib/Map.svelte';
	import RoutePanel from '$lib/RoutePanel.svelte';
	import TimeControl from '$lib/TimeControl.svelte';
	import { fetchRoute, fetchSun, type LngLat, type Moment, type RouteResult, type Sun } from '$lib/api';
	import { bucharestNow, formatMinutes, snapMinutes } from '$lib/time';

	const now = bucharestNow();
	// What the controls show, updated on every slider step...
	let date = $state(now.date);
	let minutes = $state(snapMinutes(now.minutes));
	// ...and the moment the map shows, which follows once the slider settles.
	let moment = $state<Moment>({ date: now.date, time: formatMinutes(snapMinutes(now.minutes)) });
	let sun = $state<Sun | null>(null);
	let settling = $state(false);
	let tilesLoading = $state(false);
	let error = $state<string | null>(null);

	// The trip: tap once for the start, again for the finish.
	let from = $state<LngLat | null>(null);
	let to = $state<LngLat | null>(null);
	let shade = $state(0.75);
	let route = $state<RouteResult | null>(null);
	let routing = $state(false);
	let routeError = $state<string | null>(null);

	function pick(at: LngLat) {
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
	// a superseded sun request is aborted.
	$effect(() => {
		if (!date) return;
		const next = { date, time: formatMinutes(minutes) };
		const ctrl = new AbortController();
		settling = true;
		const timer = setTimeout(async () => {
			moment = next;
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
		if (!from || !to) {
			route = null;
			return;
		}
		const [a, b, pref, when] = [from, to, shade, moment];
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

<Map {moment} {sun} bind:loading={tilesLoading} {from} {to} {route} onpick={pick} onmove={move} />
<RoutePanel {from} {to} bind:shade result={route} loading={routing} error={routeError} onclear={clear} />
<TimeControl bind:date bind:minutes sun={sun ?? undefined} loading={settling || tilesLoading} {error} />

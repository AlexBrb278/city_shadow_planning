<script lang="ts">
	import Map from '$lib/Map.svelte';
	import TimeControl from '$lib/TimeControl.svelte';
	import { fetchSun, type Moment, type Sun } from '$lib/api';
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
</script>

<Map {moment} {sun} bind:loading={tilesLoading} />
<TimeControl bind:date bind:minutes sun={sun ?? undefined} loading={settling || tilesLoading} {error} />

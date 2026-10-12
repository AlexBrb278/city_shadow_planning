<script lang="ts">
	import Map from '$lib/Map.svelte';
	import TimeControl from '$lib/TimeControl.svelte';
	import { fetchShadows, type Shadows } from '$lib/api';
	import { bucharestNow, formatMinutes, snapMinutes } from '$lib/time';

	const now = bucharestNow();
	let date = $state(now.date);
	let minutes = $state(snapMinutes(now.minutes));
	// Raw: a large GeoJSON blob that is replaced, never mutated - a deep
	// proxy would only cost time.
	let shadows = $state.raw<Shadows | null>(null);
	// True while the shade on the map doesn't match the chosen moment yet.
	let loading = $state(false);
	let error = $state<string | null>(null);

	// Refetch whenever the moment changes. Debounced so dragging the slider
	// doesn't fire a request per step; superseded requests are aborted.
	$effect(() => {
		if (!date) {
			loading = false;
			return;
		}
		const [d, t] = [date, formatMinutes(minutes)];
		const ctrl = new AbortController();
		loading = true;
		const timer = setTimeout(async () => {
			try {
				shadows = await fetchShadows(d, t, ctrl.signal);
				error = null;
			} catch (e) {
				if (!ctrl.signal.aborted) error = `Could not load shadows (${(e as Error).message})`;
			} finally {
				if (!ctrl.signal.aborted) loading = false;
			}
		}, 150);
		return () => {
			clearTimeout(timer);
			ctrl.abort();
		};
	});
</script>

<Map {shadows} />
<TimeControl bind:date bind:minutes sun={shadows?.sun} {loading} {error} />

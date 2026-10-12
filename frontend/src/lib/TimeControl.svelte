<script lang="ts">
	import type { Sun } from '$lib/api';
	import {
		SLIDER_MAX,
		SLIDER_MIN,
		SLIDER_STEP,
		bucharestNow,
		compass,
		formatMinutes,
		snapMinutes
	} from '$lib/time';

	let {
		date = $bindable(),
		minutes = $bindable(),
		sun,
		loading = false,
		error = null
	}: {
		date: string;
		minutes: number;
		sun?: Sun;
		loading?: boolean;
		error?: string | null;
	} = $props();

	function jumpToNow() {
		const now = bucharestNow();
		date = now.date;
		minutes = snapMinutes(now.minutes);
	}
</script>

<div class="panel">
	<div class="row">
		<input type="date" bind:value={date} aria-label="Date" />
		<output class="clock" class:stale={loading}>{formatMinutes(minutes)}</output>
		<button type="button" onclick={jumpToNow}>Now</button>
	</div>
	<input
		type="range"
		min={SLIDER_MIN}
		max={SLIDER_MAX}
		step={SLIDER_STEP}
		bind:value={minutes}
		aria-label="Time of day, Bucharest"
	/>
	<p class="status" class:error role="status">
		{#if error}
			{error}
		{:else if !sun}
			Loading shadows…
		{:else if sun.is_up}
			Sun {Math.round(sun.elevation_deg)}° up in the {compass(sun.azimuth_deg)}
			({Math.round(sun.azimuth_deg)}°)
		{:else}
			Sun below the horizon - no shadows to show
		{/if}
	</p>
</div>

<style>
	.panel {
		position: absolute;
		left: 50%;
		bottom: 32px;
		transform: translateX(-50%);
		width: min(480px, calc(100% - 32px));
		box-sizing: border-box;
		padding: 12px 16px;
		display: grid;
		gap: 8px;
		background: rgb(255 255 255 / 0.94);
		border-radius: 12px;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.18);
		font: 14px/1.3 system-ui, sans-serif;
		color: #1f2633;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.clock {
		margin-left: auto;
		font-size: 22px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		transition: opacity 0.15s;
	}
	.clock.stale {
		opacity: 0.5;
	}
	input[type='date'],
	button {
		font: inherit;
		padding: 4px 8px;
		border: 1px solid #c9d0db;
		border-radius: 6px;
		background: #fff;
		color: inherit;
	}
	button {
		cursor: pointer;
	}
	input[type='range'] {
		width: 100%;
		margin: 0;
		accent-color: #e0a526;
	}
	.status {
		margin: 0;
		color: #4a5466;
	}
	.status.error {
		color: #b42318;
	}
</style>

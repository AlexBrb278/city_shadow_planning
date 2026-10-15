<script lang="ts">
	import type { Sun, Weather } from '$lib/api';
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
		weather = null,
		loading = false,
		error = null
	}: {
		date: string;
		minutes: number;
		sun?: Sun;
		weather?: Weather | null;
		loading?: boolean;
		error?: string | null;
	} = $props();

	function weatherIcon(w: Weather): string {
		if (w.is_raining) return '🌧';
		if (w.cloud_cover_pct >= 80) return '☁️';
		if (w.cloud_cover_pct >= 30) return '⛅';
		return sun?.is_up ? '☀️' : '🌙';
	}

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
	{#if weather && !error}
		<p class="weather" class:wet={weather.is_raining}>
			{weatherIcon(weather)}
			{weather.summary}
			{#if weather.temperature_c !== null}· {Math.round(weather.temperature_c)}°C{/if}
			· {Math.round(weather.cloud_cover_pct)}% cloud
			{#if weather.precipitation_mm > 0}· {weather.precipitation_mm.toFixed(1)} mm rain{/if}
			{#if weather.uv_index !== null && weather.uv_index >= 3}· UV {Math.round(weather.uv_index)}{/if}
		</p>
	{/if}
</div>

<style>
	.panel {
		position: absolute;
		left: 50%;
		bottom: max(24px, env(safe-area-inset-bottom));
		transform: translateX(-50%);
		width: min(480px, calc(100% - 24px));
		box-sizing: border-box;
		padding: 12px 16px;
		display: grid;
		gap: 8px;
		background: var(--panel-bg);
		border-radius: 12px;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.18);
		font: 14px/1.3 system-ui, sans-serif;
		color: var(--panel-fg);
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
		border: 1px solid var(--panel-border);
		border-radius: 6px;
		background: var(--input-bg);
		color: inherit;
	}
	button {
		cursor: pointer;
	}
	input[type='range'] {
		width: 100%;
		margin: 0;
		accent-color: var(--accent-sun);
	}
	.status {
		margin: 0;
		color: var(--panel-muted);
	}
	.weather {
		margin: 0;
		color: var(--panel-muted);
	}
	.weather.wet {
		color: var(--me);
		font-weight: 600;
	}
	.status.error {
		color: var(--error);
	}
</style>

<script lang="ts">
	import type { LngLat, RouteResult } from '$lib/api';

	let {
		from,
		to,
		shade = $bindable(),
		raining = false,
		result,
		loading = false,
		error = null,
		startIsMe = false,
		canUseMe = false,
		onclear,
		onusepin,
		onuseme
	}: {
		/** The trip's start, wherever it comes from. */
		from: LngLat | null;
		to: LngLat | null;
		shade: number;
		/** In rain shade doesn't matter, so the preference is set aside. */
		raining?: boolean;
		result: RouteResult | null;
		loading?: boolean;
		error?: string | null;
		/** The start is the walker's GPS position. */
		startIsMe?: boolean;
		/** GPS is available, so the start could be the walker's position. */
		canUseMe?: boolean;
		onclear: () => void;
		onusepin?: () => void;
		onuseme?: () => void;
	} = $props();

	const PREFERENCES = ['Fastest', 'A little', 'Some', 'Lots', 'Max shade'];
	let label = $derived(raining ? 'Off in rain' : PREFERENCES[Math.round(shade * (PREFERENCES.length - 1))]);

	function minutes(m: number): string {
		const rounded = Math.round(Math.abs(m));
		return rounded === 0 ? 'same time' : `${m > 0 ? '+' : '−'}${rounded} min`;
	}
</script>

<section class="panel" aria-label="Route">
	{#if !from}
		<p class="hint">
			Tap the map to set where you start{#if !canUseMe}, or <span class="arrow-glyph">▲</span> to
				start from your location{/if}
		</p>
	{:else if !to}
		<p class="hint">{startIsMe ? 'From your location - tap' : 'Now tap'} where you're going</p>
	{:else if error}
		<p class="error" role="alert">{error}</p>
	{:else if result}
		{@const fast = result.fastest.properties}
		{@const shady = result.shady.properties}
		{@const w = result.weather}
		<div class="card" class:stale={loading} aria-live="polite">
			{#if w?.is_raining}
				<p class="headline">{w.summary} - taking the quickest way</p>
				<p class="detail">
					{Math.round(fast.duration_min)} min · {(fast.distance_m / 1000).toFixed(1)} km · shade won't keep
					you dry
				</p>
			{:else if !result.sun_up}
				<p class="headline">Sun's down — every street is in shade</p>
				<p class="detail">{Math.round(fast.duration_min)} min · {(fast.distance_m / 1000).toFixed(1)} km</p>
			{:else if result.delta.distance_m === 0 && shady.shade_pct === fast.shade_pct}
				<p class="headline">The fastest way is already the shadiest</p>
				<p class="detail">
					{Math.round(fast.duration_min)} min · <strong>{Math.round(fast.shade_pct)}%</strong> in shade
				</p>
			{:else}
				<p class="headline">
					<span class="swatch shady"></span>
					{minutes(result.delta.duration_min)},
					<strong>{Math.round(shady.shade_pct)}%</strong> shade vs {Math.round(fast.shade_pct)}%
				</p>
				<p class="detail">
					<span class="swatch fast"></span>
					Fastest {Math.round(fast.duration_min)} min · shady {Math.round(shady.duration_min)} min
					({(shady.distance_m / 1000).toFixed(1)} km)
				</p>
			{/if}
			{#if w && !w.is_raining && result.sun_up && w.sun_strength < 0.5}
				<p class="detail">{w.summary} ({Math.round(w.cloud_cover_pct)}% cloud) - shade counts for less today</p>
			{/if}
			{#if result.sunny_stretches.length && result.sun_up && !w?.is_raining}
				<p class="detail"><span class="swatch sun"></span>Long sunny stretches</p>
			{/if}
		</div>
	{:else}
		<p class="hint">Finding routes…</p>
	{/if}

	<div class="row" class:off={raining}>
		<label for="shade-pref">Shade <span class="pref">{label}</span></label>
		<input
			id="shade-pref"
			type="range"
			min="0"
			max="1"
			step="0.25"
			bind:value={shade}
			disabled={raining}
			aria-valuetext={label}
		/>
		{#if to || (from && !startIsMe)}
			<button type="button" onclick={onclear}>Clear</button>
		{/if}
	</div>
	{#if startIsMe}
		<button type="button" class="link" onclick={onusepin}>Start somewhere else instead</button>
	{:else if canUseMe}
		<button type="button" class="link" onclick={onuseme}>Start from my location</button>
	{/if}
</section>

<style>
	.panel {
		position: absolute;
		left: 50%;
		top: max(12px, env(safe-area-inset-top));
		transform: translateX(-50%);
		width: min(480px, calc(100% - 24px));
		box-sizing: border-box;
		padding: 10px 14px;
		display: grid;
		gap: 8px;
		background: var(--panel-bg);
		color: var(--panel-fg);
		border-radius: 12px;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.18);
		font: 14px/1.35 system-ui, sans-serif;
	}
	p {
		margin: 0;
	}
	.hint {
		color: var(--panel-muted);
	}
	.error {
		color: var(--error);
	}
	.card {
		display: grid;
		gap: 2px;
		transition: opacity 0.15s;
	}
	.card.stale {
		opacity: 0.5;
	}
	.headline {
		font-size: 16px;
		font-weight: 600;
	}
	.detail {
		color: var(--panel-muted);
	}
	.swatch {
		display: inline-block;
		width: 14px;
		height: 4px;
		margin-right: 4px;
		vertical-align: middle;
		border-radius: 2px;
	}
	.swatch.shady {
		background: var(--route-shady);
		height: 6px;
	}
	.swatch.sun {
		background: var(--route-sun);
		height: 6px;
	}
	.arrow-glyph {
		color: var(--me);
	}
	button.link {
		justify-self: start;
		padding: 0;
		border: none;
		color: var(--me);
		text-decoration: underline;
		font-size: 13px;
	}
	.swatch.fast {
		background: repeating-linear-gradient(90deg, var(--route-fast) 0 4px, transparent 4px 7px);
		outline: 1px solid rgb(255 255 255 / 0.7);
	}
	.row {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	label {
		white-space: nowrap;
		color: var(--panel-muted);
	}
	.pref {
		display: inline-block;
		min-width: 5.5em;
		color: var(--panel-fg);
		font-weight: 600;
	}
	input[type='range'] {
		flex: 1;
		min-width: 0;
		margin: 0;
		accent-color: var(--route-shady);
	}
	.off label,
	.off .pref,
	.off input[type='range'] {
		opacity: 0.45;
		filter: grayscale(1);
	}
	.off input[type='range'] {
		cursor: not-allowed;
	}
	button {
		font: inherit;
		padding: 4px 10px;
		border: 1px solid var(--panel-border);
		border-radius: 6px;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}
</style>

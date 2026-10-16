<script lang="ts">
	import type { Weather } from '$lib/api';

	let { weather = null }: { weather?: Weather | null } = $props();

	// Grey tint: none under clear-ish skies, building to full under overcast;
	// rain always gets the full tint.
	const TINT_FROM_CLOUD_PCT = 40;
	const MAX_TINT = 0.3;
	// Rain heavy enough to draw at full density, mm in the hour.
	const HEAVY_RAIN_MM = 4;
	// Drops per square pixel at full density.
	const DROPS_PER_PX = 1 / 1500;

	let raining = $derived(weather?.is_raining ?? false);
	let tint = $derived.by(() => {
		if (!weather) return 0;
		if (raining) return MAX_TINT;
		const over = (weather.cloud_cover_pct - TINT_FROM_CLOUD_PCT) / (100 - TINT_FROM_CLOUD_PCT);
		return MAX_TINT * Math.max(0, Math.min(1, over));
	});
	// Drizzle and forecast-only rain still show a few drops.
	let density = $derived(
		raining ? Math.max(0.25, Math.min(1, (weather?.precipitation_mm ?? 0) / HEAVY_RAIN_MM)) : 0
	);

	let canvas = $state<HTMLCanvasElement>();

	interface Drop {
		x: number;
		y: number;
		speed: number; // px per second
		length: number;
	}

	// Falling streaks, slanted a little as if blown by the wind. With reduced
	// motion they're drawn once and stay still.
	$effect(() => {
		if (!canvas || density === 0) return;
		const cv = canvas;
		const ctx = cv.getContext('2d');
		if (!ctx) return;
		const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
		const SLANT = 0.18; // horizontal px per vertical px
		let width = 0;
		let height = 0;
		let drops: Drop[] = [];

		const spawn = (anywhere: boolean): Drop => ({
			x: Math.random() * (width + height * SLANT),
			y: anywhere ? Math.random() * height : -20 - Math.random() * 40,
			speed: 700 + Math.random() * 500,
			length: 10 + Math.random() * 14
		});

		const resize = () => {
			const dpr = window.devicePixelRatio || 1;
			width = cv.clientWidth;
			height = cv.clientHeight;
			cv.width = Math.round(width * dpr);
			cv.height = Math.round(height * dpr);
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			const count = Math.round(width * height * DROPS_PER_PX * density);
			drops = Array.from({ length: count }, () => spawn(true));
			if (still) draw();
		};

		const draw = () => {
			ctx.clearRect(0, 0, width, height);
			ctx.strokeStyle = 'rgb(220 230 245 / 0.55)';
			ctx.lineWidth = 1.2;
			ctx.lineCap = 'round';
			ctx.beginPath();
			for (const d of drops) {
				ctx.moveTo(d.x, d.y);
				ctx.lineTo(d.x - d.length * SLANT, d.y + d.length);
			}
			ctx.stroke();
		};

		let frame = 0;
		let last = performance.now();
		const tick = (now: number) => {
			// A long gap (tab in the background) shouldn't teleport the rain.
			const dt = Math.min(0.05, (now - last) / 1000);
			last = now;
			for (let i = 0; i < drops.length; i++) {
				const d = drops[i];
				d.y += d.speed * dt;
				d.x -= d.speed * dt * SLANT;
				if (d.y > height) drops[i] = spawn(false);
			}
			draw();
			frame = requestAnimationFrame(tick);
		};

		const observer = new ResizeObserver(resize);
		observer.observe(cv);
		resize();
		if (!still) frame = requestAnimationFrame(tick);
		return () => {
			cancelAnimationFrame(frame);
			observer.disconnect();
			ctx.clearRect(0, 0, width, height);
		};
	});
</script>

<div class="tint" style:opacity={tint} aria-hidden="true"></div>
{#if raining}
	<canvas bind:this={canvas} class="rain" aria-hidden="true"></canvas>
{/if}

<style>
	.tint,
	.rain {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}
	.tint {
		background: rgb(96 104 116);
		transition: opacity 0.6s ease;
	}
</style>

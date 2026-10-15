<script lang="ts" module>
	export type Basemap = 'satellite' | 'map';
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import {
		Map as MaplibreMap,
		Marker,
		type GeoJSONSource,
		type LightSpecification,
		type VectorTileSource
	} from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Feature, FeatureCollection } from 'geojson';
	import {
		TILE_ZOOM,
		buildingTilesUrl,
		shadeTilesUrl,
		type LngLat,
		type Moment,
		type RouteResult,
		type Sun
	} from '$lib/api';
	import type { Fix } from '$lib/geolocation';

	let {
		moment,
		sun,
		sunStrength = 1,
		loading = $bindable(false),
		from = null,
		to = null,
		route = null,
		me = null,
		heading = null,
		following = $bindable(false),
		basemap = $bindable('satellite'),
		locating = false,
		onpick,
		onmove,
		onlocate
	}: {
		moment: Moment;
		sun: Sun | null;
		/** 0..1 from the weather: how strongly shadows show. */
		sunStrength?: number;
		loading?: boolean;
		/** Start pin, when the start isn't the walker's own position. */
		from?: LngLat | null;
		to?: LngLat | null;
		route?: RouteResult | null;
		/** The walker's GPS position. */
		me?: Fix | null;
		/** Which way the walker faces, degrees clockwise from north. */
		heading?: number | null;
		/** Camera locked on the walker, looking the way they face. */
		following?: boolean;
		basemap?: Basemap;
		locating?: boolean;
		/** A tap on the map. */
		onpick?: (at: LngLat) => void;
		/** A start/finish marker was dragged somewhere new. */
		onmove?: (which: 'from' | 'to', at: LngLat) => void;
		/** The locate button: start GPS, or re-lock the camera on it. */
		onlocate?: () => void;
	} = $props();

	// Lipscani / Old Town. The whole city is available; this is just where we start.
	const START: [number, number] = [26.101, 44.431];
	// MapLibre's built-in default, used while the sun is down.
	const DEFAULT_LIGHT: LightSpecification = {
		anchor: 'viewport',
		position: [1.15, 210, 30],
		intensity: 0.5
	};
	const NO_ROUTES: FeatureCollection = { type: 'FeatureCollection', features: [] };
	const FOLLOW_ZOOM = 17.5;
	const FOLLOW_PITCH = 60;
	const ROTATE_STEP = 30;

	let container: HTMLDivElement;
	let map: MaplibreMap | undefined;
	let ready = $state(false);
	let zoom = $state(16.5);
	let bearing = $state(-17);
	let shadeUrl = ''; // the shade tile URL the map currently uses

	onMount(() => {
		const m = new MaplibreMap({
			container,
			style: {
				version: 8,
				sources: {
					// Esri World Imagery: free to use with attribution; see README for
					// what production use needs.
					satellite: {
						type: 'raster',
						tiles: [
							'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
						],
						tileSize: 256,
						maxzoom: 19,
						attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics'
					},
					osm: {
						type: 'raster',
						tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
						tileSize: 256,
						maxzoom: 19,
						attribution: '&copy; OpenStreetMap contributors'
					}
				},
				layers: [
					{ id: 'satellite', type: 'raster', source: 'satellite', layout: { visibility: 'none' } },
					{ id: 'osm', type: 'raster', source: 'osm', layout: { visibility: 'none' } }
				]
			},
			center: START,
			zoom,
			pitch: 60,
			bearing,
			maxPitch: 75,
			canvasContextAttributes: { antialias: true }
		});
		map = m;

		m.on('click', (e) => onpick?.([e.lngLat.lng, e.lngLat.lat]));
		m.on('zoom', () => (zoom = m.getZoom()));
		m.on('rotate', () => (bearing = m.getBearing()));
		// Panning or turning the map by hand lets go of the walker. (Camera
		// moves made in code carry no originalEvent.) Zooming keeps the lock.
		const release = (e: { originalEvent?: unknown }) => {
			if (e.originalEvent) following = false;
		};
		m.on('dragstart', release);
		m.on('rotatestart', release);

		// Shade is current once every tile for the moment has arrived or
		// failed. (Not 'idle': that also waits on basemap tiles, and never
		// comes if one of them fails.)
		const settle = (e: object) => {
			if ('sourceId' in e && e.sourceId === 'shade' && m.isSourceLoaded('shade')) loading = false;
		};
		m.on('sourcedata', settle);
		m.on('error', settle);

		// 'style.load' rather than 'load': our layers don't depend on basemap
		// tiles, and 'load' waits for all of them - on a slow connection it
		// holds back buildings and shade, and if tiles fail it may never fire.
		m.once('style.load', () => {
			// Shade first so it draws underneath the buildings.
			shadeUrl = shadeTilesUrl(moment);
			m.addSource('shade', {
				type: 'vector',
				tiles: [shadeUrl],
				minzoom: TILE_ZOOM,
				maxzoom: TILE_ZOOM
			});
			m.addLayer({
				id: 'shade',
				type: 'fill',
				source: 'shade',
				'source-layer': 'shade',
				paint: {
					'fill-color': '#0f1a33',
					'fill-opacity': shadeOpacity(sunStrength)
				}
			});

			m.addSource('buildings', {
				type: 'vector',
				tiles: [buildingTilesUrl],
				minzoom: TILE_ZOOM,
				maxzoom: TILE_ZOOM
			});
			m.addLayer({
				id: 'buildings-3d',
				type: 'fill-extrusion',
				source: 'buildings',
				'source-layer': 'buildings',
				paint: {
					'fill-extrusion-color': [
						'match',
						['get', 'height_source'],
						'height', '#4f7cff',
						'levels', '#6fa8ff',
						'type_fallback', '#9fb8d9',
						'#c7d2e0' // default fallback height - least certain
					],
					'fill-extrusion-height': ['get', 'height_m'],
					'fill-extrusion-base': 0,
					'fill-extrusion-opacity': 0.8
				}
			});

			// Routes go on top. Fastest: thin dark dashes; shady: bold, cased;
			// the shady route's long sunny stretches in orange over it.
			m.addSource('routes', { type: 'geojson', data: NO_ROUTES });
			const style = getComputedStyle(container);
			const shady = style.getPropertyValue('--route-shady').trim() || '#0e8f7e';
			const fast = style.getPropertyValue('--route-fast').trim() || '#3d4656';
			const sunny = style.getPropertyValue('--route-sun').trim() || '#ff8c1a';
			const lineLayout = { 'line-cap': 'round', 'line-join': 'round' } as const;
			const kind = (k: string) => ['==', ['get', 'kind'], k] as ['==', ['get', string], string];
			m.addLayer({
				id: 'route-fastest-casing',
				type: 'line',
				source: 'routes',
				filter: kind('fastest'),
				layout: lineLayout,
				paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.8 }
			});
			m.addLayer({
				id: 'route-fastest',
				type: 'line',
				source: 'routes',
				filter: kind('fastest'),
				layout: lineLayout,
				paint: { 'line-color': fast, 'line-width': 3.5, 'line-dasharray': [2, 1.5] }
			});
			m.addLayer({
				id: 'route-shady-casing',
				type: 'line',
				source: 'routes',
				filter: kind('shady'),
				layout: lineLayout,
				paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': 0.9 }
			});
			m.addLayer({
				id: 'route-shady',
				type: 'line',
				source: 'routes',
				filter: kind('shady'),
				layout: lineLayout,
				paint: { 'line-color': shady, 'line-width': 6 }
			});
			m.addLayer({
				id: 'route-sun',
				type: 'line',
				source: 'routes',
				filter: kind('sun'),
				layout: lineLayout,
				paint: { 'line-color': sunny, 'line-width': 6 }
			});
			ready = true;
		});

		return () => m.remove();
	});

	/** Shadows fade under cloud: there's little contrast to see. */
	function shadeOpacity(strength: number): number {
		return 0.5 * (0.25 + 0.75 * Math.max(0, Math.min(1, strength)));
	}

	$effect(() => {
		if (!ready || !map) return;
		map.setLayoutProperty('satellite', 'visibility', basemap === 'satellite' ? 'visible' : 'none');
		map.setLayoutProperty('osm', 'visibility', basemap === 'map' ? 'visible' : 'none');
	});

	$effect(() => {
		if (ready && map) map.setPaintProperty('shade', 'fill-opacity', shadeOpacity(sunStrength));
	});

	// A new moment means new shade tiles; MapLibre keeps showing the old ones
	// until the new ones arrive.
	$effect(() => {
		const url = shadeTilesUrl(moment);
		if (!ready || !map || url === shadeUrl) return;
		shadeUrl = url;
		(map.getSource('shade') as VectorTileSource).setTiles([url]);
		loading = true;
	});

	$effect(() => {
		if (!ready || !map) return;
		const features: Feature[] = route
			? [
					route.fastest,
					route.shady,
					...route.sunny_stretches.map(
						(s): Feature => ({ type: 'Feature', geometry: s.geometry, properties: { kind: 'sun' } })
					)
				]
			: [];
		(map.getSource('routes') as GeoJSONSource).setData({ type: 'FeatureCollection', features });
	});

	// Start and finish pins, draggable to adjust the trip.
	let markers: Partial<Record<'from' | 'to', Marker>> = {};
	function syncMarker(which: 'from' | 'to', at: LngLat | null, color: string) {
		if (!map) return;
		if (!at) {
			markers[which]?.remove();
			delete markers[which];
			return;
		}
		if (!markers[which]) {
			const marker = new Marker({ color, draggable: true }).setLngLat(at).addTo(map);
			marker.on('dragend', () => {
				const p = marker.getLngLat();
				onmove?.(which, [p.lng, p.lat]);
			});
			markers[which] = marker;
		} else {
			markers[which].setLngLat(at);
		}
	}
	$effect(() => {
		if (ready) syncMarker('from', from, '#2f9e44');
	});
	$effect(() => {
		if (ready) syncMarker('to', to, '#d6336c');
	});

	// The walker: a triangle pointing where they face, lying flat on the map
	// so it turns with it. A dot while the heading is unknown.
	let meMarker: Marker | undefined;
	let meEl: HTMLDivElement | undefined;
	$effect(() => {
		if (!ready || !map) return;
		if (!me) {
			meMarker?.remove();
			meMarker = undefined;
			return;
		}
		if (!meMarker) {
			meEl = document.createElement('div');
			meEl.className = 'me-marker';
			meEl.innerHTML = `<svg viewBox="0 0 40 40" width="40" height="40" aria-hidden="true">
				<circle class="me-dot" cx="20" cy="20" r="8" />
				<path class="me-arrow" d="M20 3 L33 34 L20 27 L7 34 Z" />
			</svg>`;
			meEl.setAttribute('role', 'img');
			meEl.setAttribute('aria-label', 'Your location');
			meMarker = new Marker({ element: meEl, rotationAlignment: 'map', pitchAlignment: 'map' })
				.setLngLat(me.lngLat)
				.addTo(map);
		}
		meMarker.setLngLat(me.lngLat);
		meMarker.setRotation(heading ?? 0);
		meEl?.classList.toggle('has-heading', heading !== null);
	});

	// Follow mode: keep the walker in the lower part of the screen with the
	// camera behind them, looking the way they face.
	$effect(() => {
		if (!ready || !map || !following || !me) return;
		map.easeTo({
			center: me.lngLat,
			bearing: heading ?? map.getBearing(),
			pitch: FOLLOW_PITCH,
			zoom: Math.max(map.getZoom(), FOLLOW_ZOOM),
			offset: [0, container.clientHeight * 0.2],
			duration: 450
		});
	});

	function rotate(by: number) {
		following = false;
		map?.easeTo({ bearing: map.getBearing() + by, duration: 300 });
	}

	function northUp() {
		following = false;
		map?.easeTo({ bearing: 0, duration: 400 });
	}

	// Light the 3D buildings from where the sun is. MapLibre's polar angle is
	// measured from straight overhead.
	$effect(() => {
		if (!ready || !map) return;
		map.setLight(
			sun?.is_up
				? {
						anchor: 'map',
						position: [1.15, sun.azimuth_deg, 90 - sun.elevation_deg],
						intensity: 0.5
					}
				: DEFAULT_LIGHT
		);
	});
</script>

<div bind:this={container} class="map"></div>

<div class="controls">
	<button type="button" onclick={() => rotate(-ROTATE_STEP)} aria-label="Rotate left" title="Rotate left">
		<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4" /></svg>
	</button>
	<button type="button" onclick={northUp} aria-label="Point north up" title="North up">
		<svg viewBox="0 0 24 24" aria-hidden="true" style:transform="rotate({-bearing}deg)">
			<path class="needle-n" d="M12 3 L15.5 12 H8.5 Z" />
			<path class="needle-s" d="M12 21 L8.5 12 H15.5 Z" />
		</svg>
	</button>
	<button type="button" onclick={() => rotate(ROTATE_STEP)} aria-label="Rotate right" title="Rotate right">
		<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4" /></svg>
	</button>
	<button
		type="button"
		onclick={() => (basemap = basemap === 'satellite' ? 'map' : 'satellite')}
		aria-label={basemap === 'satellite' ? 'Show street map' : 'Show satellite'}
		title={basemap === 'satellite' ? 'Street map' : 'Satellite'}
	>
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M12 3 3 8l9 5 9-5-9-5Z M3 13l9 5 9-5 M3 17.5l9 5 9-5" />
		</svg>
	</button>
	<button
		type="button"
		class="locate"
		class:active={following}
		class:busy={locating}
		onclick={() => onlocate?.()}
		aria-label={following ? 'Following your position' : 'Follow my position'}
		aria-pressed={following}
		title="My location"
	>
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path class="locate-arrow" d="M12 3 L19 20 L12 16 L5 20 Z" />
		</svg>
	</button>
</div>

<!-- MapLibre zoom levels count 512 px tiles, the size vector tiles are drawn at,
	so zoom-15 tiles show from map zoom 15. -->
{#if zoom < TILE_ZOOM}
	<p class="hint">Zoom in to see buildings and shade</p>
{/if}

<style>
	.map {
		position: absolute;
		inset: 0;
	}
	.hint {
		position: absolute;
		bottom: 170px;
		left: 50%;
		transform: translateX(-50%);
		margin: 0;
		padding: 6px 12px;
		border-radius: 999px;
		background: rgb(31 38 51 / 0.85);
		color: #fff;
		font: 14px/1.3 system-ui, sans-serif;
		white-space: nowrap;
	}
	.controls {
		position: absolute;
		right: 12px;
		top: 50%;
		transform: translateY(-50%);
		display: grid;
		gap: 8px;
	}
	.controls button {
		width: 44px;
		height: 44px;
		display: grid;
		place-items: center;
		padding: 0;
		border: none;
		border-radius: 12px;
		background: var(--panel-bg);
		color: var(--panel-fg);
		box-shadow: 0 2px 10px rgb(0 0 0 / 0.2);
		cursor: pointer;
	}
	.controls svg {
		width: 22px;
		height: 22px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.needle-n {
		fill: #e03131;
		stroke: none;
	}
	.needle-s {
		fill: currentColor;
		stroke: none;
		opacity: 0.45;
	}
	.locate-arrow {
		fill: none;
	}
	.locate.active {
		background: var(--me);
		color: #fff;
	}
	.locate.active .locate-arrow {
		fill: currentColor;
	}
	.locate.busy svg {
		animation: pulse 1s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.35;
		}
	}
	:global(.me-marker) {
		width: 40px;
		height: 40px;
		pointer-events: none;
	}
	:global(.me-marker .me-arrow) {
		fill: var(--me);
		stroke: #fff;
		stroke-width: 2.5;
		stroke-linejoin: round;
		display: none;
	}
	:global(.me-marker .me-dot) {
		fill: var(--me);
		stroke: #fff;
		stroke-width: 3;
	}
	:global(.me-marker.has-heading .me-arrow) {
		display: inline;
	}
	:global(.me-marker.has-heading .me-dot) {
		display: none;
	}
</style>

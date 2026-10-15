<script lang="ts">
	import { onMount } from 'svelte';
	import {
		Map as MaplibreMap,
		NavigationControl,
		type LightSpecification,
		type VectorTileSource
	} from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { TILE_ZOOM, buildingTilesUrl, shadeTilesUrl, type Moment, type Sun } from '$lib/api';

	let {
		moment,
		sun,
		loading = $bindable(false)
	}: { moment: Moment; sun: Sun | null; loading?: boolean } = $props();

	// Lipscani / Old Town. The whole city is available; this is just where we start.
	const START: [number, number] = [26.101, 44.431];
	// MapLibre's built-in default, used while the sun is down.
	const DEFAULT_LIGHT: LightSpecification = {
		anchor: 'viewport',
		position: [1.15, 210, 30],
		intensity: 0.5
	};

	let container: HTMLDivElement;
	let map: MaplibreMap | undefined;
	let ready = $state(false);
	let zoom = $state(16.5);
	let shadeUrl = ''; // the shade tile URL the map currently uses

	onMount(() => {
		const m = new MaplibreMap({
			container,
			style: {
				version: 8,
				sources: {
					osm: {
						type: 'raster',
						tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
						tileSize: 256,
						attribution: '&copy; OpenStreetMap contributors'
					}
				},
				layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
			},
			center: START,
			zoom,
			pitch: 60,
			bearing: -17,
			canvasContextAttributes: { antialias: true }
		});
		map = m;

		m.addControl(new NavigationControl());
		m.on('zoom', () => (zoom = m.getZoom()));
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
					'fill-color': '#1e2a44',
					'fill-opacity': 0.45
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
					'fill-extrusion-opacity': 0.85
				}
			});
			ready = true;
		});

		return () => m.remove();
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
		top: 16px;
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
</style>

<script lang="ts">
	import { onMount } from 'svelte';
	import {
		Map as MaplibreMap,
		NavigationControl,
		type GeoJSONSource,
		type LightSpecification
	} from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { FeatureCollection } from 'geojson';
	import { fetchBuildings, type Shadows } from '$lib/api';

	let { shadows }: { shadows: Shadows | null } = $props();

	// Umbra bbox - central Bucharest (Lipscani / Old Town), kept in sync with
	// backend/pipeline/fetch_osm.py BBOX. Do not expand without updating both.
	const BBOX = { north: 44.434, south: 44.428, east: 26.106, west: 26.096 };
	const CENTER: [number, number] = [
		(BBOX.east + BBOX.west) / 2,
		(BBOX.north + BBOX.south) / 2
	];

	const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
	// MapLibre's built-in default, used while the sun is down.
	const DEFAULT_LIGHT: LightSpecification = {
		anchor: 'viewport',
		position: [1.15, 210, 30],
		intensity: 0.5
	};

	let container: HTMLDivElement;
	let map: MaplibreMap | undefined;
	let loaded = $state(false);

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
			center: CENTER,
			zoom: 16.5,
			pitch: 60,
			bearing: -17,
			canvasContextAttributes: { antialias: true }
		});
		map = m;

		m.addControl(new NavigationControl());

		// 'style.load' rather than 'load': our layers don't depend on basemap
		// tiles, and 'load' waits for all of them - on a slow connection it
		// holds back buildings and shade, and if tiles fail it may never fire.
		m.once('style.load', async () => {
			// Added before the buildings so it draws underneath them.
			m.addSource('shade', { type: 'geojson', data: EMPTY });
			m.addLayer({
				id: 'shade',
				type: 'fill',
				source: 'shade',
				paint: {
					'fill-color': '#1e2a44',
					'fill-opacity': 0.45
				}
			});
			loaded = true;

			m.addSource('buildings', { type: 'geojson', data: await fetchBuildings() });

			m.addLayer({
				id: 'buildings-3d',
				type: 'fill-extrusion',
				source: 'buildings',
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
		});

		return () => m.remove();
	});

	// Keep the shade layer, and the light on the extrusions, in step with the
	// sun. MapLibre's polar angle is measured from straight overhead.
	$effect(() => {
		if (!loaded || !map) return;
		(map.getSource('shade') as GeoJSONSource).setData(shadows ?? EMPTY);
		const sun = shadows?.sun;
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

<style>
	.map {
		position: absolute;
		inset: 0;
	}
</style>

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Map as MaplibreMap, NavigationControl } from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	// Umbra bbox - central Bucharest (Lipscani / Old Town), kept in sync with
	// backend/pipeline/fetch_osm.py BBOX. Do not expand without updating both.
	const BBOX = { north: 44.434, south: 44.428, east: 26.106, west: 26.096 };
	const CENTER: [number, number] = [
		(BBOX.east + BBOX.west) / 2,
		(BBOX.north + BBOX.south) / 2
	];

	const API_BASE = 'http://localhost:8000';

	let container: HTMLDivElement;
	let map: MaplibreMap;

	onMount(() => {
		map = new MaplibreMap({
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
			antialias: true
		});

		map.addControl(new NavigationControl());

		map.on('load', async () => {
			const res = await fetch(`${API_BASE}/buildings`);
			const buildings = await res.json();

			map.addSource('buildings', { type: 'geojson', data: buildings });

			map.addLayer({
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

		return () => map.remove();
	});

	onDestroy(() => {
		map?.remove();
	});
</script>

<div bind:this={container} class="map"></div>

<style>
	.map {
		position: absolute;
		inset: 0;
	}
</style>

<script lang="ts">
	import * as d3 from 'd3';
	import { base } from '$app/paths';
	import { formatDays } from '$lib/data';
	import { CITY_COORDS, type CityMapDatum } from '$lib/geo';
	import type { CityStats, RecentlyRented } from '$lib/types';

	interface Props {
		stats: readonly CityStats[];
		observations: readonly RecentlyRented[];
		selectedCity: string;
		selectedRoomType: string;
	}
	const { stats, observations, selectedCity, selectedRoomType }: Props = $props();

	const margin = { top: 10, right: 10, bottom: 10, left: 10 };

	let svgEl: SVGSVGElement;
	let resetZoom: (() => void) | null = $state(null);
	let wrapperEl: HTMLDivElement | null = $state(null);
	let containerWidth = $state(0);

	const mapHeight = $derived(
		containerWidth > 0 && containerWidth < 600
			? Math.max(360, Math.round(containerWidth * 0.9))
			: 520,
	);

	$effect(() => {
		if (!wrapperEl) return;
		const ro = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerWidth = entry.contentRect.width;
			}
		});
		ro.observe(wrapperEl);
		return () => ro.disconnect();
	});

	// module-level cached GeoJSON promise
	interface GeoFeature { type: string; properties: Record<string, unknown>; geometry: d3.GeoGeometryObjects }
	interface GeoFC { type: 'FeatureCollection'; features: GeoFeature[] }
	let geoPromise: Promise<GeoFC> | null = null;
	function loadGeo(): Promise<GeoFC> {
		if (!geoPromise) {
			geoPromise = fetch(`${base}/data/nl-provinces.json`).then(
				(r) => r.json() as Promise<GeoFC>,
			);
		}
		return geoPromise;
	}

	const cityData: CityMapDatum[] = $derived.by(() => {
		let perCity: Map<string, { median: number; count: number; mean: number }>;

		if (selectedRoomType) {
			perCity = new Map(
				stats
					.filter((s) => s.type_of_room === selectedRoomType)
					.map((s) => [s.city, { median: s.median_reg_days, count: s.count, mean: s.mean_reg_days }]),
			);
		} else {
			const rolled = d3.rollups(
				observations,
				(v) => ({
					median: d3.median(v, (d) => d.registration_time) ?? 0,
					count: v.length,
					mean: d3.mean(v, (d) => d.registration_time) ?? 0,
				}),
				(d) => d.city,
			);
			perCity = new Map(rolled.map(([city, vals]) => [city, vals]));
		}

		const result: CityMapDatum[] = [];
		for (const [city, vals] of perCity) {
			const coords = CITY_COORDS[city];
			if (!coords) continue;
			result.push({
				city,
				coords,
				medianDays: vals.median,
				count: vals.count,
				meanDays: vals.mean,
				highlighted: !selectedCity || city === selectedCity,
			});
		}
		return result;
	});

	interface CellDatum {
		city: string;
		coords: [number, number];
		cellPath: string;
		datum: CityMapDatum | null;
	}

	$effect(() => {
		if (!svgEl) return;
		const data = cityData;

		const containerW = containerWidth || svgEl.parentElement?.clientWidth || 600;
		const innerW = containerW - margin.left - margin.right;
		const innerH = mapHeight - margin.top - margin.bottom;

		const svg = d3
			.select(svgEl)
			.attr('width', containerW)
			.attr('height', mapHeight)
			.attr('viewBox', `0 0 ${containerW} ${mapHeight}`);

		svg.selectAll('*').remove();

		loadGeo().then((geo) => {
			const projection = d3.geoMercator().fitSize([innerW, innerH], geo as unknown as d3.GeoPermissibleObjects);
			const pathGen = d3.geoPath(projection);

			const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

			// Build data lookup from filtered cityData
			const dataMap = new Map(data.map((d) => [d.city, d]));

			// Color scale from cities that have data
			const medianExtent = d3.extent(data, (d) => d.medianDays) as [number, number];
			const colorScale = d3
				.scaleSequential(d3.interpolateYlOrRd)
				.domain(medianExtent[0] === undefined ? [0, 1] : medianExtent);

			// Voronoi from ALL 15 cities (stable tessellation regardless of filters)
			const allCityEntries = Object.entries(CITY_COORDS);
			const projected = allCityEntries.map(
				([, coords]) => projection(coords) as [number, number],
			);
			const delaunay = d3.Delaunay.from(projected);
			const voronoi = delaunay.voronoi([-200, -200, innerW + 200, innerH + 200]);

			const cellData: CellDatum[] = allCityEntries.map(([city, coords], i) => ({
				city,
				coords,
				cellPath: voronoi.renderCell(i),
				datum: dataMap.get(city) ?? null,
			}));

			// Sort: larger cells (no data / dimmed) first, smaller (highlighted) on top
			cellData.sort((a, b) => {
				const aHas = a.datum ? 1 : 0;
				const bHas = b.datum ? 1 : 0;
				if (aHas !== bHas) return aHas - bHas;
				const aHi = a.datum?.highlighted ? 1 : 0;
				const bHi = b.datum?.highlighted ? 1 : 0;
				return aHi - bHi;
			});

			// Tooltip — uses CSS vars directly so it stays theme-aware
			const tooltip = d3
				.select(document.body)
				.append('div')
				.style('pointer-events', 'none')
				.style('position', 'fixed')
				.style('z-index', '9999')
				.style('border-radius', '10px')
				.style('padding', '10px 14px')
				.style('font-size', '12px')
				.style('font-family', 'var(--font-sans)')
				.style('line-height', '1.5')
				.style('opacity', '0')
				.style('transition', 'opacity 0.12s ease')
				.style('box-shadow', 'var(--shadow-tooltip)')
				.style('background', 'var(--bg-card)')
				.style('border', '1px solid var(--border)')
				.style('color', 'var(--text-primary)');

			// Voronoi cells — use .style() with CSS vars for theme colors
			g.selectAll('path.cell')
				.data(cellData)
				.join('path')
				.attr('class', 'cell')
				.attr('d', (d) => d.cellPath)
				.style('fill', (d) => (d.datum ? colorScale(d.datum.medianDays) : 'var(--bg-card)'))
				.style('stroke', 'var(--border-light)')
				.attr('stroke-width', 0.4)
				.attr('opacity', (d) => {
					if (!d.datum) return 0.15;
					return d.datum.highlighted ? 0.85 : 0.2;
				})
				.style('cursor', (d) => (d.datum ? 'pointer' : 'default'))
				.on('mouseenter', function (event: MouseEvent, d: CellDatum) {
					if (!d.datum) return;
					d3.select(this)
						.attr('opacity', 1)
						.style('stroke', 'var(--text-primary)')
						.attr('stroke-width', 2);
					tooltip
						.html(
							`<strong>${d.datum.city}</strong><br/>` +
								`Median wait: <strong>${formatDays(Math.round(d.datum.medianDays))}</strong><br/>` +
								`Mean wait: ${formatDays(Math.round(d.datum.meanDays))}<br/>` +
								`Listings: ${String(d.datum.count)}`,
						)
						.style('opacity', '1')
						.style('left', `${String(event.clientX + 14)}px`)
						.style('top', `${String(event.clientY - 60)}px`);
				})
				.on('mousemove', (event: MouseEvent, d: CellDatum) => {
					if (!d.datum) return;
					tooltip
						.style('left', `${String(event.clientX + 14)}px`)
						.style('top', `${String(event.clientY - 60)}px`);
				})
				.on('mouseleave', function (_event: MouseEvent, d: CellDatum) {
					if (!d.datum) return;
					d3.select(this)
						.attr('opacity', d.datum.highlighted ? 0.85 : 0.2)
						.style('stroke', 'var(--border-light)')
						.attr('stroke-width', 0.4);
					tooltip.style('opacity', '0');
				});

			// Ocean mask: large rect with NL outline cut out (evenodd).
			// Uses .style() so fill tracks theme changes.
			const pad = 2000;
			const oceanRect = `M${-pad},${-pad}H${innerW + pad}V${innerH + pad}H${-pad}Z`;
			const nlHoles = geo.features.map((f) => pathGen(f as never) ?? '').join(' ');
			g.append('path')
				.attr('d', `${oceanRect} ${nlHoles}`)
				.style('fill', 'var(--bg-card)')
				.attr('fill-rule', 'evenodd')
				.style('pointer-events', 'none');

			// Province borders on top
			g.selectAll('path.province')
				.data(geo.features)
				.join('path')
				.attr('class', 'province')
				.attr('d', pathGen as never)
				.attr('fill', 'none')
				.style('stroke', 'var(--border-light)')
				.attr('stroke-width', 1)
				.style('pointer-events', 'none');

			// City location dots
			g.selectAll('circle.city-pin')
				.data(allCityEntries)
				.join('circle')
				.attr('class', 'city-pin')
				.attr('cx', ([, coords]) => projection(coords)?.[0] ?? 0)
				.attr('cy', ([, coords]) => projection(coords)?.[1] ?? 0)
				.attr('r', 3)
				.style('fill', 'var(--text-primary)')
				.style('stroke', 'var(--bg-card)')
				.attr('stroke-width', 1)
				.attr('opacity', 0.7)
				.style('pointer-events', 'none');

			// Selected city highlight border
			if (selectedCity) {
				const sel = cellData.find((d) => d.city === selectedCity && d.datum);
				if (sel) {
					g.append('path')
						.attr('d', sel.cellPath)
						.attr('fill', 'none')
						.style('stroke', 'var(--text-primary)')
						.attr('stroke-width', 2.5)
						.style('pointer-events', 'none');
				}
			}

			// City labels for selected city
			if (selectedCity) {
				const sel = dataMap.get(selectedCity);
				if (sel) {
					const pt = projection(sel.coords);
					if (pt) {
						g.append('text')
							.attr('x', pt[0])
							.attr('y', pt[1] - 8)
							.attr('text-anchor', 'middle')
							.style('fill', 'var(--text-primary)')
							.style('font-size', '11px')
							.style('font-family', 'var(--font-sans)')
							.style('font-weight', '600')
							.style('pointer-events', 'none')
							.text(sel.city);
					}
				}
			}

			// Legend — color gradient only
			const legendG = svg
				.append('g')
				.attr('transform', `translate(${margin.left + 12},${mapHeight - 50})`);

			const defs = svg.append('defs');
			const gradId = 'waittime-grad';
			const grad = defs
				.append('linearGradient')
				.attr('id', gradId)
				.attr('x1', '0%')
				.attr('x2', '100%');
			const nStops = 10;
			for (let i = 0; i <= nStops; i++) {
				const t = i / nStops;
				grad.append('stop')
					.attr('offset', `${String(t * 100)}%`)
					.attr('stop-color', d3.interpolateYlOrRd(t));
			}

			legendG
				.append('rect')
				.attr('width', 140)
				.attr('height', 10)
				.attr('rx', 3)
				.attr('fill', `url(#${gradId})`);

			legendG
				.append('text')
				.attr('x', 0)
				.attr('y', -4)
				.style('fill', 'var(--text-muted)')
				.style('font-size', '10px')
				.style('font-family', 'var(--font-sans)')
				.text('Median wait time');

			legendG
				.append('text')
				.attr('x', 0)
				.attr('y', 22)
				.style('fill', 'var(--text-muted)')
				.style('font-size', '9px')
				.style('font-family', 'var(--font-sans)')
				.text(formatDays(Math.round(medianExtent[0] ?? 0)));

			legendG
				.append('text')
				.attr('x', 140)
				.attr('y', 22)
				.attr('text-anchor', 'end')
				.style('fill', 'var(--text-muted)')
				.style('font-size', '9px')
				.style('font-family', 'var(--font-sans)')
				.text(formatDays(Math.round(medianExtent[1] ?? 0)));

			// Zoom
			const zoom = d3
				.zoom<SVGSVGElement, unknown>()
				.scaleExtent([1, 8])
				.extent([
					[0, 0],
					[containerW, mapHeight],
				])
				.filter((event: Event) => {
					if (event.type === 'wheel') return true;
					if (event.type === 'mousedown' || event.type === 'touchstart') return true;
					return false;
				})
				.on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
					g.attr('transform', event.transform.toString());
				});

			svg.call(zoom);
			svg.on('dblclick.zoom', null);

			resetZoom = () => {
				svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
			};

			return () => {
				tooltip.remove();
			};
		});

		// eslint-disable-next-line unicorn/consistent-function-scoping
		return () => {
			resetZoom = null;
		};
	});
</script>

<div bind:this={wrapperEl}>
	<h2 style="margin-bottom: 8px; font-size: 18px; font-weight: 600; color: var(--text-primary);">
		Wait Time Map
	</h2>
	<p style="margin-bottom: 16px; font-size: 14px; color: var(--text-muted); line-height: 1.6;">
		City wait times by region. Color intensity = median wait time. Scroll to zoom, drag to pan.
	</p>

	<div
		style="position: relative; width: 100%; min-height: {mapHeight}px; border-radius: var(--radius-lg); overflow: hidden; border: 1px solid var(--border-light); background: var(--bg-card);"
	>
		<svg bind:this={svgEl} style="width: 100%; display: block; touch-action: pan-y;"></svg>
		{#if resetZoom}
			<button
				onclick={resetZoom}
				title="Reset zoom"
				style="
					position: absolute; top: 10px; right: 10px;
					display: flex; align-items: center; justify-content: center;
					height: 30px; padding: 0 10px; gap: 5px;
					font-size: 12px; font-family: var(--font-sans); font-weight: 500;
					border-radius: var(--radius-sm);
					border: 1px solid var(--border);
					background: var(--bg-card);
					color: var(--text-muted);
					box-shadow: var(--shadow-sm);
					cursor: pointer;
					transition: all 0.15s;
				"
				onmouseenter={(e) => {
					(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)';
					(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--accent)';
				}}
				onmouseleave={(e) => {
					(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
					(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)';
				}}
			>
				<svg
					width="13"
					height="13"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2.5"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
					<path d="M3 3v5h5" />
				</svg>
				Reset
			</button>
		{/if}
	</div>
</div>

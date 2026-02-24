<script lang="ts">
	import * as d3 from 'd3';
	import type { Prediction, RecentlyRented } from '$lib/types';
	import { formatDays } from '$lib/data';

	interface Props {
		predictions: readonly Prediction[];
		observations: readonly RecentlyRented[];
	}

	const { predictions, observations }: Props = $props();

	const LS_KEY = 'roomnl_reg_date';

	function loadFromStorage(): string {
		if (typeof localStorage === 'undefined') return '2022-01-01';
		return localStorage.getItem(LS_KEY) ?? '2022-01-01';
	}

	let registrationDate = $state(loadFromStorage());
	let daysInput = $state('');
	let savedIndicator = $state(false);
	let savedTimer: ReturnType<typeof setTimeout> | null = null;
	let svgEl: SVGSVGElement | null = $state(null);
	let resetZoom: (() => void) | null = $state(null);
	let isMobile = $state(false);
	let showChart = $state(false);
	let wrapperEl: HTMLDivElement | null = $state(null);
	let containerWidth = $state(0);

	$effect(() => {
		const mq = globalThis.matchMedia('(max-width: 768px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => { isMobile = e.matches; };
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

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

	const margin = { top: 20, right: 65, bottom: 35, left: 60 };
	const chartHeight = 460;

	function normalCdf(z: number): number {
		const sign = z < 0 ? -1 : 1;
		const x = Math.abs(z) / Math.SQRT2;
		const t = 1 / (1 + 0.327_591_1 * x);
		const poly =
			t *
			(0.254_829_592 +
				t * (-0.284_496_736 + t * (1.421_413_741 + t * (-1.453_152_027 + t * 1.061_405_429))));
		const erf = 1 - poly * Math.exp(-x * x);
		return 0.5 * (1 + sign * erf);
	}

	function saveToStorage(date: string) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(LS_KEY, date);
		}
		if (savedTimer) clearTimeout(savedTimer);
		savedIndicator = true;
		savedTimer = setTimeout(() => { savedIndicator = false; }, 2000);
	}

	function handleDaysInput() {
		const days = Number.parseInt(daysInput, 10);
		if (Number.isNaN(days) || days < 0) return;
		const regDate = new Date(Date.now() - days * 86_400_000);
		registrationDate = regDate.toISOString().slice(0, 10);
		saveToStorage(registrationDate);
	}

	function handleDateInput() {
		const ms = new Date(registrationDate).getTime();
		const days = Math.max(0, Math.round((Date.now() - ms) / 86_400_000));
		daysInput = String(days);
		saveToStorage(registrationDate);
	}

	$effect(() => {
		const ms = new Date(registrationDate).getTime();
		daysInput = String(Math.max(0, Math.round((Date.now() - ms) / 86_400_000)));
	});

	const cities = $derived([...new Set(observations.map((o) => o.city))].toSorted());
	const colorScale = $derived(d3.scaleOrdinal(d3.schemeTableau10).domain(cities));

	const regDateMs = $derived(new Date(registrationDate).getTime());

	const myRegDaysToday = $derived(
		Math.max(0, Math.round((Date.now() - regDateMs) / 86_400_000)),
	);

	const todayProb = $derived.by(() => {
		const today = new Date();
		let closest: (typeof predictions)[number] | null = null;
		for (const p of predictions) {
			const d = new Date(p.contract_date);
			if (!closest || Math.abs(d.getTime() - today.getTime()) < Math.abs(new Date(closest.contract_date).getTime() - today.getTime())) {
				closest = p;
			}
		}
		if (!closest) return 0;
		const sigma = Math.max((closest.pred_hi - closest.pred_lo) / (2 * 1.96), 1e-9);
		const z = (myRegDaysToday - closest.pred_mean) / sigma;
		return Math.round(normalCdf(z) * 1000) / 10;
	});

	function probColor(prob: number): string {
		if (prob >= 80) return '#34d399';
		if (prob >= 50) return '#fbbf24';
		if (prob >= 20) return '#fb923c';
		return '#f87171';
	}

	$effect(() => {
		if (!svgEl) return;
		const currentRegDateMs = regDateMs;

		const cs = getComputedStyle(document.documentElement);
		const themeGrid = cs.getPropertyValue('--chart-grid').trim() || '#27272a';
		const themeAxisText = cs.getPropertyValue('--chart-axis-text').trim() || '#a1a1aa';
		const themeAxisLine = cs.getPropertyValue('--chart-axis-line').trim() || '#3f3f46';
		const themeDotStroke = cs.getPropertyValue('--chart-dot-stroke').trim() || '#18181b';
		const themeBgCard = cs.getPropertyValue('--bg-card').trim() || '#1c1c1f';
		const themeBorder = cs.getPropertyValue('--border').trim() || '#2c2c32';
		const themeTextPrimary = cs.getPropertyValue('--text-primary').trim() || '#ececf1';

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();

		const parentWidth = containerWidth || svgEl.parentElement?.clientWidth || 900;
		const width = parentWidth;
		const innerW = width - margin.left - margin.right;
		const innerH = chartHeight - margin.top - margin.bottom;

		svg.attr('width', width).attr('height', chartHeight).attr('viewBox', `0 0 ${String(width)} ${String(chartHeight)}`);

		const obsData = observations.map((o) => ({
			date: new Date(o.contract_date),
			regTime: o.registration_time,
			city: o.city,
		}));

		const predData = predictions.map((p) => ({
			date: new Date(p.contract_date),
			mean: p.pred_mean,
			lo: p.pred_lo,
			hi: p.pred_hi,
		}));

		const regDate = new Date(currentRegDateMs);

		const myRegLine = predData
			.map((p) => ({
				date: p.date,
				myTime: (p.date.getTime() - regDate.getTime()) / 86_400_000,
			}))
			.filter((d) => d.myTime >= 0);

		const probLine = predData.map((p) => {
			const myTime = (p.date.getTime() - regDate.getTime()) / 86_400_000;
			if (myTime < 0) return { date: p.date, prob: 0 };
			const sigma = Math.max((p.hi - p.lo) / (2 * 1.96), 1e-9);
			return { date: p.date, prob: normalCdf((myTime - p.mean) / sigma) * 100 };
		});

		const allDates = [...obsData.map((d) => d.date), ...predData.map((d) => d.date)];
		const xExtent = d3.extent(allDates) as [Date, Date];

		const xBase = d3.scaleTime().domain(xExtent).range([0, innerW]);

		const yMax =
			Math.max(
				d3.max(obsData, (d) => d.regTime) ?? 0,
				d3.max(predData, (d) => d.hi) ?? 0,
				d3.max(myRegLine, (d) => d.myTime) ?? 0,
			) * 1.1;
		const yL = d3.scaleLinear().domain([0, yMax]).range([innerH, 0]).nice();
		const yR = d3.scaleLinear().domain([0, 100]).range([innerH, 0]);

		const color = colorScale;

		svg.append('defs').append('clipPath').attr('id', 'clip').append('rect').attr('width', innerW).attr('height', innerH);

		const g = svg.append('g').attr('transform', `translate(${String(margin.left)},${String(margin.top)})`);
		const chart = g.append('g').attr('clip-path', 'url(#clip)');

		// grid
		g.append('g')
			.selectAll('line')
			.data(yL.ticks(8))
			.join('line')
			.attr('x1', 0)
			.attr('x2', innerW)
			.attr('y1', (d) => yL(d))
			.attr('y2', (d) => yL(d))
			.attr('stroke', themeGrid)
			.attr('stroke-dasharray', '2 2');

		// tooltip (appended to body so it's never clipped by overflow:hidden)
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
			.style('background', themeBgCard)
			.style('border', `1px solid ${themeBorder}`)
			.style('color', themeTextPrimary);

		// weekly medians per city for trend lines
		const weeklyMedians = d3.rollups(
			obsData,
			(v) => d3.median(v, (d) => d.regTime) ?? 0,
			(d) => d.city,
			(d) => d3.timeWeek.floor(d.date).getTime(),
		);
		const cityTrends = weeklyMedians.map(([city, weeks]) => ({
			city,
			points: weeks
				.map(([weekMs, median]) => ({ date: new Date(weekMs), median }))
				.toSorted((a, b) => a.date.getTime() - b.date.getTime()),
		}));

		function draw(x: d3.ScaleTime<number, number>) {
			chart.selectAll('.ci').remove();
			chart.selectAll('.gp-mean').remove();
			chart.selectAll('.my-reg').remove();
			chart.selectAll('.prob-line').remove();
			chart.selectAll('.city-trend').remove();
			chart.selectAll('.obs-dot').remove();
			chart.selectAll('.today-line').remove();
			chart.selectAll('.half-line').remove();

			if (predData.length > 0) {
				const lineGen = d3
					.line<(typeof predData)[number]>()
					.x((d) => x(d.date))
					.y((d) => yL(d.mean))
					.curve(d3.curveBasis);

				chart
					.append('path')
					.attr('class', 'ci')
					.datum(predData)
					.attr('fill', '#6366f1')
					.attr('fill-opacity', 0.18)
					.attr(
						'd',
						d3
							.area<(typeof predData)[number]>()
							.x((d) => x(d.date))
							.y0((d) => yL(d.lo))
							.y1((d) => yL(d.hi))
							.curve(d3.curveBasis),
					);

				chart
					.append('path')
					.attr('class', 'gp-mean')
					.datum(predData)
					.attr('fill', 'none')
					.attr('stroke', '#818cf8')
					.attr('stroke-width', 2)
					.attr('stroke-dasharray', '6 3')
					.attr('d', lineGen);

				// invisible wide hit area for GP mean tooltip
				const bisect = d3.bisector<(typeof predData)[number], Date>((d) => d.date).left;
				chart
					.append('path')
					.attr('class', 'gp-mean')
					.datum(predData)
					.attr('fill', 'none')
					.attr('stroke', 'transparent')
					.attr('stroke-width', 14)
					.attr('d', lineGen)
					.style('cursor', 'crosshair')
					.on('mousemove', (event: MouseEvent) => {
						const [mx] = d3.pointer(event);
						const dateAtMouse = x.invert(mx);
						const idx = Math.min(
							bisect(predData, dateAtMouse),
							predData.length - 1,
						);
						const p = predData[idx] as (typeof predData)[number] | undefined;
						if (!p) return;
						tooltip
							.style('opacity', '1')
							.html(
								`<strong style="font-size:13px;">GP Prediction</strong><br/>` +
									`<span style="color:${themeAxisText};">${p.date.toLocaleDateString('en-NL')}</span><br/>` +
									`Mean: <strong>${p.mean.toFixed(2)}d</strong> (${formatDays(Math.round(p.mean))})<br/>` +
									`95% CI: ${p.lo.toFixed(2)}d – ${p.hi.toFixed(2)}d`,
							);
						tooltip
							.style('left', `${String(event.clientX + 14)}px`)
							.style('top', `${String(event.clientY - 60)}px`);
					})
					.on('mouseleave', () => {
						tooltip.style('opacity', '0');
					});
			}

			if (myRegLine.length > 0) {
				chart
					.append('path')
					.attr('class', 'my-reg')
					.datum(myRegLine)
					.attr('fill', 'none')
					.attr('stroke', '#ef4444')
					.attr('stroke-width', 2)
					.attr('stroke-dasharray', '8 4')
					.attr(
						'd',
						d3
							.line<(typeof myRegLine)[number]>()
							.x((d) => x(d.date))
							.y((d) => yL(d.myTime)),
					);
			}

			if (probLine.length > 0) {
				const probLineGen = d3
					.line<(typeof probLine)[number]>()
					.x((d) => x(d.date))
					.y((d) => yR(d.prob))
					.curve(d3.curveBasis);

				chart
					.append('path')
					.attr('class', 'prob-line')
					.datum(probLine)
					.attr('fill', 'none')
					.attr('stroke', '#ef4444')
					.attr('stroke-width', 1.8)
					.attr('d', probLineGen);

				// invisible wide hit area for prob line tooltip
				const bisectProb = d3.bisector<(typeof probLine)[number], Date>((d) => d.date).left;
				chart
					.append('path')
					.attr('class', 'prob-line')
					.datum(probLine)
					.attr('fill', 'none')
					.attr('stroke', 'transparent')
					.attr('stroke-width', 14)
					.attr('d', probLineGen)
					.style('cursor', 'crosshair')
					.on('mousemove', (event: MouseEvent) => {
						const [mx] = d3.pointer(event);
						const dateAtMouse = x.invert(mx);
						const idx = Math.min(bisectProb(probLine, dateAtMouse), probLine.length - 1);
						const p = probLine[idx] as (typeof probLine)[number] | undefined;
						if (!p) return;
						tooltip
							.style('opacity', '1')
							.html(
								`<strong style="font-size:13px;">Probability</strong><br/>` +
									`<span style="color:${themeAxisText};">${p.date.toLocaleDateString('en-NL')}</span><br/>` +
									`P(&#8805; required): <strong style="color:#ef4444;">${p.prob.toFixed(1)}%</strong>`,
							);
						tooltip
							.style('left', `${String(event.clientX + 14)}px`)
							.style('top', `${String(event.clientY - 60)}px`);
					})
					.on('mouseleave', () => {
						tooltip.style('opacity', '0');
					});
			}

			for (const trend of cityTrends) {
				chart
					.append('path')
					.attr('class', 'city-trend')
					.datum(trend.points)
					.attr('fill', 'none')
					.attr('stroke', color(trend.city))
					.attr('stroke-width', 1.2)
					.attr('stroke-opacity', 0.5)
					.attr(
						'd',
						d3
							.line<(typeof trend.points)[number]>()
							.x((d) => x(d.date))
							.y((d) => yL(d.median))
							.curve(d3.curveBasis),
					);
			}

			chart
				.selectAll('.obs-dot')
				.data(obsData)
				.join('circle')
				.attr('class', 'obs-dot')
				.attr('cx', (d) => x(d.date))
				.attr('cy', (d) => yL(d.regTime))
				.attr('r', 2.5)
				.attr('fill', (d) => color(d.city))
				.attr('fill-opacity', 0.35)
				.attr('stroke', themeDotStroke)
				.attr('stroke-width', 0.4)
				.on('mouseenter', (event: MouseEvent, d) => {
					tooltip
						.style('opacity', '1')
						.html(
							`<strong style="font-size:13px;">${d.city}</strong><br/>` +
								`<span style="color:${themeAxisText};">${d.date.toLocaleDateString('en-NL')}</span><br/>` +
								`Reg. time: <strong>${formatDays(d.regTime)}</strong>`,
						);
					d3.select(event.currentTarget as SVGCircleElement)
						.attr('r', 5)
						.attr('fill-opacity', 1)
						.attr('stroke-width', 1.5);
				})
				.on('mousemove', (event: MouseEvent) => {
					tooltip
						.style('left', `${String(event.clientX + 14)}px`)
						.style('top', `${String(event.clientY - 60)}px`);
				})
				.on('mouseleave', (event: MouseEvent) => {
					tooltip.style('opacity', '0');
					d3.select(event.currentTarget as SVGCircleElement)
						.attr('r', 2.5)
						.attr('fill-opacity', 0.35)
						.attr('stroke-width', 0.4);
				});

			const today = new Date();
			if (today >= xExtent[0] && today <= xExtent[1]) {
				chart
					.append('line')
					.attr('class', 'today-line')
					.attr('x1', x(today))
					.attr('x2', x(today))
					.attr('y1', 0)
					.attr('y2', innerH)
					.attr('stroke', '#fbbf24')
					.attr('stroke-width', 1.5)
					.attr('stroke-dasharray', '4 4');
			}

			chart
				.append('line')
				.attr('class', 'half-line')
				.attr('x1', 0)
				.attr('x2', innerW)
				.attr('y1', yR(50))
				.attr('y2', yR(50))
				.attr('stroke', '#52525b')
				.attr('stroke-dasharray', '3 3');
		}

		// axes
		const xAxisG = g
			.append('g')
			.attr('transform', `translate(0,${String(innerH)})`)
			.call(d3.axisBottom(xBase).ticks(d3.timeMonth.every(3)));
		xAxisG.selectAll('text').attr('fill', themeAxisText).style('font-size', '11px');
		xAxisG.selectAll('line,path').attr('stroke', themeAxisLine);

		const yAxisLG = g.append('g').call(d3.axisLeft(yL).ticks(8));
		yAxisLG.selectAll('text').attr('fill', themeAxisText).style('font-size', '11px');
		yAxisLG.selectAll('line,path').attr('stroke', themeAxisLine);

		const yAxisRG = g
			.append('g')
			.attr('transform', `translate(${String(innerW)},0)`)
			.call(
				d3
					.axisRight(yR)
					.ticks(5)
					.tickFormat((d) => `${String(d)}%`),
			);
		yAxisRG.selectAll('text').attr('fill', '#ef4444').style('font-size', '11px');
		yAxisRG.selectAll('line,path').attr('stroke', themeAxisLine);

		// axis labels
		g.append('text')
			.attr('transform', 'rotate(-90)')
			.attr('y', -45)
			.attr('x', -innerH / 2)
			.attr('text-anchor', 'middle')
			.attr('fill', themeAxisText)
			.style('font-size', '12px')
			.style('font-family', 'var(--font-sans)')
			.text('Registration Time (days)');

		g.append('text')
			.attr('transform', `translate(${String(innerW + 50)},${String(innerH / 2)}) rotate(90)`)
			.attr('text-anchor', 'middle')
			.attr('fill', '#ef4444')
			.style('font-size', '12px')
			.style('font-family', 'var(--font-sans)')
			.text('Probability (%)');

		// initial draw
		draw(xBase);

		// zoom (pan only on x-axis)
		const zoom = d3
			.zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.5, 5])
			.translateExtent([
				[xBase(new Date('2025-01-01')), 0],
				[innerW * 1.5, innerH],
			])
			.extent([
				[0, 0],
				[innerW, innerH],
			])
			.filter((event: Event) => {
				if (event.type === 'wheel') return true;
				if (event.type === 'mousedown' || event.type === 'touchstart') return true;
				return false;
			})
			.on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
				const newX = event.transform.rescaleX(xBase);
				draw(newX);
				xAxisG.call(d3.axisBottom(newX).ticks(d3.timeMonth.every(3)));
				xAxisG.selectAll('text').attr('fill', themeAxisText).style('font-size', '11px');
				xAxisG.selectAll('line,path').attr('stroke', themeAxisLine);
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
</script>

<div bind:this={wrapperEl}>
	<div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 8px;">
		<h2 style="margin-bottom: 0; font-size: 18px; font-weight: 600; color: var(--text-primary);">
			Registration Time Forecast
		</h2>
		{#if isMobile}
			<button
				onclick={() => (showChart = !showChart)}
				style="
					padding: 7px 16px;
					font-size: 13px; font-family: var(--font-sans); font-weight: 500;
					border-radius: var(--radius-md);
					border: 1px solid var(--border);
					background: var(--bg-card);
					color: var(--text-primary);
					cursor: pointer;
					box-shadow: var(--shadow-sm);
				"
			>
				{showChart ? 'Hide graph' : 'Show forecast graph'}
			</button>
		{/if}
	</div>

	<!-- Controls -->
	<div style="
		display: flex; flex-wrap: wrap; align-items: end; gap: 20px;
		margin-bottom: 16px; padding: 18px 20px;
		border-radius: var(--radius-lg); border: 1px solid var(--border);
		background: var(--bg-card-alt);
	">
		<label style="display: flex; flex-direction: column; gap: 6px;">
			<span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);">Registration date</span>
			<input
				type="date"
				bind:value={registrationDate}
				oninput={handleDateInput}
				style="
					height: 40px; padding: 0 14px;
					font-size: 14px; font-family: var(--font-sans);
					border-radius: var(--radius-md);
					border: 1px solid var(--border);
					background: var(--bg-input);
					color: var(--text-primary);
					box-shadow: var(--shadow-sm);
					outline: none;
				"
			/>
		</label>
		<label style="display: flex; flex-direction: column; gap: 6px;">
			<span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);">Days registered</span>
			<div style="display: flex; align-items: center; gap: 8px;">
				<input
					type="number"
					min="0"
					bind:value={daysInput}
					onchange={handleDaysInput}
					style="
						height: 40px; width: 120px; padding: 0 14px;
						font-size: 14px; font-family: var(--font-mono);
						border-radius: var(--radius-md);
						border: 1px solid var(--border);
						background: var(--bg-input);
						color: var(--text-primary);
						box-shadow: var(--shadow-sm);
						outline: none;
					"
					placeholder="e.g. 1460"
				/>
				<span style="
					font-size: 11px; font-weight: 500;
					color: #34d399;
					opacity: {savedIndicator ? 1 : 0};
					transition: opacity 0.3s ease;
					white-space: nowrap;
				">saved</span>
			</div>
		</label>
		<div style="display: flex; align-items: center; gap: 16px; padding-bottom: 2px; font-size: 14px; color: var(--text-muted);">
			<span>
				= <span style="font-family: var(--font-mono); color: var(--text-primary); font-weight: 500;">{formatDays(myRegDaysToday)}</span>
			</span>
			<span style="
				font-weight: 600;
				font-size: 14px;
				padding: 4px 12px;
				border-radius: 20px;
				background: {probColor(todayProb)}18;
				color: {probColor(todayProb)};
			">
				{todayProb}% chance today
			</span>
		</div>
	</div>

	{#if !isMobile || showChart}
	<p style="margin-bottom: 20px; font-size: 14px; color: var(--text-muted); line-height: 1.6;">
		GP model prediction with 95% CI. Red dashed = your registration time.
		Red solid = probability (right axis). Drag to pan, scroll to zoom.
	</p>

	<!-- Legend -->
	<div style="
		display: flex; flex-direction: row; flex-wrap: nowrap;
		align-items: center; gap: 16px;
		margin-bottom: 10px; padding: 10px 16px;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-light);
		background: var(--bg-card);
		overflow-x: auto;
		font-size: 12px; color: var(--text-muted);
	">
		<span style="display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;">
			<svg width="20" height="12"><line x1="0" y1="6" x2="20" y2="6" stroke="#818cf8" stroke-width="2" stroke-dasharray="4 2" /></svg>
			GP mean
		</span>
		<span style="display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;">
			<svg width="20" height="12"><rect width="20" height="12" rx="3" fill="#6366f1" fill-opacity="0.22" /></svg>
			95% CI
		</span>
		<span style="display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;">
			<svg width="20" height="12"><line x1="0" y1="6" x2="20" y2="6" stroke="#ef4444" stroke-width="2" stroke-dasharray="5 3" /></svg>
			My reg. time
		</span>
		<span style="display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;">
			<svg width="20" height="12"><line x1="0" y1="6" x2="20" y2="6" stroke="#ef4444" stroke-width="1.8" /></svg>
			P(&#8805; required)
		</span>
		<span style="display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;">
			<svg width="20" height="12"><line x1="0" y1="6" x2="20" y2="6" stroke="#fbbf24" stroke-width="1.5" stroke-dasharray="4 4" /></svg>
			Today
		</span>
		<span style="color: var(--border); flex-shrink: 0; font-size: 14px;">|</span>
		{#each cities as city (city)}
			<span style="display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; flex-shrink: 0;">
				<svg width="10" height="10"><circle cx="5" cy="5" r="4.5" fill={colorScale(city)} /></svg>
				{city}
			</span>
		{/each}
	</div>

	<!-- Chart -->
	{#if isMobile}
		<div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: var(--radius-lg);">
			<div style="min-width: 600px; position: relative; min-height: {chartHeight}px; border-radius: var(--radius-lg); overflow: hidden; border: 1px solid var(--border-light); background: var(--bg-card);">
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
						onmouseenter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--accent)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'; }}
					>
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
							<path d="M3 3v5h5"/>
						</svg>
						Reset
					</button>
				{/if}
			</div>
		</div>
	{:else}
		<div style="position: relative; width: 100%; min-height: {chartHeight}px; border-radius: var(--radius-lg); overflow: hidden; border: 1px solid var(--border-light); background: var(--bg-card);">
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
					onmouseenter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--accent)'; }}
					onmouseleave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'; }}
				>
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
						<path d="M3 3v5h5"/>
					</svg>
					Reset
				</button>
			{/if}
		</div>
	{/if}
	{/if}
</div>

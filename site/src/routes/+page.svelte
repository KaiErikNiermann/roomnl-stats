<script lang="ts">
	import Filters from '$lib/components/Filters.svelte';
	import DataTable from '$lib/components/DataTable.svelte';
	import ForecastChart from '$lib/components/ForecastChart.svelte';
	import WaitTimeMap from '$lib/components/WaitTimeMap.svelte';
	import type { RecentlyRented, Prediction } from '$lib/types';

	const { data } = $props<{ data: import('./$types').PageData }>();

	let selectedCity = $state('');
	let selectedRoomType = $state('');

	const filtered: RecentlyRented[] = $derived(
		data.data.recentlyRented.filter((row: RecentlyRented) => {
			if (selectedCity && row.city !== selectedCity) return false;
			if (selectedRoomType && row.type_of_room !== selectedRoomType) return false;
			return true;
		}),
	);

	const filteredPredictions = $derived.by(() => {
		const all = data.data.predictions;
		// Most specific: combo match
		if (selectedCity && selectedRoomType) {
			const combo = all.filter((p: Prediction) => p.city === selectedCity && p.type_of_room === selectedRoomType);
			if (combo.length > 0) return combo;
		}
		// City-level model
		if (selectedCity) {
			const city = all.filter((p: Prediction) => p.city === selectedCity && p.type_of_room === null);
			if (city.length > 0) return city;
		}
		// Global fallback
		return all.filter((p: Prediction) => p.city === null && p.type_of_room === null);
	});
</script>

<svelte:head>
	<title>room.nl stats</title>
	<meta name="description" content="Room booking statistics and registration time predictions for Dutch student housing" />
</svelte:head>

<main style="max-width: 1140px; margin: 0 auto; padding: 40px 24px 60px;">
	<header style="margin-bottom: 36px;">
		<h1 style="font-size: 28px; font-weight: 700; letter-spacing: -0.5px; color: var(--text-primary);">
			room.nl stats
		</h1>
		<p style="margin-top: 8px; font-size: 15px; color: var(--text-muted); line-height: 1.5;">
			Student housing allocation data and registration time forecasts for the Netherlands.
		</p>
	</header>

	<section style="margin-bottom: 32px;">
		<Filters
			data={data.data.recentlyRented}
			{selectedCity}
			{selectedRoomType}
			onCityChange={(c) => (selectedCity = c)}
			onRoomTypeChange={(r) => (selectedRoomType = r)}
		/>
	</section>

	<section style="margin-bottom: 48px;">
		<ForecastChart predictions={filteredPredictions} observations={filtered} />
	</section>

	<section style="margin-bottom: 48px;">
		<WaitTimeMap stats={data.data.stats} observations={filtered} {selectedCity} {selectedRoomType} />
	</section>

	<section style="margin-bottom: 48px;">
		<h2 style="margin-bottom: 16px; font-size: 18px; font-weight: 600; color: var(--text-primary);">
			Recently Rented
		</h2>
		<DataTable data={filtered} />
	</section>

	<footer style="padding-top: 24px; border-top: 1px solid var(--border-light); text-align: center; font-size: 12px; color: var(--text-faint);">
		Data sourced from room.nl. Updated every 2 weeks. Predictions are estimates, not guarantees.
	</footer>
</main>

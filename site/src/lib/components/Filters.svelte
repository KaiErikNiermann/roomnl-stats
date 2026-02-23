<script lang="ts">
	import type { RecentlyRented } from '$lib/types';
	import { uniqueValues } from '$lib/data';

	interface Props {
		data: readonly RecentlyRented[];
		selectedCity: string;
		selectedRoomType: string;
		onCityChange: (city: string) => void;
		onRoomTypeChange: (roomType: string) => void;
	}

	const { data, selectedCity, selectedRoomType, onCityChange, onRoomTypeChange }: Props = $props();

	const cities = $derived(uniqueValues(data, 'city'));
	const roomTypes = $derived(uniqueValues(data, 'type_of_room'));
</script>

<div style="display: flex; flex-wrap: wrap; gap: 16px;">
	<label style="display: flex; flex-direction: column; gap: 6px;">
		<span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);">City</span>
		<select
			style="
				height: 40px; padding: 0 36px 0 14px;
				font-size: 14px; font-family: var(--font-sans);
				border-radius: var(--radius-md);
				border: 1px solid var(--border);
				background: var(--bg-input);
				color: var(--text-primary);
				box-shadow: var(--shadow-sm);
				cursor: pointer;
				outline: none;
				appearance: none;
				background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%236e6e80%22 stroke-width=%222.5%22><polyline points=%226 9 12 15 18 9%22/></svg>');
				background-repeat: no-repeat;
				background-position: right 12px center;
			"
			value={selectedCity}
			onchange={(e) => onCityChange(e.currentTarget.value)}
		>
			<option value="">All cities</option>
			{#each cities as city (city)}
				<option value={city}>{city}</option>
			{/each}
		</select>
	</label>

	<label style="display: flex; flex-direction: column; gap: 6px;">
		<span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);">Room type</span>
		<select
			style="
				height: 40px; padding: 0 36px 0 14px;
				font-size: 14px; font-family: var(--font-sans);
				border-radius: var(--radius-md);
				border: 1px solid var(--border);
				background: var(--bg-input);
				color: var(--text-primary);
				box-shadow: var(--shadow-sm);
				cursor: pointer;
				outline: none;
				appearance: none;
				background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%236e6e80%22 stroke-width=%222.5%22><polyline points=%226 9 12 15 18 9%22/></svg>');
				background-repeat: no-repeat;
				background-position: right 12px center;
			"
			value={selectedRoomType}
			onchange={(e) => onRoomTypeChange(e.currentTarget.value)}
		>
			<option value="">All types</option>
			{#each roomTypes as rt (rt)}
				<option value={rt}>{rt}</option>
			{/each}
		</select>
	</label>
</div>

<script lang="ts">
	import { match } from 'ts-pattern';
	import type { RecentlyRented, SortState, SortDirection } from '$lib/types';
	import { formatDays } from '$lib/data';

	interface Props {
		data: readonly RecentlyRented[];
	}

	const { data }: Props = $props();

	let sort: SortState = $state({ column: 'contract_date', direction: 'desc' });
	let page = $state(0);
	const pageSize = 25;

	function toggleSort(column: SortState['column']) {
		sort = match(sort.column === column)
			.with(true, () => ({
				column,
				direction: (sort.direction === 'asc' ? 'desc' : 'asc') as SortDirection,
			}))
			.with(false, () => ({ column, direction: 'asc' as SortDirection }))
			.exhaustive();
		page = 0;
	}

	const sorted = $derived.by(() => {
		const { column, direction } = sort;
		const multiplier = direction === 'asc' ? 1 : -1;

		return data.toSorted((a, b) => {
			const va = a[column];
			const vb = b[column];

			if (typeof va === 'string' && typeof vb === 'string') {
				return va.localeCompare(vb) * multiplier;
			}
			if (typeof va === 'number' && typeof vb === 'number') {
				return (va - vb) * multiplier;
			}
			if (typeof va === 'boolean' && typeof vb === 'boolean') {
				return (Number(va) - Number(vb)) * multiplier;
			}
			return 0;
		});
	});

	const totalPages = $derived(Math.max(1, Math.ceil(sorted.length / pageSize)));

	$effect(() => {
		if (page >= totalPages) page = Math.max(0, totalPages - 1);
	});

	const paged = $derived(sorted.slice(page * pageSize, (page + 1) * pageSize));

	const columns: { key: SortState['column']; label: string }[] = [
		{ key: 'city', label: 'City' },
		{ key: 'street', label: 'Street' },
		{ key: 'street_number', label: '#' },
		{ key: 'type_of_room', label: 'Type' },
		{ key: 'registration_time', label: 'Reg. time' },
		{ key: 'num_reactions', label: 'Reactions' },
		{ key: 'contract_date', label: 'Date' },
		{ key: 'priority', label: 'Priority' },
	];
</script>

<div style="border-radius: var(--radius-lg); border: 1px solid var(--border); background: var(--bg-card); box-shadow: var(--shadow-sm); overflow: hidden;">
	<div style="overflow-x: auto;">
		<table style="width: 100%; text-align: left; font-size: 14px; border-collapse: collapse;">
			<thead>
				<tr style="background: var(--bg-card-alt);">
					{#each columns as col (col.key)}
						<th
							style="
								padding: 14px 16px;
								font-size: 12px; font-weight: 600;
								text-transform: uppercase; letter-spacing: 0.05em;
								color: {sort.column === col.key ? 'var(--accent)' : 'var(--text-muted)'};
								border-bottom: 1px solid var(--border);
								cursor: pointer; user-select: none;
								white-space: nowrap;
								transition: color 0.15s;
							"
							onclick={() => toggleSort(col.key)}
						>
							{col.label}
							{#if sort.column === col.key}
								<span style="margin-left: 4px; font-size: 10px;">
									{sort.direction === 'asc' ? '▲' : '▼'}
								</span>
							{/if}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each paged as row, i (row.city + row.street + row.street_number + row.contract_date + row.registration_time + i)}
					<tr
						style="border-top: 1px solid var(--border-light); transition: background 0.1s;"
						onmouseenter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
						onmouseleave={(e) => (e.currentTarget.style.background = '')}
					>
						<td style="padding: 12px 16px; font-weight: 500; color: var(--text-primary);">{row.city}</td>
						<td style="padding: 12px 16px; color: var(--text-secondary);">{row.street}</td>
						<td style="padding: 12px 16px; color: var(--text-muted);">{row.street_number}</td>
						<td style="padding: 12px 16px;">
							<span style="
								display: inline-block; padding: 3px 10px;
								font-size: 12px; font-weight: 500;
								border-radius: 20px;
								background: var(--accent-muted); color: var(--accent);
							">{row.type_of_room}</span>
						</td>
						<td style="padding: 12px 16px; font-family: var(--font-mono); font-size: 13px; color: var(--accent);">{formatDays(row.registration_time)}</td>
						<td style="padding: 12px 16px; color: var(--text-muted);">{row.num_reactions}</td>
						<td style="padding: 12px 16px; color: var(--text-muted);">{row.contract_date}</td>
						<td style="padding: 12px 16px;">
							{#if row.priority}
								<span style="color: #f59e0b;">★</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if sorted.length === 0}
		<p style="padding: 40px; text-align: center; color: var(--text-muted);">No data matching current filters.</p>
	{/if}
</div>

<div style="margin-top: 14px; display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: var(--text-muted);">
	<span>{sorted.length} listings</span>
	{#if totalPages > 1}
		<div style="display: flex; align-items: center; gap: 8px;">
			<button
				style="
					padding: 7px 14px; font-size: 13px; font-family: var(--font-sans);
					border-radius: var(--radius-sm); border: 1px solid var(--border);
					background: var(--bg-card); color: var(--text-secondary);
					cursor: pointer; opacity: {page === 0 ? '0.4' : '1'};
					transition: all 0.15s;
				"
				disabled={page === 0}
				onclick={() => (page = page - 1)}
			>
				← Prev
			</button>
			<span style="min-width: 100px; text-align: center;">Page {page + 1} of {totalPages}</span>
			<button
				style="
					padding: 7px 14px; font-size: 13px; font-family: var(--font-sans);
					border-radius: var(--radius-sm); border: 1px solid var(--border);
					background: var(--bg-card); color: var(--text-secondary);
					cursor: pointer; opacity: {page >= totalPages - 1 ? '0.4' : '1'};
					transition: all 0.15s;
				"
				disabled={page >= totalPages - 1}
				onclick={() => (page = page + 1)}
			>
				Next →
			</button>
		</div>
	{/if}
</div>

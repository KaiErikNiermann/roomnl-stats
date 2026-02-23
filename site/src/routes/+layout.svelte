<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import '../app.css';
	import { browser } from '$app/environment';

	let { children } = $props();

	let dark = $state(true);

	if (browser) {
		const stored = localStorage.getItem('theme');
		dark = stored ? stored === 'dark' : globalThis.matchMedia('(prefers-color-scheme: dark)').matches;
	}

	$effect(() => {
		if (!browser) return;
		document.documentElement.classList.toggle('dark', dark);
		localStorage.setItem('theme', dark ? 'dark' : 'light');
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div style="position: fixed; top: 20px; right: 20px; z-index: 50;">
	<button
		onclick={() => (dark = !dark)}
		aria-label="Toggle theme"
		style="
			display: flex; align-items: center; justify-content: center;
			width: 38px; height: 38px;
			border-radius: var(--radius-md);
			background: var(--bg-card);
			border: 1px solid var(--border);
			color: var(--text-muted);
			box-shadow: var(--shadow-sm);
			cursor: pointer;
			transition: all 0.15s ease;
		"
	>
		{#if dark}
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
		{:else}
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
		{/if}
	</button>
</div>

{@render children()}

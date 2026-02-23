import { base } from '$app/paths';
import { match } from 'ts-pattern';
import type { RecentlyRented, Prediction, CityStats, SiteData } from './types';

function extract<T>(result: PromiseSettledResult<T>, fallback: T): T {
	return match(result)
		.with({ status: 'fulfilled' }, (r) => r.value)
		.with({ status: 'rejected' }, () => fallback)
		.exhaustive();
}

export async function loadSiteData(fetchFn: typeof fetch = fetch): Promise<SiteData> {
	const basePath = `${base}/data`;

	const [rr, pred, stats] = await Promise.allSettled([
		fetchFn(`${basePath}/recently_rented.json`).then((r) => r.json() as Promise<RecentlyRented[]>),
		fetchFn(`${basePath}/predictions.json`).then((r) => r.json() as Promise<Prediction[]>),
		fetchFn(`${basePath}/stats.json`).then((r) => r.json() as Promise<CityStats[]>),
	]);

	return {
		recentlyRented: extract(rr, [] as RecentlyRented[]),
		predictions: extract(pred, [] as Prediction[]),
		stats: extract(stats, [] as CityStats[]),
	};
}

export function uniqueValues<T, K extends keyof T>(items: readonly T[], key: K): T[K][] {
	return [...new Set(items.map((item) => item[key]))].toSorted() as T[K][];
}

export function formatDays(days: number): string {
	const years = Math.floor(days / 365);
	const months = Math.floor((days % 365) / 30);
	const remaining = days % 30;

	const parts: string[] = [];
	if (years > 0) parts.push(`${String(years)}y`);
	if (months > 0) parts.push(`${String(months)}m`);
	if (remaining > 0 || parts.length === 0) parts.push(`${String(remaining)}d`);

	return parts.join(' ');
}

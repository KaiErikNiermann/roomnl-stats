import { loadSiteData } from '$lib/data';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const data = await loadSiteData(fetch);
	return { data };
};

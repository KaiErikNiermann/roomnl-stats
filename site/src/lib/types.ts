export interface RecentlyRented {
	readonly street: string;
	readonly street_number: string;
	readonly city: string;
	readonly type_of_room: string;
	readonly contract_date: string;
	readonly num_reactions: number;
	readonly registration_time: number;
	readonly priority: boolean;
}

export interface Prediction {
	readonly city: string | null;
	readonly type_of_room: string | null;
	readonly contract_date: string;
	readonly pred_mean: number;
	readonly pred_lo: number;
	readonly pred_hi: number;
}

export interface CityStats {
	readonly city: string;
	readonly type_of_room: string;
	readonly count: number;
	readonly median_reg_days: number;
	readonly mean_reg_days: number;
	readonly min_reg_days: number;
	readonly max_reg_days: number;
	readonly median_reactions: number;
	readonly pct_priority: number;
}

export interface SiteMeta {
	readonly lastUpdated: string;
}

export interface SiteData {
	readonly recentlyRented: readonly RecentlyRented[];
	readonly predictions: readonly Prediction[];
	readonly stats: readonly CityStats[];
	readonly meta: SiteMeta | null;
}

export type SortDirection = 'asc' | 'desc';

export interface SortState {
	readonly column: keyof RecentlyRented;
	readonly direction: SortDirection;
}

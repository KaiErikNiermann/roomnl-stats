/** Hardcoded [longitude, latitude] for the 15 cities in the dataset. */
export const CITY_COORDS: Record<string, [number, number]> = {
	"'s-Gravenhage": [4.3007, 52.0705],
	Amstelveen: [4.8652, 52.3012],
	Amsterdam: [4.8952, 52.3702],
	Delft: [4.3571, 52.0116],
	Deventer: [6.155, 52.255],
	Ede: [5.6644, 52.0484],
	Groningen: [6.5665, 53.2194],
	Haarlem: [4.6462, 52.3874],
	'Haren Gn': [6.6141, 53.1713],
	Hoofddorp: [4.6889, 52.3026],
	Leiden: [4.497, 52.1601],
	Oegstgeest: [4.4691, 52.1803],
	Voorschoten: [4.4474, 52.1277],
	Wageningen: [5.6653, 51.9692],
	Weesp: [5.0419, 52.3078],
};

export interface CityMapDatum {
	readonly city: string;
	readonly coords: [number, number];
	readonly medianDays: number;
	readonly count: number;
	readonly meanDays: number;
	readonly highlighted: boolean;
}

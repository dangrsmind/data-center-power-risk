const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** Blank or absent keys must never produce a keyless CARTO request. */
export function getBasemapConfig(apiKey?: string) {
  const key = apiKey?.trim();
  if (key) {
    return {
      fallback: false,
      url: `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?api_key=${encodeURIComponent(key)}`,
      attribution: `${OSM_ATTRIBUTION} &copy; <a href="https://carto.com/attributions">CARTO</a>`,
      maxZoom: 19,
    };
  }
  return {
    fallback: true,
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: OSM_ATTRIBUTION,
    maxZoom: 19,
  };
}

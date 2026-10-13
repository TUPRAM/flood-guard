/**
 * The markers of the Public Shelter map: the places reported in use as shelters in September 2024. Drawn on the map
 * `GeoMap` owns, through its `overlay` hook.
 *
 * A marker is history, not an offer. Its popup says where the report came from, that it says nothing about today,
 * and lets the reader take the place as a destination, which they must still confirm with an authority.
 */

import type { Layer, Map as LeafletMap } from "leaflet";

import { SHELTER_HISTORY_COPY, shelterSiteLines, type ShelterHistorySite } from "@/lib/public-shelter-history";
import type { Language } from "@/lib/types";

import { MAP_POPUP_CLASS, MAP_POPUP_FRAME_CLASS } from "./mae-sai-map-kit";

type LeafletModule = typeof import("leaflet");

const SITE_ICON_HTML = [
  '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">',
  '<path d="M3.5 10.6 12 4l8.5 6.6M5.6 9.5V20h12.8V9.5M9.8 20v-5.2h4.4V20"',
  ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  "</svg>",
].join("");

/** Room the markers keep clear when the map frames them: the field and the banner above, the tools and the note below. */
const FRAME_PADDING = { topLeft: [24, 140], bottomRight: [72, 120] } as const;

/**
 * Put the located places on `map`. `onChoose` is called when the reader takes a place as their destination. With
 * `frame` the map moves to show them all. Returns the function that takes the markers away again.
 */
export function mountShelterHistory(
  L: LeafletModule,
  map: LeafletMap,
  sites: readonly ShelterHistorySite[],
  language: Language,
  onChoose: (site: ShelterHistorySite) => void,
  frame = false,
): () => void {
  const layers: Layer[] = [];
  const points: [number, number][] = [];
  for (const site of sites) {
    if (!site.point) continue;
    points.push([site.point.latitude, site.point.longitude]);
    const name = site.name[language];
    const marker = L.marker([site.point.latitude, site.point.longitude], {
      icon: L.divIcon({
        className: `public-shelter-site${site.approximate ? " is-approximate" : ""}`,
        html: SITE_ICON_HTML,
        iconSize: [30, 30],
        iconAnchor: [15, 15],
      }),
      keyboard: true,
      title: name,
      alt: name,
      zIndexOffset: 200,
    });
    const content = document.createElement("div");
    content.className = MAP_POPUP_CLASS;
    const title = document.createElement("strong");
    title.textContent = name;
    content.append(title);
    for (const line of shelterSiteLines(site, language)) {
      const paragraph = document.createElement("p");
      paragraph.textContent = line;
      content.append(paragraph);
    }
    const use = document.createElement("button");
    use.type = "button";
    use.className = "public-shelter-site-use";
    use.textContent = SHELTER_HISTORY_COPY.use[language];
    use.addEventListener("click", () => {
      map.closePopup();
      onChoose(site);
    });
    content.append(use);
    marker.bindPopup(content, { className: MAP_POPUP_FRAME_CLASS, maxWidth: 250, autoPanPaddingTopLeft: [12, 150], autoPanPaddingBottomRight: [72, 96] });
    layers.push(marker.addTo(map));
  }
  if (frame && points.length > 1) {
    map.fitBounds(L.latLngBounds(points), {
      animate: false,
      maxZoom: 13,
      paddingTopLeft: L.point(FRAME_PADDING.topLeft[0], FRAME_PADDING.topLeft[1]),
      paddingBottomRight: L.point(FRAME_PADDING.bottomRight[0], FRAME_PADDING.bottomRight[1]),
    });
  }
  return () => {
    map.closePopup();
    for (const layer of layers) layer.remove();
  };
}

import type { LayerCatalogItem, RoleVisibility } from "@floodguard/contracts";

const OPENSTREETMAP_ATTRIBUTION = "© OpenStreetMap contributors";

/** Return the deduplicated attribution required by the layers currently drawn on the map. */
export function visibleLayerAttributions(
  layers: LayerCatalogItem[],
  visibleLayerIds: ReadonlySet<string>,
  role?: RoleVisibility,
): string[] {
  const attributions: string[] = [];
  const seen = new Set<string>();

  for (const layer of layers) {
    if (!visibleLayerIds.has(layer.layer_id)) continue;
    if (role !== undefined && !layer.role_visibility.includes(role)) continue;
    const layerAttributions = [...layer.attribution];
    if (/geofabrik/i.test(layer.source_name) && !layerAttributions.some((value) => /geofabrik/i.test(value))) {
      layerAttributions.push("Geofabrik");
    }
    for (const rawAttribution of layerAttributions) {
      const attribution = canonicalAttribution(rawAttribution);
      if (!attribution) continue;
      const identity = attribution.toLocaleLowerCase("en-US");
      if (seen.has(identity)) continue;
      seen.add(identity);
      attributions.push(attribution);
    }
  }

  return attributions;
}

function canonicalAttribution(value: string): string {
  const attribution = value.trim();
  if (/^(?:©\s*)?openstreetmap contributors$/i.test(attribution)) {
    return OPENSTREETMAP_ATTRIBUTION;
  }
  return attribution;
}

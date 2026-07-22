import type { LayerCatalogItem, RoleVisibility } from "@floodguard/contracts";

/** Filter before any layer URL is fetched, exported, attributed, or cached. */
export function visibleLayersForRole(
  layers: readonly LayerCatalogItem[],
  role: RoleVisibility,
): LayerCatalogItem[] {
  return layers.filter((layer) => layer.role_visibility.includes(role));
}

export function assertLayerVisibleForRole(
  layer: LayerCatalogItem,
  role: RoleVisibility,
): void {
  if (!layer.role_visibility.includes(role)) {
    throw new Error(
      `Layer ${layer.layer_id} is not permitted for the ${role} surface.`,
    );
  }
}

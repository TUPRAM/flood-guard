interface FilterableArea {
  area_id: string;
  action_class: string;
  fpps_0_100?: number;
}

interface RankableArea extends FilterableArea {
  fpps_0_100: number;
}

interface SearchableArea extends RankableArea {
  area_name_en: string;
  area_name_th: string;
}

export interface CommandFilterState {
  activeClasses: Set<string>;
  selectedId: string;
}

/** Keep the command map and evidence panel on the same visible area. */
export function toggleCommandClass(
  current: ReadonlySet<string>,
  actionClass: string,
  selectedId: string,
  areas: readonly FilterableArea[],
): CommandFilterState {
  const activeClasses = new Set(current);
  if (activeClasses.has(actionClass) && activeClasses.size > 1) {
    activeClasses.delete(actionClass);
  } else {
    activeClasses.add(actionClass);
  }

  const selected = areas.find((area) => area.area_id === selectedId);
  if (!selected || activeClasses.has(selected.action_class)) {
    return { activeClasses, selectedId };
  }

  const replacement = areas
    .filter((area) => activeClasses.has(area.action_class))
    .toSorted((left, right) => (
      (right.fpps_0_100 ?? Number.NEGATIVE_INFINITY) - (left.fpps_0_100 ?? Number.NEGATIVE_INFINITY)
      || left.area_id.localeCompare(right.area_id)
    ))[0];
  return {
    activeClasses,
    selectedId: replacement?.area_id ?? selectedId,
  };
}

/** Rank only already-computed engine output; this function never recomputes FPPS. */
export function rankVisibleAreas<T extends RankableArea>(
  areas: readonly T[],
  activeClasses: ReadonlySet<string>,
): T[] {
  return areas
    .filter((area) => activeClasses.has(area.action_class))
    .toSorted((left, right) => (
      right.fpps_0_100 - left.fpps_0_100 || left.area_id.localeCompare(right.area_id)
    ));
}

/** Resolve a persisted selection without allowing an invalid or stale identifier to win. */
export function resolveCommandSelection<T extends RankableArea>(
  areas: readonly T[],
  persistedId?: string | null,
): T | undefined {
  return areas.find((area) => area.area_id === persistedId)
    ?? areas.toSorted((left, right) => (
      right.fpps_0_100 - left.fpps_0_100 || left.area_id.localeCompare(right.area_id)
    ))[0];
}

/** Search the already-ranked planning list by identifier or either localized name. */
export function searchRankedAreas<T extends SearchableArea>(
  areas: readonly T[],
  activeClasses: ReadonlySet<string>,
  query: string,
): T[] {
  const normalized = query.trim().toLocaleLowerCase();
  return rankVisibleAreas(areas, activeClasses).filter((area) => {
    if (!normalized) return true;
    return [area.area_id, area.area_name_en, area.area_name_th]
      .some((value) => value.toLocaleLowerCase().includes(normalized));
  });
}

/** Stable global FPPS positions; filtering or searching must not renumber an area. */
export function commandRankPositions<T extends RankableArea>(areas: readonly T[]): ReadonlyMap<string, number> {
  const classes = new Set(areas.map((area) => area.action_class));
  return new Map(rankVisibleAreas(areas, classes).map((area, index) => [area.area_id, index + 1]));
}

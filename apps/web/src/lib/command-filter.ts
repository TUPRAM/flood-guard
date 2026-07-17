interface FilterableArea {
  area_id: string;
  action_class: string;
}

interface RankableArea extends FilterableArea {
  fpps_0_100: number;
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

  const replacement = areas.find((area) => activeClasses.has(area.action_class));
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

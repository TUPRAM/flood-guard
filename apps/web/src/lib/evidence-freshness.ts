import type { FreshnessState, SourceComponent } from "@floodguard/contracts";

const FRESHNESS_ORDER: Record<FreshnessState, number> = {
  current: 0,
  aging: 1,
  historical: 2,
  unknown: 3,
};

/** Return the most limiting declared source freshness without guessing from generation time. */
export function limitingFreshness(
  components: readonly SourceComponent[],
): FreshnessState {
  return components.reduce<FreshnessState>(
    (result, component) => (
      FRESHNESS_ORDER[component.freshness] > FRESHNESS_ORDER[result]
        ? component.freshness
        : result
    ),
    "current",
  );
}

export function sourceTimestampLabel(component: SourceComponent): string {
  if (component.source_timestamp === null) return "Source time unknown";
  return component.temporal_meaning === "observation_time"
    ? "Observation time"
    : component.temporal_meaning === "valid_from"
      ? "Valid from"
      : component.temporal_meaning === "publication_year"
        ? "Publication date"
        : component.temporal_meaning === "extract_time"
          ? "Extracted at"
          : component.temporal_meaning === "generation_time"
            ? "Generated at"
            : "Source time";
}

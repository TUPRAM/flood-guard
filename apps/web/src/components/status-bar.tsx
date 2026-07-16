import { formatConfidence, formatSourceTime } from "@/lib/format";
import type { FloodGuardData, Language } from "@/lib/types";

const DATASET_LABELS = {
  fixture_demo: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e2a\u0e32\u0e18\u0e34\u0e15", en: "Fixture demo" },
  candidate: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e1c\u0e39\u0e49\u0e2a\u0e21\u0e31\u0e04\u0e23", en: "Candidate data" },
  official_input: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e19\u0e33\u0e40\u0e02\u0e49\u0e32\u0e17\u0e32\u0e07\u0e01\u0e32\u0e23", en: "Official input" },
} as const;

const OPERATIONAL_LABELS = {
  non_operational: { th: "\u0e44\u0e21\u0e48\u0e43\u0e0a\u0e48\u0e23\u0e30\u0e1a\u0e1a\u0e1b\u0e0f\u0e34\u0e1a\u0e31\u0e15\u0e34\u0e01\u0e32\u0e23", en: "Non-operational" },
  planning_only: { th: "\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e01\u0e32\u0e23\u0e27\u0e32\u0e07\u0e41\u0e1c\u0e19\u0e40\u0e17\u0e48\u0e32\u0e19\u0e31\u0e49\u0e19", en: "Planning only" },
  agency_operational: { th: "\u0e2b\u0e19\u0e48\u0e27\u0e22\u0e07\u0e32\u0e19\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19\u0e40\u0e0a\u0e34\u0e07\u0e1b\u0e0f\u0e34\u0e1a\u0e31\u0e15\u0e34\u0e01\u0e32\u0e23", en: "Agency operational" },
} as const;

const DATA_STATE_LABELS = {
  loading: { th: "\u0e01\u0e33\u0e25\u0e31\u0e07\u0e42\u0e2b\u0e25\u0e14\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25", en: "Loading data" },
  ready: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e1e\u0e23\u0e49\u0e2d\u0e21", en: "Data ready" },
  stale: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e25\u0e49\u0e32\u0e2a\u0e21\u0e31\u0e22", en: "Stale data" },
  stale_offline: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e25\u0e49\u0e32\u0e2a\u0e21\u0e31\u0e22 / \u0e2d\u0e2d\u0e1f\u0e44\u0e25\u0e19\u0e4c", en: "Stale / offline" },
  blocked: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e16\u0e39\u0e01\u0e1a\u0e25\u0e47\u0e2d\u0e01", en: "Data blocked" },
  unavailable: { th: "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e44\u0e21\u0e48\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e43\u0e0a\u0e49", en: "Data unavailable" },
} as const;

export function StatusBar({ data, language, compact = false }: { data: FloodGuardData; language: Language; compact?: boolean }) {
  const th = language === "th";
  const bundledFixture = data.dataOrigin === "offline_bundle";
  const cachedApi = data.dataOrigin === "cached_api";
  const dataset = DATASET_LABELS[data.status.dataset_mode][language];
  const operational = OPERATIONAL_LABELS[data.status.operational_status][language];
  const warning = data.status.official_warning
    ? (th ? "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e40\u0e15\u0e37\u0e2d\u0e19\u0e20\u0e31\u0e22\u0e17\u0e32\u0e07\u0e01\u0e32\u0e23" : "Official-warning input")
    : (th ? "\u0e44\u0e21\u0e48\u0e43\u0e0a\u0e48\u0e1b\u0e23\u0e30\u0e01\u0e32\u0e28\u0e17\u0e32\u0e07\u0e01\u0e32\u0e23" : "Not an official warning");
  return (
    <section className={`status-bar ${compact ? "compact" : ""}`} aria-label={th ? "\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Data status"}>
      <div className="status-chips">
        <span className={`chip ${data.status.dataset_mode === "fixture_demo" ? "fixture" : "dataset-state"}`}>{dataset}</span>
        <span className={`chip ${data.status.operational_status.replaceAll("_", "-")}`}>{operational}</span>
        <span className={`chip warning-${data.status.official_warning}`}>{warning}</span>
        {data.dataState !== "ready" && <span className={`chip data-${data.dataState}`}>{DATA_STATE_LABELS[data.dataState][language]}</span>}
        {bundledFixture && <span className="chip offline">{th ? "\u0e0a\u0e38\u0e14\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e2a\u0e32\u0e18\u0e34\u0e15\u0e2d\u0e2d\u0e1f\u0e44\u0e25\u0e19\u0e4c" : "Bundled offline fixture"}</span>}
        {cachedApi && <span className="chip offline">{th ? "\u0e2a\u0e33\u0e40\u0e19\u0e32 API \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14\u0e17\u0e35\u0e48\u0e41\u0e04\u0e0a\u0e44\u0e27\u0e49 (\u0e2d\u0e2d\u0e1f\u0e44\u0e25\u0e19\u0e4c)" : "Cached API snapshot (stale/offline)"}</span>}
      </div>
      <div className="status-meta">
        <span><b>{th ? "\u0e40\u0e27\u0e25\u0e32\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Source time"}</b> {formatSourceTime(data.status.source_timestamp, language)} ICT</span>
        <span><b>{th ? "\u0e04\u0e27\u0e32\u0e21\u0e40\u0e0a\u0e37\u0e48\u0e2d\u0e21\u0e31\u0e48\u0e19" : "Confidence"}</b> {formatConfidence(data.status.confidence_class, language)}</span>
        {!compact && <span><b>{th ? "\u0e41\u0e2b\u0e25\u0e48\u0e07\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Source"}</b> {data.status.source_name}</span>}
      </div>
      {data.fallbackReason && (
        <p className="fallback-reason" role="status">
          {cachedApi
            ? (th ? "API \u0e44\u0e21\u0e48\u0e1e\u0e23\u0e49\u0e2d\u0e21; \u0e41\u0e2a\u0e14\u0e07\u0e2a\u0e33\u0e40\u0e19\u0e32 API \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14\u0e17\u0e35\u0e48\u0e41\u0e04\u0e0a\u0e44\u0e27\u0e49: " : "API unavailable; showing the cached API snapshot: ")
            : (th ? "API \u0e44\u0e21\u0e48\u0e1e\u0e23\u0e49\u0e2d\u0e21; \u0e41\u0e2a\u0e14\u0e07\u0e0a\u0e38\u0e14\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e2a\u0e32\u0e18\u0e34\u0e15\u0e17\u0e35\u0e48\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e44\u0e27\u0e49: " : "API unavailable; showing the bundled fixture snapshot: ")}
          {data.fallbackReason}
        </p>
      )}
      {data.degradedReason && (
        <p className="fallback-reason" role="status">
          {th ? "API \u0e1b\u0e31\u0e08\u0e08\u0e38\u0e1a\u0e31\u0e19\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19\u0e1a\u0e32\u0e07\u0e2a\u0e48\u0e27\u0e19: " : "Current API is partially available: "}
          {data.degradedReason}
        </p>
      )}
    </section>
  );
}

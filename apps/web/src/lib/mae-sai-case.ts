import caseData from "@/data/mae-sai-planning-demo.json";

export interface MaeSaiScenarioArea {
  area_id: string;
  baseline_people_losing_30_min_access: number;
  scenario_people_losing_30_min_access: number;
  change_people_losing_30_min_access: number;
  baseline_equity_gap_ratio: number | null;
  scenario_equity_gap_ratio: number | null;
  change_equity_gap_ratio: number | null;
}

export interface MaeSaiScenario {
  scenario_id: string;
  title: string;
  description: string;
  changed_assumption: string;
  verification_need: string;
  run_id: string;
  overall: {
    baseline_people_losing_30_min_access: number;
    scenario_people_losing_30_min_access: number;
    change_people_losing_30_min_access: number;
    baseline_max_equity_gap_ratio: number | null;
    scenario_max_equity_gap_ratio: number | null;
    change_max_equity_gap_ratio: number | null;
  };
  areas: MaeSaiScenarioArea[];
  assumptions: string[];
}

export interface MaeSaiCase {
  meta: {
    case_id: string;
    case_version: string;
    package_sha256: string;
    study_area_id: string;
    event_label: string;
    source_timestamp: string;
    source_processing_timestamp: string;
    generated_at: string;
    operational_status: string;
    confidence_class: string;
    fpps_recalculated: boolean;
    local_accuracy_status: string;
    can_feed_decision_layer: boolean;
    official_warning: boolean;
  };
  scope: {
    description: string;
    population_basis: string;
    graph_population: number;
    graph_node_count: number;
    graph_edge_count: number;
    facility_count: number;
    threshold_minutes: number;
    priority_scope_note: string;
  };
  areas: Array<{
    area_id: string;
    name_en: string;
    name_th: string;
    baseline: {
      total_population: number;
      people_losing_30_min_access: number;
      baseline_underserved_30_min: number;
      equity_gap_ratio: number | null;
    };
    existing_priority: {
      fpps: number;
      action_class: string;
      total_population: number;
      people_losing_30_min_access: number;
    };
  }>;
  scenarios: MaeSaiScenario[];
  sources: Array<{ path: string; sha256: string; role: string }>;
  source_components: Array<{
    name: string;
    timestamp: string | null;
    temporal_meaning: string;
  }>;
  assumptions: string[];
  validation: {
    status: string;
    measured: string[];
    not_measured: string[];
    required_next_steps: string[];
  };
}

/** Committed Python-engine results; the browser only selects and displays them. */
export const maeSaiCase: MaeSaiCase = caseData;

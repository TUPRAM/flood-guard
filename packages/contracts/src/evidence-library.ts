/** Static, candidate-only evidence packages. These are not AreaDecision payloads. */
import type { DecisionBrief } from "./decision-brief";
export const EVIDENCE_AVAILABILITIES = ["available", "partial", "metadata_only", "missing", "blocked"] as const;
export type EvidenceAvailability = (typeof EVIDENCE_AVAILABILITIES)[number];

export interface EvidenceGeometry {
  type: string;
  coordinates?: unknown[];
  geometries?: EvidenceGeometry[];
}
export interface EvidenceFeatureCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: EvidenceGeometry | null; properties: Record<string, unknown> | null }[];
}
export interface EvidenceLibraryDataset {
  id: string;
  title: string;
  title_th?: string;
  role: string;
  source_urls: string[];
  temporal: { start: string | null; end: string | null; kind: string; label: string };
  limitations: string[];
  rights: { status: string; license: string | null; public_derivatives: boolean; attribution: string[] };
}
export interface EvidenceLibraryAoi {
  id: string;
  name: string;
  name_th?: string;
  geometry: EvidenceGeometry;
  event_ids: string[];
  sha256?: string;
}
export interface EvidenceLibraryEvent {
  id: string;
  name: string;
  name_th?: string;
  start: string;
  end: string;
}
export interface EvidencePackageReference {
  id: string;
  aoi_id: string;
  event_id: string;
  url: string;
  sha256: string;
}
export interface EvidenceLibraryCatalog {
  schema_version: "1.0";
  generated_at: string;
  package_version: string;
  non_operational: true;
  aois: EvidenceLibraryAoi[];
  events: EvidenceLibraryEvent[];
  datasets: EvidenceLibraryDataset[];
  packages: EvidencePackageReference[];
}
export interface EvidenceAssessment {
  components: { id: string; label: string; weight: number; value: number | null; reason: string | null }[];
  fpps: null;
  bounds: { lower: number; upper: number } | null;
  action_class: null;
  limitations: string[];
}
export interface EvidenceLibraryLayer {
  id: string;
  title: string;
  role: string;
  dataset_id: string;
  availability: EvidenceAvailability;
  reason: string | null;
  data?: EvidenceFeatureCollection;
  image_url?: string;
  bounds?: [[number, number], [number, number]];
  attribution?: string;
}
export interface EvidenceLibraryGauge {
  id: string;
  name: string;
  units: string;
  timezone: string | null;
  points: { time: string; value: number | null }[];
  limitations: string[];
}
export interface EvidenceLibraryScenario {
  id: string;
  title: string;
  kind: string;
  summary: string;
  assumptions: string[];
  metrics: { label: string; value: number | string | null; unit?: string }[];
}
export interface EvidenceLibraryPackage {
  schema_version: "1.0";
  package_version: string;
  id: string;
  aoi_id: string;
  event_id: string;
  generated_at: string;
  source_timestamp: string | null;
  confidence_class: "low";
  assumptions: string[];
  input_hashes: Record<string, string>;
  dataset_mode: "candidate";
  official_warning: false;
  operational_status: "non_operational";
  datasets: { dataset_id: string; availability: EvidenceAvailability; coverage: string; qc: string[]; summary: string }[];
  layers: EvidenceLibraryLayer[];
  gauges: EvidenceLibraryGauge[];
  assessment: EvidenceAssessment;
  scenarios: EvidenceLibraryScenario[];
  report_url: string | null;
  decision_brief?: DecisionBrief;
  downloads?: { title: string; url: string; sha256: string }[];
}

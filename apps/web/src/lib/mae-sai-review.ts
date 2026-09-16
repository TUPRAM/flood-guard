import { maeSaiCase } from "./mae-sai-case";

export interface MaeSaiReviewInput {
  areaId: string;
  scenarioId: string;
  decision: string;
  reasoning: string;
  verificationNeed: string;
  owner: string;
  role: string;
  status: "draft" | "reviewed_for_exercise";
}

export interface MaeSaiReviewRecord extends MaeSaiReviewInput {
  id: string;
  createdAt: string;
  caseId: string;
  caseVersion: string;
  packageSha256: string;
  storageScope: "device_local";
  officialWarning: false;
}

type ReviewStorage = Pick<Storage, "getItem" | "setItem">;
const REVIEW_SCHEMA = "floodguard.mae-sai-review.v1";
const MAX_RECORDS = 100;
export const MAE_SAI_REVIEW_STORAGE_KEY = `floodguard:mae-sai:reviews:v1:${maeSaiCase.meta.case_version}:${maeSaiCase.meta.package_sha256}`;

function browserStorage(): ReviewStorage {
  if (typeof window === "undefined") throw new Error("Browser storage is unavailable. This review has not been saved.");
  return window.localStorage;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizedInput(input: MaeSaiReviewInput): MaeSaiReviewInput {
  if (!maeSaiCase.areas.some((area) => area.area_id === input.areaId)) {
    throw new Error("Select a reporting area from this historical case before saving.");
  }
  if (!maeSaiCase.scenarios.some((scenario) => scenario.scenario_id === input.scenarioId)) {
    throw new Error("Select a scenario from this historical case before saving.");
  }
  if (input.status !== "draft" && input.status !== "reviewed_for_exercise") {
    throw new Error("Review status must be a draft or a review for this exercise.");
  }
  const text = (value: unknown, label: string, max: number) => {
    if (typeof value !== "string" || value.trim().length === 0 || value.trim().length > max) {
      throw new Error(`${label} must contain between 1 and ${max} characters.`);
    }
    return value.trim();
  };
  return {
    areaId: input.areaId,
    scenarioId: input.scenarioId,
    status: input.status,
    decision: text(input.decision, "Planning decision", 1000),
    reasoning: text(input.reasoning, "Decision reasoning", 4000),
    verificationNeed: text(input.verificationNeed, "Verification needed", 2000),
    owner: text(input.owner, "Follow-up team", 120),
    role: text(input.role, "Reviewer role", 120),
  };
}

function parseRecords(raw: string | null): MaeSaiReviewRecord[] {
  if (raw === null) return [];
  const value: unknown = JSON.parse(raw);
  if (!isObject(value) || value.schema !== REVIEW_SCHEMA || !Array.isArray(value.records) || value.records.length > MAX_RECORDS) {
    throw new Error("The saved review history has an unsupported format. It has been preserved without changes.");
  }
  const ids = new Set<string>();
  return value.records.map((item: unknown) => {
    if (!isObject(item)
      || typeof item.id !== "string" || !item.id.startsWith("mae-sai-review:") || ids.has(item.id)
      || typeof item.createdAt !== "string" || !Number.isFinite(Date.parse(item.createdAt))
      || item.caseId !== maeSaiCase.meta.case_id || item.caseVersion !== maeSaiCase.meta.case_version
      || item.packageSha256 !== maeSaiCase.meta.package_sha256
      || item.storageScope !== "device_local" || item.officialWarning !== false) {
      throw new Error("The saved review does not match this case version. It has been preserved without changes.");
    }
    const input = normalizedInput(item as unknown as MaeSaiReviewInput);
    ids.add(item.id);
    return {
      ...input,
      id: item.id,
      createdAt: item.createdAt,
      caseId: item.caseId,
      caseVersion: item.caseVersion,
      packageSha256: item.packageSha256,
      storageScope: "device_local",
      officialWarning: false,
    };
  });
}

/** Read only this evidence revision's local exercise history; never promote it to staff acceptance. */
export function loadMaeSaiReviews(storage?: ReviewStorage): { records: MaeSaiReviewRecord[]; warning?: string } {
  try {
    return { records: parseRecords((storage ?? browserStorage()).getItem(MAE_SAI_REVIEW_STORAGE_KEY)) };
  } catch {
    return { records: [], warning: "Saved reviews could not be read. Existing storage is preserved; no review has been confirmed or sent." };
  }
}

/** Append a decision snapshot and acknowledge it only after the browser storage accepts it. */
export function saveMaeSaiReview(input: MaeSaiReviewInput, storage?: ReviewStorage): { record: MaeSaiReviewRecord; records: MaeSaiReviewRecord[] } {
  const normalized = normalizedInput(input);
  let target: ReviewStorage;
  let records: MaeSaiReviewRecord[];
  try {
    target = storage ?? browserStorage();
    records = parseRecords(target.getItem(MAE_SAI_REVIEW_STORAGE_KEY));
  } catch {
    throw new Error("Review history is unavailable or invalid. It has not been overwritten, and this review has not been saved.");
  }
  if (records.length >= MAX_RECORDS) throw new Error("This device has reached 100 review snapshots. Export the history before starting a new case revision.");
  const record: MaeSaiReviewRecord = {
    ...normalized,
    id: `mae-sai-review:${globalThis.crypto.randomUUID()}`,
    createdAt: new Date().toISOString(),
    caseId: maeSaiCase.meta.case_id,
    caseVersion: maeSaiCase.meta.case_version,
    packageSha256: maeSaiCase.meta.package_sha256,
    storageScope: "device_local",
    officialWarning: false,
  };
  const next = [record, ...records];
  const serialized = JSON.stringify({ schema: REVIEW_SCHEMA, records: next });
  try {
    target.setItem(MAE_SAI_REVIEW_STORAGE_KEY, serialized);
    if (target.getItem(MAE_SAI_REVIEW_STORAGE_KEY) !== serialized) throw new Error("Storage did not confirm this record.");
  } catch {
    throw new Error("Browser storage could not confirm the save. Keep this page open and copy your reasoning; no server has received this review.");
  }
  return { record, records: next };
}

function plain(value: string): string {
  return value.replaceAll(/[\r\n]+/g, " ").replaceAll(/[<>]/g, "");
}

/** Export the selected saved decision with its full source package and recorded scenario values. */
export function exportMaeSaiReview(record: MaeSaiReviewRecord, format: "json" | "markdown"): string {
  const [review] = parseRecords(JSON.stringify({ schema: REVIEW_SCHEMA, records: [record] }));
  const scenario = maeSaiCase.scenarios.find((item) => item.scenario_id === review.scenarioId)!;
  const area = maeSaiCase.areas.find((item) => item.area_id === review.areaId)!;
  const areaScenario = scenario.areas.find((item) => item.area_id === review.areaId)!;
  if (format === "json") {
    return JSON.stringify({
      schema: "floodguard.mae-sai-decision-brief.v1",
      operational_status: "non_operational",
      official_warning: false,
      persistence: "Device-local exercise; no server receipt or authenticated agency approval.",
      review,
      selected_area: area,
      selected_area_scenario: areaScenario,
      selected_scenario: scenario,
      evidence_package: maeSaiCase,
    }, null, 2);
  }
  const total = scenario.overall;
  return [
    "# FloodGuard — Mae Sai historical planning decision",
    "",
    "Historical exercise · non-operational · not an official warning or evacuation instruction.",
    "Device-local record. Reviewer and team are self-described; no authenticated staff approval or server receipt.",
    "",
    "## Decision record",
    `- Record: ${review.id}`,
    `- Saved: ${review.createdAt}`,
    `- Status: ${review.status}`,
    `- Focus area: ${area.name_en} / ${area.name_th} (${area.area_id})`,
    `- Reviewer role: ${plain(review.role)}`,
    `- Follow-up team: ${plain(review.owner)}`,
    `- Decision: ${plain(review.decision)}`,
    `- Reasoning: ${plain(review.reasoning)}`,
    `- Must verify: ${plain(review.verificationNeed)}`,
    "",
    "## Comparison",
    `- Scenario: ${scenario.title} (${scenario.scenario_id})`,
    `- Changed assumption: ${scenario.changed_assumption}`,
    `- Focus-area baseline access loss: ${areaScenario.baseline_people_losing_30_min_access}`,
    `- Focus-area scenario access loss: ${areaScenario.scenario_people_losing_30_min_access}`,
    `- Focus-area change: ${areaScenario.change_people_losing_30_min_access}`,
    `- Focus-area population already underserved before disruption: ${area.baseline.baseline_underserved_30_min}`,
    "- The following overall totals cover the complete compact scenario graph, not just the focus area.",
    `- Baseline people losing 30-minute access: ${total.baseline_people_losing_30_min_access}`,
    `- Scenario people losing 30-minute access: ${total.scenario_people_losing_30_min_access}`,
    `- Change in people losing access: ${total.change_people_losing_30_min_access}`,
    `- Baseline maximum equity-gap ratio: ${total.baseline_max_equity_gap_ratio ?? "unavailable"}`,
    `- Scenario maximum equity-gap ratio: ${total.scenario_max_equity_gap_ratio ?? "unavailable"}`,
    `- Scope: ${maeSaiCase.scope.description}`,
    `- Population basis: ${maeSaiCase.scope.population_basis}`,
    `- FPPS recalculated: false. ${maeSaiCase.scope.priority_scope_note}`,
    "",
    "| Area | Baseline access loss | Scenario access loss | Change |",
    "| --- | ---: | ---: | ---: |",
    ...scenario.areas.map((area) => `| ${area.area_id} | ${area.baseline_people_losing_30_min_access} | ${area.scenario_people_losing_30_min_access} | ${area.change_people_losing_30_min_access} |`),
    "",
    "## Evidence identity",
    `- Case: ${review.caseId}`,
    `- Version: ${review.caseVersion}`,
    `- Package SHA-256: ${review.packageSha256}`,
    `- Observation: ${maeSaiCase.meta.source_timestamp}`,
    `- Source processing: ${maeSaiCase.meta.source_processing_timestamp}`,
    `- Case package generated: ${maeSaiCase.meta.generated_at}`,
    `- Confidence: ${maeSaiCase.meta.confidence_class}`,
    `- Local accuracy: ${maeSaiCase.meta.local_accuracy_status}`,
    `- Scenario run: ${scenario.run_id}`,
    "",
    "## Assumptions and limitations",
    ...[...maeSaiCase.assumptions, ...scenario.assumptions].map((item) => `- ${item}`),
    ...maeSaiCase.validation.not_measured.map((item) => `- Not measured: ${item}`),
    "",
    "## Source inventory",
    ...maeSaiCase.sources.map((source) => `- ${source.path}\n  Role: ${source.role}\n  SHA-256: ${source.sha256}`),
    "",
    "## Next validation steps",
    ...maeSaiCase.validation.required_next_steps.map((item) => `- ${item}`),
    "",
  ].join("\n");
}

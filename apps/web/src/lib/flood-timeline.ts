/**
 * Pure logic for the Mae Sai September 2024 day-by-day flood replay.
 *
 * Mirrors `floodguard.flood_timeline` (Python): water is a HAND threshold
 * reconstruction at an assumed, illustrative river stage. Nothing here is a
 * real-time detector or an official warning. No DOM access in this module.
 */

export type Language = "en" | "th";
export interface Localized { en: string; th: string }

/**
 * The one place the replay's data revision is chosen. Every other asset URL (HAND raster, imagery,
 * vectors) is read from this manifest, and the offline cache inventory and the study-integrity
 * check derive their file lists from it at build time.
 */
export const TIMELINE_MANIFEST_URL = "/studies/mae-sai-2024-timeline/r4/timeline.json";

/** Directory of a manifest URL (with trailing slash); every asset the manifest lists must live under it. */
export function manifestDirectory(manifestUrl: string = TIMELINE_MANIFEST_URL): string {
  return manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
}

/**
 * Data revision the page serves: the manifest's directory name (e.g. "r4"). Tests assert that it equals the manifest's
 * own `revision` field, so the label and the served files cannot drift apart.
 */
export function manifestRevision(manifestUrl: string = TIMELINE_MANIFEST_URL): string {
  return manifestDirectory(manifestUrl).split("/").filter(Boolean).at(-1) ?? "";
}

/** Baked access figures for one shelter set at a keyframe (`days[].stats.access[set]`). */
export interface AccessDayStats { people_lost_access: number; vulnerable_lost: number; non_vulnerable_lost: number }

export interface TimelineStats {
  flooded_km2: number;
  tambon_flooded_km2: Record<string, number>;
  road_km_impassable: number;
  road_km_wet: number;
  facilities_wet: number;
  /** Modelled residents (WorldPop 2020) in reconstructed water: district total (whole people) and per subdistrict (0.1). */
  people_in_water?: number;
  tambon_people_in_water?: Record<string, number>;
  /** Baked evacuation-access figures for a few shelter sets (the replay recomputes every set from the node file). */
  access?: Record<string, AccessDayStats>;
}

export interface TimelineDay { date: string; index: number; phase: string; stage_m: number; stats: TimelineStats }
export interface TimelinePhase { id: string; start: string; end: string; label: Localized; summary: Localized }

export interface TimelineObservation {
  id: string;
  sensor: string;
  kind: "optical" | "radar";
  utc: string;
  local: string;
  label: Localized;
  pass?: string;
  relative_orbit?: number;
}

export interface HashedAsset { href: string; sha256: string; bytes: number }

/** Interpolation knot of the assumed stage: `t` in days since 2024-09-09T00:00 ICT. */
export interface StageAnchor { t: number; stage_m: number }

/** Share of an area that lies inside the model grid. */
export interface AreaCoverage { modelled_km2: number; total_km2: number }

export interface TimelineLayer extends HashedAsset {
  id: string;
  kind: "terrain" | "sentinel-2" | "sentinel-1" | "sentinel-1-change";
  date: string | null;
  scene?: string;
}

export interface TimelineSource { id: string; name: string; licence: string; timestamp: string; attribution: string }

/**
 * WorldPop residents on the water grid: `href` is a greyscale PNG of density codes
 * (code = round(254 * ln(1 + p) / ln(1 + max_per_ha)), p = people per hectare), same size and bounds as the HAND raster.
 * `tambon_histograms[tid][code]` holds the people living on cells of each HAND code.
 */
export interface PopulationInfo extends HashedAsset {
  width: number;
  height: number;
  encoding: string;
  max_per_ha: number;
  tambon_histograms: Record<string, number[]>;
  tambon_totals: Record<string, number>;
  source: string;
  licence: string;
  timestamp: string;
  note: string;
}

/** One field of the little-endian access node file. */
export interface AccessLayoutField { name: string; dtype: string; offset: number; shape?: number[]; note?: string }

/** Evacuation access scenario: per node and shelter set, the stage level at which the walk to a dry shelter is lost. */
export interface AccessInfo {
  nodes: HashedAsset & { count: number; layout: AccessLayoutField[] };
  /** Stage levels (m) the access was evaluated at; `cut_codes` index into this list. */
  levels: number[];
  threshold_m: number;
  travel_mode: string;
  /** Subdistrict ids in `tambon_index` order (1-based). */
  tambons: string[];
  /** Shelter set ids in `cut_codes` row order, e.g. "reported_2024", "plan_1" … "plan_N". */
  sets: string[];
  totals: { population: number; vulnerable: number; non_vulnerable: number };
  scenario_tier: string;
  definition: string;
  /** Confidence class of the access figures, why, and the timestamps of the inputs they rest on. */
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
}

/** OpenStreetMap public building or ground screened as a possible shelter. */
export interface ShelterCandidate {
  id: string;
  kind: string;
  name: string;
  lon: number;
  lat: number;
  source: string;
  footprint_m2: number;
  capacity_est: number | null;
  /** Effective HAND (m) at the site, or null on high ground (never floods under these stages). */
  h: number | null;
  k: number;
  freeboard_m: number | null;
  snap_m: number;
  eligible: boolean;
  /** Screening reasons, e.g. "floods_or_under_freeboard_at_peak", "no_road_within_400m", "outside_model". */
  ineligible_reasons: string[];
  /** Inside the terrain model; false means there is no flood or freeboard result for the site. */
  m: boolean;
  high_ground?: boolean;
}

/** Greedy ranking step k (1-based position in `plan`): the site added and the coverage of the first k sites. */
export interface ShelterPlanEntry {
  candidate_id: string;
  marginal_demand: number;
  cumulative_demand: number;
  cumulative_share: number;
  late_cumulative_share: number;
  /** Residents assigned to each of the first k sites when the plan has k sites. */
  loads: number[];
}

export interface ShelterSourceRecord { title: string; publisher: string; date: string; url: string; quote_or_paraphrase: string }

/** Model check of a reported shelter's location against the reconstruction at the modelled peak. */
export interface ShelterModelCheck {
  h: number | null;
  k: number;
  freeboard_m: number | null;
  snap_m: number;
  /** Inside the terrain model; false means the check has no flood result. */
  m: boolean;
  high_ground: boolean;
  floods_at_modelled_peak: boolean;
}

/** What a reported site was used for in September 2024. */
export type ReportedRole = "shelter" | "relief_command_centre";

/** Shelter reported in use during the September 2024 flood (public reporting, not a model output). */
export interface ReportedShelter {
  id: string;
  name_en: string;
  name_th: string;
  type: string;
  tambon: string;
  lon: number | null;
  lat: number | null;
  location_method: string;
  location_evidence: string | null;
  location_confidence: string;
  period_used: string | null;
  evidence_strength: string;
  /** Null when no source reported a capacity or head count. */
  reported_capacity_or_occupancy: string | null;
  notes: string | null;
  sources: ShelterSourceRecord[];
  role: ReportedRole;
  /** First reported use: a local date ("2024-09-21") or a bound ("2024-09-15 or earlier"). */
  first_use: string;
  /** Whether the "reported_2024" access set counts the site (only located sites can be counted). */
  in_access_set: boolean;
  /** Why the site is or is not in that set. */
  access_set_note: string;
  model_check: ShelterModelCheck | null;
}

export interface ShelterMethod {
  evacuation_stage_m: number;
  late_evacuation_stage_m: number;
  threshold_m: number;
  freeboard_m: number;
  peak_stage_m: number;
  m2_per_person: number;
  usable_floor_share: number;
  max_plan_sites: number;
  snap_max_m: number;
}

/**
 * One capacity bound of a capacity-aware plan row, in whole residents: the site's capacity under that bound, the
 * residents it adds when it joins the plan (`load`, never above `capacity`), the running total `served` by the plan so
 * far, and `overflow` = demand − `served` (residents with no site in reach or no place left).
 */
export interface CapacityBound { capacity: number; load: number; served: number; overflow: number }

/** Where a site's upper-bound capacity comes from: its own footprint estimate, or a median when it has none. */
export type UpperCapacityBasis = "estimate" | "kind_median" | "all_kinds_median" | "none";

/** One site of a ranking counted with capacity. The lower bound counts an unknown capacity as 0. */
export interface CapacityPlanRow {
  candidate_id: string;
  capacity_est: number | null;
  /** "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified", or "unknown". */
  capacity_basis: string;
  upper_capacity_basis: UpperCapacityBasis;
  /** Residents within the walking limit of the plan so far, capacity ignored (capacity-aware ranking only). */
  within_reach?: number;
  lower: CapacityBound;
  upper: CapacityBound;
}

export interface CapacityTotal { capacity: number; served: number; overflow: number }

/**
 * Capacity-aware shelter plan (T1 scenario, model): who fits where under two capacity bounds. Demand is every resident
 * of a home that floods at the modelled peak (an upper bound) and capacity is an unverified footprint estimate, so the
 * sites are candidates to verify.
 */
export interface CapacityAwarePlan {
  scenario_tier: string;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  assumptions: string[];
  demand_people: number;
  demand_basis: string;
  capacity_basis: { estimate: string; unknown: string };
  /** `note` (later r4 bakes): why neither bound is a limit on who fits. */
  bounds: { lower: string; upper: string; note?: string };
  method: string;
  /** The capacity-aware ranking holds at most this many sites, and ends when the next site adds less than this share of demand. */
  max_plan_sites: number;
  min_gain_share: number;
  /** Median capacity estimate per site kind (the upper bound of a site of that kind without an estimate). */
  kind_median_capacity: Record<string, number>;
  all_kinds_median_capacity: number | null;
  /** The capacity-aware ranking: the first k rows are the plan for k sites. */
  plan: CapacityPlanRow[];
  /** The coverage ranking (`ShelterInfo.plan`) counted with capacity, row for row. */
  coverage_plan: CapacityPlanRow[];
  all_eligible: { sites: number; sites_with_estimate: number; within_reach: number; lower: CapacityTotal; upper: CapacityTotal };
}

/** The coverage ranking repeated at one what-if design stage. */
export interface WhatIfStage {
  stage_m: number;
  /** True for the stage the replay itself uses (its modelled peak). */
  modelled_peak: boolean;
  demand_people: number;
  eligible_count: number;
  uncoverable_people: number;
  knee_k: number | null;
  /** Ranked candidate ids; the first k are the plan for k sites at this stage. */
  plan: string[];
  cumulative_demand: number[];
}

/** Plan robustness: what-if levels around an illustrative peak, not return periods. */
export interface PlanRobustness {
  scenario_tier: string;
  label: string;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  assumptions: string[];
  method: string;
  stages: WhatIfStage[];
  /** `core_by_k[k - 1]`: the sites among the first k at every stage. */
  core_by_k: string[][];
}

/** Role code of the person who checked a candidate: a role, never a name. */
export type CheckerRole = "ddpm_officer" | "local_government_officer" | "village_leader" | "site_staff" | "project_team" | "other_local_contact";

/**
 * One candidate a local checker reported on. Whitelisted columns only: no name of a person, no phone or ID number and
 * no free text. The checker's access notes are never published; `access_notes_given` says only that one was written.
 */
export interface ShelterCheckRow {
  candidate_id: string;
  usable_as_shelter: boolean;
  verified_capacity: number | null;
  checked_by_role: CheckerRole;
  /** Date of the check, YYYY-MM-DD. */
  checked_on: string;
  access_notes_given: boolean;
  /** "Checked by <role> on <date>; not an official shelter register". */
  label: string;
}

/**
 * Local check of the shelter candidates through the verification sheet in the export pack. `not_conducted` until a
 * sheet is returned and imported: then `checked` is empty and nothing is implied about any site. A conducted check
 * is reported by role and is never an official shelter register; it carries its confidence, the reason for it and
 * its assumptions, one of which says that the rankings and the capacity figures do not use the check.
 */
export interface ShelterVerification {
  status: "not_conducted" | "conducted";
  label_template: string;
  /** Id of the blank sheet in `exports.files`. */
  sheet: string;
  candidate_set_sha256: string;
  candidates_listed: number;
  statement: string;
  /** Present on a conducted check: its confidence class, why, and what the check does and does not say. */
  confidence?: string;
  confidence_reason?: string;
  assumptions?: string[];
  source_timestamp?: string;
  imported_on?: string;
  returned_file_sha256?: string;
  counts?: { checked: number; usable_yes: number; usable_no: number; with_verified_capacity: number };
  checked: ShelterCheckRow[];
}

/** One download file of the export pack: a table or a map layer written from the replay's modelled blocks. */
export interface ExportFile extends HashedAsset {
  id: string;
  name: string;
  media_type: "text/csv" | "application/geo+json" | "text/plain";
  title: Localized;
  /** Evidence lanes of the file's content: "SCN" (model) and, for the reported-shelter files, "REP". */
  lanes: EvidenceLane[];
  licence: string;
  source_ids: string[];
  rows?: number;
  /** Provenance lines before the column header of a CSV. */
  header_lines?: number;
}

/**
 * The export pack (r4 on): tables and one map layer for spreadsheet and GIS users. T1 scenario (model), modelled and
 * not observed; one licence lineage per file. The files are downloads: outside the replay's precache budget.
 */
export interface ExportPack {
  scenario_tier: string;
  tier: string;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  purpose: string;
  licence: string;
  licence_rule: string;
  header: { csv: string; geojson: string; why_in_the_file: string };
  offline: string;
  assumptions: string[];
  folder: string;
  file_count: number;
  bytes: number;
  files: ExportFile[];
}

export interface ShelterInfo {
  candidates: ShelterCandidate[];
  plan: ShelterPlanEntry[];
  knee_k: number;
  demand_people: number;
  uncoverable_people: number;
  eligible_count: number;
  reported: ReportedShelter[];
  method: ShelterMethod;
  /** Capacity-aware plan under two capacity bounds (absent from a manifest baked before it existed). */
  capacitated?: CapacityAwarePlan;
  /** The coverage ranking at what-if levels around the illustrative peak (absent from an older manifest). */
  robustness?: PlanRobustness;
  /** Local check of the candidates through the verification sheet (absent from an older manifest). */
  verification?: ShelterVerification;
  /** Confidence class of the candidate screening and plan, why, and the timestamps behind the shelter figures. */
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  /** Status of the reported-sites list (public reporting, not an official register). */
  reported_status: string;
  /** Date (YYYY-MM-DD) the reported-sites list was compiled. */
  reported_compiled: string;
  /** Which reported sites the "reported_2024" access set counts. */
  reported_access_set_rule: string;
}

/**
 * How an external figure relates to the reconstruction: a calibration anchor set a stage knot (the model agrees with
 * it by construction); a calibration-informed magnitude check compares sizes, but the figure was known while the
 * stage keyframes were tuned, so agreement is not independent evidence; an independent magnitude check tests the size
 * of the modelled extent against a figure that played no part in tuning.
 */
export type ExternalCheckRole = "calibration_anchor" | "calibration_informed_magnitude_check" | "independent_magnitude_check";

/** Size comparison of the reconstruction with an external (observed or reported) product. */
export interface ExternalCheck {
  id: string;
  observed: string;
  reported_km2: number;
  reported_people?: number;
  reported_text: string;
  scope?: string;
  role: ExternalCheckRole;
  /** Model figures comparable with the external one (for a windowed product, the largest extent within its window). */
  model_km2: number;
  model_people_in_water?: number;
  model_stage_m?: number;
  /** Which model extent `model_*` describes, when the external product covers a time window. */
  model_window?: string;
  /** Model figures at the modelled peak, for reference when the comparison window excludes it. */
  model_peak_km2?: number;
  model_peak_people_in_water?: number;
  use: string;
  urls: string[];
}

export interface ExternalReference { name: string; url: string; note?: string; id?: string }

/**
 * One NOAA/GMU VIIRS daily flood map, clipped to the replay bounds: an observation (375 m optical, daily composite
 * of early-afternoon passes), compared with the reconstruction in clear-sky district pixels only. `href` is a
 * pre-coloured RGBA PNG on the replay bounds (~375 m pixels); `t` is the nominal pass time in replay days.
 */
export interface ViirsDay extends HashedAsset {
  date: string;
  nominal_local_time: string;
  t: number;
  /** Share (0-1) of the district hidden by cloud. */
  cloud_share: number;
  /** Clear-sky district area (km²) the comparison uses. */
  clear_km2: number;
  /** VIIRS flood area (sum of flood fraction x pixel area) in the clear pixels, permanent water excluded. */
  viirs_flood_km2_clear: number;
  model_stage_m: number;
  /** Modelled out-of-channel wet area averaged onto the same clear 375 m pixels. */
  model_flood_km2_clear: number;
  /** Modelled wet area over the whole district at the same moment, cloud or not. */
  model_flood_km2_district: number;
  width: number;
  height: number;
  source_file: string;
}

export interface ViirsDaily {
  product: string;
  source_url: string;
  licence: string;
  attribution: string;
  /** Label per VIIRS class code ("1" cloud, "3" normal open water, "4"-"7" flood-fraction bins, "transparent"). */
  legend: Record<string, string>;
  nominal_overpass: string;
  comparison_rule: string;
  caveat: string;
  /** Which fields of each day are model output placed beside the agency product (later r4 bakes). */
  model_fields?: { names: string[]; evidence_tier: string; note: string };
  days: ViirsDay[];
}

/** One Sentinel-2 L2A scene of the water check: its acquisition time, how much of the district it saw, and the area found. */
export interface S2CrosscheckScene {
  id: string;
  role: "pre_event" | "event";
  scene: string;
  /** Acquisition time (UTC). */
  source_timestamp: string;
  local_time: string;
  clear_km2: number;
  /** Share (0-1) of the district the scene saw clearly. */
  clear_share: number;
  /** Water or saturated mud (MNDWI above 0) in the clear pixels, mapped channels left out; null when nothing was clear. */
  water_km2: number | null;
  scl_class_km2: Record<string, number>;
}

/** One sensitivity row of the water check: the same figures under a stricter clear rule or threshold. */
export interface S2CrosscheckSensitivity {
  id: string;
  rule: string;
  event_clear_share: number;
  event_water_km2: number | null;
  pre_event_clear_share: number;
  pre_event_water_km2: number | null;
  new_water_km2: number | null;
  /** T1 scenario (model) value placed beside the observation. */
  model_agreement_iou: number | null;
}

/**
 * Sentinel-2 water check (later r4 bakes): water or saturated mud on the clear pixels of the scene before the flood
 * and of the first scene after the river fell. `scenes` and `change` are observed; `model_at_event_scene` and the
 * `model_` field of each sensitivity row are T1 scenario (model) values. The comparison is indicative.
 */
export interface S2Crosscheck {
  product: string;
  licence: string;
  attribution: string;
  /** What a positive index is called on the page: "water or saturated mud", never a flood extent. */
  label: string;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  index: string;
  water_rule: string;
  clear_rule: string;
  permanent_water_rule: string;
  scope: string;
  comparison: "indicative";
  comparison_rule: string;
  caveat: string;
  /** What the observation is consistent with; it states no cause and no land cover. */
  reading: string;
  /**
   * Present when the next VIIRS day with clear sky (`viirs_daily.days`, by date) shows less flood water than the
   * model: what that is consistent with for the day of the scene. The figures stay in `viirs_daily`.
   */
  following_day?: { viirs_date: string; reading: string };
  model_fields: { paths: string[]; evidence_tier: string; note: string };
  assumptions: string[];
  resolution_m: number;
  threshold: number;
  district_km2: number;
  permanent_water_km2: number;
  scenes: S2CrosscheckScene[];
  change: {
    pre_event_scene: string;
    event_scene: string;
    both_clear_km2: number;
    event_water_km2: number | null;
    pre_event_water_km2: number | null;
    /** Water or saturated mud on the event date that was not there before, where both dates are clear. */
    new_water_km2: number | null;
    no_longer_water_km2: number | null;
  };
  model_at_event_scene: {
    model_local_time: string;
    model_t: number;
    model_stage_m: number;
    model_flood_km2_district: number;
    /** Modelled out-of-channel water in the pixels the event scene saw clearly. */
    model_flood_km2_clear: number;
    /**
     * The same where both scenes are clear: the figure to set beside `change.new_water_km2`, which is counted in
     * those pixels (absent from a manifest baked before it existed).
     */
    model_flood_km2_both_clear?: number;
    model_overlap_km2: number;
    model_union_km2: number;
    model_agreement_iou: number | null;
    model_share_of_observed_water_reached: number | null;
    model_share_inside_observed_water: number | null;
  };
  sensitivity: S2CrosscheckSensitivity[];
}

/** Hourly rain gauge (observed forcing, not flooding). */
export interface RainStation {
  code: string;
  name_en: string;
  name_th: string;
  lat: number;
  lon: number;
  total_mm: number;
  max_hour_mm: number;
  missing_hours: number;
}

export interface Rainfall {
  stations: RainStation[];
  /** Per station code, one value per replay hour (index 0 = 9 Sep 00:00-01:00 ICT); null is a missing hour. */
  hourly_mm: Record<string, (number | null)[]>;
  source: string;
  source_url: string;
  licence: string;
  units: string;
  note: string;
}

export interface TimelineManifest {
  study_id: string;
  revision: string;
  data_mode: string;
  official_warning: false;
  real_time: false;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  timezone: string;
  area: Localized;
  bounds: [[number, number], [number, number]];
  /**
   * HAND code raster: 8-bit greyscale (grey = code), or RGB with R = the effective HAND code and, when
   * `depth_factor_channel` is "G", G = round(k * 255) for a per-cell depth factor k in (0, 1]
   * (wet iff the code is the channel or code * step < stage; depth = k * (stage - code * step); channel depth = k * stage).
   * Without a factor channel k = 1 everywhere.
   */
  hand: HashedAsset & {
    width: number;
    height: number;
    step_m: number;
    channel_code: number;
    never_code: number;
    stream_threshold_km2?: number;
    depth_factor_channel?: string | null;
    /** How k was derived: clip((A / reference_km2) ** exponent, floor, 1) from each channel's upstream area A. */
    depth_factor?: { exponent: number; floor: number; reference_km2: number; reference: string };
    /**
     * Channel of an RGB raster that flags low-confidence water ("B" from r3 on): 255 on filled pits and dead-flat
     * ground less than 0.1 m above its channel, which reads as wet at almost any stage. Absent or null: no flag.
     */
    low_confidence_channel?: string | null;
    low_confidence?: { rule: string; meaning: string };
    /** District area wet at the modelled peak and the part of it that is flagged low-confidence (km²). */
    low_confidence_share?: { peak_flooded_km2: number; low_confidence_km2: number };
  };
  impassable_depth_m: number;
  pixel_area_m2: number;
  /** Sorted stage knots (local-noon keyframes plus sub-daily anchors); the replay interpolates over these. */
  stage_anchors: StageAnchor[];
  /** Modelled versus total area per subdistrict id. */
  tambon_coverage: Record<string, AreaCoverage>;
  /** District land inside the model grid, and why the rest is not modelled. */
  model_coverage: { modelled_km2: number; district_km2: number; reason: string };
  facilities_count: { total: number; modelled: number };
  roads_not_modelled_km: number;
  phases: TimelinePhase[];
  days: TimelineDay[];
  observations: TimelineObservation[];
  layers: TimelineLayer[];
  vectors: Record<"tambons" | "roads" | "facilities", HashedAsset & { features: number }>;
  tambon_histograms: Record<string, number[]>;
  s1_anchor: {
    threshold_db_dn: number;
    newly_dark_km2: number;
    best_fit_stage_m: number;
    best_fit_model_km2: number;
    iou_at_best_fit: number;
    scope?: string;
    reconstruction_stage_at_pass_m: number;
    /** From r4: the recession keyframes were tuned to this pass, so the comparison is calibration-informed. */
    role?: ExternalCheckRole;
    use?: string;
    source_timestamp?: string;
  };
  sources: TimelineSource[];
  assumptions: string[];
  limitations: string[];
  /** Residents on the water grid (WorldPop); absent in revisions without population. */
  population?: PopulationInfo;
  /** Evacuation access scenario (T1 model); absent in revisions without it. */
  access?: AccessInfo;
  /** Shelter candidates, ranked plan and shelters reported in use in 2024. */
  shelters?: ShelterInfo;
  external_checks?: ExternalCheck[];
  external_references?: ExternalReference[];
  gauge_note?: string;
  /** Observed daily VIIRS flood maps and their clear-sky comparison with the model; absent before r3. */
  viirs_daily?: ViirsDaily;
  /** Sentinel-2 water check for the first clear scene after the river fell (15 Sep); absent before the later r4 bakes. */
  s2_crosscheck?: S2Crosscheck;
  /** Observed hourly rain at nearby gauges (forcing, not flooding); absent before r3. */
  rainfall?: Rainfall;
  /** Download files for spreadsheet and GIS users (absent from a manifest baked before the pack existed). */
  exports?: ExportPack;
  // --- Evidence envelope (r4 on). Every field is optional so that an r3-shaped manifest, which a client may still
  // hold in its offline cache, is read too; `parseTimelineManifest` fills the defaults that revision implies. ---
  schema_version?: number;
  /** Declared bake time (ISO 8601 with an offset), or the newest dated input; never a machine-clock reading. */
  generated_at?: string;
  generated_at_basis?: "declared" | "newest_input_timestamp";
  generated_at_note?: string;
  /** Null in a committed manifest: a file cannot hold the hash of the commit that adds it. */
  git_commit?: string | null;
  git_commit_reason?: string;
  data_version?: string;
  /** Same value as `data_mode`, which stays as an alias. */
  dataset_mode?: string;
  operational_status?: "non_operational";
  can_feed_decision_layer?: false;
  /** Always null: the replay computes no priority score and assigns no action class. */
  accepted_fpps?: null;
  accepted_action_class?: null;
  protocol_sha256?: null;
  protocol_sha256_reason?: string;
  permitted_use?: string;
  reason_blocked?: string;
  /** Mirrors `confidence`. */
  confidence_class?: string;
  confidence_basis?: string[];
  source_name?: string;
  event_time?: { start: string; end: string; timezone: string; note?: string };
  /** What the top-level `source_timestamp` span covers, and which inputs are dated elsewhere. */
  source_timestamp_note?: string;
  lanes?: Partial<Record<EvidenceLane, string>>;
  evidence_blocks?: EvidenceBlock[];
  exploratory_knowledge?: ExploratoryKnowledge;
  publication_eligibility?: PublicationEligibility;
  input_sha256?: InputHash[];
}

/** Evidence lane of a manifest block: scenario (model), observed, calibration, season envelope, reported, context, reference. */
export type EvidenceLane = "SCN" | "OBS" | "CAL" | "SCN-ENV" | "REP" | "CTX" | "REF";

/** Lane, tier, temporal relation and source timestamp of one part of the manifest (`covers` lists its paths). */
export interface EvidenceBlock {
  id: string;
  covers: string[];
  lane: EvidenceLane;
  evidence_tier: string;
  temporal_relation: string;
  source_timestamp: string;
  note?: string;
  season_window?: string;
  shown?: boolean;
  /**
   * Paths inside the covered content that hold T1 scenario (model) values placed beside it for comparison, e.g.
   * "viirs_daily.days[].model_flood_km2_clear". They are not in this block's lane.
   */
  scenario_fields?: string[];
}

/** An external figure and whether it was used, or already known, while the stage keyframes were tuned. */
export interface ExploratoryKnowledgeItem {
  id: string;
  /** "not_used_for_tuning": not used, and the build history does not record whether it was known at the time. */
  relation: "used_for_tuning" | "known_during_tuning" | "computed_after_keyframes_final" | "not_used_for_tuning";
  /** Null only where the build history does not record the order (relation "not_used_for_tuning"). */
  known_during_tuning: boolean | null;
  statement: string;
}
export interface ExploratoryKnowledge { purpose: string; items: ExploratoryKnowledgeItem[]; depth_factor: string; rule: string }

/** Licence and display status of one input. `shown: false` means the input is listed but not on the page. */
export interface PublicationInput {
  id: string;
  name: string;
  licence: string;
  licence_stated: boolean;
  shown: boolean;
  terms: string;
  status?: string;
  rights_record?: string;
}
export interface PublicationEligibility { status: string; scope: string; conditions: string[]; inputs: PublicationInput[] }
export interface InputHash { root: string; path: string; bytes: number; sha256: string }

export class TimelineManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimelineManifestError";
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const MANIFEST_TEXT_KEYS = ["study_id", "revision", "confidence", "confidence_reason", "source_timestamp", "timezone"] as const;
const MANIFEST_LIST_KEYS = ["stage_anchors", "phases", "days", "observations", "layers", "sources", "assumptions", "limitations"] as const;
const MANIFEST_OBJECT_KEYS = ["area", "hand", "vectors", "tambon_histograms", "tambon_coverage", "model_coverage", "s1_anchor"] as const;

/**
 * Read a fetched manifest. It accepts the r4 shape (with the evidence envelope) and the r3 shape that a client may
 * still hold in its offline cache, and returns one shape for the page: `dataset_mode`, `confidence_class`,
 * `operational_status` and the null `accepted_*` fields are filled in when an older manifest lacks them.
 *
 * It refuses, with a `TimelineManifestError`, a document that is not a replay manifest, and one that claims what the
 * replay must never claim: an official alert, a current (not historical) product, an operational status, a feed
 * into the decision layer, or an accepted priority score or action class.
 */
export function parseTimelineManifest(value: unknown): TimelineManifest {
  if (!isRecord(value)) throw new TimelineManifestError("The replay manifest is not an object.");
  for (const key of MANIFEST_TEXT_KEYS) {
    if (typeof value[key] !== "string" || !value[key]) throw new TimelineManifestError(`The replay manifest lacks ${key}.`);
  }
  for (const key of MANIFEST_LIST_KEYS) {
    if (!Array.isArray(value[key])) throw new TimelineManifestError(`The replay manifest lacks the ${key} list.`);
  }
  for (const key of MANIFEST_OBJECT_KEYS) {
    if (!isRecord(value[key])) throw new TimelineManifestError(`The replay manifest lacks ${key}.`);
  }
  if ((value.stage_anchors as unknown[]).length === 0 || (value.days as unknown[]).length === 0) {
    throw new TimelineManifestError("The replay manifest has no stage anchors or no days.");
  }
  if (value.official_warning !== false || value.real_time !== false) {
    throw new TimelineManifestError("The replay manifest must be marked as historical and as not an official warning.");
  }
  if (value.accepted_fpps != null || value.accepted_action_class != null) {
    throw new TimelineManifestError("The replay manifest carries an accepted score or action class; the replay shows neither.");
  }
  if (value.operational_status !== undefined && value.operational_status !== "non_operational") {
    throw new TimelineManifestError("The replay manifest must be non-operational.");
  }
  if (value.can_feed_decision_layer !== undefined && value.can_feed_decision_layer !== false) {
    throw new TimelineManifestError("The replay manifest must not feed the decision layer.");
  }
  const mode = typeof value.dataset_mode === "string" ? value.dataset_mode : value.data_mode;
  if (typeof mode !== "string" || !mode) throw new TimelineManifestError("The replay manifest lacks dataset_mode.");
  if (typeof value.data_mode === "string" && value.data_mode !== mode) throw new TimelineManifestError("data_mode must mirror dataset_mode.");
  const confidenceClass = typeof value.confidence_class === "string" ? value.confidence_class : value.confidence;
  if (confidenceClass !== value.confidence) throw new TimelineManifestError("confidence_class must mirror confidence.");
  return {
    ...value,
    dataset_mode: mode,
    data_mode: mode,
    confidence_class: confidenceClass,
    operational_status: "non_operational",
    can_feed_decision_layer: false,
    accepted_fpps: null,
    accepted_action_class: null,
  } as unknown as TimelineManifest;
}

/** Evidence blocks whose `covers` name `path` exactly (for example "access" or "external_checks[unosat-3991]"). */
export function evidenceBlocksFor(manifest: Pick<TimelineManifest, "evidence_blocks">, path: string): EvidenceBlock[] {
  return (manifest.evidence_blocks ?? []).filter((block) => block.covers.includes(path));
}

/**
 * Licence rows for the Sources panel: the manifest's `publication_eligibility.inputs` (r4 on), with the inputs that
 * are listed but not shown last. An older manifest has none; its licences stay on the source lines.
 */
export function licenceRows(manifest: Pick<TimelineManifest, "publication_eligibility">): PublicationInput[] {
  const rows = manifest.publication_eligibility?.inputs ?? [];
  return [...rows.filter((row) => row.shown), ...rows.filter((row) => !row.shown)];
}

const SHA256_PATTERN = /^[a-f0-9]{64}$/;
/** Manifest key of the export pack: its files are downloads, not part of the replay's precache set. */
export const EXPORT_PACK_KEY = "exports";

function hashedAssets(source: unknown): HashedAsset[] {
  const found = new Map<string, HashedAsset>();
  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    if (typeof record.href === "string" && typeof record.sha256 === "string" && SHA256_PATTERN.test(record.sha256)
      && typeof record.bytes === "number" && !found.has(record.href)) {
      found.set(record.href, { href: record.href, sha256: record.sha256, bytes: record.bytes });
    }
    Object.values(record).forEach(visit);
  };
  visit(source);
  return [...found.values()];
}

/**
 * Every hashed asset of the replay's precache set (`{ href, sha256, bytes }` anywhere in the manifest: HAND raster,
 * imagery layers, vectors, and any record a later revision adds), first occurrence per href. The top-level export
 * pack is left out: its files are downloads with a budget of their own (see `manifestExportAssets`).
 */
export function manifestAssets(manifest: unknown): HashedAsset[] {
  if (!isRecord(manifest)) return hashedAssets(manifest);
  return hashedAssets(Object.fromEntries(Object.entries(manifest).filter(([key]) => key !== EXPORT_PACK_KEY)));
}

/** The export pack's files (`exports.files`), first occurrence per href; empty for a manifest without a pack. */
export function manifestExportAssets(manifest: unknown): HashedAsset[] {
  const pack = isRecord(manifest) ? manifest[EXPORT_PACK_KEY] : null;
  return isRecord(pack) ? hashedAssets(pack.files ?? []) : [];
}

/**
 * File size for a download link, in decimal units with the unit a spreadsheet user knows: "342 kB", "1.2 MB".
 * Below 1 kB the bytes are given as they are.
 */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1000) return `${Math.round(bytes)} B`;
  if (bytes < 999_500) return `${Math.round(bytes / 1000)} kB`;
  return `${(bytes / 1e6).toFixed(1)} MB`;
}

/** Minimal GeoJSON shapes used by the replay (avoids a hard dependency on @types/geojson). */
export interface GeoFeature<G, P> { type: "Feature"; geometry: G; properties: P }
export interface GeoCollection<G, P> { type: "FeatureCollection"; features: GeoFeature<G, P>[] }
export type LineGeometry = { type: "LineString"; coordinates: [number, number][] };
export type PointGeometry = { type: "Point"; coordinates: [number, number] };
export type AreaGeometry = { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
/**
 * Road piece: class, lowest sampled (effective) HAND (m, `null` never floods), `m` = inside the model grid,
 * length (m), subdistrict, optional OSM name, and optional closure factor `k` (absent = 1). `k` is an equivalent
 * factor, not a physical depth factor: the piece is wet once the stage exceeds `h` and impassable from the earliest
 * stage at which any of its 10 m samples reaches the threshold, which is `h + threshold / k`.
 */
export interface RoadProps { c: string; h: number | null; m: boolean; len: number; t: string; n?: string; k?: number }
/**
 * Candidate facility: `m` = inside the model grid; `h` lowest (effective) HAND (m) or `null` when it never floods;
 * optional depth factor `k` at that lowest sample (so `h * k` is its physical height above drainage).
 */
export interface FacilityProps { id: string; type: string; n: string; t: string; h: number | null; m: boolean; k?: number }
export interface TambonProps { id: string; en: string; th: string }

export type RoadState = "dry" | "wet" | "impassable";

export const DAY_MS = 86_400_000;
const ICT_OFFSET_MS = 7 * 3_600_000;
/** 2024-09-09T00:00+07:00, the replay origin (t = 0). */
export const TIMELINE_EPOCH_MS = Date.UTC(2024, 8, 8, 17);
/** Replay span in days (9 Sep 00:00 to 20 Sep 00:00 ICT). */
export const TIMELINE_END_T = 11;

/** Days since 2024-09-09T00:00 ICT for an instant (Date, ISO string with offset, or epoch ms). */
export function tFromDate(input: Date | string | number): number {
  const ms = input instanceof Date ? input.getTime() : typeof input === "string" ? Date.parse(input) : input;
  return (ms - TIMELINE_EPOCH_MS) / DAY_MS;
}

/** Days since the replay origin for local ICT midnight of a `YYYY-MM-DD` date. */
export function tFromLocalDate(isoDate: string): number {
  return tFromDate(`${isoDate}T00:00:00+07:00`);
}

/** Instant for a replay position. */
export function dateFromT(t: number): Date {
  return new Date(TIMELINE_EPOCH_MS + t * DAY_MS);
}

/**
 * Assumed stage at replay position `t`: linear interpolation over the sorted `stage_anchors`
 * knots, held constant outside them (same as `numpy.interp` in `floodguard.flood_timeline.stage_at`).
 */
export function stageAt(t: number, anchors: readonly StageAnchor[]): number {
  const n = anchors.length;
  if (n === 0) throw new Error("at least one stage anchor is required");
  if (Number.isNaN(t)) return Number.NaN;
  if (t <= anchors[0].t) return anchors[0].stage_m;
  if (t >= anchors[n - 1].t) return anchors[n - 1].stage_m;
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (anchors[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = anchors[lo];
  const b = anchors[hi];
  if (t === a.t) return a.stage_m;
  const slope = (b.stage_m - a.stage_m) / (b.t - a.t);
  return slope * (t - a.t) + a.stage_m;
}

/** Whole local hours since the replay origin for `t`; the one quantiser used by the slider, readout and day buttons. */
export function hourIndex(t: number): number {
  return Math.floor(t * 24 + 1e-6);
}

/** Phase covering replay position `t` (phases span local start 00:00 to end 24:00), clamped to the ends. */
export function phaseAt<P extends Pick<TimelinePhase, "start" | "end">>(t: number, phases: readonly P[]): P {
  if (phases.length === 0) throw new Error("at least one phase is required");
  for (const phase of phases) {
    if (t >= tFromLocalDate(phase.start) && t < tFromLocalDate(phase.end) + 1) return phase;
  }
  return t < tFromLocalDate(phases[0].start) ? phases[0] : phases[phases.length - 1];
}

/** Out-of-channel flooded km² implied by a 256-bin HAND code histogram at `stage` (codes 1..254 only). */
export function floodedKm2(histogram: readonly number[], stage: number, step: number, pixelAreaM2: number): number {
  if (histogram.length !== 256) throw new Error("histogram must have 256 bins");
  let cells = 0;
  for (let code = 1; code < 255; code += 1) {
    if (code * step < stage) cells += histogram[code];
  }
  return (cells * pixelAreaM2) / 1e6;
}

/**
 * Residents on out-of-channel wet cells at `stage` from a 256-bin people-by-HAND-code histogram: the sum of
 * bins 1..254 with code * step < stage (channel and never codes excluded, like the flooded area).
 */
export function peopleInWater(histogram: readonly number[], stage: number, step: number): number {
  if (histogram.length !== 256) throw new Error("histogram must have 256 bins");
  let people = 0;
  for (let code = 1; code < 255; code += 1) {
    if (code * step < stage) people += histogram[code];
  }
  return people;
}

/**
 * Road state from its lowest sampled (effective) HAND (m); `null` never floods under these keyframes.
 * k * (stage - HAND) is rounded to 1e-6 m like Python `round(x, 6)` (so 3.5 - 3.2 counts as 0.3 m):
 * impassable when it reaches `impassableDepthM`, wet when it is above 0, else dry — the same rule as
 * `floodguard.flood_timeline.road_state` (k = 1 unless the piece carries a factor). For a road piece, k is the
 * equivalent closure factor (h + threshold / k is its earliest per-sample closure), not a physical depth factor.
 */
export function roadState(minHandM: number | null, stage: number, impassableDepthM = 0.3, depthFactorK = 1): RoadState {
  if (minHandM === null) return "dry";
  const depth = Math.round(depthFactorK * (stage - minHandM) * 1e6) / 1e6;
  if (depth >= impassableDepthM) return "impassable";
  if (depth > 0) return "wet";
  return "dry";
}

/** Reconstructed depth (m) at a candidate facility, k * (stage - HAND), or 0 when dry / never flooding. */
export function facilityDepth(minHandM: number | null, stage: number, depthFactorK = 1): number {
  return minHandM === null ? 0 : depthFactorK * Math.max(0, stage - minHandM);
}

/** True when a modelled candidate facility is in reconstructed water: stage > HAND (the rule behind the baked `facilities_wet`). */
export function facilityWet(facility: Pick<FacilityProps, "h" | "m">, stage: number): boolean {
  return facility.m && facility.h !== null && stage > facility.h;
}

export interface FacilityInWater<F> { facility: F; depth: number }

/** Modelled candidate facilities in water at `stage`, deepest first (ties by name, then id). */
export function facilitiesInWater<F extends Pick<FacilityProps, "h" | "m" | "id" | "n" | "k">>(
  facilities: readonly F[],
  stage: number,
): FacilityInWater<F>[] {
  return facilities
    .filter((facility) => facilityWet(facility, stage))
    .map((facility) => ({ facility, depth: facilityDepth(facility.h, stage, facility.k ?? 1) }))
    .sort((a, b) => b.depth - a.depth || a.facility.n.localeCompare(b.facility.n) || a.facility.id.localeCompare(b.facility.id));
}

/** Modelled share (0-1) of a subdistrict, or 1 when coverage is unknown. */
export function coverageShare(coverage: AreaCoverage | undefined): number {
  if (!coverage || !(coverage.total_km2 > 0)) return 1;
  return Math.min(1, Math.max(0, coverage.modelled_km2 / coverage.total_km2));
}

/**
 * True when the model grid covers the whole district (to 0.1%, since both areas are rounded), so the page must not
 * describe any district land as unmodelled.
 */
export function coverageComplete(coverage: Pick<TimelineManifest["model_coverage"], "modelled_km2" | "district_km2">): boolean {
  return coverageShare({ modelled_km2: coverage.modelled_km2, total_km2: coverage.district_km2 }) >= 0.999;
}

/**
 * Python `round(value, digits)` for non-negative values: rounds the exact binary value
 * (like `toFixed`), with exact decimal ties going to the even digit.
 */
export function roundLikePython(value: number, digits: number): number {
  const exact = value.toFixed(100);
  const cut = exact.indexOf(".") + 1 + digits;
  if (/^50*$/.test(exact.slice(cut))) {
    const kept = exact.slice(0, cut);
    const lastDigit = Number(kept.replace(".", "").slice(-1));
    const truncated = Number(kept);
    return lastDigit % 2 === 0 ? truncated : Number((truncated + 10 ** -digits).toFixed(digits));
  }
  return Number(value.toFixed(digits));
}

const roundTo = roundLikePython;

/**
 * District statistics at `stage`, identical in shape and rounding to `timeline.json` `days[].stats` (people in water
 * only when the manifest carries population; access figures come from `flood-timeline-evacuation`).
 * Roads and facilities outside the model grid (`m: false`) are excluded from every figure.
 */
export function districtStats(
  manifest: Pick<TimelineManifest, "tambon_histograms" | "hand" | "pixel_area_m2" | "impassable_depth_m" | "population">,
  stage: number,
  roads: readonly Pick<RoadProps, "h" | "len" | "m" | "k">[],
  facilities: readonly Pick<FacilityProps, "h" | "m">[],
): TimelineStats {
  const tambon: Record<string, number> = {};
  let total = 0;
  for (const [id, histogram] of Object.entries(manifest.tambon_histograms)) {
    tambon[id] = roundTo(floodedKm2(histogram, stage, manifest.hand.step_m, manifest.pixel_area_m2), 3);
    total += tambon[id];
  }
  let impassable = 0;
  let wet = 0;
  for (const road of roads) {
    if (!road.m) continue;
    const state = roadState(road.h, stage, manifest.impassable_depth_m, road.k ?? 1);
    if (state === "impassable") impassable += road.len;
    else if (state === "wet") wet += road.len;
  }
  const facilitiesWet = facilities.filter((facility) => facilityWet(facility, stage)).length;
  return {
    flooded_km2: roundTo(total, 3),
    tambon_flooded_km2: tambon,
    road_km_impassable: roundTo(impassable / 1000, 2),
    road_km_wet: roundTo(wet / 1000, 2),
    facilities_wet: facilitiesWet,
    ...(manifest.population ? peopleInWaterStats(manifest.population, stage, manifest.hand.step_m) : {}),
  };
}

/**
 * People in water per subdistrict (rounded to 0.1) and the district total (the sum of those, rounded to whole
 * people like Python `round`), identical to the baked `tambon_people_in_water` and `people_in_water`.
 */
export function peopleInWaterStats(
  population: Pick<PopulationInfo, "tambon_histograms">,
  stage: number,
  step: number,
): { people_in_water: number; tambon_people_in_water: Record<string, number> } {
  const tambon: Record<string, number> = {};
  let total = 0;
  for (const [id, histogram] of Object.entries(population.tambon_histograms)) {
    tambon[id] = roundTo(peopleInWater(histogram, stage, step), 1);
    total += tambon[id];
  }
  return { people_in_water: roundTo(total, 0), tambon_people_in_water: tambon };
}

// --- External checks and assumption caveats ------------------------------------------------------

/**
 * External size figures split by their manifest `role`: calibration anchors (they set a stage knot, so the model
 * agrees with them by construction), calibration-informed magnitude checks (known while tuning) and independent
 * magnitude checks. Manifest order is kept within each group; an unknown role is never shown as independent.
 */
export function externalChecksByRole(checks: readonly ExternalCheck[]): {
  calibration: ExternalCheck[];
  informed: ExternalCheck[];
  independent: ExternalCheck[];
} {
  return {
    calibration: checks.filter((check) => check.role === "calibration_anchor"),
    informed: checks.filter((check) => check.role === "calibration_informed_magnitude_check"),
    independent: checks.filter((check) => check.role === "independent_magnitude_check"),
  };
}

/**
 * Caveat the page shows under a manifest assumption that leaves out something a reader needs (the manifest itself is
 * frozen): GISTDA's report states no time zone, which the onset assumption does not say. Null for every other assumption.
 */
export function assumptionCaveat(text: string): Localized | null {
  if (/GISTDA/.test(text) && /\b18:15\b/.test(text) && !/time zone/i.test(text)) {
    return {
      en: "GISTDA's report does not state a time zone; 18:15 is assumed to be ICT. If it were UTC, this knot would fall at 11 Sep 01:15 ICT.",
      th: "รายงานของ GISTDA ไม่ได้ระบุเขตเวลา จึงสมมุติว่า 18:15 น. เป็นเวลาประเทศไทย (ICT) หากเป็นเวลา UTC จุดนี้จะตรงกับ 11 ก.ย. 01:15 น. ตามเวลาประเทศไทย",
    };
  }
  return null;
}

/**
 * Smallest non-zero flooded extent the reconstruction can produce: the out-of-channel cells of the lowest HAND code
 * that has any cells, i.e. the extent as soon as the stage passes that code. A calibration figure below this area
 * cannot be matched by any stage.
 */
export function smallestFloodedExtent(
  manifest: Pick<TimelineManifest, "tambon_histograms" | "hand" | "pixel_area_m2">,
): { km2: number; stage_m: number } | null {
  const histograms = Object.values(manifest.tambon_histograms);
  for (let code = 1; code < manifest.hand.never_code; code += 1) {
    const cells = histograms.reduce((sum, histogram) => sum + (histogram[code] ?? 0), 0);
    if (cells > 0) return { km2: (cells * manifest.pixel_area_m2) / 1e6, stage_m: code * manifest.hand.step_m };
  }
  return null;
}

/** Relative difference (model − reported) ÷ reported of an external check, or null without a reported figure. */
export function checkDifference(check: Pick<ExternalCheck, "model_km2" | "reported_km2">): number | null {
  return check.reported_km2 > 0 ? (check.model_km2 - check.reported_km2) / check.reported_km2 : null;
}

const sameUrl = (a: string, b: string) => a.trim().replace(/\/+$/, "") === b.trim().replace(/\/+$/, "");

/**
 * External references that this revision has not ingested. A reference whose URL is the source of a block the
 * manifest now carries (the VIIRS daily maps, the rain gauges) is left out, because its frozen note ("not yet
 * ingested") no longer holds; other pages of the same provider (for example an event summary) stay listed.
 */
export function referencesNotIngested(manifest: Pick<TimelineManifest, "external_references" | "viirs_daily" | "rainfall">): ExternalReference[] {
  const ingested = [manifest.viirs_daily?.source_url, manifest.rainfall?.source_url].filter((url): url is string => Boolean(url));
  return (manifest.external_references ?? []).filter((reference) => !ingested.some((url) => sameUrl(url, reference.url)));
}

// --- Observed evidence: VIIRS daily flood maps and hourly rain gauges ---------------------------

/**
 * Colour of each class in the baked VIIRS PNGs (RGBA), in legend order: flood-water fraction bins, normal open water,
 * cloud. Clear dry land is transparent. Mirrors the builder's palette; a unit test checks every baked pixel against it.
 */
export const VIIRS_CLASSES: readonly { code: string; rgba: Rgba; th: string }[] = [
  { code: "4", rgba: [231, 212, 232, 210], th: "น้ำท่วม 1–24%" },
  { code: "5", rgba: [194, 165, 207, 225], th: "น้ำท่วม 25–49%" },
  { code: "6", rgba: [153, 112, 171, 235], th: "น้ำท่วม 50–74%" },
  { code: "7", rgba: [118, 42, 131, 245], th: "น้ำท่วม 75–100%" },
  { code: "3", rgba: [60, 100, 150, 200], th: "แหล่งน้ำเปิดปกติ" },
  { code: "1", rgba: [205, 210, 220, 150], th: "เมฆ (ไม่มีการสังเกต)" },
];

/**
 * The VIIRS daily map on show at replay position `t`: the latest day whose nominal pass (`day.t`) is at or before
 * `t`, for at most one day after that pass and never past the local end of the last mapped date. Null before the
 * first pass, in a gap of more than a day, and after the mapped dates.
 */
export function viirsDayAt<D extends Pick<ViirsDay, "t" | "date">>(t: number, days: readonly D[]): D | null {
  if (days.length === 0 || Number.isNaN(t)) return null;
  let best: D | null = null;
  let lastDate = days[0].date;
  for (const day of days) {
    if (day.date > lastDate) lastDate = day.date;
    if (day.t <= t + 1e-9 && (!best || day.t > best.t)) best = day;
  }
  if (!best || t - best.t >= 1 || t >= tFromLocalDate(lastDate) + 1) return null;
  return best;
}

/** The event scene (after the river fell) and the scene before the flood of a Sentinel-2 water check, or null when either is missing. */
export function s2CrosscheckScenes(check: Pick<S2Crosscheck, "scenes">): { event: S2CrosscheckScene; pre: S2CrosscheckScene } | null {
  const event = check.scenes.find((scene) => scene.role === "event");
  const pre = check.scenes.find((scene) => scene.role === "pre_event");
  return event && pre ? { event, pre } : null;
}

/** Local (ICT) date, `YYYY-MM-DD`, of the event scene of a Sentinel-2 water check; null when the block names none. */
export function s2CrosscheckDate(check: Pick<S2Crosscheck, "scenes">): string | null {
  const scenes = s2CrosscheckScenes(check);
  if (!scenes) return null;
  const ms = Date.parse(scenes.event.source_timestamp);
  return Number.isNaN(ms) ? null : new Date(ms + ICT_OFFSET_MS).toISOString().slice(0, 10);
}

/**
 * The Sentinel-2 water check when the replay position `t` falls on the local day of its event scene (15 Sep), else
 * null: the check is one observation of one day and is shown on that day only.
 */
export function s2CrosscheckAt<C extends Pick<S2Crosscheck, "scenes">>(t: number, check: C | null | undefined): C | null {
  if (!check || Number.isNaN(t)) return null;
  const date = s2CrosscheckDate(check);
  if (!date) return null;
  const start = tFromLocalDate(date);
  return t >= start && t < start + 1 ? check : null;
}

/** Below this area (km²) a VIIRS or model figure reads as "none" (it would print as 0.0). */
export const VIIRS_NONE_KM2 = 0.05;

export type ViirsReadingKind = "no_observation" | "neither" | "model_only" | "viirs_only" | "viirs_larger" | "viirs_smaller" | "similar_size";

/**
 * One-line reading of a day's clear-sky comparison, stating agreement or disagreement plainly. It is a coarse
 * consistency check of size in cloud-free pixels, never a validation of the reconstruction.
 */
export function viirsReading(
  day: Pick<ViirsDay, "cloud_share" | "clear_km2" | "viirs_flood_km2_clear" | "model_flood_km2_clear">,
): { kind: ViirsReadingKind; en: string; th: string } {
  const clear = day.clear_km2.toFixed(1);
  const viirs = day.viirs_flood_km2_clear.toFixed(1);
  const model = day.model_flood_km2_clear.toFixed(1);
  const cloudPct = Math.round(day.cloud_share * 100);
  if (!(day.clear_km2 > 0) || day.cloud_share >= 0.995) {
    return {
      kind: "no_observation",
      en: "Cloud covered the whole district: no observation.",
      th: "เมฆปกคลุมทั้งอำเภอ: ไม่มีการสังเกต",
    };
  }
  const prefix = day.cloud_share >= 0.5
    ? { en: `Mostly cloudy (${cloudPct}% cloud). `, th: `มีเมฆมาก (${cloudPct}%) ` }
    : { en: "", th: "" };
  const viirsNone = day.viirs_flood_km2_clear < VIIRS_NONE_KM2;
  const modelNone = day.model_flood_km2_clear < VIIRS_NONE_KM2;
  const say = (kind: ViirsReadingKind, en: string, th: string) => ({ kind, en: `${prefix.en}${en}`, th: `${prefix.th}${th}` });
  if (viirsNone && modelNone) {
    return say("neither", `Neither VIIRS nor the model shows flood water in the ${clear} km² of clear sky.`,
      `ทั้ง VIIRS และแบบจำลองไม่พบน้ำท่วมในพื้นที่ท้องฟ้าโปร่ง ${clear} ตร.กม.`);
  }
  if (viirsNone) {
    return say("model_only", `VIIRS detected no flood water in the ${clear} km² of clear sky, where the model places ${model} km².`,
      `VIIRS ไม่พบน้ำท่วมในพื้นที่ท้องฟ้าโปร่ง ${clear} ตร.กม. ขณะที่แบบจำลองระบุ ${model} ตร.กม.`);
  }
  if (modelNone) {
    return say("viirs_only", `VIIRS shows ${viirs} km² of flood water in the ${clear} km² of clear sky, where the model has none.`,
      `VIIRS พบน้ำท่วม ${viirs} ตร.กม. ในพื้นที่ท้องฟ้าโปร่ง ${clear} ตร.กม. ขณะที่แบบจำลองไม่มีน้ำท่วมในบริเวณนั้น`);
  }
  const ratio = day.viirs_flood_km2_clear / day.model_flood_km2_clear;
  if (ratio >= 1.5) {
    return say("viirs_larger", `VIIRS ${viirs} km² vs model ${model} km² in the same clear pixels: VIIRS shows about ${ratio.toFixed(1)}× more.`,
      `VIIRS ${viirs} ตร.กม. เทียบกับแบบจำลอง ${model} ตร.กม. ในพิกเซลท้องฟ้าโปร่งเดียวกัน: VIIRS มากกว่าประมาณ ${ratio.toFixed(1)} เท่า`);
  }
  if (ratio <= 1 / 1.5) {
    return say("viirs_smaller", `VIIRS ${viirs} km² vs model ${model} km² in the same clear pixels: VIIRS shows about ${ratio.toFixed(1)}× the model's area.`,
      `VIIRS ${viirs} ตร.กม. เทียบกับแบบจำลอง ${model} ตร.กม. ในพิกเซลท้องฟ้าโปร่งเดียวกัน: VIIRS เป็นประมาณ ${ratio.toFixed(1)} เท่าของแบบจำลอง`);
  }
  return say("similar_size", `VIIRS ${viirs} km² vs model ${model} km² in the same clear pixels: similar in size, which does not show that the locations match.`,
    `VIIRS ${viirs} ตร.กม. เทียบกับแบบจำลอง ${model} ตร.กม. ในพิกเซลท้องฟ้าโปร่งเดียวกัน: ขนาดใกล้เคียงกัน แต่ไม่ได้แสดงว่าตำแหน่งตรงกัน`);
}

/** Rain (mm) at `code` during replay hour `hour` (0 = 9 Sep 00:00-01:00 ICT); null when missing or outside the record. */
export function rainAt(rainfall: Pick<Rainfall, "hourly_mm">, code: string, hour: number): number | null {
  const series = rainfall.hourly_mm[code];
  if (!series || !Number.isInteger(hour) || hour < 0 || hour >= series.length) return null;
  const value = series[hour];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Total, wettest hour and missing hours of an hourly series, recomputed from the values (the manifest also bakes them). */
export function rainSummary(series: readonly (number | null)[]): { total_mm: number; max_hour_mm: number; missing_hours: number } {
  let total = 0;
  let max = 0;
  let missing = 0;
  for (const value of series) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      missing += 1;
      continue;
    }
    total += value;
    max = Math.max(max, value);
  }
  return { total_mm: roundLikePython(total, 1), max_hour_mm: max, missing_hours: missing };
}

export interface DepthClass { min: number; max: number; rgba: [number, number, number, number]; label: string }

/** Five-class depth ramp (upper bound inclusive): (0,0.3], (0.3,1], (1,2], (2,3], >3 m. */
export const DEPTH_CLASSES: readonly DepthClass[] = [
  { min: 0, max: 0.3, rgba: [158, 202, 225, 225], label: "0–0.3 m" },
  { min: 0.3, max: 1, rgba: [107, 174, 214, 232], label: "0.3–1 m" },
  { min: 1, max: 2, rgba: [49, 130, 189, 238], label: "1–2 m" },
  { min: 2, max: 3, rgba: [8, 81, 156, 242], label: "2–3 m" },
  { min: 3, max: Infinity, rgba: [8, 48, 107, 246], label: "> 3 m" },
];
/** Mapped river channel (code 0), always water. */
export const CHANNEL_RGBA: readonly [number, number, number, number] = [0, 96, 107, 255];

export const rgbaCss = ([r, g, b, a]: readonly number[]) => `rgb(${r} ${g} ${b} / ${Math.round((a / 255) * 100)}%)`;

/** Depth class index for a positive depth. */
export function depthClassIndex(depth: number): number {
  for (let index = 0; index < DEPTH_CLASSES.length; index += 1) {
    if (depth <= DEPTH_CLASSES[index].max) return index;
  }
  return DEPTH_CLASSES.length - 1;
}

const pack = ([r, g, b, a]: readonly number[], littleEndian: boolean) =>
  (littleEndian ? ((a << 24) | (b << 16) | (g << 8) | r) : ((r << 24) | (g << 16) | (b << 8) | a)) >>> 0;

/**
 * 256-entry lookup of packed RGBA for each HAND code at `stage`, for a Uint32 view of ImageData
 * (little-endian ABGR by default). Code 255 and dry codes are transparent (0).
 * Pass `out` (length 256) to reuse a buffer instead of allocating one.
 */
export function buildDepthLut(stage: number, step: number, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (out && out.length !== 256) throw new Error("LUT buffer must have 256 entries");
  const lut = out ?? new Uint32Array(256);
  if (out) lut.fill(0);
  lut[0] = pack(CHANNEL_RGBA, littleEndian);
  for (let code = 1; code < 255; code += 1) {
    const hand = code * step;
    if (hand < stage) lut[code] = pack(DEPTH_CLASSES[depthClassIndex(stage - hand)].rgba, littleEndian);
  }
  return lut;
}

/** True when two lookup tables would paint identical pixels. */
export function lutEquals(a: Uint32Array | null, b: Uint32Array): boolean {
  if (!a || a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) if (a[index] !== b[index]) return false;
  return true;
}

/** Pixel indices that can ever be wet up to `maxStage` (channel plus codes below it). */
export function waterCandidates(codes: Uint8Array, maxStage: number, step: number): Uint32Array {
  const limit = maxStage + step;
  let count = 0;
  for (let index = 0; index < codes.length; index += 1) {
    const code = codes[index];
    if (code === 0 || (code !== 255 && code * step < limit)) count += 1;
  }
  const out = new Uint32Array(count);
  let cursor = 0;
  for (let index = 0; index < codes.length; index += 1) {
    const code = codes[index];
    if (code === 0 || (code !== 255 && code * step < limit)) out[cursor++] = index;
  }
  return out;
}

/**
 * Write `lut[key]` into `pixels` for candidate indices only (all other pixels stay untouched).
 * `keys` are HAND codes (256-entry LUT) or depth-factor keys `code | factor << 8` (65 536-entry LUT).
 */
export function paintDepth(keys: Uint8Array | Uint16Array, candidates: Uint32Array, lut: Uint32Array, pixels: Uint32Array): void {
  for (let index = 0; index < candidates.length; index += 1) {
    const pixel = candidates[index];
    pixels[pixel] = lut[keys[pixel]];
  }
}

export interface LatestObservation<O> { observation: O; ageDays: number }

export interface ObservationGap<O> { before: O; after: O }

/**
 * The imagery gap containing `t`: the latest observation (any sensor) before `t` and the next one after it,
 * when they are more than `minGapDays` apart and `t` lies strictly between them. `null` otherwise
 * (including exactly at an acquisition).
 */
export function observationGap<O extends Pick<TimelineObservation, "local">>(
  t: number,
  observations: readonly O[],
  minGapDays = 1,
): ObservationGap<O> | null {
  let before: { observation: O; at: number } | null = null;
  let after: { observation: O; at: number } | null = null;
  for (const observation of observations) {
    const at = tFromDate(observation.local);
    if (at <= t && (!before || at > before.at)) before = { observation, at };
    if (at > t && (!after || at < after.at)) after = { observation, at };
  }
  if (!before || !after || before.at === t || after.at - before.at <= minGapDays) return null;
  return { before: before.observation, after: after.observation };
}

/** Most recent observation at or before `t` (optionally of one kind), with its age in days. */
export function latestObservation<O extends Pick<TimelineObservation, "local" | "kind">>(
  t: number,
  observations: readonly O[],
  kind?: TimelineObservation["kind"],
): LatestObservation<O> | null {
  let best: LatestObservation<O> | null = null;
  for (const observation of observations) {
    if (kind && observation.kind !== kind) continue;
    const at = tFromDate(observation.local);
    if (at > t) continue;
    if (!best || at > t - best.ageDays) best = { observation, ageDays: t - at };
  }
  return best;
}

const WEEKDAYS: Record<Language, string[]> = {
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  th: ["อา.", "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส."],
};
const MONTHS: Record<Language, string[]> = {
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  th: ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."],
};

function ictParts(ms: number) {
  const local = new Date(ms + ICT_OFFSET_MS);
  return {
    weekday: local.getUTCDay(), day: local.getUTCDate(), month: local.getUTCMonth(), year: local.getUTCFullYear(),
    hour: local.getUTCHours(), minute: local.getUTCMinutes(),
  };
}

const pad2 = (value: number) => String(value).padStart(2, "0");

/** Thai year label: Buddhist Era with the CE year in brackets, e.g. "2567 (2024)". */
export const thaiYear = (ceYear: number): string => `${ceYear + 543} (${ceYear})`;

/**
 * "Thu 12 Sep 2024 · 12:00 ICT" / "พฤ. 12 ก.ย. 2567 (2024) · 12:00 น." (time floored to the hour). The replay's end,
 * 20 Sep 00:00, is labelled as the end of 19 Sep, the last day the replay covers.
 */
export function formatMoment(t: number, language: Language): string {
  const hour = hourIndex(t);
  const end = hour >= EVENT_HOURS;
  const p = ictParts(TIMELINE_EPOCH_MS + (end ? EVENT_HOURS - 1 : hour) * 3_600_000);
  const time = end
    ? language === "th" ? "สิ้นวัน (24:00 น.)" : "end of day (24:00 ICT)"
    : language === "th" ? `${pad2(p.hour)}:00 น.` : `${pad2(p.hour)}:00 ICT`;
  return language === "th"
    ? `${WEEKDAYS.th[p.weekday]} ${p.day} ${MONTHS.th[p.month]} ${thaiYear(p.year)} · ${time}`
    : `${WEEKDAYS.en[p.weekday]} ${p.day} ${MONTHS.en[p.month]} ${p.year} · ${time}`;
}

/** "12 Sep" / "12 ก.ย." for a local ISO date or instant. */
export function formatShortDate(input: string, language: Language): string {
  const p = ictParts(input.length === 10 ? Date.parse(`${input}T00:00:00+07:00`) : Date.parse(input));
  return `${p.day} ${MONTHS[language][p.month]}`;
}

/**
 * "9 Oct 2026" / "9 ต.ค. 2569 (2026)" for a local ISO date outside the event year (the date of a local check, of an
 * import); the input itself when it is not a date.
 */
export function formatDateWithYear(input: string, language: Language): string {
  const ms = Date.parse(input.length === 10 ? `${input}T00:00:00+07:00` : input);
  if (Number.isNaN(ms)) return input;
  const p = ictParts(ms);
  return `${p.day} ${MONTHS[language][p.month]} ${language === "th" ? thaiYear(p.year) : p.year}`;
}

/**
 * "1 Oct 2026, 16:10 ICT" / "1 ต.ค. 2569 (2026) 16:10 น." for a manifest's `generated_at`; null when the manifest
 * has none (r3) or the value is not a date.
 */
export function formatGeneratedAt(input: string | undefined, language: Language): string | null {
  const ms = input ? Date.parse(input) : Number.NaN;
  if (Number.isNaN(ms)) return null;
  const p = ictParts(ms);
  return language === "th"
    ? `${p.day} ${MONTHS.th[p.month]} ${thaiYear(p.year)} ${pad2(p.hour)}:${pad2(p.minute)} น.`
    : `${p.day} ${MONTHS.en[p.month]} ${p.year}, ${pad2(p.hour)}:${pad2(p.minute)} ICT`;
}

/** "16 Sep 06:16" style local stamp for an observation. */
export function formatLocalStamp(input: string, language: Language): string {
  const p = ictParts(Date.parse(input));
  return `${p.day} ${MONTHS[language][p.month]} ${pad2(p.hour)}:${pad2(p.minute)}${language === "th" ? " น." : " ICT"}`;
}

/** Human age of an image relative to the replay moment (negative = image is later). */
export function formatAge(ageDays: number, language: Language): string {
  const before = ageDays >= 0;
  const magnitude = Math.abs(ageDays);
  const hours = Math.round(magnitude * 24);
  const days = Math.round(magnitude);
  if (hours < 1) return language === "th" ? "ตรงกับช่วงเวลานี้" : "at this moment";
  const amount = magnitude < 1
    ? language === "th" ? `${hours} ชั่วโมง` : `${hours} hour${hours === 1 ? "" : "s"}`
    : language === "th" ? `${days} วัน` : `${days} day${days === 1 ? "" : "s"}`;
  if (language === "th") return before ? `${amount}ก่อนช่วงเวลานี้` : `${amount}หลังช่วงเวลานี้`;
  return before ? `${amount} before this moment` : `${amount} after this moment`;
}


/** "10 Sep 22:00" / "10 ก.ย. 22:00 น." for a whole-hour index on the replay clock (hours since 9 Sep 00:00 ICT). */
export function formatHourStamp(hour: number, language: Language): string {
  const p = ictParts(TIMELINE_EPOCH_MS + hour * 3_600_000);
  return `${p.day} ${MONTHS[language][p.month]} ${pad2(p.hour)}:00${language === "th" ? " น." : ""}`;
}

/**
 * Local span covering whole hours `from` … `to` (inclusive), shown by its start and end instants:
 * "10 Sep 11:00–23:00", or "10 Sep 23:00 – 11 Sep 05:00" across midnight.
 */
export function formatHourSpan(from: number, to: number, language: Language): string {
  const start = ictParts(TIMELINE_EPOCH_MS + from * 3_600_000);
  const end = ictParts(TIMELINE_EPOCH_MS + (to + 1) * 3_600_000);
  if (start.day === end.day && start.month === end.month) {
    return `${start.day} ${MONTHS[language][start.month]} ${pad2(start.hour)}:00–${pad2(end.hour)}:00${language === "th" ? " น." : ""}`;
  }
  return `${formatHourStamp(from, language)} – ${formatHourStamp(to + 1, language)}`;
}

export interface GrayRaster { width: number; height: number; data: Uint8Array }
/** Decoded 8-bit PNG: `channels` interleaved samples per pixel (1 grey, 2 grey + alpha, 3 RGB, 4 RGBA). */
export interface PngRaster { width: number; height: number; channels: number; data: Uint8Array }
export type Inflate = (data: Uint8Array) => Promise<Uint8Array> | Uint8Array;

const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];
/** Samples per pixel by PNG colour type; palette images are not supported. */
const PNG_CHANNELS: Record<number, number> = { 0: 1, 2: 3, 4: 2, 6: 4 };

/**
 * Decode an 8-bit, non-interlaced greyscale, grey + alpha, RGB or RGBA PNG into its exact samples.
 * Decoding the file directly avoids browser colour management and canvas read-back noise.
 */
export async function decodePng(bytes: Uint8Array, inflate: Inflate): Promise<PngRaster> {
  if (bytes.length < 8 || PNG_SIGNATURE.some((value, index) => bytes[index] !== value)) throw new Error("Not a PNG file");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 8;
  let width = 0;
  let height = 0;
  let channels = 0;
  const parts: Uint8Array[] = [];
  while (offset + 8 <= bytes.length) {
    const length = view.getUint32(offset);
    const type = String.fromCharCode(bytes[offset + 4], bytes[offset + 5], bytes[offset + 6], bytes[offset + 7]);
    if (type === "IHDR") {
      width = view.getUint32(offset + 8);
      height = view.getUint32(offset + 12);
      channels = PNG_CHANNELS[bytes[offset + 17]] ?? 0;
      if (bytes[offset + 16] !== 8 || !channels || bytes[offset + 20] !== 0) {
        throw new Error("Expected an 8-bit non-interlaced greyscale or RGB PNG");
      }
    } else if (type === "IDAT") {
      parts.push(bytes.subarray(offset + 8, offset + 8 + length));
    } else if (type === "IEND") {
      break;
    }
    offset += 12 + length;
  }
  if (!width || !height || parts.length === 0) throw new Error("PNG is missing image data");
  const joined = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let cursor = 0;
  for (const part of parts) {
    joined.set(part, cursor);
    cursor += part.length;
  }
  const raw = await inflate(joined);
  const bpp = channels;
  const rowBytes = width * bpp;
  const stride = rowBytes + 1;
  if (raw.length < height * stride) throw new Error("PNG image data is truncated");
  // Uint8Array stores wrap modulo 256, which is exactly PNG's filter arithmetic.
  const out = new Uint8Array(rowBytes * height);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * stride];
    const source = y * stride + 1;
    const row = y * rowBytes;
    const previous = row - rowBytes;
    switch (filter) {
      case 0:
        out.set(raw.subarray(source, source + rowBytes), row);
        break;
      case 1:
        for (let i = 0; i < rowBytes; i += 1) out[row + i] = raw[source + i] + (i >= bpp ? out[row + i - bpp] : 0);
        break;
      case 2:
        for (let i = 0; i < rowBytes; i += 1) out[row + i] = raw[source + i] + (y > 0 ? out[previous + i] : 0);
        break;
      case 3:
        for (let i = 0; i < rowBytes; i += 1) {
          const left = i >= bpp ? out[row + i - bpp] : 0;
          const up = y > 0 ? out[previous + i] : 0;
          out[row + i] = raw[source + i] + ((left + up) >> 1);
        }
        break;
      case 4:
        for (let i = 0; i < rowBytes; i += 1) {
          const left = i >= bpp ? out[row + i - bpp] : 0;
          const up = y > 0 ? out[previous + i] : 0;
          const upLeft = i >= bpp && y > 0 ? out[previous + i - bpp] : 0;
          const estimate = left + up - upLeft;
          const dLeft = Math.abs(estimate - left);
          const dUp = Math.abs(estimate - up);
          const dUpLeft = Math.abs(estimate - upLeft);
          out[row + i] = raw[source + i] + (dLeft <= dUp && dLeft <= dUpLeft ? left : dUp <= dUpLeft ? up : upLeft);
        }
        break;
      default:
        throw new Error(`Unsupported PNG filter ${filter}`);
    }
  }
  return { width, height, channels, data: out };
}

/** Decode an 8-bit, non-interlaced greyscale PNG into exact byte codes. */
export async function decodeGrayPng(bytes: Uint8Array, inflate: Inflate): Promise<GrayRaster> {
  const raster = await decodePng(bytes, inflate);
  if (raster.channels !== 1) throw new Error("Expected an 8-bit non-interlaced grayscale PNG");
  return { width: raster.width, height: raster.height, data: raster.data };
}

/** zlib inflate using the platform DecompressionStream (browsers and Node 18+). */
export async function inflateZlib(data: Uint8Array): Promise<Uint8Array> {
  const copy = new Uint8Array(data);
  const stream = new Blob([copy]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// --- HAND grid with an optional per-cell depth factor ------------------------------------------

/**
 * HAND codes per cell, plus depth-factor bytes (round(k * 255)) when the manifest declares a factor channel, and
 * low-confidence flags (1 = flagged) when it declares a low-confidence channel.
 */
export interface HandGrid { width: number; height: number; codes: Uint8Array; factors: Uint8Array | null; lowConfidence: Uint8Array | null }

/** Manifest `depth_factor_channel` values this client understands, as a sample index into an RGB(A) pixel. */
const FACTOR_CHANNELS: Record<string, number> = { G: 1 };
/** Manifest `low_confidence_channel` values this client understands, as a sample index into an RGB(A) pixel. */
const LOW_CONFIDENCE_CHANNELS: Record<string, number> = { B: 2 };
/** A low-confidence sample at or above this byte is flagged (the builder writes 255 or 0). */
export const LOW_CONFIDENCE_MIN_BYTE = 128;

function channelIndex(table: Record<string, number>, declared: string | null | undefined, name: string, channels: number): number {
  if (declared == null) return -1;
  const index = table[declared] ?? -1;
  if (index < 0) throw new Error(`Unsupported HAND ${name}: ${declared}`);
  if (channels < 3) throw new Error(`The HAND raster has no ${name.replaceAll("_", " ")}`);
  return index;
}

/**
 * Split a decoded HAND PNG into effective codes (the grey value, or R of an RGB raster) and, when
 * `depthFactorChannel` is set, the factor bytes from that channel. Without it every factor is 1, even
 * for an RGB raster. The low-confidence channel is decoded only when `lowConfidenceChannel` is declared
 * (a raster's B values are otherwise ignored). Fails closed on a declared channel the raster lacks or this
 * client does not know.
 */
export function handGridFromRaster(raster: PngRaster, depthFactorChannel?: string | null, lowConfidenceChannel?: string | null): HandGrid {
  const { width, height, channels, data } = raster;
  const factorIndex = channelIndex(FACTOR_CHANNELS, depthFactorChannel, "depth_factor_channel", channels);
  const flagIndex = channelIndex(LOW_CONFIDENCE_CHANNELS, lowConfidenceChannel, "low_confidence_channel", channels);
  if (channels === 1) return { width, height, codes: data, factors: null, lowConfidence: null };
  const count = width * height;
  const codes = new Uint8Array(count);
  const factors = factorIndex >= 0 ? new Uint8Array(count) : null;
  const lowConfidence = flagIndex >= 0 ? new Uint8Array(count) : null;
  for (let cell = 0, sample = 0; cell < count; cell += 1, sample += channels) {
    codes[cell] = data[sample];
    if (factors) factors[cell] = data[sample + factorIndex];
    if (lowConfidence) lowConfidence[cell] = data[sample + flagIndex] >= LOW_CONFIDENCE_MIN_BYTE ? 1 : 0;
  }
  return { width, height, codes, factors, lowConfidence };
}

// --- Low-confidence water (filled pits and dead-flat ground in the elevation model) -------------

/** Cells flagged low-confidence among `candidates` (cells that can ever be wet), channel cells excluded. */
export function lowConfidenceCells(codes: Uint8Array, flags: Uint8Array, candidates: Uint32Array, channelCode = 0): Uint32Array {
  if (codes.length !== flags.length) throw new Error("Codes and low-confidence flags must cover the same cells");
  let count = 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const cell = candidates[index];
    if (flags[cell] && codes[cell] !== channelCode) count += 1;
  }
  const out = new Uint32Array(count);
  let cursor = 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const cell = candidates[index];
    if (flags[cell] && codes[cell] !== channelCode) out[cursor++] = cell;
  }
  return out;
}

/** Period and stripe width (in raster cells) of the diagonal hatch on low-confidence water. */
export const LOW_CONFIDENCE_HATCH = { period: 6, stripe: 2 } as const;

/** 1 where a cell lies on a hatch stripe (diagonal "/" lines on the raster grid), else 0, for each of `cells`. */
export function hatchStripes(cells: Uint32Array, width: number, period: number = LOW_CONFIDENCE_HATCH.period, stripe: number = LOW_CONFIDENCE_HATCH.stripe): Uint8Array {
  const out = new Uint8Array(cells.length);
  for (let index = 0; index < cells.length; index += 1) {
    const cell = cells[index];
    const x = cell % width;
    const y = (cell - x) / width;
    out[index] = (x + y) % period < stripe ? 1 : 0;
  }
  return out;
}

/** Neutral the low-confidence tone mixes toward, and how much of the original colour it keeps. */
const LOW_CONFIDENCE_GREY = [226, 230, 236] as const;
const LOW_CONFIDENCE_KEEP = { base: 0.35, stripe: 0.8 } as const;

/**
 * Colour of a wet low-confidence cell: the mode's colour washed toward a pale grey (lighter, desaturated) with a
 * lower alpha between stripes; on a stripe it keeps most of its colour. Transparent stays transparent.
 */
export function lowConfidenceRgba(rgba: Rgba, onStripe: boolean): Rgba {
  const [r, g, b, a] = rgba;
  if (a === 0) return [0, 0, 0, 0];
  const keep = onStripe ? LOW_CONFIDENCE_KEEP.stripe : LOW_CONFIDENCE_KEEP.base;
  const mix = (value: number, grey: number) => Math.round(value * keep + grey * (1 - keep));
  return [mix(r, LOW_CONFIDENCE_GREY[0]), mix(g, LOW_CONFIDENCE_GREY[1]), mix(b, LOW_CONFIDENCE_GREY[2]), Math.round(a * (onStripe ? 1 : 0.72))];
}

const unpack = (value: number, littleEndian: boolean): Rgba => (littleEndian
  ? [value & 255, (value >>> 8) & 255, (value >>> 16) & 255, value >>> 24]
  : [value >>> 24, (value >>> 16) & 255, (value >>> 8) & 255, value & 255]);

/**
 * Re-colour the painted low-confidence `cells` (as `lowConfidenceRgba`, hatched by `stripes`); dry (transparent)
 * cells stay transparent, so this runs after the mode's own paint of the same frame.
 */
export function paintLowConfidence(cells: Uint32Array, stripes: Uint8Array, pixels: Uint32Array, littleEndian = true): void {
  if (cells.length !== stripes.length) throw new Error("One stripe flag is required per low-confidence cell");
  const cache = [new Map<number, number>(), new Map<number, number>()];
  for (let index = 0; index < cells.length; index += 1) {
    const cell = cells[index];
    const colour = pixels[cell];
    if (colour === 0) continue;
    const stripe = stripes[index];
    const known = cache[stripe];
    let next = known.get(colour);
    if (next === undefined) {
      next = pack(lowConfidenceRgba(unpack(colour, littleEndian), stripe === 1), littleEndian);
      known.set(colour, next);
    }
    pixels[cell] = next;
  }
}

/** Depth factor k for a stored byte round(k * 255); 255 is full depth. */
export const depthFactor = (byte: number): number => byte / 255;

/**
 * Reconstructed depth (m) of one HAND cell at `stage`, or `null` when it is dry.
 * Wet iff it is the channel or `code * step < stage` (never for `neverCode`); depth = k * (stage - code * step),
 * channel depth = k * stage. `factorByte` is 255 (k = 1) when the manifest has no factor channel.
 */
export function cellDepth(code: number, stage: number, step: number, factorByte = 255, channelCode = 0, neverCode = 255): number | null {
  const k = depthFactor(factorByte);
  if (code === channelCode) return k * Math.max(0, stage);
  if (code === neverCode || !(code * step < stage)) return null;
  return k * (stage - code * step);
}

/** Entries in a depth-factor LUT: one per `code | factor << 8` key. */
export const FACTOR_LUT_SIZE = 65_536;

/** Painter keys `code | factor << 8` for `buildFactorDepthLut`. */
export function depthFactorKeys(codes: Uint8Array, factors: Uint8Array): Uint16Array {
  if (codes.length !== factors.length) throw new Error("Codes and factors must cover the same cells");
  const keys = new Uint16Array(codes.length);
  for (let index = 0; index < codes.length; index += 1) keys[index] = codes[index] | (factors[index] << 8);
  return keys;
}

/**
 * Depth LUT indexed by `code | factor << 8`: the five depth classes of `buildDepthLut`, applied to
 * k * (stage - code * step). Wetness still depends on the code alone. The factor-255 slice equals `buildDepthLut`.
 */
export function buildFactorDepthLut(stage: number, step: number, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (out && out.length !== FACTOR_LUT_SIZE) throw new Error(`LUT buffer must have ${FACTOR_LUT_SIZE} entries`);
  const lut = out ?? new Uint32Array(FACTOR_LUT_SIZE);
  if (out) lut.fill(0);
  const channel = pack(CHANNEL_RGBA, littleEndian);
  const classes = DEPTH_CLASSES.map((item) => pack(item.rgba, littleEndian));
  for (let factor = 0; factor < 256; factor += 1) {
    const base = factor << 8;
    const k = depthFactor(factor);
    lut[base] = channel;
    for (let code = 1; code < 255; code += 1) {
      const hand = code * step;
      if (hand < stage) lut[base | code] = classes[depthClassIndex(k * (stage - hand))];
    }
  }
  return lut;
}

// --- Residents (WorldPop density codes) ---------------------------------------------------------

/**
 * People per hectare for a density code of the population raster:
 * the inverse of code = round(254 * ln(1 + p) / ln(1 + maxPerHa)). Code 0 is no residents.
 */
export function densityPerHa(code: number, maxPerHa: number): number {
  if (code <= 0) return 0;
  return Math.expm1((Math.min(code, 254) / 254) * Math.log1p(maxPerHa));
}

export interface DensityClass { min: number; max: number; rgba: Rgba }

/**
 * Sequential classes of residents per hectare (lower bound exclusive for the first, inclusive after): yellow to
 * green to deep blue, with no reds, so impassable (red) roads stay readable on top of it.
 */
export const DENSITY_CLASSES: readonly DensityClass[] = [
  { min: 0, max: 2, rgba: [237, 248, 177, 226] },
  { min: 2, max: 5, rgba: [161, 218, 180, 232] },
  { min: 5, max: 10, rgba: [65, 182, 196, 238] },
  { min: 10, max: 20, rgba: [34, 94, 168, 244] },
  { min: 20, max: Infinity, rgba: [12, 44, 132, 248] },
];
/** Wet cells where the population raster has no residents: a faint neutral so the flood outline stays readable. */
export const WET_WITHOUT_RESIDENTS_RGBA: Rgba = [96, 120, 148, 110];

/** Density class for a positive number of people per hectare, or -1 for none. */
export function densityClassIndex(perHa: number): number {
  if (!(perHa > 0)) return -1;
  const index = DENSITY_CLASSES.findIndex((item) => perHa < item.max);
  return index < 0 ? DENSITY_CLASSES.length - 1 : index;
}

/** Legend classes that occur below the raster's density cap, the last one ending at the cap. */
export function densityLegend(maxPerHa: number): DensityClass[] {
  return DENSITY_CLASSES.filter((item) => item.min < maxPerHa).map((item) => ({ ...item, max: Math.min(item.max, maxPerHa) }));
}

/** Packed colour per density code (256 entries, code 0 transparent), for the people and residents LUTs. */
export function densityColours(maxPerHa: number, littleEndian = true): Uint32Array {
  const colours = new Uint32Array(256);
  for (let code = 1; code < 256; code += 1) {
    const index = densityClassIndex(densityPerHa(code, maxPerHa));
    if (index >= 0) colours[code] = pack(DENSITY_CLASSES[index].rgba, littleEndian);
  }
  return colours;
}

/** Painter keys `handCode | densityCode << 8` for `buildPeopleLut`. */
export function peopleKeys(codes: Uint8Array, density: Uint8Array): Uint16Array {
  if (codes.length !== density.length) throw new Error("HAND and population rasters must cover the same cells");
  const keys = new Uint16Array(codes.length);
  for (let index = 0; index < codes.length; index += 1) keys[index] = codes[index] | (density[index] << 8);
  return keys;
}

/**
 * "People in flood water" LUT indexed by `handCode | densityCode << 8`: out-of-channel cells that are wet at
 * `stage` (code * step < stage, the same rule as the depth view) take their residents' density colour, wet cells
 * without residents a faint neutral; the channel keeps its colour and dry cells stay transparent.
 */
export function buildPeopleLut(stage: number, step: number, colours: Uint32Array, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (colours.length !== 256) throw new Error("Density colours must have 256 entries");
  if (out && out.length !== FACTOR_LUT_SIZE) throw new Error(`LUT buffer must have ${FACTOR_LUT_SIZE} entries`);
  const lut = out ?? new Uint32Array(FACTOR_LUT_SIZE);
  if (out) lut.fill(0);
  const channel = pack(CHANNEL_RGBA, littleEndian);
  const empty = pack(WET_WITHOUT_RESIDENTS_RGBA, littleEndian);
  let wetBelow = 1;
  while (wetBelow < 255 && wetBelow * step < stage) wetBelow += 1;
  for (let density = 0; density < 256; density += 1) {
    const base = density << 8;
    const colour = density === 0 ? empty : colours[density] || empty;
    lut[base] = channel;
    for (let code = 1; code < wetBelow; code += 1) lut[base | code] = colour;
  }
  return lut;
}

/** "All residents" LUT indexed by density code: every inhabited cell in its density colour, independent of water. */
export function buildResidentsLut(colours: Uint32Array, out?: Uint32Array): Uint32Array {
  if (colours.length !== 256) throw new Error("Density colours must have 256 entries");
  if (out && out.length !== 256) throw new Error("LUT buffer must have 256 entries");
  const lut = out ?? new Uint32Array(256);
  lut.set(colours);
  lut[0] = 0;
  return lut;
}

/** Pixel indices with residents (density code > 0). */
export function densityCandidates(density: Uint8Array): Uint32Array {
  let count = 0;
  for (let index = 0; index < density.length; index += 1) if (density[index] > 0) count += 1;
  const out = new Uint32Array(count);
  let cursor = 0;
  for (let index = 0; index < density.length; index += 1) if (density[index] > 0) out[cursor++] = index;
  return out;
}

// --- Arrival and time under water ---------------------------------------------------------------

/** Whole hours in the replay window, 9 Sep 00:00 to 20 Sep 00:00 ICT. */
export const EVENT_HOURS = TIMELINE_END_T * 24;

/**
 * Assumed stage at the start of every local hour of the replay: `stageAt(h / 24)` for h = 0 … hours - 1.
 * Each sample stands for its whole hour. Arrival, time under water and road-cut durations are counted on
 * this hourly grid, the same grid the time slider steps on, so they agree with what the slider shows.
 */
export function hourlyStages(anchors: readonly StageAnchor[], hours = EVENT_HOURS): Float64Array {
  const stages = new Float64Array(hours);
  for (let hour = 0; hour < hours; hour += 1) stages[hour] = stageAt(hour / 24, anchors);
  return stages;
}

/** Per HAND code (0-255): hourly arrival and time under water; pure functions of the stage anchors. */
export interface CodeTimings {
  /** First hour whose sampled stage exceeds `code * step`, or -1 when none does (always -1 for the never code). */
  arrivalHour: Int16Array;
  /** Hourly samples whose stage exceeds `code * step` (0 for the never code). */
  hoursUnder: Uint16Array;
}

/**
 * Replay position (days since 9 Sep 00:00 ICT) at which HAND code `code` first floods: the start of the first
 * hourly sample whose stage exceeds `code * step`, or null when none does (always null for `neverCode`).
 */
export function arrivalT(code: number, stages: ArrayLike<number>, step: number, neverCode = 255): number | null {
  if (code === neverCode) return null;
  const hand = code * step;
  for (let hour = 0; hour < stages.length; hour += 1) if (stages[hour] > hand) return hour / 24;
  return null;
}

/** Hours of the replay (hourly samples) during which HAND code `code` is under water; 0 for `neverCode`. */
export function hoursUnder(code: number, stages: ArrayLike<number>, step: number, neverCode = 255): number {
  if (code === neverCode) return 0;
  const hand = code * step;
  let hours = 0;
  for (let hour = 0; hour < stages.length; hour += 1) if (stages[hour] > hand) hours += 1;
  return hours;
}

/** `arrivalT` and `hoursUnder` for every code 0-255, as 256-entry tables for the LUT builders. */
export function codeTimings(stages: ArrayLike<number>, step: number, neverCode = 255): CodeTimings {
  const arrivalHour = new Int16Array(256).fill(-1);
  const hoursUnderWater = new Uint16Array(256);
  for (let code = 0; code < 256; code += 1) {
    const arrival = arrivalT(code, stages, step, neverCode);
    if (arrival !== null) arrivalHour[code] = Math.round(arrival * 24);
    hoursUnderWater[code] = hoursUnder(code, stages, step, neverCode);
  }
  return { arrivalHour, hoursUnder: hoursUnderWater };
}

export type Rgba = readonly [number, number, number, number];
/** A colour class over whole hours `from` … `to` (inclusive). */
export interface HourClass { from: number; to: number; rgba: Rgba }

/** Sequential "first flooded" ramp, earliest (dark) to latest (light). */
export const ARRIVAL_RAMP: readonly Rgba[] = [
  [45, 17, 96, 238],
  [106, 28, 129, 236],
  [168, 50, 125, 234],
  [224, 80, 106, 232],
  [250, 138, 92, 230],
  [253, 199, 141, 228],
];
/** Alpha for cells whose first-flooded hour is still ahead of the playhead. */
export const ARRIVAL_PENDING_ALPHA = 56;

/**
 * Equal-interval hour classes spanning the earliest to the latest arrival of any out-of-channel code
 * (one class per ramp colour, fewer when the span is shorter). Empty when nothing ever floods.
 */
export function arrivalClasses(arrivalHour: Int16Array, ramp: readonly Rgba[] = ARRIVAL_RAMP, channelCode = 0): HourClass[] {
  let min = Infinity;
  let max = -Infinity;
  arrivalHour.forEach((hour, code) => {
    if (code === channelCode || hour < 0) return;
    min = Math.min(min, hour);
    max = Math.max(max, hour);
  });
  if (!Number.isFinite(min) || ramp.length === 0) return [];
  const span = max - min + 1;
  const count = Math.min(ramp.length, span);
  return Array.from({ length: count }, (_, index) => ({
    from: min + Math.floor((index * span) / count),
    to: min + Math.floor(((index + 1) * span) / count) - 1,
    rgba: ramp[index],
  }));
}

/** Index of the class containing `hour`, or -1. */
export function hourClassIndex(hour: number, classes: readonly HourClass[]): number {
  return classes.findIndex((item) => hour >= item.from && hour <= item.to);
}

function checkLut(out: Uint32Array | undefined): Uint32Array {
  if (out && out.length !== 256) throw new Error("LUT buffer must have 256 entries");
  if (out) out.fill(0);
  return out ?? new Uint32Array(256);
}

/**
 * First-flooded LUT for `playheadHour`: cells already reached are drawn in their class colour, cells still
 * to flood are dimmed, never-flooded and never-code cells stay transparent. The channel keeps its colour.
 */
export function buildArrivalLut(
  arrivalHour: Int16Array,
  classes: readonly HourClass[],
  playheadHour: number,
  littleEndian = true,
  out?: Uint32Array,
): Uint32Array {
  const lut = checkLut(out);
  lut[0] = pack(CHANNEL_RGBA, littleEndian);
  for (let code = 1; code < 255; code += 1) {
    const hour = arrivalHour[code];
    if (hour < 0) continue;
    const index = hourClassIndex(hour, classes);
    if (index < 0) continue;
    const [r, g, b, a] = classes[index].rgba;
    lut[code] = pack(hour <= playheadHour ? [r, g, b, a] : [r, g, b, ARRIVAL_PENDING_ALPHA], littleEndian);
  }
  return lut;
}

export interface DurationClass { min: number; max: number; rgba: Rgba; label: Localized }

/**
 * Hours under water over the replay (lower bound inclusive); sequential (viridis-like), longer is darker. No browns or
 * oranges, so it never reads as the flood mud in the 15 Sep satellite image.
 */
export const DURATION_CLASSES: readonly DurationClass[] = [
  { min: 1, max: 5, rgba: [240, 229, 66, 228], label: { en: "< 6 h", th: "< 6 ชม." } },
  { min: 6, max: 23, rgba: [134, 206, 76, 230], label: { en: "6–24 h", th: "6–24 ชม." } },
  { min: 24, max: 47, rgba: [42, 170, 138, 234], label: { en: "24–48 h", th: "24–48 ชม." } },
  { min: 48, max: 95, rgba: [36, 125, 142, 238], label: { en: "48–96 h", th: "48–96 ชม." } },
  { min: 96, max: 143, rgba: [60, 78, 138, 242], label: { en: "96–144 h", th: "96–144 ชม." } },
  { min: 144, max: Infinity, rgba: [68, 18, 88, 246], label: { en: "≥ 144 h", th: "≥ 144 ชม." } },
];

/** Duration class index for a whole number of hours, or -1 for none. */
export function durationClassIndex(hours: number): number {
  return DURATION_CLASSES.findIndex((item) => hours >= item.min && hours <= item.max);
}

/** Hours-under-water LUT (static over the replay). The channel keeps its colour. */
export function buildDurationLut(hoursUnder: Uint16Array, littleEndian = true, out?: Uint32Array): Uint32Array {
  const lut = checkLut(out);
  lut[0] = pack(CHANNEL_RGBA, littleEndian);
  for (let code = 1; code < 255; code += 1) {
    const index = durationClassIndex(hoursUnder[code]);
    if (index >= 0) lut[code] = pack(DURATION_CLASSES[index].rgba, littleEndian);
  }
  return lut;
}

// --- Road cut duration -------------------------------------------------------------------------

/** Hourly impassability of one road piece over the replay (same rounding and threshold as `roadState`). */
export interface RoadCut {
  /** Hours during which the piece is impassable. */
  hours: number;
  /** First impassable hour, or null when it is never cut. */
  firstHour: number | null;
  /** Hour from which it is passable again after its last cut; null when never cut or still cut when the replay ends. */
  reopenHour: number | null;
}

export function roadCut(minHandM: number | null, stages: ArrayLike<number>, impassableDepthM = 0.3, depthFactorK = 1): RoadCut {
  let hours = 0;
  let first = -1;
  let last = -1;
  for (let hour = 0; hour < stages.length; hour += 1) {
    if (roadState(minHandM, stages[hour], impassableDepthM, depthFactorK) !== "impassable") continue;
    hours += 1;
    if (first < 0) first = hour;
    last = hour;
  }
  return {
    hours,
    firstHour: first < 0 ? null : first,
    reopenHour: last < 0 || last + 1 >= stages.length ? null : last + 1,
  };
}

export interface RoadCutClass { min: number; max: number; label: Localized; color: string; weight: number }

/** Map classes for hours impassable (lower bound inclusive). */
export const ROAD_CUT_CLASSES: readonly RoadCutClass[] = [
  { min: 0, max: 0, label: { en: "Not cut", th: "ไม่ถูกตัดขาด" }, color: "#7d8ba0", weight: 1 },
  { min: 1, max: 5, label: { en: "< 6 h", th: "< 6 ชม." }, color: "#f0a04b", weight: 2.2 },
  { min: 6, max: 23, label: { en: "6–24 h", th: "6–24 ชม." }, color: "#e0632a", weight: 2.6 },
  { min: 24, max: 47, label: { en: "24–48 h", th: "24–48 ชม." }, color: "#c62828", weight: 3 },
  { min: 48, max: Infinity, label: { en: "≥ 48 h", th: "≥ 48 ชม." }, color: "#6d0f1a", weight: 3.4 },
];

export function roadCutClassIndex(hours: number): number {
  const index = ROAD_CUT_CLASSES.findIndex((item) => hours >= item.min && hours <= item.max);
  return index < 0 ? 0 : index;
}

/** A named road (or an unnamed class-and-subdistrict group) and how long its modelled pieces were cut. */
export interface RoadCutGroup {
  key: string;
  /** OSM name shared by the pieces, or null for unnamed pieces grouped by class and subdistrict. */
  name: string | null;
  /** Road classes in the group, most important first. */
  classes: string[];
  /** Subdistrict ids of the cut pieces, longest cut length first. */
  tambons: string[];
  /** Length (km) of the pieces that are impassable at some hour. */
  kmCut: number;
  /** Longest cut of any piece (hours). */
  maxHours: number;
  firstHour: number;
  /** Last reopening of its pieces; null when some piece is still cut when the replay ends. */
  reopenHour: number | null;
  /** Indices (into the input features) of the cut pieces. */
  pieces: number[];
  /** [[south, west], [north, east]] of the cut pieces. */
  bounds: [[number, number], [number, number]];
}

const ROAD_CLASS_RANK = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"];
const classRank = (roadClass: string) => {
  const rank = ROAD_CLASS_RANK.indexOf(roadClass);
  return rank < 0 ? ROAD_CLASS_RANK.length : rank;
};

/**
 * Modelled road pieces cut at some hour, grouped by OSM name (or, for unnamed pieces, by class and
 * subdistrict). Named routes come first, so a long unnamed street aggregate never pushes a named road out of
 * the list; within each part the longest cut comes first, then most kilometres cut. Pieces outside the model
 * (`m: false`) are excluded.
 */
export function roadCutGroups(
  features: readonly { geometry: LineGeometry; properties: RoadProps }[],
  cuts: readonly RoadCut[],
  limit = 10,
): RoadCutGroup[] {
  if (features.length !== cuts.length) throw new Error("One road cut is required per feature");
  interface Draft { group: RoadCutGroup; tambonMetres: Map<string, number>; classes: Set<string>; stillCut: boolean }
  const drafts = new Map<string, Draft>();
  features.forEach((feature, index) => {
    const props = feature.properties;
    const cut = cuts[index];
    if (!props.m || cut.hours === 0 || cut.firstHour === null) return;
    const name = props.n?.trim() || null;
    const key = name ? `name:${name}` : `class:${props.c}|${props.t}`;
    let draft = drafts.get(key);
    if (!draft) {
      draft = {
        group: {
          key, name, classes: [], tambons: [], kmCut: 0, maxHours: 0, firstHour: cut.firstHour, reopenHour: null, pieces: [],
          bounds: [[Infinity, Infinity], [-Infinity, -Infinity]],
        },
        tambonMetres: new Map(), classes: new Set(), stillCut: false,
      };
      drafts.set(key, draft);
    }
    const { group } = draft;
    group.kmCut += props.len / 1000;
    group.maxHours = Math.max(group.maxHours, cut.hours);
    group.firstHour = Math.min(group.firstHour, cut.firstHour);
    if (cut.reopenHour === null) draft.stillCut = true;
    else group.reopenHour = Math.max(group.reopenHour ?? 0, cut.reopenHour);
    group.pieces.push(index);
    draft.classes.add(props.c);
    draft.tambonMetres.set(props.t, (draft.tambonMetres.get(props.t) ?? 0) + props.len);
    for (const [lon, lat] of feature.geometry.coordinates) {
      group.bounds[0][0] = Math.min(group.bounds[0][0], lat);
      group.bounds[0][1] = Math.min(group.bounds[0][1], lon);
      group.bounds[1][0] = Math.max(group.bounds[1][0], lat);
      group.bounds[1][1] = Math.max(group.bounds[1][1], lon);
    }
  });
  return [...drafts.values()]
    .map(({ group, tambonMetres, classes, stillCut }) => ({
      ...group,
      kmCut: roundLikePython(group.kmCut, 2),
      reopenHour: stillCut ? null : group.reopenHour,
      classes: [...classes].sort((a, b) => classRank(a) - classRank(b) || a.localeCompare(b)),
      tambons: [...tambonMetres].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([id]) => id),
    }))
    .sort((a, b) => Number(a.name === null) - Number(b.name === null)
      || b.maxHours - a.maxHours || b.kmCut - a.kmCut || a.key.localeCompare(b.key))
    .slice(0, limit);
}

/** How much a road class matters for keeping routes open (trunk roads first); the weight multiplies hours cut. */
export const ROAD_IMPORTANCE: Readonly<Record<string, number>> = {
  motorway: 5, trunk: 4, primary: 3, secondary: 2, tertiary: 1.5, unclassified: 1, residential: 1,
};
/** Importance of a group: the weight of its most important class (1 for unknown classes). */
export const roadImportance = (classes: readonly string[]): number => Math.max(1, ...classes.map((item) => ROAD_IMPORTANCE[item] ?? 1));

/**
 * Split route groups into named roads and unnamed street groups, each ranked by road importance × longest cut
 * (then kilometres cut, then key); `unnamedLimit` keeps only the top unnamed groups.
 */
export function rankRouteGroups(groups: readonly RoadCutGroup[], { unnamedLimit = Infinity }: { unnamedLimit?: number } = {}): { named: RoadCutGroup[]; unnamed: RoadCutGroup[] } {
  const score = (group: RoadCutGroup) => roadImportance(group.classes) * group.maxHours;
  const order = (a: RoadCutGroup, b: RoadCutGroup) => score(b) - score(a) || b.kmCut - a.kmCut || a.key.localeCompare(b.key);
  return {
    named: groups.filter((group) => group.name !== null).sort(order),
    unnamed: groups.filter((group) => group.name === null).sort(order).slice(0, unnamedLimit),
  };
}

/** Total modelled length (km) of every piece of each named road, cut or not, for context next to "km cut". */
export function namedRoadLengths(features: readonly { properties: Pick<RoadProps, "n" | "m" | "len"> }[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const { properties } of features) {
    const name = properties.n?.trim();
    if (!name || !properties.m) continue;
    out.set(name, (out.get(name) ?? 0) + properties.len / 1000);
  }
  return out;
}

/** Web Mercator northing (unitless) for a latitude in degrees. */
export function mercatorY(latitude: number): number {
  const phi = (latitude * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + phi / 2));
}

/**
 * Pixel position of a lon/lat inside a `width` x `height` frame spanning `bounds` ([[south, west], [north, east]]),
 * linear in Web Mercator, which is how the map stretches the imagery and water rasters over the same bounds.
 */
export function projectToFrame(
  longitude: number,
  latitude: number,
  bounds: readonly [readonly [number, number], readonly [number, number]],
  width: number,
  height: number,
): [number, number] {
  const [[south, west], [north, east]] = bounds;
  const top = mercatorY(north);
  const bottom = mercatorY(south);
  return [((longitude - west) / (east - west)) * width, ((top - mercatorY(latitude)) / (top - bottom)) * height];
}

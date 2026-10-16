/**
 * Progress of the proposal's pipeline, box by box (Studio page `/studio/pipeline/`).
 *
 * The five figures of the submitted proposal (GeoHackathon 2026) are redrawn in `pipeline-figures.ts`; every box there
 * points at one topic here. A topic carries its status (done, in progress, not started) as of `PIPELINE_AS_OF`, what the
 * proposal planned, where the work stands, and the evidence: figures, a small chart, images and links into the
 * repository. Several boxes can share a topic (road disruption appears in figures 1, 2 and 4), so one piece of work has
 * one status wherever it is drawn.
 *
 * Every figure here is a modelled planning figure or an agreement with another map or image. None is an observation of
 * a flood, and nothing on the page is real-time or an official warning.
 */

export type StageStatus = "done" | "in_progress" | "not_started";

export const PIPELINE_AS_OF = "16 October 2026";
export const PIPELINE_REPOSITORY = "https://github.com/TUPRAM/flood-guard";

export const STATUS_LABEL: Record<StageStatus, string> = {
  done: "Done",
  in_progress: "In progress",
  not_started: "Not started",
};

export const STATUS_MEANING: Record<StageStatus, string> = {
  done: "Built and running; its output is used, nothing named is outstanding for this round.",
  in_progress: "Built or started, but something named below is still missing.",
  not_started: "No result yet.",
};

export interface DetailNumber { label: string; value: string }
export interface DetailBar { label: string; value: number; display?: string; highlight?: boolean }
export interface DetailChart {
  title: string;
  /** Axis label, with its unit. */
  axis: string;
  max: number;
  bars: DetailBar[];
  /** A pass bar or rule drawn as a dashed line. */
  rule?: { value: number; label: string };
  note: string;
}
export interface DetailMedia { src: string; alt: string; caption: string }
/** A link opens a page of this site (`href` starting with "/"), a file of the repository (`path`) or another address. */
export interface DetailLink { label: string; href?: string; path?: string }

export interface PipelineTopic {
  id: string;
  title: string;
  status: StageStatus;
  /** One sentence: where it stands. */
  summary: string;
  /** What the proposal planned for this box, in short. */
  proposal: string;
  /** Where the work stands now. */
  now: string[];
  numbers?: DetailNumber[];
  chart?: DetailChart;
  media?: DetailMedia[];
  missing?: string[];
  links: DetailLink[];
}

const C2S_CHIP = "/studies/c2s-ms-20260915/r1/visuals/chips/S1A_IW_GRDH_1SDV_20170628T011519_20170628T011544_017227_01CBD9_0966_01031-07449";
const NAN_CASE = `${PIPELINE_REPOSITORY}/blob/claude/nan-case/docs/nan_case.md`;

export const PIPELINE_TOPICS: PipelineTopic[] = [
  // ---------------------------------------------------------------- Figure 1: the decision chain
  {
    id: "flood-input",
    title: "Flood extent or flood probability",
    status: "done",
    summary: "The decision chain runs on a flood extent today: the UNOSAT and GISTDA layer of the 2024 season, read as a scenario (case SE1).",
    proposal: "The chain starts from a flood extent or a flood probability: our own Sentinel-1 radar map, or an agency product from GISTDA or the International Charter.",
    now: [
      "Case SE1 takes the area UNOSAT and GISTDA mapped as water at any time in the 2024 season (product 4009) and treats all of it as flooded at once. It is a scenario, not one day of 2024.",
      "Our own Sentinel-1 maps run too, but none has passed its bar, so they stay report-only (see the promotion gate).",
      "The same chain was run with four flood inputs. The input decides most of the answer, which is why the input is fixed and named before a result is read.",
    ],
    chart: {
      title: "Residents in Mae Sai district who lose every road route, by flood input",
      axis: "Residents (modelled, rounded)",
      max: 70000,
      bars: [
        { label: "Season layer (UNOSAT/GISTDA)", value: 21800, display: "21,800", highlight: true },
        { label: "UN-SPIDER practice (radar)", value: 730, display: "730" },
        { label: "M1-literal (radar)", value: 66810, display: "66,810" },
        { label: "M1-v2 (radar)", value: 210, display: "210" },
      ],
      note: "Same chain, four inputs (flood input comparison, 8 Oct 2026). Report only; no class changed.",
    },
    links: [
      { label: "Flood input comparison", path: "docs/flood_input_comparison.md" },
      { label: "Rights record of product 4009", path: "docs/proposal_execution/rights_basis_4009_v1.json" },
      { label: "Planning view (case SE1)", href: "/command/" },
    ],
  },
  {
    id: "exposure",
    title: "Exposure: people and facilities",
    status: "done",
    summary: "Residents and key facilities inside the flood extent are counted for each of the eight tambons of Mae Sai.",
    proposal: "Count the people and the facilities (hospitals, shelters, schools) inside the flood extent.",
    now: [
      "Residents come from WorldPop 2020; facilities from OpenStreetMap and public lists.",
      "A check on 11 October set residents against 88,900 building outlines: 39% of modelled residents sit in cells with no building. Counted on buildings, residents in the water fall from about 17,900 to 12,600. No class changed, so counts are now said as ranges.",
    ],
    numbers: [
      { label: "Residents in the flood extent, case SE1 (grid / buildings)", value: "about 17,900 / 12,600" },
      { label: "Key facilities (OSM) in water at the replay peak", value: "4 of 42" },
      { label: "Building outlines used in the check", value: "88,900" },
    ],
    chart: {
      title: "Residents inside the flood extent, case SE1, by tambon",
      axis: "Residents (modelled, rounded)",
      max: 12000,
      bars: [
        { label: "Mae Sai (town)", value: 10100, display: "10,100 of 17,900" },
        { label: "Si Mueang Chum", value: 3050, display: "3,050 of 7,160" },
        { label: "Ko Chang", value: 2500, display: "2,500 of 6,700" },
        { label: "Ban Dai", value: 960, display: "960 of 5,040" },
      ],
      note: "WorldPop 2020 counts on the population grid. The four other tambons have under 10% of residents in the extent.",
    },
    media: [
      { src: "/studio-pipeline/case-view-peak.jpg", alt: "The case view of the Mae Sai replay at its modelled peak, with water depth, impassable roads in red and the impact panel.", caption: "Case view, Mae Sai replay at 11 Sep 2024, 02:00: modelled water depth, impassable roads (red) and the impact panel. Low confidence." },
    ],
    links: [
      { label: "Buildings against residents in the water", path: "docs/buildings_in_water.md" },
      { label: "Replay figures to quote", path: "docs/demo/replay_numbers.md" },
      { label: "Case view", href: "/studio/cases/mae-sai-2024/" },
    ],
  },
  {
    id: "road-disruption",
    title: "Road disruption",
    status: "done",
    summary: "A fixed closure rule marks roads in the flood extent as cut, at three levels: strict, central and permissive.",
    proposal: "Estimate which road links are likely to become impassable from flood evidence, road class and bridge or culvert context, and how much longer journeys take. A reasoned estimate, not an official closure.",
    now: [
      "Closure rule v1 was fixed in protocol v1b before any score was computed.",
      "On a THEOS-2 sample tile (Sukhothai, 30 July 2025, 0.5 m), 41 of the 50 road pieces the rule closes at its central level are under water on the image. With a radar candidate as the extent instead, only 5 to 16% are.",
      "For Ko Chang, one road of 1.24 km in Si Mueang Chum alone gives 3,369 of its 5,972 cut-off residents a route back. It is the first road to check at all three levels.",
    ],
    numbers: [
      { label: "Closed road pieces under water on THEOS-2 (central level)", value: "41 of 50 (82%)" },
      { label: "The same, with a radar candidate as the extent", value: "5 to 16%" },
      { label: "Impassable road at the replay peak (model)", value: "176 km of 329 km" },
      { label: "Key Ko Chang road", value: "1.24 km, reconnects 3,369 residents" },
    ],
    media: [
      { src: "/studio-pipeline/theos2-check-sukhothai.jpg", alt: "Slide comparing a THEOS-2 image, the water read from it, and Sentinel-1 radar 44 hours later at Sukhothai.", caption: "THEOS-2 check at Sukhothai, 30 July 2025 (GISTDA sample): one tile of 9 km², agreement between two sensors, not ground truth." },
    ],
    missing: [
      "Nobody has checked the key Ko Chang road on the ground.",
      "The THEOS-2 scene of 17 Sep 2024, which shows that road, arrived on 14 Oct 2026 and is not analysed yet.",
    ],
    links: [
      { label: "THEOS-2 cross-check", path: "docs/theos2_radar_cross_check.md" },
      { label: "Ko Chang road sheet", path: "docs/ko_chang_road_check.md" },
      { label: "Which road reconnects whom", path: "docs/road_reconnection.md" },
      { label: "Protocol v1b (closure rule v1)", path: "docs/proposal_execution/planning_protocol_v1b.json" },
    ],
  },
  {
    id: "access-loss",
    title: "Access loss: normal against disrupted",
    status: "done",
    summary: "Routing before and after the flood shows who loses the hospital within 30 minutes and who loses every road route.",
    proposal: "Run shortest paths on the normal and the disrupted road network to the nearest hospital, shelter and main road, within 15, 30 and 60 minutes.",
    now: [
      "Vehicle routing runs for all eight tambons in case SE1; walking access to shelters runs hour by hour in the replay.",
      "In case SE1 every Ko Chang resident who had a road route loses it. That is why Ko Chang ranks above Mae Sai town.",
      "In the replay, of the residents whose homes flood at the peak, about 6,440 could walk to one of the eight planned shelters before the flood and about 400 still can at the peak.",
    ],
    chart: {
      title: "Residents who lose every road route, case SE1, by tambon",
      axis: "Residents (modelled, rounded)",
      max: 12000,
      bars: [
        { label: "Mae Sai (town)", value: 11610, display: "11,610 of 17,450" },
        { label: "Ko Chang", value: 5970, display: "all 5,970", highlight: true },
        { label: "Si Mueang Chum", value: 2900, display: "2,900 of 6,560" },
        { label: "Ban Dai", value: 360, display: "360 of 4,010" },
      ],
      note: "Ko Chang loses every route for everyone who had one; that drives its class B.",
    },
    media: [
      { src: "/studio-pipeline/planning-view-peak.jpg", alt: "The planning view at the modelled peak, with the eight tambons listed beside a map of water and cut roads around Mae Sai town.", caption: "Planning view at 11 Sep 2024, 02:00 (exercise replay): lost access, residents in water and the fixed planning position of each tambon." },
    ],
    missing: ["Capacity-aware 2SFCA is not run: there is no dated, verified shelter capacity."],
    links: [
      { label: "Which road reconnects whom", path: "docs/road_reconnection.md" },
      { label: "2SFCA method (conditional)", path: "docs/proposal_execution/2sfca_method.md" },
      { label: "Replay figures to quote", path: "docs/demo/replay_numbers.md" },
    ],
  },
  {
    id: "population-age",
    title: "Vulnerability: age-resolved population",
    status: "in_progress",
    summary: "Age-resolved population is in, but the open 1 km age grid cannot tell the tambons apart.",
    proposal: "Age-resolved population (older adults, children) defines the vulnerable groups for exposure and the equity gap.",
    now: [
      "WorldPop 2024 age bands at 1 km feed the vulnerability component of the score.",
      "The age mix is the same in five of the eight tambons (share 0.4055), because the grid carries one age mix per district.",
    ],
    missing: ["A Thai age source at village or tambon level that we may use."],
    links: [
      { label: "Age exposure, Mae Sai", path: "outputs/planning_v1/age_exposure_mae_sai_v1.json" },
      { label: "Access loss by age", path: "docs/equity_by_age.md" },
      { label: "Purpose review of the age data", path: "docs/proposal_execution/age_data_purpose_review_v1.md" },
    ],
  },
  {
    id: "equity-gap",
    title: "Evacuation Equity Gap",
    status: "in_progress",
    summary: "The gap is computed; its direction depends on which age data are used, so it does not lead the pitch.",
    proposal: "Is access loss concentrated on vulnerable residents? The difference and the ratio between groups, with sensitivity bands.",
    now: [
      "With the open modelled age grid there is no gap of a point or more for the district.",
      "With registered age counts per tambon (DOPA), residents aged 60 and over lose hospital access 1.06 to 1.13 times as often as younger residents, in all 180 runs. Those counts leave out about two residents in five, who are not Thai nationals.",
      "In the replay the vulnerable group is a proxy defined by terrain and remoteness, not by age.",
    ],
    numbers: [
      { label: "Gap with the open age grid", value: "under 1 point" },
      { label: "Ratio 60+ against younger (registered ages)", value: "1.06 to 1.13" },
    ],
    missing: ["Age data fine enough to separate tambons.", "Age groups for children as well as older adults."],
    links: [{ label: "Access loss by age", path: "docs/equity_by_age.md" }],
  },
  {
    id: "fpps",
    title: "Priority score (FPPS) and A to E action classes",
    status: "done",
    summary: "Eight tambons are scored and classed in case SE1; seven of the eight classes hold over 180 runs.",
    proposal: "FPPS = 30% flood likelihood + 25% exposure + 20% access gap + 15% road criticality + 10% vulnerability, each on 0 to 100, mapped to classes A to E. Low confidence forces class E.",
    now: [
      "Ko Chang ranks first (78, class B, Keep Routes Open) above Mae Sai town (71, class D), because it loses every road route.",
      "The weights were tested: Ko Chang stays first with equal weights, with each weight halved or raised by half, and in 9 of 10 random weightings.",
      "Over 180 runs (3 flood sizes × 3 closure levels × 2 population datasets × 2 vulnerability scales × 5 weight sets), seven classes hold. Mae Sai town holds in half, so it reads \"unstable: verify\". This result is not yet on the published page, which still says \"stability not evaluated\".",
    ],
    numbers: [
      { label: "Ko Chang", value: "78 · B, Keep Routes Open" },
      { label: "Mae Sai (town)", value: "71 · D, unstable: verify" },
      { label: "Si Mueang Chum", value: "59 · D" },
      { label: "Ban Dai", value: "50 · D" },
      { label: "Four other tambons", value: "5 to 32 · E" },
    ],
    chart: {
      title: "How often each tambon keeps its class, over 180 runs",
      axis: "Share of runs (%)",
      max: 100,
      bars: [
        { label: "Mae Sai (town)", value: 50, display: "50%", highlight: true },
        { label: "Ko Chang", value: 78, display: "78%" },
        { label: "Pong Pha", value: 98, display: "98%" },
        { label: "Si Mueang Chum", value: 100, display: "100%" },
        { label: "Ban Dai", value: 100, display: "100%" },
        { label: "Huai Khrai", value: 100, display: "100%" },
        { label: "Wiang Phang Kham", value: 100, display: "100%" },
        { label: "Pong Ngam", value: 100, display: "100%" },
      ],
      rule: { value: 60, label: "rule: hold in 60%" },
      note: "Protocol v1b: a class must hold in at least 60% of the runs. Class E never means safe.",
    },
    media: [
      { src: "/studio-pipeline/policy-page.jpg", alt: "The top of the plain-language policy page: flood maps show where the water goes, we show who could be cut off.", caption: "The policy page explains the score and the five classes in plain language, in English and Thai." },
    ],
    links: [
      { label: "Published result, case SE1", path: "apps/web/public/planning-overlays/mae-sai-2024/se1.json" },
      { label: "Weight test", path: "docs/fpps_weight_sensitivity.md" },
      { label: "Stability over 180 runs", path: "docs/uncertainty_ensemble_rescaled_demand.md" },
      { label: "The second class reading", path: "docs/class_v2_reading.md" },
      { label: "Policy page", href: "/policy/" },
    ],
  },

  // ---------------------------------------------------------------- Figure 2: flood evidence and decision context
  {
    id: "sentinel1",
    title: "Sentinel-1 radar: acquisition",
    status: "done",
    summary: "Sentinel-1 scenes are fetched with their names, dates and SHA-256 fingerprints recorded, so inputs cannot change quietly.",
    proposal: "Pre- and post-event VV and VH. Every scene is recorded with a digital fingerprint of its contents.",
    now: [
      "Mae Sai: the pass used is 15 Sep 2024, 3.8 days after the modelled peak. There was no pass between 6 and 15 September.",
      "Nan (draft): all 14 passes from 16 July to 13 August 2025, with a dry-season image for each orbit.",
    ],
    media: [
      { src: "/geoai/scene_sar_post_vh.png", alt: "A Sentinel-1 VH radar image over the Mae Sai area after the flood; dark patches are likely water.", caption: "Sentinel-1 VH after the flood over the Mae Sai area (dark is likely water). From the earlier GeoAI analysis, kept in the archive." },
    ],
    missing: ["The Sentinel-1 rights record is drafted and still waits for the owners' confirmation."],
    links: [
      { label: "The Sentinel-1 pass gap", path: "outputs/a1_diagnosis/sentinel1_pass_gap.json" },
      { label: "Sentinel-1 rights record (draft)", path: "docs/proposal_execution/rights_basis_sentinel1_v1.json" },
    ],
  },
  {
    id: "terrain",
    title: "Terrain: DEM, HAND and slope",
    status: "done",
    summary: "Elevation, height above the nearest drainage (HAND) and slope sit on the common grid.",
    proposal: "Terrain conditions the flood evidence: DEM, HAND and slope.",
    now: [
      "HAND drives the flood susceptibility model and the terrain screen of our radar maps.",
      "Lesson from Nan: the HAND screen ruled out 71% of the water our map missed, before the radar was read.",
    ],
    media: [
      { src: "/geoai/scene_dem.png", alt: "An elevation model of the Mae Sai area: hills in the west, the flat valley in blue.", caption: "Elevation over the Mae Sai area. From the earlier GeoAI analysis, kept in the archive." },
    ],
    links: [{ label: "Flood susceptibility model", path: "docs/flood_susceptibility_model.md" }],
  },
  {
    id: "hydromet",
    title: "Hydromet context: rainfall and permanent water",
    status: "done",
    summary: "Hourly rain gauges and permanent water give context to the replay; they are not flood observations.",
    proposal: "Rainfall and permanent water as context for the flood evidence.",
    now: [
      "The replay shows hourly rain at two HII ThaiWater gauges (open data) on the same time axis as the river stage.",
      "Rainfall gives context only. It does not enter the score.",
    ],
    links: [{ label: "Case view with the rain gauges", href: "/studio/cases/mae-sai-2024/" }],
  },
  {
    id: "preprocessing",
    title: "Preprocessing",
    status: "in_progress",
    summary: "Calibration and terrain correction run; one record certifying all four steps on a product is still missing.",
    proposal: "Raw radar scenes are cleaned: position corrected, noise removed, brightness calibrated, terrain distortion fixed.",
    now: [
      "Radar is read from radiometrically terrain-corrected (RTC) Sentinel-1 products by a shared parallel reader.",
      "The steps run; the proposal names what is still missing: one published record certifying that all four ran together on a given product.",
    ],
    missing: ["One record per product that certifies the four steps."],
    links: [{ label: "Shared radar reader", path: "src/floodguard/s1_rtc.py" }],
  },
  {
    id: "feature-alignment",
    title: "Feature alignment",
    status: "done",
    summary: "Before and after radar, their change, slope and permanent water are stacked on one grid, with the same maths for training and prediction.",
    proposal: "One layered image on one grid, identical transforms at training and inference time.",
    now: [
      "The standard stack holds VV and VH before and after, their change, slope and permanent water. HAND and land cover are optional extras.",
    ],
    links: [{ label: "GeoAI method", path: "docs/proposal_execution/geoai_method.md" }],
  },
  {
    id: "sar-baseline",
    title: "SAR change detection: the deterministic baseline",
    status: "in_progress",
    summary: "Several radar methods run; none has passed its bar, so all stay report-only.",
    proposal: "Adaptive Otsu on the radar change image as the operational baseline: simple, repeatable, no black box.",
    now: [
      "Adaptive Otsu declined all 81 windows at Mae Sai: the only pass came 3.8 days after the peak.",
      "Fixed rules (UN-SPIDER practice, M1-literal, M1-v2) and a tuned detector were tested. On a held-out flooded town no method saw more than about a quarter of the water.",
      "Nan, July 2025 (draft, PR #66): our map M1-z went through the whole chain and scored IoU 0.226 against JAXA's ALOS-2 map, under the bar of 0.40 fixed before the test. All 35 tambons therefore read class E.",
    ],
    chart: {
      title: "Nan, 28 July 2025: agreement with JAXA's ALOS-2 flood map (IoU), same radar pass",
      axis: "IoU (1 = identical maps)",
      max: 0.6,
      bars: [
        { label: "Our map M1-z (under test)", value: 0.226, display: "0.23", highlight: true },
        { label: "Our frozen detector", value: 0.399, display: "0.399" },
        { label: "One-feature threshold", value: 0.467, display: "0.47" },
        { label: "UN-SPIDER practice", value: 0.51, display: "0.51" },
      ],
      rule: { value: 0.4, label: "pass bar 0.40" },
      note: "Grey bars are comparators on the same pass, reported and never renamed as our result. Agreement with another satellite's map, not ground truth.",
    },
    links: [
      { label: "Why the threshold-only method failed", path: "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md" },
      { label: "Radar against the dated agency layer", path: "docs/dated_radar_check.md" },
      { label: "Detection improvement, with a held-out test", path: "docs/radar_detection_improvement.md" },
      { label: "The Nan case (draft branch)", href: NAN_CASE },
    ],
  },
  {
    id: "rf-xgboost",
    title: "Random Forest / XGBoost refinement",
    status: "in_progress",
    summary: "Trained twice; on data they never saw, neither beat a one-feature model, so neither is promoted.",
    proposal: "Calibrated Random Forest and XGBoost combine radar change with terrain and context. Label-gated; promoted only if they beat the baseline on hold-out.",
    now: [
      "Flood susceptibility (8 Oct): random forest and boosted trees against one terrain feature (height above the nearest stream), tested on three districts never seen. ROC AUC 0.921 and 0.925 against 0.923. The rule asked for 0.02 more, so the one-feature model is cited, as a screening layer.",
      "Radar classifier (9 Oct): boosted trees trained on the agency layer of 22 Oct 2024, checked against the water on a THEOS-2 tile: IoU 0.11, against 0.57 for a single radar threshold. Not adopted.",
    ],
    numbers: [
      { label: "Susceptibility, ROC AUC on unseen districts: one feature", value: "0.923" },
      { label: "Random forest", value: "0.921" },
      { label: "Boosted trees", value: "0.925" },
    ],
    chart: {
      title: "THEOS-2 tile, Sukhothai: agreement with the water on the 0.5 m image (IoU)",
      axis: "IoU (1 = identical maps)",
      max: 0.6,
      bars: [
        { label: "Trained boosted trees (under test)", value: 0.11, display: "0.11", highlight: true },
        { label: "Fixed rule M1-v2", value: 0.21, display: "0.21" },
        { label: "Fixed rule UN-SPIDER", value: 0.26, display: "0.26" },
        { label: "Fixed rule M1-literal", value: 0.38, display: "0.38" },
        { label: "One-feature threshold", value: 0.57, display: "0.57" },
      ],
      note: "One tile of 9 km², one event. The trained model flags a ninth of the water the image shows.",
    },
    links: [
      { label: "Flood susceptibility model", path: "docs/flood_susceptibility_model.md" },
      { label: "Radar flood classifier", path: "docs/radar_flood_classifier.md" },
    ],
  },
  {
    id: "unet",
    title: "U-Net / FPN deep segmentation",
    status: "in_progress",
    summary: "A SAR U-Net is benchmarked on public labelled chips; its skill in Thailand is not measured.",
    proposal: "A governed deep-learning candidate. It stays report-only until it beats the baseline on an untouched event.",
    now: [
      "C2S-MS public benchmark (15 Sep 2026): 900 chips from 18 events, whole events held apart; U-Net beside random forest and XGBoost.",
      "Applied to Mae Sai (22 August and 15 September 2024) with probability, validity and abstention. No Thai reference exists to score it.",
    ],
    media: [
      { src: `${C2S_CHIP}/radar.png`, alt: "A radar chip from the C2S-MS public benchmark.", caption: "C2S-MS benchmark chip (2017, outside Thailand): radar input." },
      { src: `${C2S_CHIP}/reference.png`, alt: "The human water label for the same chip.", caption: "The same chip: human water label." },
      { src: `${C2S_CHIP}/sar/unet/probability.png`, alt: "The U-Net water probability for the same chip.", caption: "The same chip: U-Net water probability." },
    ],
    missing: ["Rights-cleared, time-matched Thai flood labels to fine-tune and test on."],
    links: [{ label: "C2S-MS study", href: "/studio/studies/c2s-ms-20260915/" }],
  },
  {
    id: "observation-product",
    title: "Flood observation product",
    status: "in_progress",
    summary: "Our maps carry probability, validity, uncertainty and abstention; none is decision-eligible yet.",
    proposal: "Every candidate returns a probability surface with validity, sensor quality, uncertainty and abstention.",
    now: [
      "M1-v2 at Mae Sai flags 3.0 km² and gives no answer for 77% of the cells; the no-answer share stays in the record instead of being counted as dry.",
    ],
    links: [{ label: "Radar results, Mae Sai", path: "outputs/planning_v1/radar_o1_mae_sai_v1.json" }],
  },
  {
    id: "promotion-gate",
    title: "Evidence and promotion gate",
    status: "done",
    summary: "The gate works: a map that fails cannot change any road, access, equity result or score.",
    proposal: "One decision: may this flood map influence anything? Criteria: provenance verified, licence cleared, spatial hold-out frozen, calibration in order, human review complete.",
    now: [
      "Rules and bars are committed before each test (signed protocols v1a and v1b, frozen plans).",
      "Low confidence forces class E. At Nan all 35 tambons read E. That changed no class there, because their classes would have been E anyway.",
      "Our own radar through the Mae Sai chain (case O1) was not issued.",
    ],
    links: [
      { label: "Protocol v1b", path: "docs/proposal_execution/planning_protocol_v1b.json" },
      { label: "Model authorisation", path: "docs/proposal_execution/ml_authorization.md" },
    ],
  },
  {
    id: "report-only",
    title: "Blocked: report-only record",
    status: "done",
    summary: "Every refused result stays visible, with the reason attached.",
    proposal: "A result that fails the gate is held for review: inspectable, with the blocking reason, never silently replaced.",
    now: [
      "Report-only so far: the radar candidates at Mae Sai, the radar classifier, the detection improvement, the trained susceptibility trees and the Nan radar map (draft).",
    ],
    links: [{ label: "Open points and blockers", path: "docs/proposal_execution/UNRESOLVED.md" }],
  },
  {
    id: "roads-facilities",
    title: "Roads and facilities",
    status: "done",
    summary: "OpenStreetMap roads and hospitals, and the shelters reported in 2024 news, are on the network.",
    proposal: "Road topology and service locations as the decision context.",
    now: [
      "Shelters: 19 reported in 2024 news, 15 located. Shelter capacity is estimated from building footprints, not from a listed figure.",
    ],
    links: [{ label: "Shelters reported in 2024", path: "outputs/mae_sai_reported_shelters_2024.json" }],
  },
  {
    id: "decision-layer",
    title: "Protected deterministic decision layer",
    status: "done",
    summary: "Exposure, road risk, access, equity and FPPS are deterministic, tested Python functions.",
    proposal: "The decision side stays deterministic and inspectable; only gated evidence may enter it.",
    now: [
      "Each stage has a --verify step; every result file names the hashes of both protocols and of its inputs.",
    ],
    links: [
      { label: "Planning outputs and how to rerun them", path: "outputs/planning_v1/README.md" },
      { label: "Decision engine code", path: "src/floodguard" },
    ],
  },
  {
    id: "public-view",
    title: "Public preparedness view",
    status: "done",
    summary: "A Thai-first phone view: plain alerts for a home, shelters, a household plan and official hotlines. No score.",
    proposal: "Citizen view, Thai first, from a reduced evidence set. No evacuation instructions.",
    now: ["Five tabs: Home, Report, Shelter, Prepare and SOS, with practice scenarios that replay September 2024."],
    media: [
      { src: "/studio-pipeline/public-five-tabs.jpg", alt: "Five phone screens of the public view: Home, Report, Shelter, Prepare and SOS.", caption: "Public view, practice replay: Home, Report, Shelter, Prepare and SOS." },
    ],
    links: [{ label: "Public view", href: "/public/" }],
  },
  {
    id: "command-view",
    title: "Planning command workspace",
    status: "done",
    summary: "The exercise replay for coordinators: each tambon hour by hour, practice items and the fixed planning position.",
    proposal: "Map-first prioritisation for government and rescue teams.",
    now: ["The exercise replay prints the modelled figures of each tambon hour by hour; practice items (EX) go to team callsigns. It dispatches no one."],
    media: [
      { src: "/studio-pipeline/command-exercise-rest.jpg", alt: "The command exercise at replay hour 84, with the tambon table and the district map.", caption: "Command exercise at replay hour 84 (12 Sep 2024, 12:00)." },
    ],
    links: [{ label: "Planning view", href: "/command/" }],
  },
  {
    id: "studio-view",
    title: "Studio: evidence and blockers",
    status: "done",
    summary: "Studies, the case replay, evidence reports, the team check page and this pipeline page.",
    proposal: "Provenance, quality, model records, blockers and authorisation state, for technical review. Absences are shown, never filled in.",
    now: ["The team records its own acceptance of each result on the team check page before it goes on a page."],
    links: [
      { label: "Studio", href: "/studio/" },
      { label: "Team check page", href: "/studio/validation-check/" },
    ],
  },

  // ---------------------------------------------------------------- Figure 3: implementation architecture
  {
    id: "api-service",
    title: "FastAPI artifact and scenario service",
    status: "done",
    summary: "A typed API checks artifacts against their schemas, keeps blocked and unavailable states explicit and serves versioned endpoints.",
    proposal: "Schema checks, role projections and versioned endpoints between the pages and the compute layer.",
    now: ["Python 3.12, FastAPI and Pydantic, with its own tests in services/api."],
    links: [{ label: "API service", path: "services/api/README.md" }],
  },
  {
    id: "contracts",
    title: "Shared JSON Schema and TypeScript contracts",
    status: "done",
    summary: "One set of identifiers, fields and states shared by Python, the API and the pages.",
    proposal: "Keep identifiers, fields and authorisation states consistent across layers.",
    now: ["The contracts package is type-checked and tested in every CI run."],
    links: [{ label: "Contracts package", path: "packages/contracts/package.json" }],
  },
  {
    id: "geoai-runner",
    title: "Isolated GeoAI runner",
    status: "done",
    summary: "Model training and inference run in their own Python environment; the pages and decision tests never import it.",
    proposal: "Tile export, controlled training, tiled inference and uncertainty, with heavy ML dependencies kept apart.",
    now: ["Its contract layer states that a candidate run cannot feed the decision layer."],
    links: [{ label: "GeoAI runner", path: "services/geoai-runner/README.md" }],
  },
  {
    id: "trusted-adapter",
    title: "Trusted adapter",
    status: "done",
    summary: "The only bridge from a model product to the reporting areas; it refuses anything not cleared.",
    proposal: "Only a gated, provenance-tracked observation may cross from the GeoAI side to the decision engine.",
    now: ["Nothing has crossed it yet: no observation of ours is cleared. A report-only bridge records candidate evidence without feeding the decision table."],
    links: [{ label: "Report-only bridge", path: "src/floodguard/candidate_zonal_receipt.py" }],
  },
  {
    id: "external-workspace",
    title: "External data workspace",
    status: "done",
    summary: "Satellite, terrain, population and road files stay outside Git; the repository keeps manifests and hashes.",
    proposal: "Candidate rasters and model files stay in an external workspace.",
    now: ["Every external input is named with its SHA-256 in the receipts."],
    links: [{ label: "Receipts", path: "docs/proposal_execution/RECEIPTS.jsonl" }],
  },
  {
    id: "manifest-outputs",
    title: "Manifest-backed outputs",
    status: "done",
    summary: "COG, GeoJSON, CSV and JSON outputs, each with a receipt.",
    proposal: "Reproducible outputs bound to their inputs.",
    now: ["Published files carry source time, confidence and assumptions; the pages check them against their hashes."],
    links: [{ label: "Planning outputs", path: "outputs/planning_v1/README.md" }],
  },
  {
    id: "offline-bundles",
    title: "Offline judging bundles",
    status: "in_progress",
    summary: "The competition build installs for offline use; a rehearsal on a second laptop has not been made.",
    proposal: "Role-filtered, checksummed bundles that open without a connection.",
    now: ["The offline install has a 12 MB budget and its own tests."],
    missing: ["A full offline rehearsal on a second laptop."],
    links: [{ label: "Offline dry-run checklist", path: "docs/demo/offline_dry_run_checklist.md" }],
  },

  // ---------------------------------------------------------------- Figure 4: the twelve stages
  {
    id: "event-registration",
    title: "Event registration",
    status: "done",
    summary: "Every analysis is stamped with its area, event, data version and run.",
    proposal: "A fixed identity for area, event, data and run, so a map of one place or date cannot pass for another.",
    now: ["Study areas carry a geometry SHA-256; result files name their event window and run."],
    links: [{ label: "Planning outputs", path: "outputs/planning_v1/README.md" }],
  },
  {
    id: "labels-partitions",
    title: "Labels and partitions",
    status: "in_progress",
    summary: "The splitting works and labels exist from several sources; a qualified Thai reference does not.",
    proposal: "Tiles fixed in advance for learning and for testing; a reference map supplies the correct answers.",
    now: [
      "Three team members labelled 300 THEOS-2 points; they agree with each other on 57% of them.",
      "The agency layer dated 22 Oct 2024 at Mae Sai (3.6 km²) served as training labels for the radar classifier.",
    ],
    missing: ["A reference with permission to use, trained reviewers, independent double-checking and a locked version."],
    links: [
      { label: "THEOS-2 water labels, three labellers", path: "docs/theos2_water_label_check.md" },
      { label: "A second THEOS-2 water rule", path: "docs/theos2_water_rule_v2.md" },
    ],
  },
  {
    id: "model-training",
    title: "Model training",
    status: "in_progress",
    summary: "Candidate models are trained with every run recorded; none has beaten the simple baselines.",
    proposal: "Candidate flood models learn from the training tiles, each run recording its settings and inputs.",
    now: [
      "Trained so far: random forest and boosted trees (susceptibility and radar), and a SAR U-Net on the C2S-MS benchmark.",
      "On data they never saw, a one-feature model held up as well or better each time.",
    ],
    links: [
      { label: "Flood susceptibility model", path: "docs/flood_susceptibility_model.md" },
      { label: "Radar flood classifier", path: "docs/radar_flood_classifier.md" },
      { label: "C2S-MS study", href: "/studio/studies/c2s-ms-20260915/" },
    ],
  },
  {
    id: "evaluation",
    title: "Evaluation and calibration",
    status: "in_progress",
    summary: "Held-out tests run against other references; a qualified Thai reference is still missing.",
    proposal: "Score against held-back tiles, check calibration, and set a rule for when to abstain.",
    now: [
      "Tests so far: three unseen districts with calibration (susceptibility), THEOS-2 tiles (radar), and JAXA's map at Nan (our radar map).",
      "These are agreement figures with another map or image, not ground truth.",
    ],
    missing: ["A qualified Thai event reference."],
    links: [
      { label: "Flood susceptibility model", path: "docs/flood_susceptibility_model.md" },
      { label: "The Nan case (draft branch)", href: NAN_CASE },
    ],
  },
  {
    id: "decision-eligible-product",
    title: "Decision-eligible flood observation product",
    status: "in_progress",
    summary: "No observation product of ours has passed the gate; the chain reads the agency layer as a scenario.",
    proposal: "Only a product that passes every gate may feed road disruption, access and the score.",
    now: ["The decision chain runs today on the UNOSAT/GISTDA season layer, named as a scenario."],
    missing: ["A radar map of ours that passes its bar on a qualified reference."],
    links: [{ label: "Flood input comparison", path: "docs/flood_input_comparison.md" }],
  },

  // ---------------------------------------------------------------- Figure 5: the three sites
  {
    id: "site-mae-sai",
    title: "Benchmark: Mae Sai, Chiang Rai (September 2024)",
    status: "in_progress",
    summary: "The full decision chain runs on the 2024 event; the method itself is not yet qualified.",
    proposal: "Can the method be qualified? A historical benchmark with the full decision chain.",
    now: [
      "Case SE1 scores the eight tambons; an hour-by-hour replay runs from 9 to 19 September.",
      "The replay peak is fitted to the mud line of the 15 Sep 2024 Sentinel-2 image (89% covered). On the held-back half it covered 62%, so it is a fit, not a check.",
      "Added beyond the proposal: a second event, the Nan floods of July 2025 (draft, PR #66).",
    ],
    media: [
      { src: "/studio-pipeline/replay-river-fit-peaks.jpg", alt: "Two maps of the modelled peak of the Mae Sai replay, revisions r4 and r5, and where they differ.", caption: "The modelled peak of replay r4 and r5, and where they differ." },
    ],
    missing: ["A qualified reference for the event.", "A ground check of the Ko Chang roads."],
    links: [
      { label: "Replay fitted to the satellite image", path: "docs/replay_river_fit.md" },
      { label: "Case view", href: "/studio/cases/mae-sai-2024/" },
    ],
  },
  {
    id: "site-hat-yai",
    title: "Urban transfer: Hat Yai, Songkhla (November 2025)",
    status: "in_progress",
    summary: "A candidate road-closure sensitivity ran; a qualified transfer is blocked.",
    proposal: "Does it transfer to urban stress? Roads, hospitals, shelters and dense-urban radar.",
    now: [
      "An uncalibrated radar change candidate, seven reviewed hospital destinations and a fixed road graph.",
      "The new 30-minute walking loss moves from about 9,940 to 374 residents with the closure-length rule alone, so the headline is not robust to that assumption.",
    ],
    chart: {
      title: "Hat Yai: residents newly beyond a 30-minute walk to a hospital, by closure rule",
      axis: "Residents (modelled, rounded)",
      max: 10000,
      bars: [
        { label: "Any overlap closes the road", value: 9940, display: "9,940" },
        { label: "At least 20 m of overlap", value: 6825, display: "6,825" },
        { label: "At least 50 m of overlap", value: 374, display: "374" },
      ],
      note: "Candidate sensitivity on a hypothetical rule; no reference, no score.",
    },
    missing: ["An event reference, qualified roads and facilities, and calibrated radar."],
    links: [{ label: "Hat Yai transfer study", path: "docs/proposal_execution/hat_yai_transfer.md" }],
  },
  {
    id: "site-bangkok",
    title: "Scale target: Lower Chao Phraya, Greater Bangkok",
    status: "not_started",
    summary: "Roadmap only: baseline access context for two lower-basin areas, no flood input.",
    proposal: "Can the architecture scale? Data coverage, computation and governance. Not a final-round commitment.",
    now: ["Baseline access context exists for two areas; no flood case is built."],
    links: [{ label: "Lower basin context", path: "docs/proposal_execution/lower_basin_context.md" }],
  },
];

export const TOPIC_BY_ID: Record<string, PipelineTopic> = Object.fromEntries(PIPELINE_TOPICS.map((topic) => [topic.id, topic]));

export function statusCounts(topicIds: Iterable<string>): Record<StageStatus, number> {
  const counts: Record<StageStatus, number> = { done: 0, in_progress: 0, not_started: 0 };
  for (const id of new Set(topicIds)) counts[TOPIC_BY_ID[id].status] += 1;
  return counts;
}

export function linkHref(link: DetailLink): string {
  if (link.href) return link.href;
  return `${PIPELINE_REPOSITORY}/blob/master/${link.path}`;
}

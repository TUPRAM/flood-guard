/**
 * The "Follow-up on technical mentoring" segment of Mentoring Session II (0:10 to 0:25), as a Studio page
 * (`/studio/technical-follow-up/`).
 *
 * Part 1 shows the data pipeline as fourteen stages in four steps. Each stage opens a detail panel: most reuse a topic
 * of the pipeline page (`pipeline-progress.ts`), so the two pages say the same thing; the five stages that page does not
 * draw as a box of their own have their topic here. Parts 2 to 4 are the GeoAI decisions, the handling of uncertainty
 * and the open blockers.
 *
 * Every figure is a modelled planning figure or an agreement with another map or image. Nothing here is real-time or
 * an official warning.
 */

import { TOPIC_BY_ID, type PipelineTopic } from "./pipeline-progress";

export const FOLLOW_UP_DATE = "16 October 2026";

/** Topics of this page only: stages that the proposal's figures do not draw as a box of their own. */
export const FOLLOW_UP_TOPICS: PipelineTopic[] = [
  {
    id: "theos2-check",
    title: "THEOS-2 check",
    status: "in_progress",
    summary: "THEOS-2 has been used on sample tiles; the scene over Mae Sai arrived on 14 October and is not analysed yet.",
    proposal: "Very high resolution optical images (0.5 m) show which roads were under water, which radar cannot see well.",
    now: [
      "Sukhothai sample tile (30 July 2025): where the radar flags water, the image shows water in 6 to 8 cases of 10, but the radar flags only a quarter to a half of the water the image shows.",
      "The road-closure rule agreed with the image for 41 of 50 closed road pieces, given the image's own water as the extent.",
      "The water read from the image was checked against 300 points labelled by three team members: of what the rule calls water, 90% is water; it finds 71% of the water the team marked. A second, simpler rule did 8 points better.",
      "GISTDA delivered the clear scene of 17 September 2024 over Mae Sai town and the west of Ko Chang on 14 October. Our test plan for it was fixed, and the radar readings frozen, before it arrived.",
    ],
    numbers: [
      { label: "Closed road pieces under water on the image", value: "41 of 50" },
      { label: "Radar flags that are water on the image", value: "61 to 76%" },
      { label: "Image water flagged by the radar", value: "22 to 50%" },
      { label: "Team labels: rule's water that is water / water found", value: "90% / 71%" },
    ],
    media: [
      { src: "/studio-pipeline/theos2-check-sukhothai.jpg", alt: "Slide comparing a THEOS-2 image, the water read from it, and Sentinel-1 radar 44 hours later at Sukhothai.", caption: "THEOS-2 check at Sukhothai, 30 July 2025 (GISTDA sample): one tile of 9 km², agreement between two sensors, not ground truth." },
    ],
    missing: ["Running the frozen plan on the 17 Sep 2024 scene.", "Written terms from GISTDA for showing the imagery in the final pitch."],
    links: [
      { label: "THEOS-2 cross-check", path: "docs/theos2_radar_cross_check.md" },
      { label: "THEOS-2 water labels, three labellers", path: "docs/theos2_water_label_check.md" },
      { label: "A second THEOS-2 water rule", path: "docs/theos2_water_rule_v2.md" },
      { label: "Frozen plan for the Mae Sai scene", path: "docs/proposal_execution/theos2_study_event_check_plan_v1.md" },
    ],
  },
  {
    id: "susceptibility",
    title: "Flood susceptibility model",
    status: "done",
    summary: "Runs as a screening layer: one terrain feature held up as well as the trained trees on three unseen districts.",
    proposal: "The proposal's method 2: Random Forest or XGBoost on terrain, drainage and context. Without event labels it stays a susceptibility layer and cannot replace a flood extent.",
    now: [
      "Trained on Mae Sai; tested once, after a freeze, on Mae Chan, Chiang Saen and Mae Fa Luang.",
      "The rule fixed before the test: a tree model is cited only if it is at least 0.02 better on both ranking scores the plan named (ROC AUC is one). Neither was, so the one-feature model (height above the nearest stream) is cited.",
      "It is a screening layer only: it feeds no planning score today.",
    ],
    numbers: [
      { label: "ROC AUC, one feature", value: "0.923" },
      { label: "ROC AUC, random forest", value: "0.921" },
      { label: "ROC AUC, boosted trees", value: "0.925" },
      { label: "Calibration error, one feature (lower is better)", value: "0.046" },
    ],
    chart: {
      title: "ROC AUC on three districts the models never saw",
      axis: "ROC AUC (1 = perfect ranking)",
      max: 1,
      bars: [
        { label: "One terrain feature (cited)", value: 0.923, display: "0.923", highlight: true },
        { label: "Random forest", value: 0.921, display: "0.921" },
        { label: "Boosted trees", value: 0.925, display: "0.925" },
      ],
      note: "The three are the same within 0.002; the rule asked for 0.02 more before a tree model could be cited.",
    },
    links: [
      { label: "Flood susceptibility model", path: "docs/flood_susceptibility_model.md" },
      { label: "Its plan, fixed before the test", path: "docs/proposal_execution/flood_susceptibility_model_plan_v1.md" },
    ],
  },
  {
    id: "ground-check",
    title: "Ground check of roads",
    status: "not_started",
    summary: "Nobody has looked at the key Ko Chang road on site, so its closure is still a model result.",
    proposal: "Road status is an estimate, not an official closure; candidate road risk stays labelled apart from confirmed conditions.",
    now: [
      "The desk sheet is done: one road of 1.24 km in Si Mueang Chum alone gives 3,369 of Ko Chang's 5,972 cut-off residents a route back. It is the first road to check at all three closure levels.",
      "The elevation model cannot tell whether that road is raised.",
      "The THEOS-2 scene of 17 Sep 2024 covers it and could show whether it was under water.",
    ],
    numbers: [
      { label: "Key road length", value: "1.24 km" },
      { label: "Ko Chang residents it reconnects", value: "3,369 of 5,972" },
    ],
    missing: ["One afternoon with the DDPM Chiang Rai office, or someone who knows the road.", "The THEOS-2 check of the 17 Sep 2024 scene."],
    links: [
      { label: "Ko Chang road sheet", path: "docs/ko_chang_road_check.md" },
      { label: "Which road reconnects whom", path: "docs/road_reconnection.md" },
    ],
  },
  {
    id: "stability",
    title: "Stability over 180 runs",
    status: "done",
    summary: "Seven of eight classes hold; Mae Sai town's does not, so it reads \"unstable: verify\".",
    proposal: "Perturb the weights and the input uncertainty, and flag rankings or classes that change under small assumptions.",
    now: [
      "The whole chain ran 180 ways: 3 flood sizes × 3 road-closure levels × 2 population datasets × 2 vulnerability scales × 5 weight sets.",
      "Protocol v1b: a class must hold in at least 60% of the runs. Ko Chang holds in 78%; Mae Sai town in 50%, because its class depends on the population data.",
      "This result is not yet on the published page, which still says \"stability not evaluated\".",
    ],
    chart: TOPIC_BY_ID.fpps.chart,
    links: [
      { label: "Stability over 180 runs", path: "docs/uncertainty_ensemble_rescaled_demand.md" },
      { label: "Planning outputs (plan task E10)", path: "outputs/planning_v1/README.md" },
    ],
  },
  {
    id: "web-views",
    title: "Three web views",
    status: "done",
    summary: "Public, Planning and Studio views read the same evidence; each shows what its audience may see. English and Thai.",
    proposal: "Three role-specific surfaces on one evidence context, separated in code, not only in layout.",
    now: [
      "Public: a Thai-first phone view with plain alerts for a home, shelters, a household plan and official hotlines, and no score.",
      "Planning: the exercise replay of September 2024 for coordinators, hour by hour.",
      "Studio: studies, the case replay, the team check page and the pipeline page. A plain-language policy page explains the score.",
    ],
    media: [
      { src: "/studio-pipeline/public-five-tabs.jpg", alt: "Five phone screens of the public view: Home, Report, Shelter, Prepare and SOS.", caption: "Public view, practice replay: Home, Report, Shelter, Prepare and SOS." },
      { src: "/studio-pipeline/planning-view-peak.jpg", alt: "The planning view at the modelled peak, with the eight tambons beside a map of water and cut roads.", caption: "Planning view at 11 Sep 2024, 02:00 (exercise replay)." },
      { src: "/studio-pipeline/policy-page.jpg", alt: "The top of the plain-language policy page.", caption: "The policy page, in English and Thai." },
    ],
    links: [
      { label: "Public view", href: "/public/" },
      { label: "Planning view", href: "/command/" },
      { label: "Policy page", href: "/policy/" },
      { label: "Studio", href: "/studio/" },
    ],
  },
  {
    id: "planner-test",
    title: "Test with planners",
    status: "not_started",
    summary: "No district office or planner has used the tool yet; the proposal promised a stakeholder review.",
    proposal: "A planner or disaster officer uses the Planning view and says what they understood and what they would distrust.",
    now: [
      "A one-page pack for an outside reader and an invitation are drafted: ten minutes of reading, four questions, three lines of answer each.",
    ],
    missing: ["Fifteen minutes with a planner, a DDPM contact or the GISTDA facilitator, and their written lines."],
    links: [
      { label: "One page for an outside reader", path: "docs/mentoring/outside_review_pack.md" },
      { label: "Invitation draft", path: "docs/mentoring/outside_review_invitation_draft.md" },
    ],
  },
];

const OWN = Object.fromEntries(FOLLOW_UP_TOPICS.map((topic) => [topic.id, topic]));

/** A topic of this page or of the pipeline page. */
export function followUpTopic(id: string): PipelineTopic {
  return OWN[id] ?? TOPIC_BY_ID[id];
}

export interface FollowUpStage { id: string; topic: string; title: string; lines: [string, string] }
export interface FollowUpStep { id: string; title: string; colour: string; stages: FollowUpStage[] }

/** Part 1: the four steps and their fourteen stages, as on graphic 1 of the presentation. */
export const PIPELINE_STEPS: FollowUpStep[] = [
  {
    id: "flood-extent",
    title: "1 · Flood extent",
    colour: "#087f8c",
    stages: [
      { id: "agency-map", topic: "flood-input", title: "Agency flood map", lines: ["UNOSAT / GISTDA 2024 layer", "feeds every decision"] },
      { id: "own-radar", topic: "sar-baseline", title: "Our own radar map", lines: ["Sentinel-1; missed its bar at", "Nan (IoU 0.23, bar 0.40)"] },
      { id: "theos2", topic: "theos2-check", title: "THEOS-2 check", lines: ["Sample tile only so far;", "Mae Sai scene in, not yet run"] },
      { id: "susceptibility", topic: "susceptibility", title: "Susceptibility model", lines: ["Screening layer only; AUC", "0.92 on 3 unseen districts"] },
    ],
  },
  {
    id: "roads-people",
    title: "2 · Roads and people",
    colour: "#376d89",
    stages: [
      { id: "residents", topic: "exposure", title: "Residents", lines: ["WorldPop grid, checked", "against 88,900 buildings"] },
      { id: "roads", topic: "road-disruption", title: "Roads and closures", lines: ["OpenStreetMap; closure rule", "fixed before any result"] },
      { id: "facilities", topic: "roads-facilities", title: "Hospitals and shelters", lines: ["Public lists and OSM; shelter", "places listed, not verified"] },
    ],
  },
  {
    id: "access-loss",
    title: "3 · Access loss",
    colour: "#537d5b",
    stages: [
      { id: "routing", topic: "access-loss", title: "Routing, before / after", lines: ["Hospital within 30 min;", "any road route out"] },
      { id: "equity", topic: "equity-gap", title: "Equity gap by age", lines: ["Computed; open age data", "cannot separate tambons"] },
      { id: "ground-check", topic: "ground-check", title: "Ground check of roads", lines: ["The key Ko Chang road is", "not yet seen on site"] },
    ],
  },
  {
    id: "score-action",
    title: "4 · Score and action",
    colour: "#896829",
    stages: [
      { id: "score", topic: "fpps", title: "Score and class A–E", lines: ["8 tambons of Mae Sai; rules", "signed before scoring"] },
      { id: "stability", topic: "stability", title: "Stability, 180 runs", lines: ["7 of 8 classes hold;", "Mae Sai town: \"verify\""] },
      { id: "web-views", topic: "web-views", title: "Three web views", lines: ["Planning, public, policy;", "English and Thai"] },
      { id: "planner-test", topic: "planner-test", title: "Test with planners", lines: ["No district office has", "used it yet"] },
    ],
  },
];

export const ALL_STAGES: FollowUpStage[] = PIPELINE_STEPS.flatMap((step) => step.stages);

export interface Blocker { blocker: string; unblock: string }

/** Part 4: what the team cannot solve alone. */
export const BLOCKERS: Blocker[] = [
  { blocker: "Ko Chang's key road is not checked on the ground", unblock: "An afternoon with the DDPM Chiang Rai office. The THEOS-2 scene of 17 Sep 2024 shows the road; analysis not run yet" },
  { blocker: "The delivered THEOS-2 scene shows only the west edge of Ko Chang", unblock: "The 21 Sep 2024 scenes over Ko Chang, from GISTDA" },
  { blocker: "Our own radar is below its bar", unblock: "One named method tested on an unopened reserve event (Ubon 2022), bar fixed first" },
  { blocker: "The open age data are too coarse for equity by tambon", unblock: "A Thai age source at village or tambon level that we may use" },
  { blocker: "No planner has used the tool", unblock: "15 minutes with a planner or the GISTDA facilitator" },
];

export const AGENDA = [
  { time: "0:10–0:14", part: "1 · Data pipeline status" },
  { time: "0:14–0:19", part: "2 · GeoAI workflow decisions" },
  { time: "0:19–0:23", part: "3 · How we handle uncertainty" },
  { time: "0:23–0:25", part: "4 · Unresolved blockers" },
];

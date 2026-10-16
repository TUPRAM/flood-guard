/**
 * The five figures of the submitted proposal, redrawn as clickable diagrams for `/studio/pipeline/`.
 *
 * Box labels and captions are the proposal's own wording, kept as submitted. Each box points at a topic in
 * `pipeline-progress.ts`, which holds its status and details. Coordinates are in each figure's own view box.
 */

export type BoxShape = "rect" | "data" | "terminal" | "diamond" | "row";
/** The proposal's own line style for a box: plain, conditional (dashed), protected (bold), blocked (hatched), roadmap (dotted). */
export type BoxStroke = "plain" | "dashed" | "bold" | "hatched" | "dotted";

export interface FigureLine { text: string; kind?: "title" | "sub" | "kicker" | "question" }
export interface FigureBox {
  id: string;
  topic: string;
  shape: BoxShape;
  stroke?: BoxStroke;
  x: number;
  y: number;
  w: number;
  h: number;
  lines: FigureLine[];
}
export interface FigureEdge {
  points: [number, number][];
  dashed?: boolean;
  dotted?: boolean;
  arrow?: "end" | "both" | "none";
}
export interface FigureNote { x: number; y: number; text: string; kind?: "heading" | "italic" | "small"; anchor?: "start" | "middle" }
/** A frame drawn around a group of boxes, with an optional heading inside (the protected decision layer). */
export interface FigureFrame { x: number; y: number; w: number; h: number; stroke: BoxStroke; title?: string }

export interface PipelineFigure {
  id: string;
  number: number;
  /** The caption as printed in the proposal. */
  caption: string;
  section: string;
  width: number;
  height: number;
  boxes: FigureBox[];
  edges: FigureEdge[];
  notes: FigureNote[];
  frames?: FigureFrame[];
}

const t = (text: string): FigureLine => ({ text, kind: "title" });
const s = (text: string): FigureLine => ({ text, kind: "sub" });

const FIGURE_1: PipelineFigure = {
  id: "figure-1",
  number: 1,
  caption: "FloodGuard decision chain from flood observation to exposure, road disruption, access loss, evacuation equity and action priority.",
  section: "Proposal section 1.4",
  width: 1300,
  height: 430,
  boxes: [
    { id: "f1-flood", topic: "flood-input", shape: "data", x: 380, y: 16, w: 540, h: 84, lines: [t("Flood extent or flood probability"), s("Sentinel-1 SAR · GISTDA / Charter products")] },
    { id: "f1-exposure", topic: "exposure", shape: "rect", x: 20, y: 150, w: 380, h: 95, lines: [t("Exposure"), s("people and facilities")] },
    { id: "f1-road", topic: "road-disruption", shape: "rect", x: 460, y: 150, w: 380, h: 95, lines: [t("Road disruption"), s("links likely cut")] },
    { id: "f1-access", topic: "access-loss", shape: "rect", x: 900, y: 150, w: 380, h: 95, lines: [t("Access loss"), s("normal vs disrupted")] },
    { id: "f1-vulnerability", topic: "population-age", shape: "data", x: 20, y: 310, w: 340, h: 100, lines: [t("Vulnerability"), s("age-resolved population")] },
    { id: "f1-equity", topic: "equity-gap", shape: "rect", x: 440, y: 310, w: 420, h: 100, lines: [t("Evacuation Equity Gap"), s("is access loss concentrated on vulnerable residents?")] },
    { id: "f1-priority", topic: "fpps", shape: "terminal", x: 950, y: 310, w: 330, h: 100, lines: [t("Priority score"), s("A-E action class")] },
  ],
  edges: [
    { points: [[650, 100], [650, 125], [210, 125], [210, 150]] },
    { points: [[650, 100], [650, 150]] },
    { points: [[650, 125], [1090, 125], [1090, 150]] },
    { points: [[210, 245], [210, 275], [1090, 275], [1090, 245]], arrow: "none" },
    { points: [[650, 245], [650, 310]] },
    { points: [[350, 360], [440, 360]], dashed: true },
    { points: [[860, 360], [950, 360]] },
  ],
  notes: [],
};

const FIGURE_2: PipelineFigure = {
  id: "figure-2",
  number: 2,
  caption: "AI, ML, and analytical responsibility map implementation workflow.",
  section: "Proposal section 3.2",
  width: 1400,
  height: 760,
  boxes: [
    { id: "f2-s1", topic: "sentinel1", shape: "rect", x: 10, y: 40, w: 215, h: 70, lines: [t("Sentinel-1 SAR"), s("pre- and post-event VV, VH")] },
    { id: "f2-terrain", topic: "terrain", shape: "rect", x: 250, y: 40, w: 215, h: 70, lines: [t("Terrain"), s("DEM, HAND, slope")] },
    { id: "f2-hydromet", topic: "hydromet", shape: "rect", x: 490, y: 40, w: 215, h: 70, lines: [t("Hydromet context"), s("rainfall, permanent water")] },
    { id: "f2-preprocess", topic: "preprocessing", shape: "rect", x: 10, y: 160, w: 695, h: 64, lines: [t("Canonical preprocessing and feature alignment"), s("calibration, correction, common grid, validity mask")] },
    { id: "f2-sar", topic: "sar-baseline", shape: "rect", x: 45, y: 300, w: 195, h: 72, lines: [t("SAR change detection"), s("operational baseline")] },
    { id: "f2-rf", topic: "rf-xgboost", shape: "rect", stroke: "dashed", x: 262, y: 300, w: 195, h: 72, lines: [t("RF / XGBoost"), s("refinement, label-gated")] },
    { id: "f2-unet", topic: "unet", shape: "rect", stroke: "dashed", x: 480, y: 300, w: 195, h: 72, lines: [t("U-Net / FPN"), s("governed candidate")] },
    { id: "f2-product", topic: "observation-product", shape: "rect", x: 10, y: 408, w: 695, h: 64, lines: [t("Flood observation product"), s("probability, validity, uncertainty, abstention")] },
    { id: "f2-gate", topic: "promotion-gate", shape: "diamond", x: 247, y: 492, w: 220, h: 104, lines: [t("Evidence and"), t("Promotion gate")] },
    { id: "f2-blocked", topic: "report-only", shape: "rect", stroke: "hatched", x: 10, y: 668, w: 330, h: 66, lines: [t("Blocked"), s("report-only, held for review")] },
    { id: "f2-roads", topic: "roads-facilities", shape: "rect", x: 840, y: 40, w: 215, h: 70, lines: [t("Roads and facilities"), s("topology, service locations")] },
    { id: "f2-population", topic: "population-age", shape: "rect", x: 1080, y: 40, w: 215, h: 70, lines: [t("Population by age"), s("exposure, vulnerability groups")] },
    { id: "f2-exposure", topic: "exposure", shape: "row", x: 842, y: 190, w: 451, h: 42, lines: [s("Exposure")] },
    { id: "f2-road", topic: "road-disruption", shape: "row", x: 842, y: 232, w: 451, h: 42, lines: [s("Road risk")] },
    { id: "f2-access", topic: "access-loss", shape: "row", x: 842, y: 274, w: 451, h: 42, lines: [s("Access loss")] },
    { id: "f2-equity", topic: "equity-gap", shape: "row", x: 842, y: 316, w: 451, h: 42, lines: [s("Equity gap")] },
    { id: "f2-fpps", topic: "fpps", shape: "row", x: 842, y: 358, w: 451, h: 40, lines: [s("FPPS and A–E classes")] },
    { id: "f2-public", topic: "public-view", shape: "rect", x: 730, y: 478, w: 205, h: 70, lines: [t("Public preparedness"), s("citizen view, Thai-first")] },
    { id: "f2-command", topic: "command-view", shape: "rect", x: 958, y: 478, w: 205, h: 70, lines: [t("Command workspace"), s("government, rescue")] },
    { id: "f2-studio", topic: "studio-view", shape: "rect", x: 1185, y: 478, w: 205, h: 70, lines: [t("Transparency studio"), s("reviewers, technical staff")] },
  ],
  frames: [{ x: 840, y: 150, w: 455, h: 250, stroke: "bold", title: "Protected deterministic decision layer" }],
  edges: [
    { points: [[117, 110], [117, 135], [597, 135], [597, 110]], arrow: "none" },
    { points: [[357, 110], [357, 160]] },
    { points: [[357, 224], [357, 280]] },
    { points: [[142, 300], [142, 288], [577, 288], [577, 300]], arrow: "none" },
    { points: [[359, 288], [359, 300]], arrow: "none" },
    { points: [[142, 372], [142, 390], [577, 390], [577, 372]], arrow: "none" },
    { points: [[357, 390], [357, 408]] },
    { points: [[357, 472], [357, 492]] },
    { points: [[467, 544], [720, 544], [720, 300], [838, 300]] },
    { points: [[357, 596], [357, 628], [175, 628], [175, 668]] },
    { points: [[425, 575], [500, 618]], dotted: true, arrow: "none" },
    { points: [[947, 110], [947, 150]], dashed: true },
    { points: [[1187, 110], [1187, 150]], dashed: true },
    { points: [[1067, 400], [1067, 458], [832, 458], [832, 478]] },
    { points: [[1067, 400], [1067, 478]] },
    { points: [[1067, 458], [1287, 458], [1287, 478]] },
  ],
  notes: [
    { x: 10, y: 24, text: "Flood evidence pipeline", kind: "heading" },
    { x: 840, y: 24, text: "Decision context", kind: "heading" },
    { x: 359, y: 278, text: "controlled model comparison", kind: "italic", anchor: "middle" },
    { x: 590, y: 536, text: "pass", kind: "italic", anchor: "middle" },
    { x: 250, y: 620, text: "fail", kind: "italic", anchor: "middle" },
    { x: 1067, y: 448, text: "Role-specific output surfaces, same underlying evidence", kind: "italic", anchor: "middle" },
    { x: 505, y: 632, text: "Promotion criteria", kind: "heading" },
    { x: 515, y: 654, text: "i. provenance verified", kind: "small" },
    { x: 515, y: 674, text: "ii. licence cleared", kind: "small" },
    { x: 515, y: 694, text: "iii. spatial holdout frozen", kind: "small" },
    { x: 515, y: 714, text: "iv. calibration valid", kind: "small" },
    { x: 515, y: 734, text: "v. human review complete", kind: "small" },
  ],
};

const FIGURE_3: PipelineFigure = {
  id: "figure-3",
  number: 3,
  caption: "FloodGuard implementation architecture. The GeoAI runner is isolated from the deterministic decision engine. Only validated, provenance-tracked flood observations can influence decision outputs.",
  section: "Proposal section 3.2.5",
  width: 1420,
  height: 760,
  boxes: [
    { id: "f3-public", topic: "public-view", shape: "rect", x: 40, y: 34, w: 420, h: 92, lines: [t("Public Preparedness"), s("Thai-first mobile view")] },
    { id: "f3-command", topic: "command-view", shape: "rect", x: 480, y: 34, w: 420, h: 92, lines: [t("Planning Command Center"), s("map-first prioritisation")] },
    { id: "f3-studio", topic: "studio-view", shape: "rect", x: 920, y: 34, w: 420, h: 92, lines: [t("Validation Studio"), s("evidence and blockers")] },
    { id: "f3-api", topic: "api-service", shape: "rect", x: 260, y: 182, w: 880, h: 68, lines: [t("FastAPI artifact and scenario service"), s("validation, role projections and versioned endpoints")] },
    { id: "f3-contracts", topic: "contracts", shape: "rect", x: 260, y: 266, w: 880, h: 50, lines: [t("Shared JSON Schema and TypeScript contracts")] },
    { id: "f3-engine", topic: "decision-layer", shape: "rect", stroke: "bold", x: 70, y: 376, w: 480, h: 130, lines: [t("Deterministic decision engine"), s("exposure, road risk, access, equity, FPPS, A to E actions"), s("Reproducible CSV, GeoJSON and briefs")] },
    { id: "f3-product", topic: "observation-product", shape: "terminal", x: 595, y: 370, w: 200, h: 34, lines: [t("Observation Product")] },
    { id: "f3-gate", topic: "promotion-gate", shape: "diamond", x: 600, y: 414, w: 190, h: 46, lines: [t("Evidence Gate")] },
    { id: "f3-adapter", topic: "trusted-adapter", shape: "terminal", x: 595, y: 470, w: 200, h: 34, lines: [t("Trusted Adapter")] },
    { id: "f3-runner", topic: "geoai-runner", shape: "rect", stroke: "dashed", x: 840, y: 376, w: 480, h: 130, lines: [t("Isolated GeoAI runner"), s("tile export, controlled training, tiled inference, uncertainty"), s("Heavy ML dependencies stay isolated")] },
    { id: "f3-failclosed", topic: "report-only", shape: "terminal", stroke: "hatched", x: 380, y: 546, w: 640, h: 40, lines: [s("Fail closed: candidate or incomplete evidence remains report only")] },
    { id: "f3-external", topic: "external-workspace", shape: "rect", x: 70, y: 642, w: 430, h: 88, lines: [t("External data workspace"), s("satellite, terrain, population and roads")] },
    { id: "f3-manifest", topic: "manifest-outputs", shape: "rect", x: 520, y: 642, w: 430, h: 88, lines: [t("Manifest-backed outputs"), s("COG, GeoJSON, CSV, JSON and receipts")] },
    { id: "f3-offline", topic: "offline-bundles", shape: "rect", x: 970, y: 642, w: 430, h: 88, lines: [t("Offline judging bundles"), s("role-filtered and checksummed")] },
  ],
  edges: [
    { points: [[690, 126], [690, 182]] },
    { points: [[700, 250], [700, 266]] },
    { points: [[700, 316], [700, 340], [310, 340], [310, 376]] },
    { points: [[700, 340], [1080, 340], [1080, 376]] },
    { points: [[1340, 80], [1395, 80], [1395, 441], [1322, 441]], dashed: true },
    { points: [[552, 387], [593, 387]], arrow: "both" },
    { points: [[797, 387], [838, 387]], arrow: "both" },
    { points: [[552, 437], [598, 437]], arrow: "both" },
    { points: [[792, 437], [838, 437]], arrow: "both" },
    { points: [[552, 487], [593, 487]], arrow: "both" },
    { points: [[797, 487], [838, 487]], arrow: "both" },
    { points: [[695, 504], [695, 546]], dotted: true, arrow: "none" },
    { points: [[285, 506], [285, 642]] },
    { points: [[1185, 506], [1185, 642]] },
  ],
  notes: [
    { x: 10, y: 20, text: "Experience layer", kind: "heading" },
    { x: 10, y: 170, text: "Service and contract layer", kind: "heading" },
    { x: 10, y: 334, text: "Compute layer", kind: "heading" },
    { x: 10, y: 624, text: "Data and artifact layer", kind: "heading" },
  ],
};

const FIGURE_4: PipelineFigure = {
  id: "figure-4",
  number: 4,
  caption: "The FloodGuard evidence pipeline: twelve processing stages separated by a single evidence-promotion gate.",
  section: "Proposal section 3.4",
  width: 1360,
  height: 840,
  boxes: [
    { id: "f4-1", topic: "event-registration", shape: "rect", x: 10, y: 20, w: 290, h: 100, lines: [t("1  Event registration"), s("fixed identity for area, event, data"), s("and run")] },
    { id: "f4-2", topic: "sentinel1", shape: "rect", x: 350, y: 20, w: 290, h: 100, lines: [t("2  Acquisition"), s("scenes fetched; manifests and"), s("checksums recorded")] },
    { id: "f4-3", topic: "preprocessing", shape: "rect", x: 690, y: 20, w: 290, h: 100, lines: [t("3  Preprocessing"), s("orbit, noise, calibration, terrain"), s("correction")] },
    { id: "f4-4", topic: "feature-alignment", shape: "rect", x: 1030, y: 20, w: 290, h: 100, lines: [t("4  Feature alignment"), s("shared grid; identical train and"), s("inference transforms")] },
    { id: "f4-5", topic: "sar-baseline", shape: "rect", x: 1030, y: 165, w: 290, h: 100, lines: [t("5  Deterministic baseline"), s("adaptive Otsu threshold on Sentinel-1"), s("change")] },
    { id: "f4-6", topic: "labels-partitions", shape: "rect", x: 690, y: 165, w: 290, h: 100, lines: [t("6  Labels and partitions"), s("frozen tiles; untouched spatial"), s("holdout")] },
    { id: "f4-7", topic: "model-training", shape: "rect", x: 350, y: 165, w: 290, h: 100, lines: [t("7  Model training"), s("candidate models bound to run receipts")] },
    { id: "f4-8", topic: "evaluation", shape: "rect", x: 10, y: 165, w: 290, h: 100, lines: [t("8  Evaluation and calibration"), s("held-out metrics, calibration,"), s("abstention rule")] },
    { id: "f4-9", topic: "promotion-gate", shape: "diamond", x: 10, y: 345, w: 310, h: 150, lines: [t("9  Evidence-promotion gate"), s("provenance · licence · holdout · review")] },
    { id: "f4-record", topic: "report-only", shape: "terminal", x: 440, y: 368, w: 300, h: 104, lines: [t("Report-only or planning-only"), t("record"), s("inspectable, with the blocking"), s("reason attached")] },
    { id: "f4-studio", topic: "studio-view", shape: "rect", x: 800, y: 320, w: 330, h: 80, lines: [t("Validation & Evidence Studio"), s("absences displayed, never substituted")] },
    { id: "f4-unchanged", topic: "promotion-gate", shape: "terminal", x: 800, y: 440, w: 330, h: 90, lines: [t("Decision layer remains unchanged"), s("cannot alter road, access, equity or FPPS")] },
    { id: "f4-eligible", topic: "decision-eligible-product", shape: "data", x: 20, y: 590, w: 290, h: 100, lines: [t("Decision-eligible Flood"), t("Observation Product"), s("probability, validity,"), s("uncertainty, abstention")] },
    { id: "f4-10", topic: "road-disruption", shape: "rect", x: 360, y: 590, w: 280, h: 100, lines: [t("10  Road disruption"), s("candidate disrupted links; travel-time"), s("change")] },
    { id: "f4-11", topic: "access-loss", shape: "rect", x: 700, y: 590, w: 280, h: 100, lines: [t("11  Access loss and equity"), s("15/30/60-minute reach; Evacuation"), s("Equity Gap")] },
    { id: "f4-12", topic: "fpps", shape: "rect", x: 1040, y: 590, w: 300, h: 100, lines: [t("12  FPPS and A-E action"), s("weighted score, sensitivity, reason"), s("codes")] },
    { id: "f4-surfaces", topic: "studio-view", shape: "terminal", x: 1020, y: 745, w: 330, h: 80, lines: [t("Public · Command · Studio"), s("same evidence, role-specific presentation")] },
  ],
  edges: [
    { points: [[300, 70], [350, 70]] },
    { points: [[640, 70], [690, 70]] },
    { points: [[980, 70], [1030, 70]] },
    { points: [[1175, 120], [1175, 165]] },
    { points: [[1030, 215], [980, 215]] },
    { points: [[690, 215], [640, 215]] },
    { points: [[350, 215], [300, 215]] },
    { points: [[165, 265], [165, 345]] },
    { points: [[320, 420], [440, 420]] },
    { points: [[740, 420], [765, 420], [765, 360], [800, 360]] },
    { points: [[765, 420], [765, 485], [800, 485]], dashed: true },
    { points: [[165, 495], [165, 590]] },
    { points: [[300, 640], [360, 640]] },
    { points: [[640, 640], [700, 640]] },
    { points: [[980, 640], [1040, 640]] },
    { points: [[1185, 690], [1185, 745]] },
  ],
  notes: [
    { x: 385, y: 410, text: "any gate fails", kind: "small", anchor: "middle" },
    { x: 220, y: 548, text: "all gates pass", kind: "small", anchor: "middle" },
  ],
};

const FIGURE_5: PipelineFigure = {
  id: "figure-5",
  number: 5,
  caption: "Study-area progression: three sites, three questions, three levels of evidential commitment.",
  section: "Proposal section 4.4",
  width: 1360,
  height: 300,
  boxes: [
    { id: "f5-mae-sai", topic: "site-mae-sai", shape: "rect", stroke: "bold", x: 10, y: 20, w: 330, h: 260, lines: [{ text: "Benchmark", kind: "kicker" }, t("Mae Sai, Chiang Rai"), s("September 2024"), { text: "Can the method be qualified?", kind: "question" }, s("Historical benchmark and"), s("full decision chain")] },
    { id: "f5-hat-yai", topic: "site-hat-yai", shape: "rect", stroke: "dashed", x: 515, y: 20, w: 330, h: 260, lines: [{ text: "Urban Transfer", kind: "kicker" }, t("Hat Yai, Songkhla"), s("November 2025"), { text: "Does it transfer to urban stress?", kind: "question" }, s("Roads, hospitals, shelters"), s("and dense-urban SAR")] },
    { id: "f5-bangkok", topic: "site-bangkok", shape: "rect", stroke: "dotted", x: 1020, y: 20, w: 330, h: 260, lines: [{ text: "Scale Target", kind: "kicker" }, t("Lower Chao Phraya"), s("Greater Bangkok"), { text: "Can the architecture scale?", kind: "question" }, s("Data coverage, computation"), s("and governance")] },
  ],
  edges: [
    { points: [[340, 150], [515, 150]] },
    { points: [[845, 150], [1020, 150]] },
  ],
  notes: [
    { x: 428, y: 118, text: "Qualified method and", kind: "small", anchor: "middle" },
    { x: 428, y: 136, text: "explicit limitations", kind: "small", anchor: "middle" },
    { x: 933, y: 118, text: "Successful second-area", kind: "small", anchor: "middle" },
    { x: 933, y: 136, text: "replication", kind: "small", anchor: "middle" },
  ],
};

export const PIPELINE_FIGURES: PipelineFigure[] = [FIGURE_1, FIGURE_2, FIGURE_3, FIGURE_4, FIGURE_5];

/** The figures a topic is drawn in, by number, for the detail panel. */
export function figuresOfTopic(topicId: string): number[] {
  return PIPELINE_FIGURES.filter((figure) => figure.boxes.some((box) => box.topic === topicId)).map((figure) => figure.number);
}

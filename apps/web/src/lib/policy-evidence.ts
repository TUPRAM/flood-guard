const SOURCE_COMMIT = "2e5a099ee075532e27236067810699ce6996c5c4";
const SOURCE_ROOT = `https://github.com/TUPRAM/flood-guard/blob/${SOURCE_COMMIT}`;

/** A user-facing string in both page languages. */
export interface BilingualText {
  en: string;
  th: string;
}

/**
 * Fixed historical worked example, reproduced once from the committed 28 Sep 2026 study (r2 inputs).
 *
 * It predates the signed scoring frame (decision D4, 30 Sep 2026) and protocol v1b, so it is kept only to show how
 * FPPS and the A–E classes behave on real places. It is not a protocol result and must not be cited as the Mae Sai
 * case score. Nothing here is recomputed: under the plan's blinding rule no FPPS, class or ensemble may be computed
 * before v1b is hashed, and the D4/v1 scores come from the planning assessment after that.
 */
export const POLICY_EVIDENCE = {
  title: "Worked example from the 28 Sep study (before the signed scoring frame)",
  titleTh: "ตัวอย่างการคำนวณจากงานศึกษาวันที่ 28 ก.ย. (ก่อนกรอบคะแนนที่ลงนามแล้ว)",
  status: "historical_worked_example",
  /** The chip carried beside every score the page shows: pre-D4 anchors, the r2 reconstruction, and pre-v1b. */
  scoreLabel: {
    en: "Historical example · pre-D4 anchors · r2 · pre-v1b, not a protocol result",
    th: "ตัวอย่างย้อนหลัง · จุดอ้างอิงก่อน D4 · r2 · ก่อน v1b ไม่ใช่ผลตามโปรโตคอล",
  },
  context: "Mae Sai historical reconstruction · assumed peak · reported 2024 shelter set",
  generatedAt: null,
  sourceCommittedAt: "2026-09-28T07:45:21Z",
  reproducedOn: "2026-09-29",
  sourceCommit: SOURCE_COMMIT,
  sourceArtifact: "apps/web/public/studies/mae-sai-2024-timeline/r2/timeline.json",
  sourceSha256: "5e2cea385ac7fe53952976e4d6cc75aed54b997b62d55aa7652fdcf83964eb6b",
  sourceUrl: `${SOURCE_ROOT}/apps/web/public/studies/mae-sai-2024-timeline/r2/timeline.json`,
  methodUrl: `${SOURCE_ROOT}/apps/web/src/lib/replay-fpps.ts`,
  scoringUrl: `${SOURCE_ROOT}/apps/web/src/lib/fpps.ts`,
  playbookUrl: `${SOURCE_ROOT}/apps/web/src/lib/action-playbook.ts`,
  revision: "r2",
  schemaVersion: 1,
  /** Evidence tier (plan v2 §3.3): a scenario on a terrain-model reconstruction, not an observation. */
  tier: "T1 scenario (model)",
  tierTh: "สถานการณ์จำลองระดับ T1 (แบบจำลอง)",
  confidence: "low",
  confidenceReason: "Terrain-model reconstruction with illustrative stages; spatial agreement with late-recession radar is weak.",
  confidenceReasonTh: "เป็นการจำลองจากแบบจำลองภูมิประเทศโดยใช้ระดับน้ำเชิงอธิบาย ความสอดคล้องเชิงพื้นที่กับภาพเรดาร์ช่วงน้ำลดยังต่ำ",
  eventStart: "2024-09-09",
  eventEnd: "2024-09-19",
  sourceTimestamp: "2024-09-05T03:58:19Z/2024-09-15T23:16:01Z",
  scenario: {
    timestamp: "2024-09-12T12:00:00+07:00",
    label: "12 September 2024, 12:00 ICT",
    assumedStageMetres: 3.5,
    shelterSet: "reported_2024",
    shelterLabel: "Shelters reported in use in September 2024",
    population: "WorldPop 2020 modelled residents",
    anchorVersion: "replay_fpps_anchor_v1",
  },
  /** Status against the signed decisions (docs/decision-log-d1-d16.md). */
  conformsToSignedFrame: false,
  computedBeforeProtocolV1b: true,
  /** r2 `model_coverage` at the source commit: 294.4 of 305.6 km² of the district was modelled (0.9634, shown as 96.3%). */
  reconstructionCoverageShare: 0.963,
  reconstructionCoverage: {
    modelledKm2: 294.4,
    districtKm2: 305.6,
    manifestField: "model_coverage",
    reason: "The Copernicus DEM tile used stops at 100°E; district land east of it is not modelled.",
    partiallyModelled: [
      { id: "TH570903", name: "Ko Chang", nameTh: "เกาะช้าง", modelledKm2: 37.67, totalKm2: 47.41 },
      { id: "TH570905", name: "Si Mueang Chum", nameTh: "ศรีเมืองชุม", modelledKm2: 40.45, totalKm2: 41.89 },
    ],
  },
  /** The replay that is live now. It is a narrative surface (D7): it computes no FPPS and assigns no class. */
  currentReplay: {
    route: "/studio/cases/mae-sai-2024/",
    revision: "r3",
    coverageShare: 1,
    tier: "T1 scenario (model)",
    computesFpps: false,
    /**
     * External size figures by their r3 manifest `role` (a unit test reads them back from r3 `timeline.json`).
     * GISTDA's reported area only sets the 10 Sep 18:15 stage knot; no GISTDA map is used.
     */
    calibrationAnchor: { id: "gistda-radarsat2-20240910", role: "calibration_anchor", reportedKm2: 9.9 },
    calibrationInformedCheck: { id: "unosat-3991", role: "calibration_informed_magnitude_check", decision: "R1" },
  },
  /**
   * Labels in the pinned r2 source that a later signed decision overturned. The page shows each beside the source
   * link, so a reader who opens the r2 manifest is not left with the old label.
   */
  supersededLabels: [
    {
      field: "external_checks[unosat-3991].role",
      sourceValue: "independent_magnitude_check",
      currentValue: "calibration_informed_magnitude_check",
      decision: "R1",
      decidedOn: "2026-09-30",
    },
  ],
  supersededBy: "planning assessment after v1b (D4, D6, D7)",
  decisionRefs: ["D4", "D6", "D7", "R1", "R2"],
  decisionLog: "docs/decision-log-d1-d16.md",
  stats: [
    { label: "Mae Sai", value: "89.34", unit: "pre-D4 scenario FPPS", detail: "Class E · low confidence · historical example" },
    { label: "Si Mueang Chum", value: "85.98", unit: "pre-D4 scenario FPPS", detail: "Class E · low confidence · historical example" },
    { label: "Ban Dai", value: "81.14", unit: "pre-D4 scenario FPPS", detail: "Class E · low confidence · historical example" },
  ],
  rankings: [
    { id: "TH570901", name: "Mae Sai", nameTh: "แม่สาย", score: 89.34, actionClass: "E" },
    { id: "TH570905", name: "Si Mueang Chum", nameTh: "ศรีเมืองชุม", score: 85.98, actionClass: "E" },
    { id: "TH570908", name: "Ban Dai", nameTh: "บ้านด้าย", score: 81.14, actionClass: "E" },
    { id: "TH570903", name: "Ko Chang", nameTh: "เกาะช้าง", score: 76.38, actionClass: "E" },
    { id: "TH570904", name: "Pong Pha", nameTh: "โป่งผา", score: 66.13, actionClass: "E" },
    { id: "TH570909", name: "Pong Ngam", nameTh: "โป่งงาม", score: 53.93, actionClass: "E" },
    { id: "TH570902", name: "Huai Khrai", nameTh: "ห้วยไคร้", score: 34.09, actionClass: "E" },
    { id: "TH570906", name: "Wiang Phang Kham", nameTh: "เวียงพางคำ", score: 31.27, actionClass: "E" },
  ],
  weights: { flood: 0.3, exposure: 0.25, access: 0.2, roads: 0.15, context: 0.1 },
  /** The pre-D4 anchors the example used (replay_fpps_anchor_v1). */
  anchors: {
    floodAreaShare: 0.25,
    exposedPopulationShare: 0.25,
    exposedPeople: 5000,
    disruptedWeightedRoadShare: 0.5,
    terrainRemotenessPopulationShare: 0.25,
  },
  officialWarning: false,
  canFeedDecisionLayer: false,
  acceptedFpps: null,
  acceptedActionClass: null,
  assumptions: [
    "Historical worked example: pre-D4 anchors (replay_fpps_anchor_v1) on the r2 reconstruction, which modelled 96.3% of the district.",
    "Computed before protocol v1b was hashed: not a protocol result and not the Mae Sai case score.",
    "Scenario FPPS is a priority index, not a flood probability or an official priority list.",
    "The first component is a normalized reconstructed inundated-area proxy; a full component score does not mean certain flooding.",
    "Access assumes an open, dry shelter within a 2 km walk on roads still passable; site operation and safe travel are unverified.",
    "The access calculation is not a capacity-constrained shelter allocation.",
    "Vulnerability is a terrain/remoteness proxy, not a demographic or social-vulnerability assessment.",
    "Every assigned class remains E because confidence is low. Class E never means safe. Confirming water alone does not authorize escalation.",
  ],
  verification: {
    scoreReproduction: "Recomputed all eight rows once, on 29 Sep 2026, from the exact committed TypeScript methods and original r2 Git asset bytes.",
    sourceSelection: "The r3 replay computes no FPPS (D7), so this example cannot be refreshed from it. It is replaced only by D4/v1 planning-assessment results after protocol v1b is hashed.",
    generationTimestamp: "The source manifest does not record a generation time; the commit date is recorded separately.",
    scientificValidation: "Not established",
    operationalAcceptance: "Not established",
  },
} as const;

/** One FPPS component: its weight, the signed D4 definition, and what the worked example used instead. */
export interface SignedFrameComponent {
  key: "flood_likelihood_0_100" | "exposure_0_100" | "access_gap_0_100" | "road_criticality_0_100" | "vulnerability_context_0_100";
  weight: number;
  name: BilingualText;
  question: BilingualText;
  signed: BilingualText;
  workedExample: BilingualText;
}

/**
 * The signed scoring frame (D4, 30 Sep 2026; plan v2 §3.4 "normalisation frame v1"). Weights follow AGENTS.md and
 * `src/floodguard/scoring.py`; each component is scaled 0–100 against a fixed, declared anchor.
 */
export const SIGNED_SCORING_FRAME: {
  decision: "D4";
  signedOn: string;
  decisionLog: string;
  floodAnchorShare: number;
  floodSensitivityShares: readonly [number, number];
  floodAnchorChosenAfterData: true;
  permanentWater: string;
  components: readonly SignedFrameComponent[];
} = {
  decision: "D4",
  signedOn: "2026-09-30",
  decisionLog: "docs/decision-log-d1-d16.md",
  floodAnchorShare: 0.2,
  floodSensitivityShares: [0.1, 0.3],
  floodAnchorChosenAfterData: true,
  permanentWater: "ESA WorldCover class 80",
  components: [
    {
      key: "flood_likelihood_0_100",
      weight: 0.3,
      name: { en: "Flood likelihood", th: "โอกาสน้ำท่วม" },
      question: { en: "How much of the land floods?", th: "น้ำท่วมพื้นที่มากเพียงใด?" },
      signed: {
        en: "100 × min(1, flooded share of the area's land that is not permanent water ÷ 0.20). Permanent water = ESA WorldCover class 80 for every case, with JRC reported as a sensitivity note. Anchor 0.20; 0.10 and 0.30 run one at a time as sensitivity checks.",
        th: "100 × min(1, สัดส่วนที่น้ำท่วมของพื้นที่ที่ไม่ใช่แหล่งน้ำถาวรของหน่วยพื้นที่ ÷ 0.20) แหล่งน้ำถาวร = ESA WorldCover คลาส 80 ในทุกกรณี และรายงาน JRC เป็นหมายเหตุด้านความไว จุดอ้างอิง 0.20 ตรวจความไวที่ 0.10 และ 0.30 ทีละค่า",
      },
      workedExample: {
        en: "Flooded share (outside the mapped river channel) of the area r2 modelled ÷ 0.25. No WorldCover mask.",
        th: "สัดส่วนที่น้ำท่วม (นอกร่องน้ำที่ทำแผนที่ไว้) ของพื้นที่ที่ r2 จำลอง ÷ 0.25 ไม่ใช้หน้ากากน้ำ WorldCover",
      },
    },
    {
      key: "exposure_0_100",
      weight: 0.25,
      name: { en: "Exposure", th: "ความล่อแหลม" },
      question: { en: "Who lives inside the flood extent?", th: "ใครอาศัยอยู่ในพื้นที่น้ำท่วม?" },
      signed: {
        en: "100 × residents whose cell centre is inside the flood extent ÷ the area's residents (WorldPop 2020). Share only, no headcount. Sensitivity axis: population vintage (2024/2020 1 km rescale).",
        th: "100 × ผู้อยู่อาศัยที่จุดกึ่งกลางเซลล์อยู่ในขอบเขตน้ำท่วม ÷ ผู้อยู่อาศัยทั้งหมดของพื้นที่ (WorldPop 2020) ใช้สัดส่วนเท่านั้น ไม่ใช้จำนวนคน แกนทดสอบความไว: ปีของข้อมูลประชากร (ปรับสเกล 2024/2020 ที่ความละเอียด 1 กม.)",
      },
      workedExample: {
        en: "Half the share of residents in water (full at 0.25), half a headcount (full at 5,000 people).",
        th: "ครึ่งหนึ่งจากสัดส่วนผู้อยู่อาศัยในน้ำ (เต็มที่ 0.25) อีกครึ่งจากจำนวนคน (เต็มที่ 5,000 คน)",
      },
    },
    {
      key: "access_gap_0_100",
      weight: 0.2,
      name: { en: "Access gap", th: "ช่องว่างการเข้าถึง" },
      question: { en: "Who loses access they had?", th: "ใครสูญเสียการเข้าถึงที่เคยมี?" },
      signed: {
        en: "Mean of newly lost shares, weighted by access before the flood. Public level: hospital (vehicle, 30 min) + main-road entry (vehicle, 15 min). Pitch level: adds DDPM located shelter (walking, 30 min). Counted only for people with access before the flood. Facility axis: public set, corroborated set, all listed.",
        th: "ค่าเฉลี่ยของสัดส่วนที่เพิ่งสูญเสียการเข้าถึง ถ่วงน้ำหนักด้วยการเข้าถึงก่อนน้ำท่วม ระดับสาธารณะ: โรงพยาบาล (ยานพาหนะ 30 นาที) + ทางเข้าถนนสายหลัก (ยานพาหนะ 15 นาที) ระดับนำเสนอ: เพิ่มศูนย์พักพิงที่ ปภ. ระบุตำแหน่ง (เดิน 30 นาที) นับเฉพาะผู้ที่เข้าถึงได้ก่อนน้ำท่วม แกนสถานที่: ชุดสาธารณะ ชุดที่มีหลักฐานยืนยัน และทุกแห่งในรายการ",
      },
      workedExample: {
        en: "Share of residents with flooded homes who have no open, dry shelter of the reported 2024 set within a 2 km walk on passable roads, including people already out of reach before the flood.",
        th: "สัดส่วนผู้อยู่อาศัยที่บ้านถูกน้ำท่วมซึ่งไม่มีศูนย์พักพิงที่เปิดและแห้งของชุดที่มีรายงานปี 2567 ในระยะเดิน 2 กม. บนถนนที่ยังสัญจรได้ รวมผู้ที่อยู่นอกระยะตั้งแต่ก่อนน้ำท่วม",
      },
    },
    {
      key: "road_criticality_0_100",
      weight: 0.15,
      name: { en: "Road criticality", th: "ความสำคัญของถนน" },
      question: { en: "Who loses every route to a hospital or main road?", th: "ใครสูญเสียทุกเส้นทางไปโรงพยาบาลหรือถนนสายหลัก?" },
      signed: {
        en: "100 × residents with a route to any hospital or main road before the flood who lose all routes ÷ those residents.",
        th: "100 × ผู้อยู่อาศัยที่มีเส้นทางไปโรงพยาบาลหรือถนนสายหลักก่อนน้ำท่วมแต่สูญเสียทุกเส้นทาง ÷ ผู้อยู่อาศัยกลุ่มนั้น",
      },
      workedExample: {
        en: "Class-weighted share of modelled road length that is impassable (0.3 m or deeper), full at 0.5. It counts road length, not people cut off.",
        th: "สัดส่วนความยาวถนนที่จำลอง (ถ่วงน้ำหนักตามประเภทถนน) ที่สัญจรไม่ได้ (น้ำลึก 0.3 ม. ขึ้นไป) เต็มที่ 0.5 นับความยาวถนน ไม่ใช่จำนวนคนที่ถูกตัดขาด",
      },
    },
    {
      key: "vulnerability_context_0_100",
      weight: 0.1,
      name: { en: "Vulnerability/context", th: "ความเปราะบาง/บริบท" },
      question: { en: "How many dependants (children and older people)?", th: "มีผู้พึ่งพิง (เด็กและผู้สูงอายุ) มากเพียงใด?" },
      signed: {
        en: "100 × clip((dependent share, ages 0–14 and 60+, − P10) ÷ (P90 − P10), 0, 1). P10 and P90 are national subdistrict percentiles of the WorldPop 2024 1 km dependent share, computed once in v1b before any case scoring. Sensitivity axes: P5/P95 anchors; the terrain/remoteness proxy on case O1 only.",
        th: "100 × clip((สัดส่วนประชากรพึ่งพิง อายุ 0–14 ปี และ 60 ปีขึ้นไป − P10) ÷ (P90 − P10), 0, 1) โดย P10 และ P90 เป็นเปอร์เซ็นไทล์ระดับตำบลทั่วประเทศของสัดส่วนประชากรพึ่งพิงจาก WorldPop 2024 ความละเอียด 1 กม. คำนวณครั้งเดียวใน v1b ก่อนให้คะแนนกรณีใด แกนทดสอบความไว: จุดอ้างอิง P5/P95 และตัวแทนจากภูมิประเทศและความห่างไกลเฉพาะกรณี O1",
      },
      workedExample: {
        en: "Share of residents in the terrain/remoteness proxy group, full at 0.25. Not a demographic measure.",
        th: "สัดส่วนผู้อยู่อาศัยในกลุ่มตัวแทนจากภูมิประเทศและความห่างไกล เต็มที่ 0.25 ไม่ใช่ตัวชี้วัดทางประชากร",
      },
    },
  ],
};

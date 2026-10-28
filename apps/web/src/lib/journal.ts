import { POLICY_GOVERNMENT_SOURCES, POLICY_READING, type PolicyReading } from "./policy-brief";
import type { BilingualText } from "./policy-evidence";

/** The reference list (`src/app/journal`), shared with the audience by QR code. */
export const JOURNAL_ROUTE = "/journal/";

/** The public repository; a `code` path below links to its file on master. */
export const JOURNAL_REPOSITORY = "https://github.com/TUPRAM/flood-guard/blob/master/";

/** The two days the records were read: the policy page's list, and the method papers added for this page. */
export const JOURNAL_CHECKED = { policy: "2026-10-12", methods: "2026-10-28" } as const;

export interface JournalEntry extends PolicyReading {
  /** The day the record (authors, year, venue, DOI) was read. The full text was not read. */
  checked: string;
  /** Where the repository uses it, as a path from the repository root. */
  code?: string;
}

export interface JournalGroup {
  id: string;
  title: BilingualText;
  /** One line under the title: the step of the system these papers stand behind. */
  intro: BilingualText;
  items: readonly JournalEntry[];
}

/**
 * The method papers behind the radar, terrain, model and access steps. The policy page cites none of them. Every
 * DOI was resolved on Crossref on 28 October 2026 (the two arXiv records on arXiv) and its authors, year and venue
 * copied from that record.
 */
const METHOD_PAPERS: readonly Omit<JournalEntry, "checked">[] = [
  {
    id: "small-2011",
    reference: "Small, D. (2011). Flattening gamma: Radiometric terrain correction for SAR imagery. IEEE Transactions on Geoscience and Remote Sensing, 49(8), 3081–3093.",
    url: "https://doi.org/10.1109/TGRS.2011.2120616",
    use: {
      en: "Terrain-flattened gamma nought: the radar scenes we read have their brightness corrected for slope before any water is looked for.",
      th: "ค่า gamma nought ที่ปรับแก้ผลภูมิประเทศ: ภาพเรดาร์ที่เราใช้ได้รับการปรับแก้ความสว่างตามความลาดชันก่อนเริ่มหาน้ำ",
    },
    code: "src/floodguard/s1_rtc.py",
  },
  {
    id: "lee-1980",
    reference: "Lee, J.-S. (1980). Digital image enhancement and noise filtering by use of local statistics. IEEE Transactions on Pattern Analysis and Machine Intelligence, PAMI-2(2), 165–168.",
    url: "https://doi.org/10.1109/TPAMI.1980.4766994",
    use: {
      en: "The local-statistics filter that smooths radar speckle in the first radar benchmark (M1).",
      th: "ตัวกรองแบบสถิติเฉพาะที่ซึ่งลดสัญญาณรบกวนแบบจุด (speckle) ของภาพเรดาร์ในการทดสอบเรดาร์ชุดแรก (M1)",
    },
    code: "src/floodguard/sar_change_v2.py",
  },
  {
    id: "lee-1981",
    reference: "Lee, J.-S. (1981). Refined filtering of image noise using local statistics. Computer Graphics and Image Processing, 15(4), 380–389.",
    url: "https://doi.org/10.1016/S0146-664X(81)80018-4",
    use: {
      en: "The refined Lee filter (7 × 7 window) of the revised radar benchmark M1-v2, which keeps the edges of water bodies sharper.",
      th: "ตัวกรอง Refined Lee (หน้าต่าง 7 × 7) ที่ใช้ในการทดสอบเรดาร์ฉบับแก้ไข M1-v2 ซึ่งรักษาขอบของแหล่งน้ำให้คมกว่า",
    },
    code: "src/floodguard/sar_change_v2.py",
  },
  {
    id: "otsu-1979",
    reference: "Otsu, N. (1979). A threshold selection method from gray-level histograms. IEEE Transactions on Systems, Man, and Cybernetics, 9(1), 62–66.",
    url: "https://doi.org/10.1109/TSMC.1979.4310076",
    use: {
      en: "Picks the line between water and land from the histogram of an image; our radar baseline applies it tile by tile (adaptive Otsu).",
      th: "เลือกเส้นแบ่งระหว่างน้ำกับพื้นดินจากฮิสโทแกรมของภาพ วิธีพื้นฐาน (baseline) ด้านเรดาร์ของเราใช้วิธีนี้ทีละช่องย่อย (tile) (adaptive Otsu)",
    },
    code: "src/floodguard/geoid_radar_benchmark.py",
  },
  {
    id: "ronneberger-2015",
    reference: "Ronneberger, O., Fischer, P., & Brox, T. (2015). U-Net: Convolutional networks for biomedical image segmentation. In Medical Image Computing and Computer-Assisted Intervention – MICCAI 2015 (LNCS 9351, pp. 234–241). Springer.",
    url: "https://doi.org/10.1007/978-3-319-24574-4_28",
    use: {
      en: "U-Net, the encoder–decoder network of the GeoAI lanes in the controlled radar experiment.",
      th: "U-Net โครงข่ายแบบเข้ารหัส–ถอดรหัสของสาย GeoAI ในการทดลองเรดาร์แบบควบคุม",
    },
    code: "src/floodguard/controlled_experiment.py",
  },
  {
    id: "lin-2017",
    reference: "Lin, T.-Y., Dollár, P., Girshick, R., He, K., Hariharan, B., & Belongie, S. (2017). Feature pyramid networks for object detection. In 2017 IEEE Conference on Computer Vision and Pattern Recognition (CVPR) (pp. 936–944).",
    url: "https://doi.org/10.1109/CVPR.2017.106",
    use: {
      en: "The Feature Pyramid Network, the one other architecture the controlled experiment allows beside U-Net.",
      th: "Feature Pyramid Network สถาปัตยกรรมอีกแบบเดียวที่การทดลองแบบควบคุมอนุญาตให้ใช้นอกเหนือจาก U-Net",
    },
    code: "src/floodguard/controlled_experiment.py",
  },
  {
    id: "bonafilia-2020",
    reference: "Bonafilia, D., Tellman, B., Anderson, T., & Issenberg, E. (2020). Sen1Floods11: A georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1. In 2020 IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops (CVPRW) (pp. 835–845).",
    url: "https://doi.org/10.1109/CVPRW50498.2020.00113",
    use: {
      en: "The common benchmark for radar flood models, cited in the proposal for its design; no FloodGuard model was trained on its images.",
      th: "ชุดข้อมูลมาตรฐานสำหรับแบบจำลองน้ำท่วมจากเรดาร์ อ้างอิงในข้อเสนอโครงการในแง่การออกแบบชุดข้อมูล ไม่มีแบบจำลองใดของ FloodGuard ที่ฝึกด้วยภาพจากชุดนี้",
    },
  },
  {
    id: "bountos-2024",
    reference: "Bountos, N. I., Sdraka, M., Zavras, A., Karasante, I., Karavias, A., Herekakis, T., Thanasou, A., Michail, D., & Papoutsis, I. (2024). Kuro Siwo: 33 billion m² under the water. A global multi-temporal satellite dataset for rapid flood mapping. NeurIPS 2024 Datasets and Benchmarks Track. arXiv:2311.12056.",
    url: "https://arxiv.org/abs/2311.12056",
    use: {
      en: "A multi-event radar flood set under CC BY, reviewed as a training source; whether it covers Thailand was not verified.",
      th: "ชุดข้อมูลน้ำท่วมจากเรดาร์หลายเหตุการณ์ภายใต้สัญญาอนุญาต CC BY ที่พิจารณาเป็นแหล่งข้อมูลฝึก ยังไม่ได้ตรวจสอบว่าครอบคลุมประเทศไทยหรือไม่",
    },
  },
  {
    id: "tarpanelli-2022",
    reference: "Tarpanelli, A., Mondini, A. C., & Camici, S. (2022). Effectiveness of Sentinel-1 and Sentinel-2 for flood detection assessment in Europe. Natural Hazards and Earth System Sciences, 22(8), 2473–2489.",
    url: "https://doi.org/10.5194/nhess-22-2473-2022",
    use: {
      en: "Compares radar and optical satellites for flood detection: why optical images serve as a check beside radar, limited by cloud.",
      th: "เปรียบเทียบดาวเทียมเรดาร์และดาวเทียมเชิงแสงในการตรวจหาน้ำท่วม เป็นเหตุผลที่ภาพเชิงแสงใช้ตรวจทานควบคู่กับเรดาร์ โดยมีข้อจำกัดจากเมฆ",
    },
  },
  {
    id: "thammaboribal-2025",
    reference: "Thammaboribal, P., et al. (2025). Flood mapping and damage assessment using UN-SPIDER recommended practices in Google Earth Engine: A case study of the 2024 Chiang Rai flood, Thailand. International Journal of Geoinformatics, 21(3).",
    url: "https://doi.org/10.52939/ijg.v21i3.4039",
    use: {
      en: "A published radar map of the same 2024 Chiang Rai flood, its threshold tuned on 80 GISTDA ground points: a comparison for us, not our reference.",
      th: "แผนที่น้ำท่วมจากเรดาร์ที่ตีพิมพ์แล้วของเหตุการณ์เชียงราย 2567 เดียวกัน โดยปรับค่าเกณฑ์จากจุดภาคสนามของ GISTDA 80 จุด ใช้เปรียบเทียบ ไม่ใช่ข้อมูลอ้างอิงของเรา",
    },
  },
  {
    id: "renno-2008",
    reference: "Rennó, C. D., Nobre, A. D., Cuartas, L. A., Soares, J. V., Hodnett, M. G., Tomasella, J., & Waterloo, M. J. (2008). HAND, a new terrain descriptor using SRTM-DEM: Mapping terra-firme rainforest environments in Amazonia. Remote Sensing of Environment, 112(9), 3469–3481.",
    url: "https://doi.org/10.1016/j.rse.2008.03.018",
    use: {
      en: "Defines HAND, the height of each cell above the nearest stream, computed from an elevation model.",
      th: "นิยามค่า HAND คือความสูงของแต่ละเซลล์เหนือลำน้ำที่ใกล้ที่สุด คำนวณจากแบบจำลองระดับสูงเชิงเลข (DEM)",
    },
  },
  {
    id: "nobre-2011",
    reference: "Nobre, A. D., Cuartas, L. A., Hodnett, M., Rennó, C. D., Rodrigues, G., Silveira, A., Waterloo, M., & Saleska, S. (2011). Height Above the Nearest Drainage – a hydrologically relevant new terrain model. Journal of Hydrology, 404(1–2), 13–29.",
    url: "https://doi.org/10.1016/j.jhydrol.2011.03.051",
    use: {
      en: "HAND as a hydrological terrain model: our flood timeline wets a cell when the assumed river stage rises above its HAND value.",
      th: "HAND ในฐานะแบบจำลองภูมิประเทศทางอุทกวิทยา ลำดับเวลาน้ำท่วมของเราถือว่าเซลล์ใดเปียกเมื่อระดับน้ำในลำน้ำที่สมมติสูงกว่าค่า HAND ของเซลล์นั้น",
    },
    code: "src/floodguard/flood_timeline.py",
  },
  {
    id: "pekel-2016",
    reference: "Pekel, J.-F., Cottam, A., Gorelick, N., & Belward, A. S. (2016). High-resolution mapping of global surface water and its long-term changes. Nature, 540(7633), 418–422.",
    url: "https://doi.org/10.1038/nature20584",
    use: {
      en: "JRC Global Surface Water: places with water ten months a year or more count as permanent water, not as flood.",
      th: "ข้อมูลน้ำผิวดิน JRC Global Surface Water พื้นที่ที่มีน้ำตั้งแต่สิบเดือนต่อปีขึ้นไปนับเป็นแหล่งน้ำถาวร ไม่นับเป็นน้ำท่วม",
    },
    code: "src/floodguard/diagnosis_layers.py",
  },
  {
    id: "breiman-2001",
    reference: "Breiman, L. (2001). Random forests. Machine Learning, 45(1), 5–32.",
    url: "https://doi.org/10.1023/A:1010933404324",
    use: {
      en: "Random forests, one of the two tree models compared in the flood susceptibility test.",
      th: "Random forest หนึ่งในสองแบบจำลองต้นไม้ที่เปรียบเทียบกันในการทดสอบความอ่อนไหวต่อน้ำท่วม",
    },
    code: "src/floodguard/flood_susceptibility_ml.py",
  },
  {
    id: "friedman-2001",
    reference: "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. The Annals of Statistics, 29(5), 1189–1232.",
    url: "https://doi.org/10.1214/aos/1013203451",
    use: {
      en: "Gradient-boosted trees, the other tree model of the susceptibility test (in scikit-learn’s histogram form).",
      th: "Gradient-boosted trees แบบจำลองต้นไม้อีกแบบหนึ่งในการทดสอบความอ่อนไหว (ในรูปแบบฮิสโทแกรมของ scikit-learn)",
    },
    code: "src/floodguard/flood_susceptibility_ml.py",
  },
  {
    id: "zadrozny-2002",
    reference: "Zadrozny, B., & Elkan, C. (2002). Transforming classifier scores into accurate multiclass probability estimates. In Proceedings of the Eighth ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (pp. 694–699).",
    url: "https://doi.org/10.1145/775047.775151",
    use: {
      en: "Isotonic calibration, which turns raw model values into probabilities; we fit it on out-of-fold values only.",
      th: "การปรับเทียบแบบ isotonic ซึ่งแปลงค่าดิบของแบบจำลองเป็นความน่าจะเป็น เราปรับเทียบจากค่านอกชุดฝึก (out-of-fold) เท่านั้น",
    },
    code: "src/floodguard/flood_susceptibility_ml.py",
  },
  {
    id: "guo-2017",
    reference: "Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural networks. In Proceedings of the 34th International Conference on Machine Learning (PMLR 70, pp. 1321–1330).",
    url: "https://arxiv.org/abs/1706.04599",
    use: {
      en: "Expected calibration error (ECE): one of the checks a model must pass before it is promoted.",
      th: "ค่าคาดหมายของความคลาดเคลื่อนในการปรับเทียบ (ECE) หนึ่งในเกณฑ์ที่แบบจำลองต้องผ่านก่อนถูกยกระดับขึ้นใช้งาน",
    },
    code: "src/floodguard/model_promotion.py",
  },
  {
    id: "brier-1950",
    reference: "Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. Monthly Weather Review, 78(1), 1–3.",
    url: "https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2",
    use: {
      en: "The Brier score, the mean squared error of a probability, reported with every model result.",
      th: "คะแนน Brier ค่าความคลาดเคลื่อนกำลังสองเฉลี่ยของความน่าจะเป็น รายงานไว้กับผลของแบบจำลองทุกครั้ง",
    },
    code: "src/floodguard/probability_aggregation.py",
  },
  {
    id: "dijkstra-1959",
    reference: "Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. Numerische Mathematik, 1(1), 269–271.",
    url: "https://doi.org/10.1007/BF01386390",
    use: {
      en: "Shortest travel times over the road graph, before and after flooded roads are removed (SciPy’s implementation).",
      th: "เวลาเดินทางที่สั้นที่สุดบนโครงข่ายถนน ก่อนและหลังตัดถนนที่ถูกน้ำท่วมออก (ใช้การคำนวณของ SciPy)",
    },
    code: "src/floodguard/evacuation_access.py",
  },
  {
    id: "luo-2003",
    reference: "Luo, W., & Wang, F. (2003). Measures of spatial accessibility to health care in a GIS environment: Synthesis and a case study in the Chicago region. Environment and Planning B: Planning and Design, 30(6), 865–884.",
    url: "https://doi.org/10.1068/b29120",
    use: {
      en: "The two-step floating catchment method: our shelter and service check compares supply with demand within 15, 30 and 60 minutes.",
      th: "วิธี two-step floating catchment การตรวจสอบศูนย์พักพิงและบริการของเราเปรียบเทียบความสามารถในการรองรับกับความต้องการภายในเวลาเดินทาง 15, 30 และ 60 นาที",
    },
    code: "src/floodguard/two_step_access.py",
  },
];

const ENTRIES: ReadonlyMap<string, JournalEntry> = new Map<string, JournalEntry>([
  ...POLICY_READING.flatMap((group) => group.items).map((item): [string, JournalEntry] => [item.id, { ...item, checked: JOURNAL_CHECKED.policy }]),
  ...METHOD_PAPERS.map((item): [string, JournalEntry] => [item.id, { ...item, checked: JOURNAL_CHECKED.methods }]),
]);

function pick(ids: readonly string[]): JournalEntry[] {
  return ids.map((id) => {
    const found = ENTRIES.get(id);
    if (!found) throw new Error(`The reference list has no entry ${id}.`);
    return found;
  });
}

/**
 * The papers in the order of the system: radar, terrain, models, access, people, the score, and the frameworks it
 * answers to. The policy page's own list is read here, not copied, so the two pages cannot disagree.
 */
export const JOURNAL_GROUPS: readonly JournalGroup[] = [
  {
    id: "radar",
    title: { en: "Finding water in radar images", th: "การหาน้ำจากภาพเรดาร์" },
    intro: { en: "Step 1: from Sentinel-1 images to a map of likely water.", th: "ขั้นที่ 1: จากภาพ Sentinel-1 สู่แผนที่บริเวณที่น่าจะมีน้ำ" },
    items: pick(["small-2011", "lee-1980", "lee-1981", "otsu-1979", "ronneberger-2015", "lin-2017", "bonafilia-2020", "bountos-2024", "tarpanelli-2022", "thammaboribal-2025"]),
  },
  {
    id: "terrain",
    title: { en: "Terrain and the history of water", th: "ภูมิประเทศและประวัติของน้ำ" },
    intro: { en: "Step 2: where water can collect, and where it is always present.", th: "ขั้นที่ 2: บริเวณที่น้ำขังได้ และบริเวณที่มีน้ำอยู่เสมอ" },
    items: pick(["renno-2008", "nobre-2011", "pekel-2016"]),
  },
  {
    id: "models",
    title: { en: "Models, calibration and measures of accuracy", th: "แบบจำลอง การปรับเทียบ และตัววัดความแม่นยำ" },
    intro: { en: "How a model’s numbers become probabilities, and how we test them.", th: "ตัวเลขของแบบจำลองกลายเป็นความน่าจะเป็นได้อย่างไร และเราทดสอบอย่างไร" },
    items: pick(["breiman-2001", "friedman-2001", "zadrozny-2002", "guo-2017", "brier-1950"]),
  },
  {
    id: "access",
    title: { en: "Roads and lost access", th: "ถนนและการสูญเสียการเข้าถึง" },
    intro: { en: "Step 3: who can no longer reach a hospital, a shelter or a main road.", th: "ขั้นที่ 3: ใครไปถึงโรงพยาบาล ศูนย์พักพิง หรือถนนสายหลักไม่ได้อีกต่อไป" },
    items: pick(["dijkstra-1959", "luo-2003", "coles-2017", "green-2017", "pregnolato-2017", "papilloud-2021", "tariverdi-2023", "logan-2020", "hallegatte-2019"]),
  },
  {
    id: "people",
    title: { en: "Who is harmed most", th: "ใครได้รับผลกระทบมากที่สุด" },
    intro: { en: "Why the score counts children and older people.", th: "เหตุใดคะแนนจึงนับเด็กและผู้สูงอายุ" },
    items: pick(["jonkman-2009", "rufat-2015", "cutter-2003"]),
  },
  {
    id: "score",
    title: { en: "Building a score and testing its weights", th: "การสร้างคะแนนและการทดสอบน้ำหนัก" },
    intro: { en: "Step 4: the Flood Preparedness Priority Score and the test of its five weights.", th: "ขั้นที่ 4: คะแนนลำดับความสำคัญในการเตรียมรับมือน้ำท่วม และการทดสอบน้ำหนักทั้งห้า" },
    items: pick(["oecd-2008", "greco-2019", "moreira-2021", "tate-2012", "saisana-2005", "becker-2017", "de-brito-2018"]),
  },
  {
    id: "frameworks",
    title: { en: "Frameworks, Thailand and the 2024 flood", th: "กรอบการดำเนินงาน ประเทศไทย และน้ำท่วมปี 2567" },
    intro: { en: "What the work answers to, and who holds the duty to act.", th: "งานนี้ต้องสอดคล้องกับกรอบใด และใครมีหน้าที่ดำเนินการ" },
    items: pick(["sendai-target-d", "wmo-1150", "inform", "unosat-mae-sai", "marks-2016"]),
  },
];

/** Thai law and plans, as the policy page lists them. */
export const JOURNAL_THAI_SOURCES = POLICY_GOVERNMENT_SOURCES;

export interface JournalResource {
  id: string;
  name: string;
  /** Who publishes it, and the licence or terms as the publisher states them. Not translated. */
  terms: string;
  url: string;
  use: BilingualText;
}

/** The data the published results are built from, with the terms recorded in `docs/source_registry.md`. */
export const JOURNAL_DATA: readonly JournalResource[] = [
  {
    id: "sentinel-1",
    name: "Copernicus Sentinel-1 radar (Copernicus Data Space Ecosystem; terrain-corrected scenes from Microsoft Planetary Computer)",
    terms: "European Commission / ESA. Free and open; Copernicus Sentinel data legal notice.",
    url: "https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-1",
    use: { en: "Radar images before and after the September 2024 Mae Sai flood.", th: "ภาพเรดาร์ก่อนและหลังน้ำท่วมแม่สายเดือนกันยายน 2567" },
  },
  {
    id: "sentinel-2",
    name: "Copernicus Sentinel-2 Level-2A optical images",
    terms: "European Commission / ESA. Free and open; Copernicus Sentinel data legal notice.",
    url: "https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel2.html",
    use: { en: "Optical images as an automatic check beside radar, where cloud allows.", th: "ภาพเชิงแสงสำหรับตรวจทานอัตโนมัติควบคู่กับเรดาร์ เมื่อเมฆไม่บดบัง" },
  },
  {
    id: "copernicus-dem",
    name: "Copernicus DEM GLO-30",
    terms: "European Space Agency. Copernicus DEM licence; attribution required.",
    url: "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
    use: { en: "Elevation for slope, HAND and the flood timeline.", th: "ความสูงภูมิประเทศสำหรับความลาดชัน ค่า HAND และลำดับเวลาน้ำท่วม" },
  },
  {
    id: "jrc-gsw",
    name: "JRC Global Surface Water v1.4",
    terms: "European Commission JRC / Google. Free; acknowledgement required.",
    url: "https://global-surface-water.appspot.com/download",
    use: { en: "Permanent rivers and ponds, kept apart from flood water.", th: "แม่น้ำและแหล่งน้ำถาวร แยกออกจากน้ำท่วม" },
  },
  {
    id: "worldcover",
    name: "ESA WorldCover 2021 v200 (10 m land cover)",
    terms: "European Space Agency. CC BY 4.0.",
    url: "https://esa-worldcover.org/en/data-access",
    use: { en: "Land cover, including the permanent water class used by the score.", th: "สิ่งปกคลุมดิน รวมถึงประเภทแหล่งน้ำถาวรที่คะแนนใช้" },
  },
  {
    id: "worldpop",
    name: "WorldPop Thailand 100 m population, 2020 (doi:10.5258/SOTON/WP00645)",
    terms: "WorldPop, University of Southampton. CC BY 4.0.",
    url: "https://hub.worldpop.org/geodata/summary?id=6439",
    use: { en: "Modelled residents in 2020, not a count of 2024, and their age groups.", th: "จำนวนผู้อยู่อาศัยจากแบบจำลองปี 2563 ไม่ใช่การนับปี 2567 และกลุ่มอายุของผู้อยู่อาศัย" },
  },
  {
    id: "osm",
    name: "OpenStreetMap Thailand (Geofabrik extract)",
    terms: "© OpenStreetMap contributors. Open Database License (ODbL).",
    url: "https://download.geofabrik.de/asia/thailand.html",
    use: { en: "Roads, hospitals, schools and shelter candidates for the access check.", th: "ถนน โรงพยาบาล โรงเรียน และจุดที่อาจเป็นศูนย์พักพิงสำหรับการตรวจสอบการเข้าถึง" },
  },
  {
    id: "ngis",
    name: "Thai NGIS services: DOPA subdistrict boundaries, DWR rivers, highway centrelines",
    terms: "Thai government GIS portal (ngis.go.th); terms of each layer as published.",
    url: "https://ngis.go.th/",
    use: { en: "Tambon boundaries for every figure, and the rivers behind HAND.", th: "ขอบเขตตำบลที่ใช้สรุปตัวเลขทุกรายการ และลำน้ำที่ใช้คำนวณค่า HAND" },
  },
  {
    id: "hdx-cod-ab",
    name: "Thailand administrative boundaries (OCHA COD-AB on HDX)",
    terms: "OCHA / HDX. Terms as stated on the dataset page.",
    url: "https://data.humdata.org/dataset/cod-ab-tha",
    use: { en: "Matching area codes across sources; codes are joined, never names.", th: "จับคู่รหัสพื้นที่ระหว่างแหล่งข้อมูล โดยเชื่อมด้วยรหัส ไม่ใช้ชื่อ" },
  },
  {
    id: "unosat",
    name: "UNOSAT product 3991: water extents over Mae Sai, 13–19 September 2024",
    terms: "UNOSAT / UNITAR. Public report; reuse of its GIS geometry not cleared.",
    url: "https://unosat.org/products/3991",
    use: { en: "The agency view of the event, used as evidence in the story, not as a training label.", th: "มุมมองของหน่วยงานต่อเหตุการณ์ ใช้เป็นหลักฐานประกอบเรื่องราว ไม่ใช้เป็นป้ายกำกับ (label) สำหรับฝึกแบบจำลอง" },
  },
  {
    id: "theos-2",
    name: "THEOS-2 sample images (provided for GeoHackathon 2026)",
    terms: "GISTDA. Provided to the teams for this hackathon.",
    url: "https://www.gistda.or.th/",
    use: { en: "Very high resolution optical context; not a flood reference.", th: "ภาพเชิงแสงความละเอียดสูงมากเพื่อบริบท ไม่ใช่ข้อมูลอ้างอิงน้ำท่วม" },
  },
];

/** The open-source software the pipeline and the site are built on. */
export const JOURNAL_SOFTWARE: readonly JournalResource[] = [
  {
    id: "geoai",
    name: "geoai-py 0.41.1 (opengeos/geoai)",
    terms: "Wu, Q., and contributors. MIT License.",
    url: "https://github.com/opengeos/geoai",
    use: { en: "The GeoAI toolkit of the isolated GeoAI runner.", th: "ชุดเครื่องมือ GeoAI ของตัวประมวลผล GeoAI ที่แยกส่วนไว้" },
  },
  {
    id: "smp",
    name: "segmentation-models-pytorch 0.5.0, on PyTorch",
    terms: "Iakubovskii, P., and contributors. MIT License.",
    url: "https://github.com/qubvel-org/segmentation_models.pytorch",
    use: { en: "The U-Net and FPN networks of the controlled experiment.", th: "โครงข่าย U-Net และ FPN ของการทดลองแบบควบคุม" },
  },
  {
    id: "scikit-learn",
    name: "scikit-learn (Pedregosa et al., 2011, Journal of Machine Learning Research 12, 2825–2830)",
    terms: "BSD 3-Clause License.",
    url: "https://jmlr.org/papers/v12/pedregosa11a.html",
    use: { en: "Tree models, isotonic calibration and cross-validation.", th: "แบบจำลองต้นไม้ การปรับเทียบแบบ isotonic และการตรวจสอบไขว้" },
  },
  {
    id: "scipy",
    name: "SciPy (Virtanen et al., 2020, Nature Methods 17, 261–272)",
    terms: "BSD 3-Clause License.",
    url: "https://doi.org/10.1038/s41592-019-0686-2",
    use: { en: "Shortest paths on the road graph and the image filters.", th: "เส้นทางที่สั้นที่สุดบนโครงข่ายถนนและตัวกรองภาพ" },
  },
  {
    id: "pysheds",
    name: "pysheds",
    terms: "Bartos, M., and contributors. GPL-3.0 License.",
    url: "https://github.com/mdbartos/pysheds",
    use: { en: "Flow directions and HAND from the elevation model.", th: "ทิศทางการไหลของน้ำและค่า HAND จากแบบจำลองระดับสูงเชิงเลข (DEM)" },
  },
  {
    id: "rasterio",
    name: "Rasterio 1.4.4, on GDAL",
    terms: "BSD 3-Clause License (GDAL: MIT-style licence).",
    url: "https://rasterio.readthedocs.io/",
    use: { en: "Reading and writing every raster, with its coordinate system.", th: "อ่านและเขียนข้อมูลแรสเตอร์ทุกชุดพร้อมระบบพิกัด" },
  },
  {
    id: "qgis",
    name: "QGIS",
    terms: "QGIS project. GPL-2.0 License.",
    url: "https://qgis.org/",
    use: { en: "Visual checks of reference polygons and the manual review mask.", th: "ตรวจด้วยสายตาสำหรับรูปหลายเหลี่ยมอ้างอิงและหน้ากากตรวจทานด้วยมือ" },
  },
  {
    id: "leaflet",
    name: "Leaflet 1.9.4",
    terms: "Agafonkin, V., and contributors. BSD 2-Clause License.",
    url: "https://leafletjs.com/",
    use: { en: "The maps on this site.", th: "แผนที่บนเว็บไซต์นี้" },
  },
];

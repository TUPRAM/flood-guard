import { STOP_HOURS, type ChapterId, type PublicTab, type SegmentId, type StopId } from "@/lib/journey/timeline";

export type { PublicTab } from "@/lib/journey/timeline";

export type JourneyLanguage = "en" | "th";
type Text = Record<JourneyLanguage, string>;
const t = (en: string, th: string): Text => ({ en, th });

/**
 * The story follows three fictional people, each with a reason to use one real FloodGuard page: Lalita (the public
 * app), Narin (the case view) and Pim (the command exercise). Mali and Dao, Lalita's mother and daughter, give her
 * household plan its needs. None of them represents a real person. The place is real: Mae Sai town around the Public
 * app's example home, with the water of the published replay (r5), a model reconstruction of September 2024 with low
 * confidence. Thai text is written by the team's assistant and has not had a native review.
 */
export type CharacterId = "lalita" | "narin" | "pim";

export interface Character {
  name: Text;
  role: Text;
  /** The question that brings this person to their FloodGuard page. */
  question: Text;
}

export const CHARACTERS: Record<CharacterId, Character> = {
  lalita: {
    name: t("Lalita", "ลลิตา"),
    role: t("Resident · looks after her mother and daughter", "ผู้อยู่อาศัย · ดูแลแม่และลูกสาว"),
    question: t("Can my family still get where they need to go?", "ครอบครัวของฉันยังไปในที่ที่ต้องไปได้หรือไม่"),
  },
  narin: {
    name: t("Narin", "นรินทร์"),
    role: t("Planning officer · Mae Sai District Office", "เจ้าหน้าที่วางแผน · ที่ว่าการอำเภอแม่สาย"),
    question: t("What do we know, and what still needs checking?", "เรารู้อะไรแล้ว และอะไรที่ยังต้องตรวจสอบ"),
  },
  pim: {
    name: t("Pim", "พิมพ์"),
    role: t("District planning coordinator", "ผู้ประสานงานวางแผนระดับอำเภอ"),
    question: t("What should our team review together first?", "ทีมควรทบทวนเรื่องใดร่วมกันก่อน"),
  },
};

export const CHAPTER_LABELS: Record<ChapterId, { number: string; title: Text }> = {
  opening: { number: "", title: t("Opening", "เริ่มต้น") },
  everyday: { number: "01", title: t("Lalita's family", "ครอบครัวของลลิตา") },
  conditions: { number: "02", title: t("Rain, and a plan", "ฝนตกและแผนรับมือ") },
  night: { number: "03", title: t("The night", "คืนนั้น") },
  affected: { number: "04", title: t("Cut off · Narin", "ถูกตัดขาด · นรินทร์") },
  response: { number: "05", title: t("The district · Pim", "ภาพรวมอำเภอ · พิมพ์") },
  after: { number: "06", title: t("Water going down", "น้ำลด") },
};

export const UI = {
  title: t("Home dry.\nWay cut off.", "บ้านยังแห้ง\nแต่ทางออกถูกตัดขาด"),
  subtitle: t(
    "Mae Sai, September 2024. Lalita looks after her mother and daughter. Narin checks what is known. Pim brings the district together. Fictional people on the real map, with the replay's modelled water.",
    "แม่สาย กันยายน 2567 (2024) ลลิตาดูแลแม่และลูกสาว นรินทร์ตรวจสอบสิ่งที่รู้แล้ว พิมพ์ประสานภาพรวมของอำเภอ ตัวละครสมมุติบนแผนที่จริง กับน้ำจากแบบจำลองของภาพจำลองย้อนหลัง",
  ),
  begin: t("Begin the story", "เริ่มเรื่องราว"),
  skip: t("Skip to the apps", "ข้ามไปที่แอป"),
  skipShort: t("Apps", "แอป"),
  scrollHint: t("Scroll, swipe or use the arrow keys", "เลื่อน ปัด หรือใช้ปุ่มลูกศร"),
  illustrative: t(
    "Fictional people on the real map of Mae Sai · water from the FloodGuard replay (r5): a model reconstruction of September 2024, low confidence · not a forecast, not real-time",
    "ตัวละครสมมุติบนแผนที่จริงของแม่สาย · น้ำจากภาพจำลองย้อนหลัง (r5) ของ FloodGuard: การสร้างเหตุการณ์กันยายน 2567 (2024) ขึ้นใหม่ด้วยแบบจำลอง ความเชื่อมั่นต่ำ · ไม่ใช่การพยากรณ์ ไม่ใช่ข้อมูลเรียลไทม์",
  ),
  /** Short credits, in the Credits panel; the full credits and licences are in public/journey/town/LICENSE.txt. */
  credits: t(
    "Buildings: Google Open Buildings v3 (CC BY 4.0), Microsoft footprints (ODbL) · © OpenStreetMap contributors · Copernicus DEM © DLR, Airbus DS · Water: FloodGuard replay r5 · Heights and looks of buildings illustrative",
    "อาคาร: Google Open Buildings v3 (CC BY 4.0), Microsoft footprints (ODbL) · © ผู้ร่วมให้ข้อมูล OpenStreetMap · Copernicus DEM © DLR, Airbus DS · น้ำ: ภาพจำลองย้อนหลัง r5 ของ FloodGuard · ความสูงและรูปลักษณ์ของอาคารเป็นภาพประกอบ",
  ),
  creditsButton: t("Credits", "เครดิต"),
  creditsTitle: t("About this story and its data", "เกี่ยวกับเรื่องราวและข้อมูลนี้"),
  illustrativeLooks: t(
    "Heights and looks of buildings, and Lalita's house and yard, are illustrative.",
    "ความสูงและรูปลักษณ์ของอาคาร รวมถึงบ้านและลานบ้านของลลิตา เป็นภาพประกอบ",
  ),
  /** One line of data credits on the title screen; the full credits are in the Credits panel. */
  creditsShort: t(
    "© OpenStreetMap contributors · Google Open Buildings (CC BY 4.0) · Microsoft footprints (ODbL) · Copernicus DEM",
    "© ผู้ร่วมให้ข้อมูล OpenStreetMap · Google Open Buildings (CC BY 4.0) · Microsoft footprints (ODbL) · Copernicus DEM",
  ),
  /** The replay clock: `{moment}` is the replay hour as the case view writes it. */
  clock: t("Replay · {moment} · model, low confidence", "ภาพจำลองย้อนหลัง · {moment} · แบบจำลอง ความเชื่อมั่นต่ำ"),
  fictional: t("Fictional character", "ตัวละครสมมุติ"),
  previous: t("Previous", "ก่อนหน้า"),
  next: t("Next", "ถัดไป"),
  backToStory: t("Back to the story", "กลับไปที่เรื่องราว"),
  story: t("Story", "เรื่องราว"),
  openPage: t("Open as its own page", "เปิดเป็นหน้าแยก"),
  loadingPage: t("Loading the real page…", "กำลังโหลดหน้าจริง…"),
  loadingWorld: t("Preparing the neighbourhood…", "กำลังเตรียมชุมชน…"),
  home: t("FloodGuard home", "หน้าแรก FloodGuard"),
  replay: t("Replay the story", "เล่นเรื่องราวอีกครั้ง"),
  chapters: t("Story chapters", "บทของเรื่องราว"),
  skipTitle: t("Go straight to a real FloodGuard page", "ไปที่หน้า FloodGuard จริงโดยตรง"),
  close: t("Close", "ปิด"),
  fallbackTitle: t("The 3D story could not start on this device", "ไม่สามารถเริ่มเรื่องราวแบบ 3 มิติบนอุปกรณ์นี้ได้"),
  fallbackBody: t(
    "You can still follow the story and open every real FloodGuard page below.",
    "คุณยังติดตามเรื่องราวและเปิดหน้า FloodGuard จริงทุกหน้าได้ด้านล่าง",
  ),
};

/** Labels projected onto the 3D scene: places, the walk, and the people when the camera is with them. */
export const LABELS: Record<string, Text> = {
  home: t("Lalita's home · the app's example home", "บ้านของลลิตา · บ้านตัวอย่างในแอป"),
  neighbour: t("Neighbours · water at home in the model", "เพื่อนบ้าน · น้ำเข้าบ้านตามแบบจำลอง"),
  neighbourPeak: t("Neighbours · water reached 0.75 m here at the peak (model)", "เพื่อนบ้าน · น้ำเคยสูงถึง 0.75 ม. ช่วงน้ำสูงสุด (แบบจำลอง)"),
  shelter: t("Municipality office shelter · reported in use, Sept 2024", "ศูนย์พักพิงเทศบาลตำบลแม่สาย · มีรายงานว่าเปิดใช้ ก.ย. 2567"),
  route: t("Usual walk to the shelter", "ทางเดินปกติไปศูนย์พักพิง"),
  low: t("Low point on the walk · cut at 30 cm of water (model)", "จุดต่ำบนทางเดิน · ถูกตัดเมื่อน้ำลึก 30 ซม. (แบบจำลอง)"),
  cut: t("Walk cut · water 30 cm or more (model)", "ทางเดินถูกตัด · น้ำลึก 30 ซม. ขึ้นไป (แบบจำลอง)"),
  river: t("Sai River · border with Myanmar", "แม่น้ำสาย · ชายแดนเมียนมา"),
  office: t("Mae Sai District Office · reported command centre, 2024", "ที่ว่าการอำเภอแม่สาย · มีรายงานว่าเป็นศูนย์บัญชาการปี 2567"),
  wat: t("Wat Mueang Daeng · reported flooded, 11–12 Sep 2024", "วัดเหมืองแดง · มีรายงานว่าน้ำท่วม 11–12 ก.ย. 2567"),
  signal: t("Simulated call to hotline 1784 · nothing dialled", "จำลองการโทรสายด่วน 1784 · ไม่มีการโทรจริง"),
  lalita: t("Lalita", "ลลิตา"),
  mali: t("Mali, her mother", "มะลิ แม่ของเธอ"),
  dao: t("Dao, her daughter", "ดาว ลูกสาวของเธอ"),
  narin: t("Narin", "นรินทร์"),
  pim: t("Pim", "พิมพ์"),
};

/** The simulated call on the operations-room monitor: drawn in both languages, as the scene does not change language. */
export const MONITOR = {
  header: t("STORY MODE · SIMULATED CALL TO 1784", "โหมดเรื่องราว · จำลองการโทร 1784"),
  title: t("Dry home, walk to the shelter cut", "บ้านแห้ง ทางเดินไปศูนย์พักพิงถูกตัด"),
  note: t("Fictional household. Nothing was dialled or sent.", "ครัวเรือนสมมุติ ไม่มีการโทรหรือส่งข้อมูลจริง"),
};

export interface Caption {
  from: number;
  to: number;
  eyebrow?: Text;
  /** Whose part of the story this is (shown with the caption). */
  who?: CharacterId;
  /** The caption that introduces `who`: shows their role and their question. */
  meet?: boolean;
  /** The headline sentence. */
  text: Text;
  /** A few supporting points shown under the headline (for reading at your own pace or presenting). */
  points?: Text[];
  /**
   * Where the story waits for "Next" while this caption is shown (segment progress, inside [from, to)). A caption
   * without one is read while the camera passes (it leads into the next one).
   */
  pause?: number;
}

/**
 * Captions over the 3D scene: [start, end) progress ranges within a segment. Every feature a caption names is one the
 * real page has: the Public app's example home and practice scenarios, Prepare (household needs), Shelter (a
 * destination the household has checked; the app does not know capacity), Report (saved on the device, sent nowhere)
 * and SOS (official hotlines); the case view's replay and its confidence; the command exercise's hourly table,
 * practice items and trainee mode. Every time and depth named is the replay's (r5), at the hour the caption shows.
 */
export const CAPTIONS: Record<SegmentId, Caption[]> = {
  opening: [],
  everyday: [
    {
      from: 0.2, to: 0.52, pause: 0.4, who: "lalita", meet: true,
      eyebrow: t("01 · Meet Lalita", "01 · พบกับลลิตา"),
      text: t(
        "This is Mae Sai, a few hundred metres from the Sai River. Lalita lives here with her mother, Mali, and her daughter, Dao, who is eight.",
        "นี่คือแม่สาย ห่างจากแม่น้ำสายไม่กี่ร้อยเมตร ลลิตาอาศัยอยู่ที่นี่กับมะลิ แม่ของเธอ และดาว ลูกสาววัยแปดขวบ",
      ),
      points: [
        t("Her house stands at the Public app's example home: a point of the model, not an address.", "บ้านของเธออยู่ที่บ้านตัวอย่างในแอปประชาชน ซึ่งเป็นจุดหนึ่งของแบบจำลอง ไม่ใช่ที่อยู่จริง"),
        t("If they have to leave, their plan is to walk to the shelter at the municipality office, about 1.6 km south.", "หากต้องออกจากบ้าน แผนของพวกเขาคือเดินไปศูนย์พักพิงที่สำนักงานเทศบาล ห่างไปทางใต้ราว 1.6 กม."),
        t("The teal line is that walk.", "เส้นสีเขียวอมฟ้าคือทางเดินนั้น"),
      ],
    },
    {
      from: 0.9, to: 1.01, pause: 0.985, who: "lalita",
      text: t(
        "Monday 9 September 2024, midday. Heavy rain is expected. Lalita checks what is known about her area.",
        "วันจันทร์ที่ 9 กันยายน 2567 (2024) เที่ยงวัน คาดว่าจะมีฝนตกหนัก ลลิตาตรวจดูว่ามีข้อมูลอะไรเกี่ยวกับพื้นที่ของเธอบ้าง",
      ),
      points: [
        t("She opens the FloodGuard Public app.", "เธอเปิดแอป FloodGuard สำหรับประชาชน"),
        t("It helps her prepare. It is not an official warning.", "แอปช่วยให้เธอเตรียมพร้อม แต่ไม่ใช่การแจ้งเตือนทางการ"),
      ],
    },
  ],
  "enter-phone": [
    {
      from: 0.55, to: 1.01, pause: 0.92, who: "lalita",
      text: t("This is the real Public app, on a normal day.", "นี่คือแอปสำหรับประชาชนจริง ในวันปกติ"),
      points: [
        t("It opens on the example home in Mae Sai town: the same place as this story.", "แอปเปิดที่บ้านตัวอย่างในตัวเมืองแม่สาย ซึ่งเป็นที่เดียวกับในเรื่องนี้"),
        t("Practice scenarios replay the 2024 flood at this home, hour by hour.", "สถานการณ์ฝึกซ้อมย้อนดูน้ำท่วมปี 2567 ที่บ้านหลังนี้ทีละชั่วโมง"),
        t("A replay of 2024 says nothing about today. It is not a forecast.", "ภาพจำลองย้อนหลังของปี 2567 ไม่ได้บอกอะไรเกี่ยวกับวันนี้ และไม่ใช่การพยากรณ์"),
      ],
    },
  ],
  conditions: [
    {
      from: 0.12, to: 0.55, pause: 0.5, who: "lalita",
      eyebrow: t("02 · Rain, and a plan", "02 · ฝนตกและแผนรับมือ"),
      text: t(
        "Tuesday 10 September, afternoon. The rain has not stopped; in the replay the river is a little above its channel, and the fast rise comes in the evening.",
        "วันอังคารที่ 10 กันยายน ช่วงบ่าย ฝนยังไม่หยุด ในภาพจำลองย้อนหลัง แม่น้ำสูงกว่าร่องน้ำเล็กน้อย และจะขึ้นเร็วในช่วงค่ำ",
      ),
      points: [
        t("In the model, water collects first in the lowest streets, toward the river.", "ในแบบจำลอง น้ำขังที่ถนนที่ต่ำที่สุดฝั่งแม่น้ำก่อน"),
        t("Lalita's street is still dry.", "ถนนหน้าบ้านลลิตายังแห้งอยู่"),
        t("Times and depths come from the replay: a reconstruction with low confidence.", "เวลาและความลึกมาจากภาพจำลองย้อนหลัง ซึ่งสร้างขึ้นใหม่ด้วยความเชื่อมั่นต่ำ"),
      ],
    },
    {
      from: 0.6, to: 1.01, pause: 0.95, who: "lalita",
      text: t(
        "Their walk to the shelter dips through low ground about 110 m south of the house.",
        "ทางเดินไปศูนย์พักพิงของพวกเขาผ่านพื้นที่ต่ำห่างจากบ้านไปทางใต้ราว 110 เมตร",
      ),
      points: [
        t("If that dip floods, the walk is cut.", "ถ้าจุดต่ำนั้นน้ำท่วม ทางเดินก็ถูกตัด"),
        t("Lalita cannot control the river.", "ลลิตาควบคุมแม่น้ำไม่ได้"),
        t("She can make a plan before she needs one.", "แต่เธอวางแผนไว้ก่อนที่จะต้องใช้ได้"),
      ],
    },
  ],
  "return-phone": [
    {
      from: 0.28, to: 0.58, pause: 0.45, who: "lalita",
      text: t(
        "Lalita talks it through with Mali and Dao: what to pack, who helps whom, when to go.",
        "ลลิตาคุยกับมะลิและดาวว่าต้องเตรียมอะไร ใครช่วยใคร และจะไปเมื่อไร",
      ),
      points: [
        t("Mali needs her regular medicine with her.", "มะลิต้องมียาประจำตัวติดไว้"),
        t("Dao needs a grown-up she knows, and a place to meet.", "ดาวต้องมีผู้ใหญ่ที่รู้จักคอยดูแล และมีจุดนัดพบ"),
        t("They agree how they will follow official updates.", "ทุกคนตกลงกันว่าจะติดตามข่าวทางการอย่างไร"),
      ],
    },
    {
      from: 0.62, to: 1.01, pause: 0.92, who: "lalita",
      text: t("She writes it into her household plan in the app.", "เธอบันทึกเรื่องเหล่านี้ลงในแผนของครัวเรือนในแอป"),
      points: [
        t("Prepare: a child, an older adult and regular medicine each add their own actions.", "เตรียมพร้อม: เด็ก ผู้สูงอายุ และยาประจำตัว แต่ละข้อมีสิ่งที่ต้องทำของตัวเอง"),
        t("Shelter: she enters a place she has checked with the authorities. The app does not know if it is open or full.", "ที่พักพิง: เธอใส่สถานที่ที่สอบถามกับหน่วยงานแล้ว แอปไม่รู้ว่าที่นั่นเปิดอยู่หรือเต็มแล้ว"),
        t("SOS: the official hotlines, kept in one place.", "SOS: รวมสายด่วนทางการไว้ในที่เดียว"),
      ],
    },
  ],
  night: [
    {
      from: 0.0, to: 0.2, pause: 0.06, who: "lalita",
      eyebrow: t("03 · The night", "03 · คืนนั้น"),
      text: t("Lalita notes what she sees in Report: water in the street toward the river.", "ลลิตาบันทึกสิ่งที่เห็นในแท็บรายงาน: มีน้ำบนถนนฝั่งแม่น้ำ"),
      points: [
        t("The note stays on her phone. FloodGuard sends it nowhere.", "บันทึกนี้อยู่ในโทรศัพท์ของเธอ FloodGuard ไม่ได้ส่งไปที่ใด"),
        t("Asking for help goes through official channels.", "การขอความช่วยเหลือต้องผ่านช่องทางทางการ"),
      ],
    },
    {
      from: 0.38, to: 0.56, pause: 0.42, who: "lalita",
      text: t(
        "10 September, 22:00. In the model, water is now on many streets between the house and the river.",
        "10 กันยายน เวลา 22:00 น. ในแบบจำลอง น้ำท่วมถนนหลายสายระหว่างบ้านกับแม่น้ำแล้ว",
      ),
      points: [
        t("The house is still dry.", "บ้านยังแห้งอยู่"),
        t("The app's practice scenario for this hour: roads under water.", "สถานการณ์ฝึกซ้อมในแอปของชั่วโมงนี้: ถนนจมน้ำ"),
        t("Depths are modelled, with low confidence.", "ความลึกมาจากแบบจำลอง ความเชื่อมั่นต่ำ"),
      ],
    },
    {
      from: 0.56, to: 0.78, pause: 0.66, who: "lalita",
      text: t(
        "Midnight. Water is already over the low point on their walk: about 13 cm in the model. At 30 cm the walk is cut.",
        "เที่ยงคืน น้ำท่วมจุดต่ำบนทางเดินแล้ว ลึกราว 13 ซม. ตามแบบจำลอง ถ้าลึกถึง 30 ซม. ทางเดินจะถูกตัด",
      ),
      points: [
        t("Mali cannot walk 1.6 km quickly, at night, in the rain.", "มะลิเดิน 1.6 กม. ได้ไม่เร็ว ในเวลากลางคืนและฝนตก"),
        t("They stay on dry ground at home, the medicine bag ready.", "พวกเขาอยู่บนที่แห้งในบ้าน และเตรียมกระเป๋ายาไว้พร้อม"),
        t("In the model, the house stays dry at every hour of the replay.", "ในแบบจำลอง บ้านแห้งตลอดทุกชั่วโมงของภาพจำลองย้อนหลัง"),
      ],
    },
    {
      from: 0.78, to: 1.01, pause: 0.88, who: "lalita",
      text: t("About 1:00. The dip is under 30 cm of water or more. The walk is cut.", "ราวตีหนึ่ง จุดต่ำมีน้ำลึก 30 ซม. ขึ้นไป ทางเดินถูกตัดแล้ว"),
      points: [
        t("In the model, every walk to a reported shelter within 2 km is cut.", "ในแบบจำลอง ทางเดินไปศูนย์พักพิงที่มีรายงานภายในระยะ 2 กม. ถูกตัดทั้งหมด"),
        t("Their home is dry. The way out is not.", "บ้านของพวกเขาแห้ง แต่ทางออกไม่แห้ง"),
        t("Lost access, not only water at home, is what FloodGuard looks at.", "FloodGuard ดูการเข้าถึงที่ขาดหาย ไม่ใช่แค่น้ำที่เข้าบ้าน"),
      ],
    },
  ],
  "cut-off": [
    {
      from: 0.06, to: 0.3, pause: 0.16, who: "lalita",
      eyebrow: t("04 · Cut off", "04 · ถูกตัดขาด"),
      text: t(
        "Thursday 12 September, midday: the river's highest point in the replay.",
        "วันพฤหัสบดีที่ 12 กันยายน เที่ยงวัน ระดับแม่น้ำสูงที่สุดในภาพจำลองย้อนหลัง",
      ),
      points: [
        t("Lalita's home is dry; the street in front of it is not.", "บ้านของลลิตายังแห้ง แต่ถนนหน้าบ้านไม่แห้ง"),
        t("Her neighbours, 110 m away, have water in the house: 0.75 m in the model.", "เพื่อนบ้านที่อยู่ห่างไป 110 เมตร มีน้ำเข้าบ้าน ลึก 0.75 เมตรตามแบบจำลอง"),
        t("Practice scenario on her phone: cut off, home dry.", "สถานการณ์ฝึกซ้อมในโทรศัพท์ของเธอ: ถูกตัดขาด บ้านยังแห้ง"),
      ],
    },
    {
      from: 0.3, to: 0.48, pause: 0.38, who: "lalita",
      text: t("From above, the house stands on a dry patch, with water on most sides.", "เมื่อมองจากด้านบน บ้านตั้งอยู่บนพื้นที่แห้ง มีน้ำล้อมเกือบทุกด้าน"),
      points: [
        t("In the model, most roads within 1 km are under water.", "ในแบบจำลอง ถนนส่วนใหญ่ภายในระยะ 1 กม. จมน้ำ"),
        t("Homes that are dry but cut off: this is what the access analysis finds.", "บ้านที่แห้งแต่ถูกตัดขาด คือสิ่งที่การวิเคราะห์การเข้าถึงค้นพบ"),
      ],
    },
    {
      from: 0.48, to: 0.72, pause: 0.58, who: "lalita",
      text: t(
        "Mali's medicine is running low. Lalita calls the official hotline, 1784, to ask for help.",
        "ยาของมะลิใกล้หมด ลลิตาโทรหาสายด่วนทางการ 1784 เพื่อขอความช่วยเหลือ",
      ),
      points: [
        t("Story mode: the call is simulated. Nothing is dialled.", "โหมดเรื่องราว: เป็นการจำลอง ไม่มีการโทรจริง"),
        t("The call goes through the hotline, not through FloodGuard.", "สายนี้ผ่านสายด่วน ไม่ได้ผ่าน FloodGuard"),
        t("In 2024, the Mae Sai District Office ran the incident command centre (reported).", "ในปี 2567 ที่ว่าการอำเภอแม่สายเป็นศูนย์บัญชาการเหตุการณ์ (ตามรายงาน)"),
      ],
    },
    {
      from: 0.95, to: 1.01, pause: 0.985, who: "narin", meet: true,
      eyebrow: t("Meet Narin", "พบกับนรินทร์"),
      text: t(
        "Narin is a planning officer at the Mae Sai District Office. Calls like Lalita's are part of what he has to make sense of.",
        "นรินทร์เป็นเจ้าหน้าที่วางแผนที่ที่ว่าการอำเภอแม่สาย สายแบบเดียวกับของลลิตาเป็นส่วนหนึ่งของสิ่งที่เขาต้องทำความเข้าใจ",
      ),
      points: [
        t("He has not seen every road or shelter himself.", "เขาไม่ได้เห็นถนนหรือที่พักพิงทุกแห่งด้วยตัวเอง"),
        t("Not every report is confirmed.", "ไม่ใช่ทุกรายงานที่ได้รับการยืนยัน"),
        t("Before anyone acts, he looks at the evidence.", "ก่อนลงมือทำอะไร เขาดูหลักฐานก่อน"),
      ],
    },
  ],
  "enter-monitor": [
    {
      from: 0.4, to: 1.01, pause: 0.93, who: "narin",
      text: t(
        "Narin opens the case view at the same hour: 12 September, 12:00.",
        "นรินทร์เปิดหน้าเคสที่ชั่วโมงเดียวกัน: 12 กันยายน เวลา 12:00 น.",
      ),
      points: [
        t("The same replay as Lalita's phone: Mae Sai, September 2024, hour by hour.", "ภาพจำลองย้อนหลังเดียวกับในโทรศัพท์ของลลิตา: แม่สาย กันยายน 2567 ทีละชั่วโมง"),
        t("Modelled water, roads, facilities and residents in water, each marked low confidence.", "น้ำ ถนน สถานบริการ และผู้อยู่อาศัยในน้ำจากแบบจำลอง ทั้งหมดระบุว่าความเชื่อมั่นต่ำ"),
        t("Reports and the model do not always agree: Wat Mueang Daeng was reported flooded; the model shows it dry.", "รายงานกับแบบจำลองไม่ได้ตรงกันเสมอ: มีรายงานว่าวัดเหมืองแดงน้ำท่วม แต่แบบจำลองแสดงว่าแห้ง"),
      ],
    },
  ],
  aerial: [
    {
      from: 0.14, to: 0.3, pause: 0.22, who: "pim", meet: true,
      eyebrow: t("05 · Meet Pim", "05 · พบกับพิมพ์"),
      text: t(
        "Pim coordinates planning for the district from the same office. Narin's evidence is one input; she has many communities to think about.",
        "พิมพ์ประสานงานการวางแผนของอำเภอจากที่ทำการเดียวกัน หลักฐานของนรินทร์เป็นข้อมูลส่วนหนึ่ง เธอต้องคิดถึงหลายชุมชน",
      ),
      points: [
        t("Her job is to organise the discussion, not to hand it to a computer.", "งานของเธอคือจัดการการหารือ ไม่ใช่ปล่อยให้คอมพิวเตอร์ตัดสินใจ"),
        t("She brings the team round the planning table.", "เธอชวนทีมมารวมกันที่โต๊ะวางแผน"),
      ],
    },
    {
      from: 0.38, to: 0.7, pause: 0.6, who: "pim",
      text: t(
        "Across the district, the model finds other dry homes cut off like Lalita's.",
        "ทั่วทั้งอำเภอ แบบจำลองพบบ้านหลังอื่นที่แห้งแต่ถูกตัดขาดเหมือนบ้านของลลิตา",
      ),
      points: [
        t("Every walk from a home to a shelter can be checked the same way.", "ทางเดินจากบ้านไปศูนย์พักพิงทุกเส้นตรวจได้ด้วยวิธีเดียวกัน"),
        t("Cut walks show where help may not get through on foot.", "ทางเดินที่ถูกตัดชี้ว่าความช่วยเหลืออาจเดินเท้าไปไม่ถึงที่ใด"),
      ],
    },
    {
      from: 0.74, to: 1.01, pause: 0.95, who: "pim",
      text: t(
        "Pim runs it as an exercise: the team replays the flood hour by hour and practises what they would do.",
        "พิมพ์จัดเป็นการฝึกซ้อม ทีมย้อนดูน้ำท่วมทีละชั่วโมงและฝึกว่าจะทำอะไร",
      ),
      points: [
        t("Each subdistrict's modelled figures, hour by hour.", "ตัวเลขจากแบบจำลองของแต่ละตำบล ทีละชั่วโมง"),
        t("Practice incidents, marked EX, are assigned to team callsigns.", "เหตุการณ์ฝึกซ้อมที่มีป้าย EX ถูกมอบหมายให้ทีมตามรหัสเรียกขาน"),
        t("People decide. The tool dispatches no one.", "คนเป็นผู้ตัดสินใจ เครื่องมือไม่ได้สั่งการใคร"),
      ],
    },
  ],
  after: [
    {
      from: 0.14, to: 0.62, pause: 0.5, who: "lalita",
      eyebrow: t("06 · Water going down", "06 · น้ำลด"),
      text: t("Saturday 14 September. In the replay, the water is going down.", "วันเสาร์ที่ 14 กันยายน ในภาพจำลองย้อนหลัง น้ำกำลังลด"),
      points: [
        t("The lines on the walls show how high it came in the model.", "รอยบนผนังแสดงว่าน้ำขึ้นสูงแค่ไหนตามแบบจำลอง"),
        t("Practice scenario on her phone: water going down.", "สถานการณ์ฝึกซ้อมในโทรศัพท์ของเธอ: น้ำกำลังลด"),
      ],
    },
    {
      from: 0.7, to: 1.01, pause: 0.97, who: "lalita",
      text: t("Make the plan before you need it: know your walk, and where it gets cut.", "วางแผนไว้ก่อนที่จะต้องใช้: รู้จักทางเดินของคุณ และรู้ว่าจุดไหนจะถูกตัด"),
      points: [
        t("Try the practice scenarios for the example home in the Public app.", "ลองใช้สถานการณ์ฝึกซ้อมของบ้านตัวอย่างในแอปประชาชน"),
        t("Coordinators can replay the same hours in the command exercise.", "ผู้ประสานงานย้อนดูชั่วโมงเดียวกันได้ในแบบฝึกบัญชาการ"),
        t("The people are fictional. The place, the replay and its limits are real.", "ตัวละครเป็นเรื่องสมมุติ แต่สถานที่ ภาพจำลองย้อนหลัง และข้อจำกัดของมันเป็นของจริง"),
      ],
    },
  ],
};

export interface StopCopy {
  page: Text;
  note: Text;
  /** Whose page this is in the story. */
  who: CharacterId;
  href: (language: JourneyLanguage) => string;
  /** On the public app: the tab the page is switched to when the story arrives. */
  tab?: PublicTab;
  continueLabel?: Text;
  /** Shown over the real page while it is open. */
  warning?: Text;
}

export const STOPS: Record<StopId, StopCopy> = {
  public: {
    page: t("Real page · Public app", "หน้าจริง · แอปประชาชน"),
    note: t(
      "Lalita's first look, on a normal day. The app opens on the example home in Mae Sai town, the place of this story.",
      "การเปิดดูครั้งแรกของลลิตาในวันปกติ แอปเปิดที่บ้านตัวอย่างในตัวเมืองแม่สาย ซึ่งเป็นสถานที่ของเรื่องนี้",
    ),
    who: "lalita",
    href: () => "/public/?practice=normal",
    tab: "home",
    continueLabel: t("Continue: rain, and a plan", "ไปต่อ: ฝนตกและแผนรับมือ"),
  },
  "public-prepare": {
    page: t("Real page · Prepare", "หน้าจริง · เตรียมพร้อม"),
    note: t(
      "Lalita's household plan. It stays on this device; nothing is sent. Practice scenario: shallow water on roads.",
      "แผนของครัวเรือนของลลิตา เก็บไว้ในอุปกรณ์นี้ ไม่มีการส่งข้อมูล สถานการณ์ฝึกซ้อม: น้ำตื้นบนถนน",
    ),
    who: "lalita",
    href: () => "/public/?tab=prepare&practice=heads_up",
    tab: "prepare",
    continueLabel: t("Continue: the night", "ไปต่อ: คืนนั้น"),
    warning: t(
      "The SOS tab's buttons open your phone's call or message app with real hotline numbers. The story never uses them.",
      "ปุ่มในแท็บ SOS จะเปิดแอปโทรศัพท์หรือข้อความพร้อมหมายเลขสายด่วนจริง เรื่องราวนี้ไม่ใช้ปุ่มเหล่านั้น",
    ),
  },
  case: {
    page: t("Real page · Case view", "หน้าจริง · หน้าเคส"),
    note: t(
      "Narin's evidence, opened at 12 September 2024, 12:00: the same replay as the story. Historical, reconstructed, low confidence.",
      "หลักฐานของนรินทร์ เปิดที่ 12 กันยายน 2567 เวลา 12:00 น. ภาพจำลองย้อนหลังเดียวกับในเรื่อง ข้อมูลในอดีต สร้างขึ้นใหม่ ความเชื่อมั่นต่ำ",
    ),
    who: "narin",
    href: (language) => `/studio/cases/mae-sai-2024/?t=${STOP_HOURS.case}&lang=${language}`,
    continueLabel: t("Continue: the district", "ไปต่อ: ภาพรวมอำเภอ"),
  },
  command: {
    page: t("Real page · Command exercise", "หน้าจริง · แบบฝึกบัญชาการ"),
    note: t(
      "Pim's planning table, opened at the same hour. An exercise replay for review and coordination: not real-time, not dispatch. Reports saved on this device appear here too.",
      "โต๊ะวางแผนของพิมพ์ เปิดที่ชั่วโมงเดียวกัน การเล่นซ้ำเพื่อฝึกทบทวนและประสานงาน ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่การสั่งการ รายงานที่บันทึกในอุปกรณ์นี้จะแสดงที่นี่ด้วย",
    ),
    who: "pim",
    href: (language) => `/command/?t=${STOP_HOURS.command}&lang=${language}`,
    continueLabel: t("Continue: water going down", "ไปต่อ: น้ำลด"),
  },
};

/** The iframe address for a stop: the real route, untouched. Both public-app stops share one frame at `/public/`. */
export function stopFrameSrc(stop: StopId, language: JourneyLanguage): string {
  return stop === "public-prepare" ? STOPS.public.href(language) : STOPS[stop].href(language);
}

/** The replay clock line for a moment written by `formatMoment` (flood-timeline.ts). */
export function clockText(moment: string, language: JourneyLanguage): string {
  return UI.clock[language].replace("{moment}", moment);
}

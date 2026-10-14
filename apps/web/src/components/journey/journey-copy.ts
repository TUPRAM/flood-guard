import type { ChapterId, SegmentId, StopId } from "@/lib/journey/timeline";

export type JourneyLanguage = "en" | "th";
type Text = Record<JourneyLanguage, string>;
const t = (en: string, th: string): Text => ({ en, th });

/**
 * The story follows three fictional people, each with a reason to use one real FloodGuard page: Lalita (the public
 * app), Narin (the case view) and Pim (the command exercise). Mali and Dao, Lalita's mother and daughter, give her
 * household plan its needs. None of them represents a real person.
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
    role: t("Planning officer · district office", "เจ้าหน้าที่วางแผน · สำนักงานอำเภอ"),
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
  affected: { number: "03", title: t("The road · Narin", "ถนน · นรินทร์") },
  response: { number: "04", title: t("The district · Pim", "ภาพรวมอำเภอ · พิมพ์") },
};

export const UI = {
  title: t("One road.\nThree people.", "ถนนหนึ่งสาย\nคนสามคน"),
  subtitle: t(
    "Lalita looks after her mother and daughter. Narin checks what is known. Pim brings the district together. A fictional story, told through the real FloodGuard pages.",
    "ลลิตาดูแลแม่และลูกสาว นรินทร์ตรวจสอบสิ่งที่รู้แล้ว พิมพ์ประสานภาพรวมของอำเภอ เรื่องสมมุติที่เล่าผ่านหน้า FloodGuard จริง",
  ),
  begin: t("Begin the story", "เริ่มเรื่องราว"),
  skip: t("Skip to the apps", "ข้ามไปที่แอป"),
  scrollHint: t("Scroll, swipe or use the arrow keys", "เลื่อน ปัด หรือใช้ปุ่มลูกศร"),
  illustrative: t(
    "Fictional people in an illustrative scenario · not a real place, not a forecast, not real-time data",
    "ตัวละครสมมุติในสถานการณ์จำลอง · ไม่ใช่สถานที่จริง ไม่ใช่การพยากรณ์ และไม่ใช่ข้อมูลเรียลไทม์",
  ),
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

/** Labels projected onto the 3D scene: places, and the people when the camera is with them. */
export const LABELS: Record<string, Text> = {
  home: t("Lalita's home", "บ้านของลลิตา"),
  clinic: t("Clinic", "คลินิก"),
  connection: t("Usual way to the clinic", "เส้นทางปกติไปคลินิก"),
  crossing: t("Connection potentially affected", "เส้นทางที่อาจได้รับผลกระทบ"),
  operations: t("District office (illustrative)", "สำนักงานอำเภอ (จำลอง)"),
  signal: t("Simulated call to hotline 1784 · nothing dialled", "จำลองการโทรสายด่วน 1784 · ไม่มีการโทรจริง"),
  lalita: t("Lalita", "ลลิตา"),
  mali: t("Mali, her mother", "มะลิ แม่ของเธอ"),
  dao: t("Dao, her daughter", "ดาว ลูกสาวของเธอ"),
  narin: t("Narin", "นรินทร์"),
  pim: t("Pim", "พิมพ์"),
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
 * real page has: the public app's area overview, Prepare (household needs), Shelter (a destination the household has
 * confirmed; the app does not know capacity), Report (saved on the device, sent nowhere) and SOS (official hotlines);
 * the case view's replay and its confidence; the command exercise's hourly table, practice items and trainee mode.
 */
export const CAPTIONS: Record<SegmentId, Caption[]> = {
  opening: [],
  everyday: [
    {
      from: 0.08, to: 0.5, pause: 0.46, who: "lalita", meet: true,
      eyebrow: t("01 · Meet Lalita", "01 · พบกับลลิตา"),
      text: t(
        "This is Lalita's street. She lives here with her mother, Mali, and her eight-year-old daughter, Dao.",
        "นี่คือถนนบ้านของลลิตา เธออาศัยอยู่กับมะลิ แม่ของเธอ และดาว ลูกสาววัยแปดขวบ",
      ),
      points: [
        t("Mali has regular appointments at the clinic down the road.", "มะลิต้องไปพบแพทย์ที่คลินิกปลายถนนเป็นประจำ"),
        t("Lalita takes Dao to school and Mali to her appointments.", "ลลิตาเป็นคนพาดาวไปโรงเรียนและพามะลิไปหาหมอ"),
        t("The teal line is their usual way to the clinic.", "เส้นสีเขียวอมฟ้าคือเส้นทางปกติไปคลินิก"),
      ],
    },
    {
      from: 0.55, to: 1.01, pause: 0.985, who: "lalita",
      text: t(
        "Heavy rain is expected. Before the rumours start, Lalita checks what is known about her area.",
        "คาดว่าจะมีฝนตกหนัก ก่อนข่าวลือจะเริ่ม ลลิตาตรวจดูว่ามีข้อมูลอะไรเกี่ยวกับพื้นที่ของเธอบ้าง",
      ),
      points: [
        t("She opens the FloodGuard public app.", "เธอเปิดแอป FloodGuard สำหรับประชาชน"),
        t("It helps her prepare. It is not an official warning.", "แอปช่วยให้เธอเตรียมพร้อม แต่ไม่ใช่การแจ้งเตือนทางการ"),
      ],
    },
  ],
  "enter-phone": [
    {
      from: 0.55, to: 1.01, pause: 0.92, who: "lalita",
      text: t("This is the real public app: what Lalita sees on her phone.", "นี่คือแอปสำหรับประชาชนจริง สิ่งที่ลลิตาเห็นบนโทรศัพท์"),
      points: [
        t("She chooses a planning area, or searches for an address.", "เธอเลือกพื้นที่วางแผน หรือค้นหาที่อยู่"),
        t("It shows a historical planning priority, with its date and confidence.", "แอปแสดงลำดับความสำคัญจากข้อมูลในอดีต พร้อมวันที่และระดับความเชื่อมั่น"),
        t("A historical priority is not a prediction that her street will flood.", "ลำดับความสำคัญจากอดีตไม่ใช่การทำนายว่าถนนของเธอจะน้ำท่วม"),
      ],
    },
  ],
  conditions: [
    {
      from: 0.12, to: 0.55, pause: 0.53, who: "lalita",
      eyebrow: t("02 · Rain, and a plan", "02 · ฝนตกและแผนรับมือ"),
      text: t("The rain sets in. The channel rises and low ground begins to pond.", "ฝนเริ่มตกหนัก ระดับน้ำในลำน้ำสูงขึ้น และพื้นที่ต่ำเริ่มมีน้ำขัง"),
      points: [
        t("Water collects first where the ground is lowest.", "น้ำขังที่จุดต่ำที่สุดก่อน"),
        t("Lalita's house stands on higher ground and stays dry.", "บ้านของลลิตาตั้งอยู่บนที่สูงและยังแห้ง"),
        t("An illustrative scenario, not a forecast.", "เป็นสถานการณ์จำลอง ไม่ใช่การพยากรณ์"),
      ],
    },
    {
      from: 0.6, to: 1.01, pause: 0.95, who: "lalita",
      text: t(
        "The road is still dry. But it dips through the lowest ground, on Mali's way to the clinic.",
        "ถนนยังแห้งอยู่ แต่ถนนลาดต่ำผ่านพื้นที่ที่ต่ำที่สุด บนทางที่มะลิใช้ไปคลินิก",
      ),
      points: [
        t("If that stretch floods, the clinic is cut off from the house.", "ถ้าถนนช่วงนั้นน้ำท่วม บ้านจะไปคลินิกไม่ได้"),
        t("Lalita cannot control the weather.", "ลลิตาควบคุมสภาพอากาศไม่ได้"),
        t("She can make a plan before she needs one.", "แต่เธอวางแผนไว้ก่อนที่จะต้องใช้ได้"),
      ],
    },
  ],
  "return-phone": [
    {
      from: 0.28, to: 0.58, pause: 0.45, who: "lalita",
      text: t(
        "Lalita talks it through with Mali and Dao: what to pack, who helps whom, where they could go.",
        "ลลิตาคุยกับมะลิและดาวว่าต้องเตรียมอะไร ใครช่วยใคร และจะไปที่ไหนได้บ้าง",
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
  "sos-signal": [
    {
      from: 0.0, to: 0.2, pause: 0.06, who: "lalita",
      eyebrow: t("03 · The road", "03 · ถนน"),
      text: t("Lalita notes what she sees in Report: water in the low part of the road.", "ลลิตาบันทึกสิ่งที่เห็นในแท็บรายงาน: น้ำเริ่มท่วมถนนช่วงที่ต่ำ"),
      points: [
        t("The note stays on her phone. FloodGuard sends it nowhere.", "บันทึกนี้อยู่ในโทรศัพท์ของเธอ FloodGuard ไม่ได้ส่งไปที่ใด"),
        t("Asking for help goes through official channels.", "การขอความช่วยเหลือต้องผ่านช่องทางทางการ"),
      ],
    },
    {
      from: 0.22, to: 0.5, pause: 0.47, who: "lalita",
      text: t(
        "Now the water crosses the road. Lalita's home and the clinic stay dry; the way between them does not.",
        "ตอนนี้น้ำท่วมข้ามถนนแล้ว บ้านของลลิตาและคลินิกยังแห้ง แต่ทางระหว่างกันไม่ได้แห้ง",
      ),
      points: [
        t("Both buildings stand on higher ground.", "อาคารทั้งสองตั้งอยู่บนที่สูง"),
        t("The low stretch of road between them is under water.", "ถนนช่วงต่ำระหว่างทั้งสองจมน้ำ"),
        t("Lost access, not only flooding, is what FloodGuard looks at.", "FloodGuard ดูการเข้าถึงที่ขาดหาย ไม่ใช่แค่น้ำท่วม"),
      ],
    },
    {
      from: 0.52, to: 0.84, pause: 0.72, who: "lalita",
      text: t(
        "Mali needs to see her doctor. Lalita calls the official hotline, 1784, to ask how to get her there.",
        "มะลิต้องไปพบแพทย์ ลลิตาโทรหาสายด่วนทางการ 1784 เพื่อถามว่าจะพาแม่ไปได้อย่างไร",
      ),
      points: [
        t("Story mode: the call is simulated. Nothing is dialled.", "โหมดเรื่องราว: เป็นการจำลอง ไม่มีการโทรจริง"),
        t("The call goes through the hotline, not through FloodGuard.", "สายนี้ผ่านสายด่วน ไม่ได้ผ่าน FloodGuard"),
        t("In this story, requests like hers reach the district office.", "ในเรื่องนี้ คำขอแบบเดียวกับของเธอส่งต่อมาถึงสำนักงานอำเภอ"),
      ],
    },
    {
      from: 0.88, to: 1.01, pause: 0.985, who: "narin", meet: true,
      eyebrow: t("Meet Narin", "พบกับนรินทร์"),
      text: t(
        "Narin is a planning officer at the district office. Calls like Lalita's are part of what he has to make sense of.",
        "นรินทร์เป็นเจ้าหน้าที่วางแผนที่สำนักงานอำเภอ สายแบบเดียวกับของลลิตาเป็นส่วนหนึ่งของสิ่งที่เขาต้องทำความเข้าใจ",
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
        "Narin opens the case view: a real, past flood in Mae Sai, September 2024. It is not Lalita's street.",
        "นรินทร์เปิดหน้าเคส: น้ำท่วมจริงในอดีตที่แม่สาย กันยายน 2024 ไม่ใช่ถนนของลลิตา",
      ),
      points: [
        t("He replays it day by day, with dated satellite images.", "เขาย้อนดูทีละวัน พร้อมภาพดาวเทียมที่ระบุวันที่"),
        t("Modelled water, roads, facilities and residents in water, each marked low confidence.", "น้ำ ถนน สถานบริการ และผู้อยู่อาศัยในน้ำจากแบบจำลอง ทั้งหมดระบุว่าความเชื่อมั่นต่ำ"),
        t("Who could walk to a shelter, and who could not: the equity gap.", "ใครเดินไปถึงที่พักพิงได้ และใครไปไม่ถึง: ช่องว่างความเท่าเทียม"),
      ],
    },
  ],
  aerial: [
    {
      from: 0.14, to: 0.3, pause: 0.22, who: "pim", meet: true,
      eyebrow: t("04 · Meet Pim", "04 · พบกับพิมพ์"),
      text: t(
        "Pim coordinates planning for the district. Narin's evidence is one input; she has many communities to think about.",
        "พิมพ์ประสานงานการวางแผนของอำเภอ หลักฐานของนรินทร์เป็นข้อมูลส่วนหนึ่ง เธอต้องคิดถึงหลายชุมชน",
      ),
      points: [
        t("Her job is to organise the discussion, not to hand it to a computer.", "งานของเธอคือจัดการการหารือ ไม่ใช่ปล่อยให้คอมพิวเตอร์ตัดสินใจ"),
        t("She brings the team round the planning table.", "เธอชวนทีมมารวมกันที่โต๊ะวางแผน"),
      ],
    },
    {
      from: 0.38, to: 0.7, pause: 0.6, who: "pim",
      text: t(
        "From above, Lalita's road is one of many links between people and the services they need.",
        "เมื่อมองจากด้านบน ถนนของลลิตาเป็นเพียงหนึ่งในหลายเส้นทางที่เชื่อมผู้คนกับบริการที่จำเป็น",
      ),
      points: [
        t("Every household–service link can be checked the same way.", "ทุกเส้นทางระหว่างครัวเรือนกับบริการตรวจได้ด้วยวิธีเดียวกัน"),
        t("Cut links show where help may not get through.", "เส้นทางที่ขาดชี้ว่าความช่วยเหลืออาจไปไม่ถึงที่ใด"),
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
};

/** The public app's tabs a stop can open on (the app's own bottom navigation). */
export type PublicTab = "home" | "prepare";

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
      "Lalita's first look. The app's data covers Mae Sai district; her street in this story is illustrated.",
      "การเปิดดูครั้งแรกของลลิตา ข้อมูลในแอปครอบคลุมอำเภอแม่สาย ส่วนถนนของเธอในเรื่องนี้เป็นภาพจำลอง",
    ),
    who: "lalita",
    href: () => "/public/",
    tab: "home",
    continueLabel: t("Continue: rain, and a plan", "ไปต่อ: ฝนตกและแผนรับมือ"),
  },
  "public-prepare": {
    page: t("Real page · Prepare", "หน้าจริง · เตรียมพร้อม"),
    note: t("Lalita's household plan. It stays on this device; nothing is sent.", "แผนของครัวเรือนของลลิตา เก็บไว้ในอุปกรณ์นี้ ไม่มีการส่งข้อมูล"),
    who: "lalita",
    href: () => "/public/?tab=prepare",
    tab: "prepare",
    continueLabel: t("Continue: the road", "ไปต่อ: ถนน"),
    warning: t(
      "The SOS tab's buttons open your phone's call or message app with real hotline numbers. The story never uses them.",
      "ปุ่มในแท็บ SOS จะเปิดแอปโทรศัพท์หรือข้อความพร้อมหมายเลขสายด่วนจริง เรื่องราวนี้ไม่ใช้ปุ่มเหล่านั้น",
    ),
  },
  case: {
    page: t("Real page · Case view", "หน้าจริง · หน้าเคส"),
    note: t(
      "Narin's evidence. Mae Sai, September 2024: historical, reconstructed, low confidence. Not the illustrated street.",
      "หลักฐานของนรินทร์ แม่สาย กันยายน 2024: ข้อมูลในอดีต สร้างขึ้นใหม่ ความเชื่อมั่นต่ำ ไม่ใช่ถนนในภาพจำลอง",
    ),
    who: "narin",
    href: (language) => `/studio/cases/mae-sai-2024/?lang=${language}`,
    continueLabel: t("Continue: the district", "ไปต่อ: ภาพรวมอำเภอ"),
  },
  command: {
    page: t("Real page · Command exercise", "หน้าจริง · แบบฝึกบัญชาการ"),
    note: t(
      "Pim's planning table. An exercise replay for review and coordination: not real-time, not dispatch. Reports saved on this device appear here too.",
      "โต๊ะวางแผนของพิมพ์ การเล่นซ้ำเพื่อฝึกทบทวนและประสานงาน ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่การสั่งการ รายงานที่บันทึกในอุปกรณ์นี้จะแสดงที่นี่ด้วย",
    ),
    who: "pim",
    href: (language) => `/command/?t=36&lang=${language}`,
  },
};

/** The iframe address for a stop: the real route, untouched. Both public-app stops share one frame at `/public/`. */
export function stopFrameSrc(stop: StopId, language: JourneyLanguage): string {
  return stop === "public-prepare" ? STOPS.public.href(language) : STOPS[stop].href(language);
}

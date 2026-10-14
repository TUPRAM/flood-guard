import type { ChapterId, SegmentId, StopId } from "@/lib/journey/timeline";

export type JourneyLanguage = "en" | "th";
type Text = Record<JourneyLanguage, string>;
const t = (en: string, th: string): Text => ({ en, th });

export const CHAPTER_LABELS: Record<ChapterId, { number: string; title: Text }> = {
  opening: { number: "", title: t("Opening", "เริ่มต้น") },
  everyday: { number: "01", title: t("Everyday connections", "การเชื่อมต่อในชีวิตประจำวัน") },
  conditions: { number: "02", title: t("Conditions change", "สถานการณ์เปลี่ยนไป") },
  affected: { number: "03", title: t("Connections affected", "การเชื่อมต่อได้รับผลกระทบ") },
  response: { number: "04", title: t("Coordinated response", "การประสานงานรับมือ") },
};

export const UI = {
  title: t("See the flood.\nUnderstand what it changes.", "เห็นน้ำท่วม\nเข้าใจสิ่งที่เปลี่ยนไป"),
  subtitle: t(
    "Follow one household, one road and one clinic — from a phone in someone's hand to a team reviewing what needs attention.",
    "ติดตามบ้านหนึ่งหลัง ถนนหนึ่งสาย และคลินิกหนึ่งแห่ง ตั้งแต่โทรศัพท์ในมือของคนคนหนึ่ง จนถึงทีมที่ทบทวนสิ่งที่ต้องดูแล",
  ),
  begin: t("Begin the story", "เริ่มเรื่องราว"),
  skip: t("Skip to the apps", "ข้ามไปที่แอป"),
  scrollHint: t("Scroll, swipe or use the arrow keys", "เลื่อน ปัด หรือใช้ปุ่มลูกศร"),
  illustrative: t(
    "Illustrative scenario · not a real place, forecast or live data",
    "สถานการณ์จำลองเพื่ออธิบาย · ไม่ใช่สถานที่จริง การพยากรณ์ หรือข้อมูลสด",
  ),
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

export const LABELS: Record<string, Text> = {
  home: t("Home", "บ้าน"),
  clinic: t("Clinic", "คลินิก"),
  connection: t("Usual connection", "เส้นทางปกติ"),
  crossing: t("Connection potentially affected", "เส้นทางที่อาจได้รับผลกระทบ"),
  operations: t("Operations room (illustrative)", "ห้องปฏิบัติการ (จำลอง)"),
  signal: t("Simulated SOS · nothing sent", "SOS จำลอง · ไม่มีการส่งจริง"),
};

export interface Caption {
  from: number;
  to: number;
  eyebrow?: Text;
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

/** Captions over the 3D scene: [start, end) progress ranges within a segment. */
export const CAPTIONS: Record<SegmentId, Caption[]> = {
  opening: [],
  everyday: [
    {
      from: 0.08, to: 0.5, pause: 0.46,
      eyebrow: t("01 · Everyday connections", "01 · การเชื่อมต่อในชีวิตประจำวัน"),
      text: t("A home and a clinic are linked by the same local road.", "บ้านและคลินิกเชื่อมกันด้วยถนนสายเดียวกันในชุมชน"),
      points: [
        t("The household relies on this road to reach care.", "ครัวเรือนนี้ต้องใช้ถนนสายนี้เพื่อไปรับการรักษา"),
        t("The teal line is their usual route to the clinic.", "เส้นสีเขียวอมฟ้าคือเส้นทางปกติไปคลินิก"),
        t("An illustrated neighbourhood, not a real place.", "ชุมชนนี้เป็นภาพจำลอง ไม่ใช่สถานที่จริง"),
      ],
    },
    {
      from: 0.55, to: 1.01, pause: 0.985,
      text: t("Every day, people check what is happening nearby — on their phone.", "ทุกวัน ผู้คนตรวจดูสิ่งที่เกิดขึ้นรอบตัวผ่านโทรศัพท์"),
      points: [
        t("The FloodGuard public app shows the area around them.", "แอป FloodGuard สำหรับประชาชนแสดงพื้นที่รอบตัว"),
        t("It explains how to prepare and where the shelters are.", "แอปบอกวิธีเตรียมพร้อมและที่ตั้งของที่พักพิง"),
        t("It is a preparedness tool, not an official warning.", "เป็นเครื่องมือเตรียมความพร้อม ไม่ใช่การแจ้งเตือนทางการ"),
      ],
    },
  ],
  "enter-phone": [
    {
      from: 0.55, to: 1.01, pause: 0.92,
      text: t("This is the real FloodGuard public app.", "นี่คือแอป FloodGuard สำหรับประชาชนจริง"),
      points: [
        t("The same app a resident would open — live and interactive.", "เป็นแอปเดียวกับที่ประชาชนใช้ ใช้งานได้จริง"),
        t("Search a place to see its historical planning priority.", "ค้นหาพื้นที่เพื่อดูลำดับความสำคัญจากข้อมูลในอดีต"),
        t("Every figure shows its date and confidence.", "ทุกตัวเลขแสดงวันที่และระดับความเชื่อมั่น"),
      ],
    },
  ],
  conditions: [
    {
      from: 0.12, to: 0.55, pause: 0.53,
      eyebrow: t("02 · Conditions change", "02 · สถานการณ์เปลี่ยนไป"),
      text: t("The channel rises and low ground begins to pond.", "ระดับน้ำในลำน้ำสูงขึ้น และพื้นที่ต่ำเริ่มมีน้ำขัง"),
      points: [
        t("Heavy rain fills the channel and the low swale.", "ฝนตกหนักทำให้น้ำเต็มลำน้ำและร่องน้ำที่ต่ำ"),
        t("Water collects first where the ground is lowest.", "น้ำขังที่จุดต่ำที่สุดก่อน"),
        t("An illustrative scenario, not a forecast.", "เป็นสถานการณ์จำลอง ไม่ใช่การพยากรณ์"),
      ],
    },
    {
      from: 0.6, to: 1.01, pause: 0.95,
      text: t("The road is still dry — for now. Which places might need attention?", "ถนนยังแห้งอยู่ในตอนนี้ แล้วพื้นที่ใดที่อาจต้องเฝ้าระวัง"),
      points: [
        t("The usual route still works today.", "เส้นทางปกติยังใช้ได้ในตอนนี้"),
        t("But it dips through the lowest ground near the swale.", "แต่ถนนลาดต่ำผ่านพื้นที่ต่ำที่สุดใกล้ร่องน้ำ"),
        t("Planning asks: who depends on that stretch?", "การวางแผนจึงถามว่า ใครต้องพึ่งถนนช่วงนั้น"),
      ],
    },
  ],
  "return-phone": [
    {
      from: 0.25, to: 1.01, pause: 0.92,
      text: t("Back on the phone: prepare, check shelters, or ask for help.", "กลับมาที่โทรศัพท์: เตรียมพร้อม ดูที่พักพิง หรือขอความช่วยเหลือ"),
      points: [
        t("A household plan and shelter information are one tap away.", "แผนของครัวเรือนและข้อมูลที่พักพิงเปิดได้ในแตะเดียว"),
        t("Official contacts are listed in the app.", "แอปมีช่องทางติดต่อหน่วยงานทางการ"),
        t("In this story the SOS is simulated — nothing is sent.", "ในเรื่องนี้ SOS เป็นการจำลอง ไม่มีการส่งจริง"),
      ],
    },
  ],
  "sos-signal": [
    {
      from: 0.0, to: 0.2, pause: 0.06,
      eyebrow: t("03 · Connections affected", "03 · การเชื่อมต่อได้รับผลกระทบ"),
      text: t("Story mode: a simulated SOS. Nothing real is sent.", "โหมดเรื่องราว: SOS จำลอง ไม่มีการส่งจริง"),
      points: [
        t("No call, message or report leaves this page.", "ไม่มีการโทร ข้อความ หรือรายงานใดออกจากหน้านี้"),
        t("It stands in for a household asking for help.", "เป็นการจำลองครัวเรือนที่ขอความช่วยเหลือ"),
      ],
    },
    {
      from: 0.22, to: 0.5, pause: 0.47,
      text: t("The water now crosses the usual road. The home and the clinic stay dry — the connection between them does not.", "ตอนนี้น้ำท่วมข้ามถนนสายปกติ บ้านและคลินิกยังแห้ง แต่เส้นทางระหว่างกันไม่ได้แห้ง"),
      points: [
        t("Both buildings stand on higher ground.", "อาคารทั้งสองตั้งอยู่บนที่สูง"),
        t("The low stretch of road between them is under water.", "ถนนช่วงต่ำระหว่างทั้งสองจมน้ำ"),
        t("Losing access, not only flooding, is what FloodGuard measures.", "FloodGuard วัดการเข้าถึงที่ขาดหาย ไม่ใช่แค่น้ำท่วม"),
      ],
    },
    {
      from: 0.52, to: 0.84, pause: 0.72,
      text: t("The simulated alert reaches an operations room (illustrative).", "การแจ้งเตือนจำลองไปถึงห้องปฏิบัติการ (จำลอง)"),
      points: [
        t("A team that plans and coordinates the local response.", "ทีมที่วางแผนและประสานการรับมือในพื้นที่"),
        t("They see requests alongside what the map shows.", "ทีมเห็นคำขอความช่วยเหลือควบคู่กับข้อมูลบนแผนที่"),
      ],
    },
    {
      from: 0.88, to: 1.01, pause: 0.985,
      text: t("A responder opens a case to review what is known — and what is not.", "เจ้าหน้าที่เปิดเคสเพื่อทบทวนสิ่งที่รู้และสิ่งที่ยังไม่รู้"),
      points: [
        t("Evidence comes with its time stamp and confidence.", "หลักฐานทุกชิ้นมีเวลาและระดับความเชื่อมั่น"),
        t("Gaps in the data are shown, not hidden.", "ช่องว่างของข้อมูลถูกแสดง ไม่ถูกซ่อน"),
      ],
    },
  ],
  "enter-monitor": [
    {
      from: 0.4, to: 1.01, pause: 0.93,
      text: t("This is the real FloodGuard case view — a separate, historical Mae Sai 2024 case, not this illustrated street.", "นี่คือหน้าเคส FloodGuard จริง เป็นเคสแม่สายปี 2024 ในอดีตที่แยกต่างหาก ไม่ใช่ถนนในภาพจำลองนี้"),
      points: [
        t("Replay September 2024 hour by hour.", "ย้อนดูเหตุการณ์เดือนกันยายน 2024 ทีละชั่วโมง"),
        t("Reconstructed for learning: not real time, not an official warning.", "สร้างขึ้นใหม่เพื่อการเรียนรู้ ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่การแจ้งเตือนทางการ"),
      ],
    },
  ],
  aerial: [
    {
      from: 0.3, to: 0.62, pause: 0.6,
      eyebrow: t("04 · Coordinated response", "04 · การประสานงานรับมือ"),
      text: t("From one household's question to the wider picture: which connections need review?", "จากคำถามของบ้านหนึ่งหลัง สู่ภาพรวม: เส้นทางใดที่ต้องทบทวน"),
      points: [
        t("Every household–service link can be checked the same way.", "ทุกเส้นทางระหว่างครัวเรือนกับบริการตรวจได้ด้วยวิธีเดียวกัน"),
        t("Cut connections show where help may not get through.", "เส้นทางที่ขาดชี้ว่าความช่วยเหลืออาจไปไม่ถึงที่ใด"),
      ],
    },
    {
      from: 0.66, to: 1.01, pause: 0.95,
      text: t("The team reviews options together — review and coordination, not automatic dispatch.", "ทีมทบทวนทางเลือกร่วมกัน เป็นการทบทวนและประสานงาน ไม่ใช่การสั่งการอัตโนมัติ"),
      points: [
        t("Priorities are a starting point for discussion.", "ลำดับความสำคัญเป็นจุดเริ่มต้นของการหารือ"),
        t("People decide; the tool does not dispatch anyone.", "คนเป็นผู้ตัดสินใจ เครื่องมือไม่ได้สั่งการใคร"),
      ],
    },
  ],
};

export interface StopCopy {
  page: Text;
  note: Text;
  href: (language: JourneyLanguage) => string;
  continueLabel?: Text;
  warning?: Text;
}

export const STOPS: Record<StopId, StopCopy> = {
  public: {
    page: t("Real page · Public app", "หน้าจริง · แอปประชาชน"),
    note: t("Live and interactive. Explore it, then continue the story.", "ใช้งานได้จริง ลองสำรวจ แล้วไปต่อในเรื่องราว"),
    href: () => "/public/",
    continueLabel: t("Continue: conditions change", "ไปต่อ: สถานการณ์เปลี่ยนไป"),
  },
  "public-sos": {
    page: t("Real page · Public app", "หน้าจริง · แอปประชาชน"),
    note: t("Prepare a household plan, check shelters, read official contacts.", "เตรียมแผนครัวเรือน ดูที่พักพิง อ่านช่องทางติดต่อทางการ"),
    href: () => "/public/",
    continueLabel: t("Simulate SOS (story mode)", "จำลอง SOS (โหมดเรื่องราว)"),
  },
  case: {
    page: t("Real page · Case view", "หน้าจริง · หน้าเคส"),
    note: t("Mae Sai, September 2024: historical, reconstructed, low confidence. Not the illustrated street.", "แม่สาย กันยายน 2024: ข้อมูลในอดีต สร้างขึ้นใหม่ ความเชื่อมั่นต่ำ ไม่ใช่ถนนในภาพจำลอง"),
    href: (language) => `/studio/cases/mae-sai-2024/?lang=${language}`,
    continueLabel: t("Continue: coordinated response", "ไปต่อ: การประสานงานรับมือ"),
  },
  command: {
    page: t("Real page · Command exercise", "หน้าจริง · แบบฝึกบัญชาการ"),
    note: t("An exercise replay for review and coordination — not real-time, not dispatch.", "การเล่นซ้ำเพื่อฝึกทบทวนและประสานงาน ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่การสั่งการ"),
    href: (language) => `/command/?t=36&lang=${language}`,
  },
};

/** The iframe address for a stop: the real route, untouched. */
export function stopFrameSrc(stop: StopId, language: JourneyLanguage): string {
  return STOPS[stop].href(language);
}

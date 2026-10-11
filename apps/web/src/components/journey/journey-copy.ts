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
  reduceMotion: t("Reduce motion", "ลดการเคลื่อนไหว"),
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

/** Short captions over the 3D scene: [start, end) progress ranges within a segment. */
export const CAPTIONS: Record<SegmentId, Array<{ from: number; to: number; eyebrow?: Text; text: Text }>> = {
  opening: [],
  everyday: [
    { from: 0.08, to: 0.5, eyebrow: t("01 · Everyday connections", "01 · การเชื่อมต่อในชีวิตประจำวัน"), text: t("A home and a clinic are linked by the same local road.", "บ้านและคลินิกเชื่อมกันด้วยถนนสายเดียวกันในชุมชน") },
    { from: 0.55, to: 1.01, text: t("Every day, people check what is happening nearby — on their phone.", "ทุกวัน ผู้คนตรวจดูสิ่งที่เกิดขึ้นรอบตัวผ่านโทรศัพท์") },
  ],
  "enter-phone": [{ from: 0.55, to: 1.01, text: t("This is the real FloodGuard public app.", "นี่คือแอป FloodGuard สำหรับประชาชนจริง") }],
  conditions: [
    { from: 0.12, to: 0.55, eyebrow: t("02 · Conditions change", "02 · สถานการณ์เปลี่ยนไป"), text: t("The channel rises and low ground begins to pond.", "ระดับน้ำในลำน้ำสูงขึ้น และพื้นที่ต่ำเริ่มมีน้ำขัง") },
    { from: 0.6, to: 1.01, text: t("The road is still dry — for now. Which places might need attention?", "ถนนยังแห้งอยู่ในตอนนี้ แล้วพื้นที่ใดที่อาจต้องเฝ้าระวัง") },
  ],
  "return-phone": [{ from: 0.25, to: 1.01, text: t("Back on the phone: prepare, check shelters, or ask for help.", "กลับมาที่โทรศัพท์: เตรียมพร้อม ดูที่พักพิง หรือขอความช่วยเหลือ") }],
  "sos-signal": [
    { from: 0.0, to: 0.16, eyebrow: t("03 · Connections affected", "03 · การเชื่อมต่อได้รับผลกระทบ"), text: t("Story mode: a simulated SOS. Nothing real is sent.", "โหมดเรื่องราว: SOS จำลอง ไม่มีการส่งจริง") },
    { from: 0.2, to: 0.5, text: t("The water now crosses the usual road. The home and the clinic stay dry — the connection between them does not.", "ตอนนี้น้ำท่วมข้ามถนนสายปกติ บ้านและคลินิกยังแห้ง แต่เส้นทางระหว่างกันไม่ได้แห้ง") },
    { from: 0.52, to: 0.84, text: t("The simulated alert reaches an operations room (illustrative).", "การแจ้งเตือนจำลองไปถึงห้องปฏิบัติการ (จำลอง)") },
    { from: 0.88, to: 1.01, text: t("A responder opens a case to review what is known — and what is not.", "เจ้าหน้าที่เปิดเคสเพื่อทบทวนสิ่งที่รู้และสิ่งที่ยังไม่รู้") },
  ],
  "enter-monitor": [
    { from: 0.4, to: 1.01, text: t("This is the real FloodGuard case view — a separate, historical Mae Sai 2024 case, not this illustrated street.", "นี่คือหน้าเคส FloodGuard จริง เป็นเคสแม่สายปี 2024 ในอดีตที่แยกต่างหาก ไม่ใช่ถนนในภาพจำลองนี้") },
  ],
  aerial: [
    { from: 0.3, to: 0.62, eyebrow: t("04 · Coordinated response", "04 · การประสานงานรับมือ"), text: t("From one household's question to the wider picture: which connections need review?", "จากคำถามของบ้านหนึ่งหลัง สู่ภาพรวม: เส้นทางใดที่ต้องทบทวน") },
    { from: 0.66, to: 1.01, text: t("The team reviews options together — review and coordination, not automatic dispatch.", "ทีมทบทวนทางเลือกร่วมกัน เป็นการทบทวนและประสานงาน ไม่ใช่การสั่งการอัตโนมัติ") },
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
    warning: t(
      "The app's SOS tab places real phone calls. For the story, use the simulated SOS — nothing is sent.",
      "แท็บ SOS ในแอปจะโทรออกจริง สำหรับเรื่องราวนี้ ให้ใช้ SOS จำลอง ซึ่งไม่มีการส่งใดๆ",
    ),
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

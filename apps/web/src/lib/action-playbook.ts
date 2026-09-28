/**
 * What each FPPS action class asks of responders and residents, step by step through a flood.
 *
 * The one-line headline per class is the project's canonical recommended action (`floodguard.briefs.RECOMMENDED_ACTIONS`
 * and `THAI_RECOMMENDED_ACTIONS`); `action-playbook.test.ts` checks it word for word against the parity fixture. The
 * steps expand that line into three stages — before the water arrives, while it is high, and as it recedes — so a
 * reader sees what comes next, not only what to do now. This is planning guidance for a preparedness tool: it is not an
 * official warning, and residents follow instructions from the district office and the Department of Disaster
 * Prevention and Mitigation (DDPM).
 */

import type { ActionClass } from "@floodguard/contracts";

export type Localized = { en: string; th: string };
export type PlaybookStage = "before" | "during" | "after";
export const PLAYBOOK_STAGES: readonly PlaybookStage[] = ["before", "during", "after"];

export interface StageActions {
  responders: readonly Localized[];
  residents: readonly Localized[];
}

export interface ClassPlaybook {
  name: Localized;
  /** When the class applies (the `assign_action_class` rule in words). */
  when: Localized;
  /** Canonical recommended action from `floodguard.briefs`. */
  headline: Localized;
  stages: Record<PlaybookStage, StageActions>;
}

export const STAGE_LABELS: Record<PlaybookStage, Localized> = {
  before: { en: "Before the water arrives", th: "ก่อนน้ำมา" },
  during: { en: "While the water is high", th: "ขณะน้ำสูง" },
  after: { en: "As the water recedes", th: "เมื่อน้ำลด" },
};

/** Replay phase id → playbook stage: dry is before, onset and peak are during, receding and receded are after. */
export function stageForPhase(phaseId: string | null | undefined): PlaybookStage {
  if (phaseId === "onset" || phaseId === "peak") return "during";
  if (phaseId === "receding" || phaseId === "gone") return "after";
  return "before";
}

const l = (en: string, th: string): Localized => ({ en, th });

/** Resident lines every class shares: the official channels come first. */
const FOLLOW_OFFICIAL = l(
  "Follow warnings and evacuation orders from the district office and DDPM (hotline 1784); this page is not a warning.",
  "ปฏิบัติตามคำเตือนและคำสั่งอพยพจากที่ว่าการอำเภอและกรมป้องกันและบรรเทาสาธารณภัย (สายด่วน 1784) หน้านี้ไม่ใช่การแจ้งเตือน",
);

export const ACTION_PLAYBOOK: Record<ActionClass, ClassPlaybook> = {
  A: {
    name: l("Protect Lives Now", "ปกป้องชีวิตทันที"),
    when: l(
      "Exposure 70+ and access gap 70+: many people are in the water and most of them cannot walk to a dry shelter.",
      "การสัมผัสน้ำท่วม 70+ และช่องว่างการเข้าถึง 70+: มีผู้คนจำนวนมากอยู่ในน้ำ และส่วนใหญ่เดินไปที่พักพิงที่แห้งไม่ได้",
    ),
    headline: l(
      "Pre-position rescue assets, open shelters, issue targeted warnings, and coordinate medical continuity.",
      "จัดเตรียมกำลังช่วยเหลือ เปิดศูนย์พักพิง ส่งคำเตือนเฉพาะพื้นที่ และประสานความต่อเนื่องทางการแพทย์",
    ),
    stages: {
      before: {
        responders: [
          l("Stage boats and rescue teams at the edge of the expected flood zone, not inside it.", "จัดวางเรือและทีมกู้ภัยที่ขอบพื้นที่ที่คาดว่าน้ำจะท่วม ไม่ใช่ภายในพื้นที่"),
          l("Open and stock the dry shelters nearest the people at risk: water, food, bedding, toilets, power.", "เปิดและเตรียมศูนย์พักพิงที่แห้งใกล้ผู้เสี่ยงภัยที่สุด: น้ำ อาหาร เครื่องนอน ห้องน้ำ ไฟฟ้า"),
          l("List bedridden, elderly and disabled residents and assign who moves each of them first.", "ทำรายชื่อผู้ป่วยติดเตียง ผู้สูงอายุ และผู้พิการ และกำหนดผู้รับผิดชอบเคลื่อนย้ายแต่ละคนก่อน"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Pack a go-bag: medicines, ID and documents in a waterproof bag, phone and charger, water, torch.", "เตรียมกระเป๋าฉุกเฉิน: ยา บัตรประชาชนและเอกสารในถุงกันน้ำ โทรศัพท์และที่ชาร์จ น้ำดื่ม ไฟฉาย"),
          l("Know your nearest dry shelter and the route to it; if you need help to move, leave early.", "รู้ที่ตั้งศูนย์พักพิงที่แห้งใกล้บ้านและเส้นทางไป หากต้องมีคนช่วยเคลื่อนย้าย ให้ออกเดินทางแต่เนิ่น ๆ"),
        ],
      },
      during: {
        responders: [
          l("Rescue by boat where roads are cut, starting with people who cannot walk out.", "ช่วยเหลือด้วยเรือในจุดที่ถนนถูกตัดขาด เริ่มจากผู้ที่เดินออกมาเองไม่ได้"),
          l("Warn door to door and by loudspeaker in the streets the model shows filling first.", "แจ้งเตือนแบบเคาะประตูบ้านและใช้เครื่องขยายเสียงในถนนที่แบบจำลองแสดงว่าน้ำท่วมก่อน"),
          l("Keep patients who depend on power, oxygen or dialysis in care; move them before access is lost.", "ดูแลผู้ป่วยที่ต้องพึ่งไฟฟ้า ออกซิเจน หรือการฟอกไต ให้ได้รับการรักษาต่อเนื่อง และย้ายก่อนเส้นทางถูกตัดขาด"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("If you cannot reach a shelter, go to the highest floor or high ground and signal for help.", "หากไปศูนย์พักพิงไม่ได้ ให้ขึ้นชั้นบนสุดหรือที่สูง และส่งสัญญาณขอความช่วยเหลือ"),
          l("Do not walk or drive through flood water. Switch off electricity at the main if it is safe to reach.", "อย่าเดินหรือขับรถผ่านน้ำท่วม ปิดสะพานไฟหลักหากเข้าถึงได้อย่างปลอดภัย"),
          l("Call 1784 (DDPM) or 1669 (medical emergency) for rescue.", "โทร 1784 (ปภ.) หรือ 1669 (เจ็บป่วยฉุกเฉิน) เพื่อขอความช่วยเหลือ"),
        ],
      },
      after: {
        responders: [
          l("Account for everyone evacuated or rescued, and reunite families.", "ตรวจสอบรายชื่อผู้อพยพและผู้ได้รับการช่วยเหลือทุกคน และช่วยให้ครอบครัวได้พบกัน"),
          l("Check homes for structural damage and live electricity before people return.", "ตรวจความเสียหายของโครงสร้างบ้านและไฟฟ้ารั่วก่อนให้ผู้คนกลับเข้าบ้าน"),
          l("Screen for injuries, skin infections and water-borne illness at shelters.", "คัดกรองการบาดเจ็บ โรคผิวหนัง และโรคที่มากับน้ำในศูนย์พักพิง"),
        ],
        residents: [
          l("Go home only when officials say it is safe.", "กลับบ้านเมื่อเจ้าหน้าที่แจ้งว่าปลอดภัยแล้วเท่านั้น"),
          l("Boil or treat drinking water; wear boots and gloves when clearing mud.", "ต้มหรือฆ่าเชื้อน้ำดื่ม สวมรองเท้าบูทและถุงมือเมื่อทำความสะอาดโคลน"),
        ],
      },
    },
  },
  B: {
    name: l("Keep Routes Open", "รักษาเส้นทางให้สัญจรได้"),
    when: l(
      "Road criticality 75+ and access gap 55+: main roads are cut and people are being isolated.",
      "ความสำคัญของถนน 75+ และช่องว่างการเข้าถึง 55+: ถนนสายหลักถูกตัดขาดและผู้คนเริ่มถูกตัดขาด",
    ),
    headline: l(
      "Plan closures, detours, pumps, temporary crossings, or road-elevation priorities.",
      "วางแผนปิดถนน ทางเบี่ยง เครื่องสูบน้ำ จุดข้ามชั่วคราว หรือการยกระดับถนนจุดสำคัญ",
    ),
    stages: {
      before: {
        responders: [
          l("Plan closures and detours for the roads the model cuts first, and publish them.", "วางแผนการปิดถนนและทางเบี่ยงสำหรับถนนที่แบบจำลองแสดงว่าถูกตัดก่อน และประกาศให้ทราบ"),
          l("Stage pumps, barriers and temporary-crossing kits at the low points.", "จัดวางเครื่องสูบน้ำ แนวกั้น และอุปกรณ์ทำจุดข้ามชั่วคราวที่จุดต่ำ"),
          l("Choose one lifeline route per subdistrict to keep open for rescue and supplies.", "กำหนดเส้นทางหลักหนึ่งเส้นต่อตำบลที่จะรักษาไว้ให้ใช้ได้สำหรับกู้ภัยและขนส่งเสบียง"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Learn a second way out of your village, and store food and water for several days of isolation.", "รู้เส้นทางออกจากหมู่บ้านเส้นที่สอง และสำรองอาหารและน้ำสำหรับหลายวันหากถูกตัดขาด"),
        ],
      },
      during: {
        responders: [
          l("Close flooded roads with staffed barriers; keep the lifeline route open.", "ปิดถนนที่น้ำท่วมโดยมีเจ้าหน้าที่ประจำแนวกั้น และรักษาเส้นทางหลักให้ใช้ได้"),
          l("Pump out underpasses and dips on the lifeline route first.", "สูบน้ำออกจากทางลอดและจุดต่ำบนเส้นทางหลักก่อน"),
          l("Resupply cut-off villages by boat or high-clearance truck.", "ส่งเสบียงให้หมู่บ้านที่ถูกตัดขาดด้วยเรือหรือรถยกสูง"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Use the announced detours; never drive past a closure or into moving water.", "ใช้ทางเบี่ยงที่ประกาศ อย่าขับรถผ่านจุดปิดถนนหรือลงไปในน้ำไหล"),
          l("If your village is cut off, stay put, keep your phone charged and report your situation.", "หากหมู่บ้านถูกตัดขาด ให้อยู่ในที่ปลอดภัย ชาร์จโทรศัพท์ให้พร้อม และแจ้งสถานการณ์ของคุณ"),
        ],
      },
      after: {
        responders: [
          l("Inspect bridges and road bases before reopening; clear the lifeline route first.", "ตรวจสะพานและฐานถนนก่อนเปิดใช้ และเคลียร์เส้นทางหลักก่อน"),
          l("Record where and for how long each road was cut to rank road-raising works.", "บันทึกจุดและระยะเวลาที่ถนนแต่ละเส้นถูกตัด เพื่อจัดลำดับงานยกระดับถนน"),
        ],
        residents: [
          l("Report washed-out or damaged roads and bridges to the subdistrict office.", "แจ้งถนนหรือสะพานที่ชำรุดหรือถูกน้ำกัดเซาะไปยังองค์การบริหารส่วนตำบลหรือเทศบาล"),
        ],
      },
    },
  },
  C: {
    name: l("Protect Essential Services", "ปกป้องบริการที่จำเป็น"),
    when: l(
      "Exposure 65+ and access gap 50+: clinics, schools and utilities serving many people are exposed or hard to reach.",
      "การสัมผัสน้ำท่วม 65+ และช่องว่างการเข้าถึง 50+: สถานพยาบาล โรงเรียน และสาธารณูปโภคที่ให้บริการคนจำนวนมากเสี่ยงหรือเข้าถึงยาก",
    ),
    headline: l(
      "Floodproof facilities, secure backup access, and activate mobile services.",
      "ป้องกันสถานบริการสำคัญจากน้ำท่วม จัดทางเข้าถึงสำรอง และเปิดบริการเคลื่อนที่",
    ),
    stages: {
      before: {
        responders: [
          l("Sandbag and raise equipment, medicines and records at clinics, schools and water plants.", "วางกระสอบทรายและยกอุปกรณ์ ยา และเอกสารในสถานพยาบาล โรงเรียน และโรงผลิตน้ำประปาให้สูงขึ้น"),
          l("Fuel backup generators and agree a backup access route to each facility.", "เติมเชื้อเพลิงเครื่องปั่นไฟสำรอง และกำหนดเส้นทางสำรองเข้าแต่ละสถานบริการ"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Refill prescriptions early and keep a written list of your medicines.", "รับยาล่วงหน้าและจดรายการยาที่ใช้ประจำไว้"),
        ],
      },
      during: {
        responders: [
          l("Run mobile clinics and safe-water points at the shelters.", "เปิดหน่วยแพทย์เคลื่อนที่และจุดแจกน้ำสะอาดที่ศูนย์พักพิง"),
          l("Move patients who depend on power before the facility loses access.", "ย้ายผู้ป่วยที่ต้องพึ่งไฟฟ้าก่อนที่สถานบริการจะถูกตัดขาด"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Use the mobile services at the shelters, and tell staff about urgent medical needs.", "ใช้บริการเคลื่อนที่ที่ศูนย์พักพิง และแจ้งเจ้าหน้าที่หากมีความจำเป็นทางการแพทย์เร่งด่วน"),
        ],
      },
      after: {
        responders: [
          l("Clean and disinfect facilities; test the water supply before reopening.", "ทำความสะอาดและฆ่าเชื้อสถานบริการ ตรวจคุณภาพน้ำประปาก่อนเปิดให้บริการ"),
          l("Restore in order: health care, then water, then schools.", "ฟื้นฟูตามลำดับ: บริการสุขภาพ ตามด้วยน้ำประปา แล้วจึงโรงเรียน"),
        ],
        residents: [
          l("Use tap water only after the water authority says it is safe.", "ใช้น้ำประปาเมื่อหน่วยงานประปาแจ้งว่าปลอดภัยแล้วเท่านั้น"),
        ],
      },
    },
  },
  D: {
    name: l("Build Resilience", "เสริมความพร้อมรับมือ"),
    when: l(
      "Score 35+ but not an immediate crisis on the A–C rules: the area floods, but people can still reach help.",
      "คะแนน 35+ แต่ยังไม่เข้าเกณฑ์วิกฤตตามกฎ A–C: พื้นที่ถูกน้ำท่วม แต่ผู้คนยังเข้าถึงความช่วยเหลือได้",
    ),
    headline: l(
      "Prioritize drainage, canal maintenance, retention areas, green-blue infrastructure, and local drills.",
      "ให้ความสำคัญกับการระบายน้ำ การบำรุงรักษาคลอง พื้นที่รับน้ำ โครงสร้างพื้นฐานสีเขียว-น้ำเงิน และการซ้อมแผนในพื้นที่",
    ),
    stages: {
      before: {
        responders: [
          l("Clear drains and canals, and check that retention areas are empty.", "ลอกท่อระบายน้ำและคลอง และตรวจว่าพื้นที่รับน้ำว่างพร้อมรับน้ำ"),
          l("Run a local evacuation drill and update the shelter and vulnerable-resident lists.", "ซ้อมอพยพในพื้นที่ และปรับปรุงรายชื่อศูนย์พักพิงและกลุ่มเปราะบาง"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Join the drill; raise sockets and appliances above past flood levels.", "เข้าร่วมการซ้อม ยกปลั๊กไฟและเครื่องใช้ไฟฟ้าให้สูงกว่าระดับน้ำที่เคยท่วม"),
        ],
      },
      during: {
        responders: [
          l("Watch the water and road figures; be ready to move up to A, B or C if they rise.", "ติดตามระดับน้ำและสภาพถนน พร้อมยกระดับเป็นกลุ่ม A B หรือ C หากสถานการณ์รุนแรงขึ้น"),
          l("Lend spare crews and equipment to higher-priority subdistricts.", "สนับสนุนกำลังคนและอุปกรณ์ที่ว่างให้ตำบลที่มีลำดับความสำคัญสูงกว่า"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Keep your go-bag ready and check on neighbours who live alone.", "เตรียมกระเป๋าฉุกเฉินให้พร้อม และดูแลเพื่อนบ้านที่อยู่ลำพัง"),
        ],
      },
      after: {
        responders: [
          l("Record damage and lessons learned; fund drainage upgrades where this flood hit.", "บันทึกความเสียหายและบทเรียน และจัดงบปรับปรุงระบบระบายน้ำในจุดที่น้ำท่วมครั้งนี้"),
        ],
        residents: [
          l("Tell the subdistrict office where water collected or drained slowly.", "แจ้งองค์การบริหารส่วนตำบลหรือเทศบาลถึงจุดที่น้ำขังหรือระบายช้า"),
        ],
      },
    },
  },
  E: {
    name: l("Monitor and Verify", "เฝ้าระวังและตรวจสอบ"),
    when: l(
      "Confidence is low, or the score is below 35. E does not mean no risk: it means check before acting on the score.",
      "ความเชื่อมั่นต่ำ หรือคะแนนต่ำกว่า 35 กลุ่ม E ไม่ได้แปลว่าไม่มีความเสี่ยง แต่หมายถึงต้องตรวจสอบก่อนดำเนินการตามคะแนน",
    ),
    headline: l(
      "Monitor conditions, verify field data, and improve source confidence before escalation.",
      "ติดตามสถานการณ์ ตรวจสอบข้อมูลภาคสนาม และปรับปรุงความเชื่อมั่นของแหล่งข้อมูลก่อนยกระดับการดำเนินการ",
    ),
    stages: {
      before: {
        responders: [
          l("Confirm the modelled water with village heads, the district office and the nearest gauge.", "ยืนยันน้ำตามแบบจำลองกับผู้ใหญ่บ้าน ที่ว่าการอำเภอ และสถานีวัดน้ำที่ใกล้ที่สุด"),
          l("Request the next satellite image over the area and compare it with the model.", "ขอภาพดาวเทียมภาพถัดไปของพื้นที่และเปรียบเทียบกับแบบจำลอง"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Report water levels and blocked roads you see to the subdistrict office.", "แจ้งระดับน้ำและถนนที่ใช้ไม่ได้ที่คุณพบเห็นไปยังองค์การบริหารส่วนตำบลหรือเทศบาล"),
        ],
      },
      during: {
        responders: [
          l("Send a field team or drone to check the places with the highest score first.", "ส่งทีมภาคสนามหรือโดรนไปตรวจพื้นที่ที่คะแนนสูงสุดก่อน"),
          l("Once the water is confirmed, act on the class the score implies — do not wait for the model.", "เมื่อยืนยันน้ำแล้ว ให้ดำเนินการตามกลุ่มที่คะแนนบ่งชี้ทันที ไม่ต้องรอแบบจำลอง"),
        ],
        residents: [
          FOLLOW_OFFICIAL,
          l("Stay ready to leave; share photos and water levels with local officials.", "เตรียมพร้อมที่จะออกจากพื้นที่ และส่งภาพถ่ายหรือระดับน้ำให้เจ้าหน้าที่ในพื้นที่"),
        ],
      },
      after: {
        responders: [
          l("Compare what happened with the model to improve the next estimate.", "เปรียบเทียบเหตุการณ์จริงกับแบบจำลองเพื่อปรับปรุงการประเมินครั้งต่อไป"),
        ],
        residents: [
          l("Share where and how high the water came, to improve future warnings.", "แจ้งจุดที่น้ำท่วมและความสูงของน้ำ เพื่อช่วยปรับปรุงการเตือนภัยในอนาคต"),
        ],
      },
    },
  },
};

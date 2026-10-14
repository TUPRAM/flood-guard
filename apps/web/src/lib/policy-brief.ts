import type { BilingualText } from "./policy-evidence";

/**
 * The text of the plain-language policy page (`/policy/`): what the government asks for, what the team proposes, the
 * ground rules, the common questions and the reading list. The scored figures are not here: the page takes them from
 * the published case (`policy-case.ts`), the weights from the signed scoring frame (`policy-evidence.ts`) and the
 * weight test from `policy-weight-sensitivity.json`.
 *
 * The English text follows the team's policy document of 12 October 2026. The Thai text is written by the assistant
 * and has not been reviewed by a native speaker.
 */

export interface PolicySource {
  id: string;
  title: BilingualText;
  owner: BilingualText;
  url: string;
}

/** Official texts the three points rest on. Each was opened on 12 October 2026. */
export const POLICY_GOVERNMENT_SOURCES: readonly PolicySource[] = [
  {
    id: "plan",
    title: { en: "National Disaster Prevention and Mitigation Plan 2021–2027", th: "แผนการป้องกันและบรรเทาสาธารณภัยแห่งชาติ พ.ศ. 2564–2570" },
    owner: { en: "Department of Disaster Prevention and Mitigation", th: "กรมป้องกันและบรรเทาสาธารณภัย" },
    url: "https://catalog.disaster.go.th/dataset/dpm-gd007",
  },
  {
    id: "strategies",
    title: { en: "The plan’s five strategies, in summary", th: "สรุปยุทธศาสตร์ทั้งห้าของแผนแห่งชาติ" },
    owner: { en: "Office of Natural Resources and Environmental Policy and Planning", th: "สำนักงานนโยบายและแผนทรัพยากรธรรมชาติและสิ่งแวดล้อม" },
    url: "https://eqmplatform.onep.go.th/public-plan/detail/1061",
  },
  {
    id: "act",
    title: { en: "Disaster Prevention and Mitigation Act B.E. 2550 (2007)", th: "พระราชบัญญัติป้องกันและบรรเทาสาธารณภัย พ.ศ. 2550" },
    owner: { en: "Government-hosted text", th: "เอกสารที่เผยแพร่โดยหน่วยงานรัฐ" },
    url: "https://www.maeyom.go.th/customers/webpage/datas/content/download/230824/e3647a8b.pdf",
  },
  {
    id: "prd",
    title: { en: "Chiang Rai prepares for the 2026 flood season: walls, warning times and two exercises (15 May 2026)", th: "เชียงรายเตรียมรับมือฤดูน้ำหลาก 2569: พนังกั้นน้ำ เวลาแจ้งเตือน และการฝึกซ้อมสองครั้ง (15 พ.ค. 2569)" },
    owner: { en: "Chiang Rai Public Relations Office", th: "สำนักงานประชาสัมพันธ์จังหวัดเชียงราย" },
    url: "https://chiangrai.prd.go.th/th/content/category/detail/id/9/iid/503464",
  },
  {
    id: "pdpa",
    title: { en: "Personal Data Protection Act B.E. 2562 (2019)", th: "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562" },
    owner: { en: "Ministry of Digital Economy and Society (unofficial English translation)", th: "กระทรวงดิจิทัลเพื่อเศรษฐกิจและสังคม (คำแปลภาษาอังกฤษอย่างไม่เป็นทางการ)" },
    url: "https://www.mdes.go.th/law/detail/3577-Personal-Data-Protection-Act-B-E--2562--2019-",
  },
];

export interface PolicyPoint {
  id: string;
  title: BilingualText;
  says: BilingualText;
  means: BilingualText;
  /** What the "Sources" line names, in the order of the document, with the source each part comes from. */
  sources: readonly { label: BilingualText; source: string }[];
}

/** "What the government is focused on": three points, each in the government's words, then what it means for us. */
export const POLICY_GOVERNMENT_POINTS: readonly PolicyPoint[] = [
  {
    id: "know-the-risk",
    title: { en: "Know the risk before the water comes", th: "รู้ความเสี่ยงก่อนน้ำมา" },
    says: {
      en: "Reducing risk is the first strategy of the National Plan 2021–2027, with risk assessment at national, provincial, district and local level. The 2007 Act requires every province to have its own plan that matches the national one. In May 2026 Chiang Rai described its flood plan for Mae Sai in three steps (repair the walls now, and study a permanent barrier estimated at about 2.9 billion baht) and its warning times: about 4 hours’ notice for Mae Sai and 9 to 12 hours for Chiang Rai city.",
      th: "การลดความเสี่ยงเป็นยุทธศาสตร์แรกของแผนแห่งชาติ พ.ศ. 2564–2570 โดยให้ประเมินความเสี่ยงทั้งระดับชาติ จังหวัด อำเภอ และท้องถิ่น พระราชบัญญัติ พ.ศ. 2550 กำหนดให้ทุกจังหวัดมีแผนของตนเองที่สอดคล้องกับแผนแห่งชาติ ในเดือนพฤษภาคม 2569 จังหวัดเชียงรายชี้แจงแผนรับมือน้ำท่วมแม่สายเป็นสามระยะ (ซ่อมพนังกั้นน้ำทันที และศึกษาพนังถาวรซึ่งประมาณการไว้ราว 2,900 ล้านบาท) และเวลาแจ้งเตือนล่วงหน้า: ประมาณ 4 ชั่วโมงสำหรับแม่สาย และ 9 ถึง 12 ชั่วโมงสำหรับตัวเมืองเชียงราย",
    },
    means: {
      en: "Government is already investing in “when will the water arrive”. The next question is “who is affected when it does”. That is the question FloodGuard answers.",
      th: "ภาครัฐลงทุนกับคำถามว่า “น้ำจะมาถึงเมื่อใด” อยู่แล้ว คำถามถัดไปคือ “เมื่อน้ำมาถึง ใครได้รับผลกระทบ” ซึ่งเป็นคำถามที่ FloodGuard ตอบ",
    },
    sources: [
      { label: { en: "National Plan, Strategy 1", th: "แผนแห่งชาติ ยุทธศาสตร์ที่ 1" }, source: "plan" },
      { label: { en: "Act, sections 15–16", th: "พระราชบัญญัติ มาตรา 15–16" }, source: "act" },
      { label: { en: "Chiang Rai PRD, May 2026", th: "สำนักงานประชาสัมพันธ์จังหวัดเชียงราย พ.ค. 2569" }, source: "prd" },
    ],
  },
  {
    id: "reach-everyone",
    title: { en: "Reach everyone, including people who are easily missed", th: "เข้าถึงทุกคน รวมถึงผู้ที่มักถูกมองข้าม" },
    says: {
      en: "The plan wants warnings to reach vulnerable groups equally, evacuation plans to name main and backup routes for each type of hazard, and shelters to sit in safe places that are easy to reach. Its national indicators include disruption to basic services such as hospitals and schools, and whether people can actually receive warnings.",
      th: "แผนแห่งชาติต้องการให้การแจ้งเตือนเข้าถึงกลุ่มเปราะบางอย่างเท่าเทียม ให้แผนอพยพระบุเส้นทางหลักและเส้นทางสำรองสำหรับภัยแต่ละประเภท และให้ศูนย์พักพิงตั้งอยู่ในที่ปลอดภัยและเดินทางไปถึงได้ง่าย ตัวชี้วัดระดับชาติของแผนรวมถึงการหยุดชะงักของบริการพื้นฐาน เช่น โรงพยาบาลและโรงเรียน และประชาชนได้รับการแจ้งเตือนจริงหรือไม่",
    },
    means: {
      en: "“Access” is already a national standard. FloodGuard measures it place by place: which roads, hospitals and shelters people could lose.",
      th: "“การเข้าถึง” เป็นมาตรฐานระดับชาติอยู่แล้ว FloodGuard วัดการเข้าถึงเป็นรายพื้นที่ ว่าประชาชนอาจสูญเสียถนน โรงพยาบาล และศูนย์พักพิงใด",
    },
    sources: [
      { label: { en: "National Plan, chapter 2 indicators and emergency-management guidance (evacuation, shelters, warnings)", th: "แผนแห่งชาติ ตัวชี้วัดในบทที่ 2 และแนวทางการจัดการภาวะฉุกเฉิน (การอพยพ ศูนย์พักพิง การแจ้งเตือน)" }, source: "plan" },
      { label: { en: "Act, section 12(2)", th: "พระราชบัญญัติ มาตรา 12 (2)" }, source: "act" },
    ],
  },
  {
    id: "practise",
    title: { en: "Practise with the people responsible", th: "ฝึกซ้อมร่วมกับผู้มีหน้าที่รับผิดชอบ" },
    says: {
      en: "Provinces and local governments carry the legal duty, and plans must be reviewed when facts change or after five years. The plan expects drills at least once a year. Chiang Rai scheduled a tabletop exercise on 20 May 2026 (about 350 people) and a field exercise on 22 May (about 890 people) covering flood evacuation in Mae Sai and landslide evacuation in Mae Fah Luang.",
      th: "จังหวัดและองค์กรปกครองส่วนท้องถิ่นมีหน้าที่ตามกฎหมาย และต้องทบทวนแผนเมื่อข้อเท็จจริงเปลี่ยนไปหรือเมื่อครบห้าปี แผนแห่งชาติคาดหวังให้ฝึกซ้อมอย่างน้อยปีละครั้ง จังหวัดเชียงรายกำหนดการฝึกซ้อมบนโต๊ะในวันที่ 20 พฤษภาคม 2569 (ประมาณ 350 คน) และการฝึกภาคสนามในวันที่ 22 พฤษภาคม (ประมาณ 890 คน) ครอบคลุมการอพยพกรณีน้ำท่วมที่แม่สาย และกรณีดินโคลนถล่มที่แม่ฟ้าหลวง",
    },
    means: {
      en: "Exercises are where new evidence gets tested. We offer scenario material for the next one.",
      th: "การฝึกซ้อมคือเวทีทดสอบหลักฐานใหม่ เราเสนอสถานการณ์จำลองสำหรับการฝึกครั้งถัดไป",
    },
    sources: [
      { label: { en: "Act, sections 15, 20–21 and 44", th: "พระราชบัญญัติ มาตรา 15, 20–21 และ 44" }, source: "act" },
      { label: { en: "National Plan, drills", th: "แผนแห่งชาติ ส่วนการฝึกซ้อม" }, source: "plan" },
      { label: { en: "Chiang Rai PRD, May 2026", th: "สำนักงานประชาสัมพันธ์จังหวัดเชียงราย พ.ค. 2569" }, source: "prd" },
    ],
  },
];

export interface PolicyProposal {
  id: string;
  title: BilingualText;
  what: BilingualText;
  whyNow: BilingualText;
  supplies: BilingualText;
  decides: BilingualText;
}

/** "What we propose": three practical steps. None replaces an official plan. */
export const POLICY_PROPOSALS: readonly PolicyProposal[] = [
  {
    id: "access-check",
    title: { en: "Add an access check to flood risk assessment", th: "เพิ่มการตรวจสอบการเข้าถึงในการประเมินความเสี่ยงน้ำท่วม" },
    what: {
      en: "When a local flood plan lists risky areas, also list which roads, hospitals and shelters could be lost, and who relies on them.",
      th: "เมื่อแผนรับมือน้ำท่วมของท้องถิ่นระบุพื้นที่เสี่ยง ให้ระบุด้วยว่าอาจสูญเสียถนน โรงพยาบาล และศูนย์พักพิงใด และใครพึ่งพาสิ่งเหล่านั้น",
    },
    whyNow: {
      en: "National indicators already track disruption to hospitals and basic services. The Act requires plans to cover evacuation, public health and communications.",
      th: "ตัวชี้วัดระดับชาติติดตามการหยุดชะงักของโรงพยาบาลและบริการพื้นฐานอยู่แล้ว และพระราชบัญญัติกำหนดให้แผนครอบคลุมการอพยพ การสาธารณสุข และการสื่อสาร",
    },
    supplies: {
      en: "A ranked comparison of communities and a map of lost connections.",
      th: "การเปรียบเทียบชุมชนตามลำดับ และแผนที่ของเส้นทางเชื่อมต่อที่สูญเสีย",
    },
    decides: {
      en: "Provincial, district and local directors under the Act.",
      th: "ผู้อำนวยการจังหวัด อำเภอ และท้องถิ่นตามพระราชบัญญัติ",
    },
  },
  {
    id: "easiest-to-miss",
    title: { en: "Check who is easiest to miss, and whether shelters really work for them", th: "ตรวจสอบว่าใครถูกมองข้ามได้ง่ายที่สุด และศูนย์พักพิงใช้ได้จริงสำหรับเขาหรือไม่" },
    what: {
      en: "For each priority area, show who loses access and whether children under 15 and adults aged 60 or over lose it more often than everyone else. Check each shelter for usable capacity, access, staffing and opening status.",
      th: "สำหรับพื้นที่สำคัญแต่ละแห่ง ให้แสดงว่าใครสูญเสียการเข้าถึง และเด็กอายุต่ำกว่า 15 ปีกับผู้ใหญ่อายุ 60 ปีขึ้นไปสูญเสียบ่อยกว่าคนอื่นหรือไม่ ตรวจสอบศูนย์พักพิงแต่ละแห่งเรื่องความจุที่ใช้ได้จริง การเดินทางไปถึง เจ้าหน้าที่ และสถานะการเปิด",
    },
    whyNow: {
      en: "The plan asks that warnings and help reach vulnerable groups equally, and it names ageing as a growing vulnerability.",
      th: "แผนแห่งชาติขอให้การแจ้งเตือนและความช่วยเหลือเข้าถึงกลุ่มเปราะบางอย่างเท่าเทียม และระบุว่าสังคมสูงวัยเป็นความเปราะบางที่เพิ่มขึ้น",
    },
    supplies: {
      en: "An equity ratio beside the raw counts, and a shelter checklist.",
      th: "อัตราส่วนความเป็นธรรมที่แสดงคู่กับจำนวนจริง และรายการตรวจสอบศูนย์พักพิง",
    },
    decides: {
      en: "Local directors, with community input.",
      th: "ผู้อำนวยการท้องถิ่น โดยรับฟังความเห็นของชุมชน",
    },
  },
  {
    id: "road-is-cut",
    title: { en: "Use a “road is cut” scenario in the next drill, then check it in the field", th: "ใช้สถานการณ์ “ถนนถูกตัดขาด” ในการฝึกซ้อมครั้งถัดไป แล้วตรวจสอบในพื้นที่จริง" },
    what: {
      en: "Add a segment: “This road is closed. Where do people go?” Compare shelter options. Pilot in Mae Sai. Every finding gets a named owner, a field check and a review date.",
      th: "เพิ่มช่วงหนึ่งในการฝึก: “ถนนสายนี้ปิด ประชาชนจะไปทางใด?” เปรียบเทียบทางเลือกของศูนย์พักพิง นำร่องที่แม่สาย ข้อค้นพบทุกข้อมีผู้รับผิดชอบที่ระบุชื่อ การตรวจสอบภาคสนาม และวันทบทวน",
    },
    whyNow: {
      en: "The plan expects annual drills, and Chiang Rai has just rehearsed Mae Sai floods.",
      th: "แผนแห่งชาติคาดหวังให้ฝึกซ้อมทุกปี และจังหวัดเชียงรายเพิ่งฝึกซ้อมกรณีน้ำท่วมแม่สาย",
    },
    supplies: {
      en: "The 2024 season scenario (case SE1), a candidate shelter list and discussion questions.",
      th: "สถานการณ์จำลองฤดูน้ำปี 2567 (กรณี SE1) รายชื่อสถานที่ที่อาจใช้เป็นศูนย์พักพิง และคำถามสำหรับการอภิปราย",
    },
    decides: {
      en: "The directors who run the exercise; road owners and shelter managers confirm each finding in the field.",
      th: "ผู้อำนวยการที่จัดการฝึกซ้อม โดยเจ้าของถนนและผู้ดูแลศูนย์พักพิงยืนยันข้อค้นพบแต่ละข้อในพื้นที่",
    },
  },
];

/** The five kinds of attention (classes A to E), in plain words. */
export const POLICY_ATTENTION: readonly { letter: "A" | "B" | "C" | "D" | "E"; title: BilingualText; text: BilingualText }[] = [
  { letter: "A", title: { en: "Protect lives now", th: "ปกป้องชีวิตทันที" }, text: { en: "Many people exposed and losing access.", th: "ประชาชนจำนวนมากอยู่ในพื้นที่น้ำท่วมและสูญเสียการเข้าถึง" } },
  { letter: "B", title: { en: "Keep routes open", th: "รักษาเส้นทางให้สัญจรได้" }, text: { en: "Key roads fail.", th: "ถนนสายสำคัญใช้การไม่ได้" } },
  { letter: "C", title: { en: "Protect essential services", th: "คุ้มครองบริการจำเป็น" }, text: { en: "Hospitals, shelters or other services at risk.", th: "โรงพยาบาล ศูนย์พักพิง หรือบริการอื่นมีความเสี่ยง" } },
  { letter: "D", title: { en: "Build resilience", th: "สร้างความพร้อมระยะยาว" }, text: { en: "A high priority to work on over time.", th: "ลำดับความสำคัญสูงที่ต้องดำเนินการต่อเนื่อง" } },
  { letter: "E", title: { en: "Monitor and verify", th: "ติดตามและตรวจสอบ" }, text: { en: "Low score or weak evidence. Check before acting. E never means safe.", th: "คะแนนต่ำหรือหลักฐานยังอ่อน ตรวจสอบก่อนดำเนินการ ระดับ E ไม่ได้หมายความว่าปลอดภัย ไม่ว่ากรณีใด" } },
];

/** Ground rules. */
export const POLICY_GROUND_RULES: readonly { title: BilingualText; text: BilingualText }[] = [
  {
    title: { en: "Evidence shown.", th: "แสดงหลักฐาน" },
    text: { en: "Source, date and confidence travel with every result.", th: "ผลลัพธ์ทุกรายการมีแหล่งข้อมูล วันที่ และระดับความเชื่อมั่นกำกับ" },
  },
  {
    title: { en: "People decide.", th: "คนเป็นผู้ตัดสินใจ" },
    text: {
      en: "Officials with legal responsibility decide. FloodGuard does not issue warnings, order evacuations, allocate budgets or decide who receives relief.",
      th: "เจ้าหน้าที่ผู้มีหน้าที่ตามกฎหมายเป็นผู้ตัดสินใจ FloodGuard ไม่ออกประกาศเตือนภัย ไม่สั่งอพยพ ไม่จัดสรรงบประมาณ และไม่ตัดสินว่าใครได้รับความช่วยเหลือ",
    },
  },
  {
    title: { en: "Personal data protected.", th: "คุ้มครองข้อมูลส่วนบุคคล" },
    text: {
      en: "We publish aggregated needs only. No household records without a lawful purpose, defined access and retention (Personal Data Protection Act 2019).",
      th: "เราเผยแพร่เฉพาะความต้องการในภาพรวม ไม่รับข้อมูลรายครัวเรือนหากไม่มีวัตถุประสงค์ที่ชอบด้วยกฎหมาย และยังไม่ได้กำหนดสิทธิ์การเข้าถึงและระยะเวลาเก็บรักษา (พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562)",
    },
  },
  {
    title: { en: "Missing voices.", th: "เสียงที่ยังขาดหาย" },
    text: { en: "We check who population data misses and invite communities to correct us.", th: "เราตรวจสอบว่าข้อมูลประชากรตกหล่นใคร และเชิญชุมชนช่วยแก้ไขให้ถูกต้อง" },
  },
];

/** Common questions. */
export const POLICY_QUESTIONS: readonly { question: BilingualText; answer: BilingualText }[] = [
  {
    question: { en: "Is this a warning system?", th: "นี่คือระบบเตือนภัยหรือไม่?" },
    answer: { en: "No. For current conditions, follow official local information.", th: "ไม่ใช่ สำหรับสถานการณ์ปัจจุบัน โปรดติดตามข้อมูลทางการของพื้นที่" },
  },
  {
    question: { en: "Does class E mean a place is safe?", th: "ระดับ E หมายความว่าพื้นที่ปลอดภัยหรือไม่?" },
    answer: { en: "No. It means lower relative priority in this scenario, or not enough evidence yet.", th: "ไม่ใช่ หมายถึงลำดับความสำคัญเชิงเปรียบเทียบต่ำกว่าในสถานการณ์จำลองนี้ หรือหลักฐานยังไม่เพียงพอ" },
  },
  {
    question: { en: "Does 65 out of 100 mean a 65% chance of flooding?", th: "65 จาก 100 หมายถึงโอกาสน้ำท่วม 65% หรือไม่?" },
    answer: { en: "No. It is a comparison score.", th: "ไม่ใช่ เป็นคะแนนสำหรับเปรียบเทียบพื้นที่" },
  },
  {
    question: { en: "Is this the government’s plan?", th: "นี่คือแผนของภาครัฐหรือไม่?" },
    answer: { en: "No. These are our proposals. No agency has adopted them.", th: "ไม่ใช่ เป็นข้อเสนอของเรา ยังไม่มีหน่วยงานใดนำไปใช้" },
  },
  {
    question: { en: "Are the numbers real?", th: "ตัวเลขเป็นของจริงหรือไม่?" },
    answer: { en: "They are modelled for a scenario and have not been checked in the field yet.", th: "เป็นตัวเลขจากแบบจำลองสำหรับสถานการณ์สมมุติ และยังไม่ได้ตรวจสอบในพื้นที่จริง" },
  },
  {
    question: { en: "Who is responsible if something goes wrong?", th: "หากเกิดความผิดพลาด ใครเป็นผู้รับผิดชอบ?" },
    answer: {
      en: "Under the Act, local governments and provincial and district directors hold the duty. FloodGuard only supplies evidence.",
      th: "ตามพระราชบัญญัติ องค์กรปกครองส่วนท้องถิ่นและผู้อำนวยการจังหวัดและอำเภอเป็นผู้มีหน้าที่ FloodGuard เพียงจัดหาหลักฐานให้",
    },
  },
];

export interface PolicyReading {
  id: string;
  /** Authors, year, title and where it was published, as a reference is written. Not translated. */
  reference: string;
  url: string;
  /** What the page takes from it, in one sentence. */
  use: BilingualText;
}

export interface PolicyReadingGroup {
  id: string;
  title: BilingualText;
  items: readonly PolicyReading[];
}

/**
 * Further reading: international frameworks and peer-reviewed research behind the access view, the attention to age,
 * and the way the score is built and tested. Every link was opened or its record checked on 12 October 2026. A paper
 * here supports an idea of the page; none endorses FloodGuard and none gives the five weights.
 */
export const POLICY_READING: readonly PolicyReadingGroup[] = [
  {
    id: "frameworks",
    title: { en: "International frameworks", th: "กรอบการดำเนินงานระหว่างประเทศ" },
    items: [
      {
        id: "sendai-target-d",
        reference: "UNDRR. Sendai Framework for Disaster Risk Reduction 2015–2030: indicators for global target D (damage to critical infrastructure and disruption of basic services, among them health and educational facilities).",
        url: "https://www.preventionweb.net/sendai-framework/sendai-framework-indicators",
        use: {
          en: "Countries already report disruption of health, education and other basic services (indicators D-5 to D-8): lost access is an agreed measure, not our invention.",
          th: "ประเทศต่าง ๆ รายงานการหยุดชะงักของบริการสุขภาพ การศึกษา และบริการพื้นฐานอื่นอยู่แล้ว (ตัวชี้วัด D-5 ถึง D-8) การสูญเสียการเข้าถึงจึงเป็นตัววัดที่ตกลงร่วมกัน ไม่ใช่สิ่งที่เราคิดขึ้นเอง",
        },
      },
      {
        id: "wmo-1150",
        reference: "World Meteorological Organization (2015, 2021). WMO Guidelines on Multi-hazard Impact-based Forecast and Warning Services (WMO-No. 1150), Parts I and II.",
        url: "https://www.preventionweb.net/publication/wmo-guidelines-multi-hazard-impact-based-forecast-and-warning-services",
        use: {
          en: "Warning services are asked to move from what the hazard will be to what it will do to people and services, the same step this page proposes for planning.",
          th: "บริการเตือนภัยถูกขอให้ก้าวจากการบอกว่าภัยจะเป็นอย่างไร ไปสู่การบอกว่าภัยจะส่งผลต่อประชาชนและบริการอย่างไร ซึ่งเป็นก้าวเดียวกับที่หน้านี้เสนอสำหรับการวางแผน",
        },
      },
      {
        id: "inform",
        reference: "European Commission Joint Research Centre. INFORM Risk Index: concept and methodology (hazard and exposure, vulnerability, lack of coping capacity).",
        url: "https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology",
        use: {
          en: "A widely used risk index is built from hazard and exposure, vulnerability and coping capacity; our five parts follow the same families, with access in the place of coping capacity.",
          th: "ดัชนีความเสี่ยงที่ใช้กันแพร่หลายสร้างจากภัยและการเปิดรับ ความเปราะบาง และขีดความสามารถในการรับมือ องค์ประกอบทั้งห้าของเราอยู่ในกลุ่มเดียวกัน โดยใช้การเข้าถึงแทนขีดความสามารถในการรับมือ",
        },
      },
      {
        id: "unosat-mae-sai",
        reference: "UNOSAT (2024). Satellite detected water extents from 13 to 19 September 2024 over Mae Sai District, Chiang Rai Province, Thailand.",
        url: "https://thailand.un.org/en/280291-satellite-detected-water-extents-13-19-september-2024-over-mea-sai-district-chiang-rai",
        use: {
          en: "The agency map of the September 2024 flood in Mae Sai: about 70 km² of land affected, a preliminary analysis not validated in the field.",
          th: "แผนที่ของหน่วยงานสำหรับน้ำท่วมแม่สายเดือนกันยายน 2567: พื้นที่ได้รับผลกระทบประมาณ 70 ตร.กม. เป็นการวิเคราะห์เบื้องต้นที่ยังไม่ได้ตรวจสอบภาคสนาม",
        },
      },
    ],
  },
  {
    id: "access",
    title: { en: "Research: floods cut access, not only land", th: "งานวิจัย: น้ำท่วมตัดการเข้าถึง ไม่ใช่เพียงท่วมพื้นที่" },
    items: [
      {
        id: "coles-2017",
        reference: "Coles, D., Yu, D., Wilby, R. L., Green, D., & Herring, Z. (2017). Beyond ‘flood hotspots’: Modelling emergency service accessibility during flooding in York, UK. Journal of Hydrology, 546, 419–436.",
        url: "https://doi.org/10.1016/j.jhydrol.2016.12.013",
        use: {
          en: "Pairs a flood model with the road network to show where ambulances and fire engines cannot arrive in time: the method family our access check belongs to.",
          th: "ใช้แบบจำลองน้ำท่วมร่วมกับโครงข่ายถนนเพื่อแสดงว่ารถพยาบาลและรถดับเพลิงไปถึงไม่ทันเวลาที่ใด ซึ่งเป็นวิธีการกลุ่มเดียวกับการตรวจสอบการเข้าถึงของเรา",
        },
      },
      {
        id: "green-2017",
        reference: "Green, D., Yu, D., Pattison, I., Wilby, R., et al. (2017). City-scale accessibility of emergency responders operating during flood events. Natural Hazards and Earth System Sciences, 17, 1–16.",
        url: "https://doi.org/10.5194/nhess-17-1-2017",
        use: {
          en: "In Leicester the share of the city a fire engine reaches in 10 minutes falls from 100% to 66.5%, 39.8% and 26.2% as the surface-water flood grows.",
          th: "ในเมืองเลสเตอร์ สัดส่วนของเมืองที่รถดับเพลิงไปถึงได้ใน 10 นาทีลดจาก 100% เหลือ 66.5%, 39.8% และ 26.2% เมื่อน้ำท่วมผิวดินรุนแรงขึ้น",
        },
      },
      {
        id: "pregnolato-2017",
        reference: "Pregnolato, M., Ford, A., Wilkinson, S. M., & Dawson, R. J. (2017). The impact of flooding on road transport: A depth-disruption function. Transportation Research Part D, 55, 67–81.",
        url: "https://doi.org/10.1016/j.trd.2017.06.020",
        use: {
          en: "Relates the depth of water on a road to the speed vehicles can keep; studies that apply it treat a road as impassable from about 0.3 m, the depth our replay uses.",
          th: "เชื่อมโยงความลึกของน้ำบนถนนกับความเร็วที่ยานพาหนะวิ่งได้ งานที่นำไปใช้ถือว่าถนนสัญจรไม่ได้ตั้งแต่ประมาณ 0.3 ม. ซึ่งเป็นความลึกที่การย้อนดูของเราใช้",
        },
      },
      {
        id: "papilloud-2021",
        reference: "Papilloud, T., & Keiler, M. (2021). Vulnerability patterns of road network to extreme floods based on accessibility measures. Transportation Research Part D, 100, 103045.",
        url: "https://doi.org/10.1016/j.trd.2021.103045",
        use: {
          en: "Finds that an overall measure can miss the places that are hit hardest locally, where the well-connected roads serving them flood: the pattern of Ko Chang.",
          th: "พบว่าตัววัดภาพรวมอาจมองข้ามพื้นที่ที่ได้รับผลกระทบหนักที่สุดในระดับท้องถิ่น ซึ่งถนนเชื่อมต่อหลักของพื้นที่นั้นถูกน้ำท่วม เป็นรูปแบบเดียวกับตำบลเกาะช้าง",
        },
      },
      {
        id: "tariverdi-2023",
        reference: "Tariverdi, M., Nunez-del-Prado, M., Leonova, N., & Rentschler, J. (2023). Measuring accessibility to public services and infrastructure criticality for disasters risk management. Scientific Reports, 13, 1569.",
        url: "https://doi.org/10.1038/s41598-023-28460-z",
        use: {
          en: "A World Bank method that ranks road segments by how many people they keep connected to health services; in Manila about 22% of residents lose access to higher-level care in the flood scenario.",
          th: "วิธีของธนาคารโลกที่จัดลำดับช่วงถนนตามจำนวนประชาชนที่ถนนนั้นช่วยให้เข้าถึงบริการสุขภาพ ในกรุงมะนิลา ประชาชนประมาณ 22% สูญเสียการเข้าถึงสถานพยาบาลระดับสูงในสถานการณ์น้ำท่วม",
        },
      },
      {
        id: "logan-2020",
        reference: "Logan, T. M., & Guikema, S. D. (2020). Reframing resilience: Equitable access to essential services. Risk Analysis, 40(8), 1538–1553.",
        url: "https://doi.org/10.1111/risa.13492",
        use: {
          en: "Argues that resilience should be judged by whether people keep fair access to essential services, the idea behind showing an equity ratio beside the counts.",
          th: "เสนอว่าควรวัดความสามารถในการรับมือจากการที่ประชาชนยังเข้าถึงบริการจำเป็นได้อย่างเป็นธรรม ซึ่งเป็นแนวคิดเบื้องหลังการแสดงอัตราส่วนความเป็นธรรมคู่กับจำนวนจริง",
        },
      },
      {
        id: "hallegatte-2019",
        reference: "Hallegatte, S., Rentschler, J., & Rozenberg, J. (2019). Lifelines: The Resilient Infrastructure Opportunity. World Bank.",
        url: "https://openknowledge.worldbank.org/entities/publication/c3a753a6-2310-501b-a37e-5dcab3e96a0b",
        use: {
          en: "Defines resilient infrastructure by whether it keeps serving its users during and after a shock, not only by whether it is damaged.",
          th: "นิยามโครงสร้างพื้นฐานที่ทนทานจากการที่ยังให้บริการผู้ใช้ได้ทั้งระหว่างและหลังเกิดภัย ไม่ใช่เพียงจากการที่เสียหายหรือไม่",
        },
      },
    ],
  },
  {
    id: "people",
    title: { en: "Research: who is harmed most", th: "งานวิจัย: ใครได้รับผลกระทบมากที่สุด" },
    items: [
      {
        id: "jonkman-2009",
        reference: "Jonkman, S. N., Maaskant, B., Boyd, E., & Levitan, M. L. (2009). Loss of life caused by the flooding of New Orleans after Hurricane Katrina. Risk Analysis, 29(5), 676–698.",
        url: "https://doi.org/10.1111/j.1539-6924.2008.01190.x",
        use: {
          en: "Nearly 60% of the people who died were over 65: the reason older residents are counted in the score and in the equity check.",
          th: "ผู้เสียชีวิตเกือบ 60% มีอายุเกิน 65 ปี เป็นเหตุผลที่นับผู้สูงอายุทั้งในคะแนนและในการตรวจสอบความเป็นธรรม",
        },
      },
      {
        id: "rufat-2015",
        reference: "Rufat, S., Tate, E., Burton, C. G., & Maroof, A. S. (2015). Social vulnerability to floods: Review of case studies and implications for measurement. International Journal of Disaster Risk Reduction, 14, 470–486.",
        url: "https://doi.org/10.1016/j.ijdrr.2015.09.013",
        use: {
          en: "A review of 67 flood case studies: demographic characteristics, socioeconomic status and health drive who is harmed. Age is one of these, and our score has no income or health measure yet.",
          th: "การทบทวนกรณีศึกษาน้ำท่วม 67 กรณี: ลักษณะทางประชากร ฐานะทางเศรษฐกิจและสังคม และสุขภาพ เป็นตัวกำหนดว่าใครได้รับผลกระทบ อายุเป็นหนึ่งในนั้น และคะแนนของเรายังไม่มีตัววัดรายได้หรือสุขภาพ",
        },
      },
      {
        id: "cutter-2003",
        reference: "Cutter, S. L., Boruff, B. J., & Shirley, W. L. (2003). Social vulnerability to environmental hazards. Social Science Quarterly, 84(2), 242–261.",
        url: "https://doi.org/10.1111/1540-6237.8402002",
        use: {
          en: "The social vulnerability index that most later ones build on. Age is among the characteristics it uses to explain who is harmed.",
          th: "ดัชนีความเปราะบางทางสังคมที่ดัชนีรุ่นหลังส่วนใหญ่ต่อยอด อายุเป็นหนึ่งในลักษณะที่ดัชนีนี้ใช้อธิบายว่าใครได้รับผลกระทบ",
        },
      },
      {
        id: "marks-2016",
        reference: "Marks, D., & Lebel, L. (2016). Disaster governance and the scalar politics of incomplete decentralization: Fragmented and contested responses to the 2011 floods in Central Thailand. Habitat International, 52, 57–66.",
        url: "https://scholars.cityu.edu.hk/en/publications/disaster-governance-and-the-scalar-politics-of-incomplete-decentr/",
        use: {
          en: "On the 2011 floods in Thailand: local bodies held the duty but often lacked capacity and support. Evidence a local team can read by itself answers that gap.",
          th: "ว่าด้วยมหาอุทกภัยปี 2554 ของไทย: องค์กรปกครองส่วนท้องถิ่นมีหน้าที่ แต่มักขาดขีดความสามารถและการสนับสนุน หลักฐานที่ทีมท้องถิ่นอ่านเองได้ช่วยตอบช่องว่างนี้",
        },
      },
    ],
  },
  {
    id: "index",
    title: { en: "Research: building a score and testing its weights", th: "งานวิจัย: การสร้างคะแนนและการทดสอบน้ำหนัก" },
    items: [
      {
        id: "oecd-2008",
        reference: "OECD & European Commission Joint Research Centre (2008). Handbook on Constructing Composite Indicators: Methodology and User Guide. OECD Publishing.",
        url: "https://www.oecd.org/en/publications/handbook-on-constructing-composite-indicators-methodology-and-user-guide_9789264043466-en.html",
        use: {
          en: "The standard guide: weights are value judgements, set by statistics or by the people concerned, and must be stated openly and tested.",
          th: "คู่มือมาตรฐาน: น้ำหนักเป็นการตัดสินเชิงคุณค่า กำหนดด้วยวิธีทางสถิติหรือโดยผู้เกี่ยวข้อง และต้องระบุอย่างเปิดเผยและทดสอบ",
        },
      },
      {
        id: "greco-2019",
        reference: "Greco, S., Ishizaka, A., Tasiou, M., & Torrisi, G. (2019). On the methodological framework of composite indices: A review of the issues of weighting, aggregation, and robustness. Social Indicators Research, 141, 61–94.",
        url: "https://doi.org/10.1007/s11205-017-1832-9",
        use: {
          en: "Reviews the ways to weight and add up an index, and notes that checking robustness afterwards gets less attention than it deserves.",
          th: "ทบทวนวิธีให้น้ำหนักและรวมค่าดัชนี และชี้ว่าการตรวจสอบความทนทานของผลลัพธ์ภายหลังได้รับความสนใจน้อยกว่าที่ควร",
        },
      },
      {
        id: "moreira-2021",
        reference: "Moreira, L. L., de Brito, M. M., & Kobiyama, M. (2021). Review article: A systematic review and future prospects of flood vulnerability indices. Natural Hazards and Earth System Sciences, 21, 1513–1530.",
        url: "https://doi.org/10.5194/nhess-21-1513-2021",
        use: {
          en: "Of 95 flood vulnerability indices, equal weighting is the most common choice (24.2%), and only 9.5% test sensitivity. We state our weights and test them below.",
          th: "ในดัชนีความเปราะบางต่อน้ำท่วม 95 ชิ้น การให้น้ำหนักเท่ากันเป็นทางเลือกที่พบมากที่สุด (24.2%) และมีเพียง 9.5% ที่ทดสอบความอ่อนไหว เราระบุน้ำหนักของเราและทดสอบไว้ด้านล่าง",
        },
      },
      {
        id: "tate-2012",
        reference: "Tate, E. (2012). Social vulnerability indices: A comparative assessment using uncertainty and sensitivity analysis. Natural Hazards, 63(2), 325–347.",
        url: "https://doi.org/10.1007/s11069-012-0152-2",
        use: {
          en: "Shows that an index built in levels, like ours, is most sensitive to its weighting scheme: the reason the weight test exists.",
          th: "แสดงว่าดัชนีที่สร้างเป็นลำดับชั้นเช่นของเรา อ่อนไหวต่อวิธีให้น้ำหนักมากที่สุด เป็นเหตุผลที่ต้องมีการทดสอบน้ำหนัก",
        },
      },
      {
        id: "saisana-2005",
        reference: "Saisana, M., Saltelli, A., & Tarantola, S. (2005). Uncertainty and sensitivity analysis techniques as tools for the quality assessment of composite indicators. Journal of the Royal Statistical Society: Series A, 168(2), 307–323.",
        url: "https://doi.org/10.1111/j.1467-985X.2005.00350.x",
        use: {
          en: "The method we follow: vary the choices, weights among them, many times and report how often the order holds.",
          th: "วิธีที่เราใช้: เปลี่ยนตัวเลือกต่าง ๆ รวมถึงน้ำหนัก หลายครั้ง แล้วรายงานว่าลำดับคงเดิมบ่อยเพียงใด",
        },
      },
      {
        id: "becker-2017",
        reference: "Becker, W., Saisana, M., Paruolo, P., & Vandecasteele, I. (2017). Weights and importance in composite indicators: Closing the gap. Ecological Indicators, 80, 12–22.",
        url: "https://doi.org/10.1016/j.ecolind.2017.03.056",
        use: {
          en: "A weight of 30% does not mean a part decides 30% of the result: parts that move together count more. Flood and exposure do in our case, and so do the two access parts.",
          th: "น้ำหนัก 30% ไม่ได้หมายความว่าองค์ประกอบนั้นกำหนดผลลัพธ์ 30% องค์ประกอบที่เปลี่ยนไปด้วยกันมีผลมากกว่า ในกรณีของเรา น้ำท่วมกับการเปิดรับเป็นเช่นนั้น และองค์ประกอบการเข้าถึงทั้งสองก็เช่นกัน",
        },
      },
      {
        id: "de-brito-2018",
        reference: "de Brito, M. M., Evers, M., & Almoradie, A. D. S. (2018). Participatory flood vulnerability assessment: A multi-criteria approach. Hydrology and Earth System Sciences, 22, 373–390.",
        url: "https://doi.org/10.5194/hess-22-373-2018",
        use: {
          en: "Sets the weights with 101 local experts instead of by the analysts: the way our weights should be reviewed with Mae Sai officials.",
          th: "กำหนดน้ำหนักร่วมกับผู้เชี่ยวชาญในพื้นที่ 101 คน แทนที่จะให้นักวิเคราะห์กำหนดเอง เป็นแนวทางที่ควรใช้ทบทวนน้ำหนักของเราร่วมกับเจ้าหน้าที่แม่สาย",
        },
      },
    ],
  },
];

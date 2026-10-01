"use client";

import { Fragment, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { LanguageToggle } from "./language-toggle";
import { useLanguage } from "@/lib/use-language";
import { POLICY_EVIDENCE, SIGNED_SCORING_FRAME } from "@/lib/policy-evidence";
import { competitionPagesAvailable, MAE_SAI_REPLAY_ROUTE } from "@/lib/policy-links";
import type { Language } from "@/lib/types";
import styles from "./policy-page.module.css";

type Translate = (en: string, th: string) => string;

const sources = [
  { title: "National disaster plan · 2021–2027", th: "แผนป้องกันและบรรเทาสาธารณภัยแห่งชาติ พ.ศ. 2564–2570", owner: { en: "DDPM", th: "กรมป้องกันและบรรเทาสาธารณภัย (ปภ.)" }, url: "https://catalog.disaster.go.th/dataset/dpm-gd007" },
  { title: "The plan’s five strategies", th: "ยุทธศาสตร์ทั้งห้าของแผนแห่งชาติ", owner: { en: "ONEP", th: "สำนักงานนโยบายและแผนทรัพยากรธรรมชาติและสิ่งแวดล้อม (สผ.)" }, url: "https://eqmplatform.onep.go.th/public-plan/detail/1061" },
  { title: "Disaster Prevention and Mitigation Act · 2007", th: "พ.ร.บ. ป้องกันและบรรเทาสาธารณภัย พ.ศ. 2550", owner: { en: "Government-hosted text", th: "เอกสารจากหน่วยงานรัฐ" }, url: "https://www.maeyom.go.th/customers/webpage/datas/content/download/230824/e3647a8b.pdf" },
  { title: "Mae Sai preparedness exercises · May 2026", th: "การเตรียมฝึกซ้อมรับมืออุทกภัยแม่สาย พฤษภาคม 2569", owner: { en: "Chiang Rai PRD", th: "ประชาสัมพันธ์จังหวัดเชียงราย" }, url: "https://chiangrai.prd.go.th/th/content/category/detail/id/9/iid/503464" },
  { title: "Personal Data Protection Act · 2019", th: "พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562", owner: { en: "MDES · unofficial English translation", th: "กระทรวงดิจิทัลเพื่อเศรษฐกิจและสังคม · ฉบับแปลภาษาอังกฤษอย่างไม่เป็นทางการ" }, url: "https://www.mdes.go.th/law/detail/3577-Personal-Data-Protection-Act-B-E--2562--2019-" },
  { title: "LifeDee: routes and safe-area research · July 2026", th: "LifeDee: การพัฒนาเส้นทางอพยพและพื้นที่ปลอดภัย กรกฎาคม 2569", owner: { en: "GISTDA", th: "จิสด้า (GISTDA)" }, url: "https://gistda.or.th/news/evacuation-routes-and-safe-areas-for-vulnerable-groups-from-space-technology-to-strengthen-disaster-preparedness-and-to-drive-thailand-toward-resilient-city/" },
] as const;

const COMPONENT_COLORS = ["#087f8c", "#376d89", "#537d5b", "#896829", "#866781"] as const;
/** v1 class rules (`src/floodguard/scoring.py`, `assign_action_class`), binding under D6. */
const SCORING_RULES_URL = "https://github.com/TUPRAM/flood-guard/blob/129ff03b6fe5e4467faac165d365f8fefc5e03e0/src/floodguard/scoring.py#L187-L204";
const E_NEVER_SAFE = { en: "Class E never means safe.", th: "ระดับ E ไม่ได้หมายความว่าปลอดภัย ไม่ว่ากรณีใด" } as const;

/** A component name with a line-break opportunity after each slash, so "Vulnerability/context" can wrap in a narrow column. */
function breakableName(name: string): ReactNode {
  const parts = name.split("/");
  return parts.map((part, i) => <Fragment key={i}>{part}{i < parts.length - 1 && <>/<wbr /></>}</Fragment>);
}

export function PolicyPage() {
  const [language, setLanguage] = useLanguage("en");
  const [audience, setAudience] = useState(1);
  const [action, setAction] = useState(4);
  const t: Translate = (en, th) => language === "th" ? th : en;
  const chapters = [
    ["purpose", t("Purpose", "เป้าหมาย")], ["evidence", t("Worked example", "ตัวอย่างการคำนวณ")],
    ["signed-frame", t("Signed frame (D4)", "กรอบที่ลงนาม (D4)")], ["priorities", t("FPPS & actions", "FPPS และการดำเนินการ")],
    ["access", t("Access & equity", "การเข้าถึงและความเป็นธรรม")], ["thailand", t("Thai policy", "นโยบายไทย")],
    ["responsibility", t("Responsibility", "ความรับผิดชอบ")],
  ];
  const roles = [
    { name: t("Public", "ประชาชน"), question: t("What should my household prepare?", "ครัวเรือนควรเตรียมอะไร?"), answer: t("Understand possible disruption, prepare a household plan, and find official guidance with its source and time.", "เข้าใจผลกระทบที่อาจเกิดขึ้น เตรียมแผนครัวเรือน และค้นหาคำแนะนำจากหน่วยงานทางการพร้อมแหล่งที่มาและเวลา"), output: t("Plain-language context + practical preparedness", "บริบทที่เข้าใจง่าย + การเตรียมพร้อมที่ทำได้จริง"), route: "/public/" },
    { name: t("Planning", "การวางแผน"), question: t("Where should we focus, and why?", "ควรให้ความสำคัญกับพื้นที่ใด เพราะอะไร?"), answer: t("Compare communities, disrupted connections, and shelter options. Turn the findings into field checks and a reviewed planning brief.", "เปรียบเทียบชุมชน เส้นทางที่อาจขาด และทางเลือกศูนย์พักพิง ใช้ผลวิเคราะห์กำหนดการตรวจพื้นที่และจัดทำสรุปแผนที่ผ่านการทบทวน"), output: t("Reasons + options + a responsible reviewer", "เหตุผล + ทางเลือก + ผู้รับผิดชอบทบทวน"), route: "/command/" },
    { name: t("Studio", "สตูดิโอ"), question: t("Is the evidence fit for this decision?", "หลักฐานเหมาะกับการตัดสินใจนี้หรือไม่?"), answer: t("Inspect sources, model assumptions, coverage, and validation. Show what is measured, reconstructed, and still unknown.", "ตรวจแหล่งข้อมูล สมมติฐาน ขอบเขต และการตรวจสอบความถูกต้อง แยกสิ่งที่ตรวจวัด สิ่งที่จำลอง และสิ่งที่ยังไม่ทราบ"), output: t("Traceable sources + limits + reproducible methods", "แหล่งข้อมูลที่ตรวจย้อนกลับได้ + ข้อจำกัด + วิธีที่ทำซ้ำได้"), route: "/studio/" },
  ];
  const components = SIGNED_SCORING_FRAME.components.map((c, i) => ({
    key: c.key, weight: Math.round(c.weight * 100), name: t(c.name.en, c.name.th), description: t(c.question.en, c.question.th), color: COMPONENT_COLORS[i],
  }));
  const actions = [
    { letter: "A", title: t("Protect lives now", "ปกป้องชีวิตทันที"), text: t("Review assistance, transport, shelter, and medical continuity needs with responsible emergency authorities.", "ทบทวนความต้องการช่วยเหลือ การเดินทาง ศูนย์พักพิง และบริการแพทย์ร่วมกับหน่วยงานรับผิดชอบ"), owner: t("Emergency authorities", "หน่วยงานจัดการสาธารณภัย"), when: t("Exposure ≥70 and access gap ≥70", "ความล่อแหลม ≥70 และช่องว่างการเข้าถึง ≥70") },
    { letter: "B", title: t("Keep routes open", "รักษาเส้นทางให้สัญจรได้"), text: t("Prioritize road inspections and contingency connections. Road owners verify conditions and feasible alternatives.", "จัดลำดับการตรวจถนนและเส้นทางสำรอง ให้หน่วยงานเจ้าของถนนยืนยันสภาพและทางเลือกที่เป็นไปได้"), owner: t("Road owners + local coordinators", "เจ้าของถนน + ผู้ประสานงานท้องถิ่น"), when: t("Road criticality ≥75 and access gap ≥55", "ความสำคัญของถนน ≥75 และช่องว่างการเข้าถึง ≥55") },
    { letter: "C", title: t("Protect essential services", "คุ้มครองบริการจำเป็น"), text: t("Check continuity of clinics, schools, and utilities: access, staffing, supplies, and backup arrangements.", "ตรวจความต่อเนื่องของคลินิก โรงเรียน และสาธารณูปโภค ทั้งการเข้าถึง บุคลากร สิ่งของ และแผนสำรอง"), owner: t("Facility operators + local teams", "ผู้ดูแลสถานที่ + ทีมท้องถิ่น"), when: t("Exposure ≥65 and access gap ≥50", "ความล่อแหลม ≥65 และช่องว่างการเข้าถึง ≥50") },
    { letter: "D", title: t("Build resilience", "สร้างความพร้อมระยะยาว"), text: t("Compare drainage, route redundancy, accessible shelters, maintenance, and preparedness exercises.", "เปรียบเทียบการระบายน้ำ เส้นทางสำรอง ศูนย์พักพิงที่เข้าถึงได้ การบำรุงรักษา และการฝึกซ้อม"), owner: t("Local planning and budget teams", "ทีมแผนและงบประมาณท้องถิ่น"), when: t("Remaining cases after the earlier rules", "กรณีที่เหลือหลังตรวจเงื่อนไขก่อนหน้า") },
    { letter: "E", title: t("Monitor and verify", "ติดตามและตรวจสอบ"), text: t("Assign the next evidence check. Low confidence always gives Class E, even when possible consequences are serious.", "กำหนดการตรวจสอบหลักฐานขั้นถัดไป ความเชื่อมั่นต่ำทำให้เป็นระดับ E เสมอ แม้ผลกระทบที่เป็นไปได้จะรุนแรง"), owner: t("Evidence reviewers + field teams", "ผู้ทบทวนหลักฐาน + ทีมตรวจพื้นที่"), when: t("Low confidence OR FPPS <35 — checked first", "ความเชื่อมั่นต่ำ หรือ FPPS <35 — ตรวจเงื่อนไขนี้ก่อน") },
  ];
  const selectedRole = roles[audience];
  const selectedAction = actions[action];
  const linksToCompetitionPages = competitionPagesAvailable();

  return <main id="main-content" className={styles.page} lang={language}>
    <header className={styles.header}>
      <Link href="/" prefetch={false} className={styles.brand} aria-label={t("FloodGuard home", "หน้าแรก FloodGuard")}>FloodGuard<span>.</span></Link>
      <span className={styles.headerLabel}>{t("Policy & public value", "นโยบายและประโยชน์ต่อสังคม")}</span>
      <LanguageToggle language={language} onChange={setLanguage} />
      <Link href="/" prefetch={false} className={styles.back}>{t("Back to the story", "กลับสู่เรื่องราว")} <span aria-hidden="true">↗</span></Link>
    </header>

    <div className={styles.container}>
      <section className={styles.hero} id="purpose" aria-labelledby="policy-title">
        <div>
          <p className={styles.eyebrow}>{t("COMMUNICATION & POLICY · MENTORING BRIEF", "การสื่อสารและนโยบาย · เอกสารประกอบการให้คำปรึกษา")}</p>
          <h1 id="policy-title">{t("From flood evidence", "จากหลักฐานน้ำท่วม")}<br /><span>{t("to better preparedness.", "สู่การเตรียมพร้อมที่ดีขึ้น")}</span></h1>
          <p className={styles.lead}>{t("Understand who could lose access, which connections matter, and what local teams should check next.", "เข้าใจว่าใครอาจสูญเสียการเข้าถึง เส้นทางใดสำคัญ และทีมท้องถิ่นควรตรวจสอบอะไรต่อ")}</p>
          <a className={styles.primary} href="#evidence">{t("Start with a worked example", "เริ่มจากตัวอย่างการคำนวณ")} <span aria-hidden="true">↓</span></a>
          <p className={styles.heroNote}>{t("Preparedness and planning support. Not an official warning system.", "สนับสนุนการเตรียมพร้อมและวางแผน ไม่ใช่ระบบเตือนภัยอย่างเป็นทางการ")}</p>
        </div>
        <div className={styles.journey} role="group" aria-label={t("Evidence to decision", "จากหลักฐานสู่การตัดสินใจ")}>
          <p className={styles.journeyTitle}>{t("THE QUESTION AFTER THE FLOOD MAP", "คำถามถัดจากแผนที่น้ำท่วม")}</p>
          <ol>
            <li><span aria-hidden="true">01</span><div><small>{t("EVIDENCE", "หลักฐาน")}</small><strong>{t("Where could water reach?", "น้ำอาจท่วมถึงที่ใด?")}</strong></div></li>
            <li><span aria-hidden="true">02</span><div><small>{t("CONSEQUENCE", "ผลกระทบ")}</small><strong>{t("Who could lose access?", "ใครอาจสูญเสียการเข้าถึง?")}</strong></div></li>
            <li><span aria-hidden="true">03</span><div><small>{t("PUBLIC VALUE", "ประโยชน์ต่อสังคม")}</small><strong>{t("What should we prepare?", "เราควรเตรียมอะไร?")}</strong></div></li>
          </ol>
          <p>{t("Evidence informs the choice. Responsible people make the decision.", "หลักฐานช่วยพิจารณาทางเลือก ผู้รับผิดชอบเป็นผู้ตัดสินใจ")}</p>
        </div>
      </section>
    </div>

    <nav className={styles.chapterNav} aria-label={t("On this page", "เนื้อหาในหน้านี้")}><div>{chapters.map(([id, label]) => <a href={`#${id}`} key={id}>{label}</a>)}</div></nav>

    <div className={styles.container}>
      <section className={styles.section} aria-labelledby="audiences-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("ONE EVIDENCE BASE", "หลักฐานร่วมกัน")}</p><h2 id="audiences-title">{t("Three views. Different decisions.", "สามมุมมอง การตัดสินใจต่างกัน")}</h2></div>
        <div className={styles.audienceLayout}>
          <div className={styles.roleButtons} role="group" aria-label={t("Choose an audience", "เลือกกลุ่มผู้ใช้")}>{roles.map((role, i) => <button key={role.route} type="button" aria-pressed={audience === i} aria-controls="policy-role" onClick={() => setAudience(i)}><span aria-hidden="true">0{i + 1}</span>{role.name}<span aria-hidden="true">↗</span></button>)}</div>
          <div id="policy-role" className={styles.rolePanel} aria-live="polite"><p className={styles.smallLabel}>{selectedRole.name}</p><h3>{selectedRole.question}</h3><p>{selectedRole.answer}</p><div className={styles.roleOutput}><span>{selectedRole.output}</span><a href={selectedRole.route}>{t("Open view", "เปิดมุมมอง")} <span aria-hidden="true">↗</span></a></div></div>
        </div>
      </section>

      <section id="evidence" className={`${styles.section} ${styles.evidence}`} aria-labelledby="evidence-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("01 · HISTORICAL WORKED EXAMPLE", "01 · ตัวอย่างการคำนวณย้อนหลัง")}</p><h2 id="evidence-title">{t(POLICY_EVIDENCE.title, POLICY_EVIDENCE.titleTh)}</h2><p>{t("Kept so mentors can see the score and the classes on real places. It predates the signed decisions below and is not the Mae Sai case score.", "เก็บไว้เพื่อให้ผู้ให้คำปรึกษาเห็นคะแนนและระดับบนพื้นที่จริง ตัวอย่างนี้เกิดก่อนมติที่ลงนามด้านล่าง และไม่ใช่คะแนนของกรณีแม่สาย")}</p></div>
        <PolicyEvidence language={language} />
        {linksToCompetitionPages && <ReplayLink t={t} />}
      </section>

      <SignedFrame t={t} />

      <section id="priorities" className={styles.section} aria-labelledby="priorities-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("03 · HOW FPPS AND THE CLASSES WORK", "03 · FPPS และระดับการดำเนินการทำงานอย่างไร")}</p><h2 id="priorities-title">{t("A priority score, with reasons.", "คะแนนความสำคัญที่อธิบายได้")}</h2><p>{t("The Flood Preparedness Priority Score (FPPS) combines five concerns on a 0–100 scale. The weights are project choices for review, not Thai warning levels.", "คะแนนลำดับความสำคัญในการเตรียมพร้อมรับน้ำท่วม (FPPS) รวมข้อพิจารณาห้าด้านเป็นคะแนน 0–100 น้ำหนักเป็นทางเลือกของโครงการเพื่อทบทวน ไม่ใช่ระดับเตือนภัยของไทย")}</p></div>
        <div className={styles.weightBar} aria-hidden="true">{components.map((c) => <div key={c.key} style={{ flex: c.weight, background: c.color }}>{c.weight}%</div>)}</div>
        <div className={styles.components}>{components.map((c) => <div key={c.key} style={{ "--component-color": c.color } as CSSProperties}><span className={styles.componentWeight}>{c.weight}%</span><h3>{breakableName(c.name)}</h3><p>{c.description}</p></div>)}</div>
        <div className={styles.scoreNote}><strong>{t("65 / 100 ≠ 65% flood probability", "65 / 100 ≠ โอกาสน้ำท่วม 65%")}</strong><span>{t("Read the score with its evidence, assumptions, and missing information.", "อ่านคะแนนควบคู่กับหลักฐาน สมมติฐาน และข้อมูลที่ยังขาด")}</span></div>
        <details className={styles.details}><summary>{t("How are the components interpreted?", "องค์ประกอบคะแนนหมายถึงอะไร?")}<span aria-hidden="true">+</span></summary><div>
          <p>{t("The default weights are flood likelihood 30%, exposure 25%, access gap 20%, road criticality 15%, and vulnerability/context 10%. In reconstruction studies, the flood component is a scenario inundation proxy, not a calibrated probability.", "น้ำหนักมาตรฐานคือโอกาสน้ำท่วม 30% ความล่อแหลม 25% ช่องว่างการเข้าถึง 20% ความสำคัญของถนน 15% และความเปราะบางหรือบริบท 10% ในงานจำลองย้อนหลัง องค์ประกอบน้ำท่วมเป็นตัวแทนขอบเขตน้ำตามสถานการณ์ ไม่ใช่ความน่าจะเป็นที่สอบเทียบแล้ว")}</p>
          <p>{t("Under D4 the scaling is frozen: each component is scored against a fixed, declared anchor (see the table above), never rescaled across a batch of areas. Terrain or remoteness proxies do not establish age, disability, or care needs. Check sensitivity: correlated inputs and changing weights can change rankings.", "ตาม D4 การปรับสเกลถูกกำหนดตายตัว: ทุกองค์ประกอบคิดคะแนนเทียบกับจุดอ้างอิงที่ประกาศไว้ (ดูตารางด้านบน) ไม่ปรับสเกลใหม่ตามกลุ่มพื้นที่ที่คำนวณพร้อมกัน ตัวแทนจากภูมิประเทศหรือความห่างไกลไม่สามารถระบุอายุ ความพิการ หรือความต้องการดูแล ควรตรวจความไว เพราะข้อมูลที่สัมพันธ์กันและน้ำหนักที่เปลี่ยนอาจเปลี่ยนลำดับความสำคัญ")}</p>
          <p>{t("Proposed rule: keep required missing inputs unavailable. Some older candidate calculations filled missing aggregates with zero; this is not evidence of zero risk.", "ข้อเสนอ: แสดงข้อมูลที่จำเป็นแต่ขาดว่าไม่พร้อมใช้งาน การคำนวณชุดเก่าบางส่วนแทนค่าที่ขาดด้วยศูนย์ ซึ่งไม่ใช่หลักฐานว่าไม่มีความเสี่ยง")}</p>
        </div></details>

        <div className={styles.actionsHeading}><h3>{t("A–E: what kind of attention?", "A–E: ควรให้ความสำคัญด้านใด?")}</h3><p>{t("Action families for review. Select one to explore.", "กลุ่มการดำเนินการเพื่อทบทวน เลือกเพื่อดูรายละเอียด")}</p></div>
        <div className={styles.actionButtons} role="group" aria-label={t("Explore action classes", "สำรวจระดับการดำเนินการ")}>{actions.map((a, i) => <button type="button" key={a.letter} aria-label={`${a.letter} · ${a.title}`} aria-pressed={action === i} aria-controls="policy-action" onClick={() => setAction(i)}><b>{a.letter}</b><span>{a.title}</span></button>)}</div>
        <div id="policy-action" className={styles.actionPanel} aria-live="polite"><span className={styles.actionLetter} aria-hidden="true">{selectedAction.letter}</span><div><h4>{selectedAction.title}</h4><p>{selectedAction.text}</p><p className={styles.actionOwner}>{t("Suggested reviewer", "ผู้ทบทวนที่เสนอ")}: {selectedAction.owner}</p></div></div>
        <p className={styles.caution}><span aria-hidden="true">↳</span> <strong>{t(E_NEVER_SAFE.en, E_NEVER_SAFE.th)}</strong> {t("Official instructions and credible immediate threats take precedence over this planning index.", "คำสั่งทางการและภัยเฉพาะหน้าที่มีหลักฐานต้องได้รับความสำคัญเหนือดัชนีวางแผนนี้")}</p>
        <details className={styles.details}><summary>{t("See the exact decision rules", "ดูเงื่อนไขการจัดระดับ")}<span aria-hidden="true">+</span></summary><div>
          <p>{t("Evaluate in this order. A–D require confidence above low and FPPS ≥35. These are the v1 project thresholds, binding under D6; they are not official alert categories.", "พิจารณาตามลำดับนี้ A–D ต้องมีความเชื่อมั่นสูงกว่าระดับต่ำและ FPPS ≥35 เงื่อนไขเหล่านี้เป็นเกณฑ์ v1 ของโครงการที่มีผลผูกพันตาม D6 ไม่ใช่ระดับเตือนภัยทางการ")}</p>
          <ol className={styles.rules}>{[actions[4], ...actions.slice(0, 4)].map((a) => <li key={a.letter}><b>{a.letter}</b><span>{a.when}</span></li>)}</ol>
          <p>{t("Class E has two reasons, shown separately. Low confidence: “Monitor and obtain better evidence before action.” FPPS below 35: “Lower relative priority. This is not a safety statement.”", "ระดับ E มีสองเหตุผลที่แสดงแยกกัน ความเชื่อมั่นต่ำ: “ติดตามและหาหลักฐานที่ดีขึ้นก่อนดำเนินการ” FPPS ต่ำกว่า 35: “ลำดับความสำคัญเชิงเปรียบเทียบต่ำกว่า ไม่ใช่ข้อความยืนยันความปลอดภัย”")}</p>
          <a href={SCORING_RULES_URL}>{t("Inspect the v1 class rules (scoring.py)", "ตรวจสอบกฎการจัดระดับ v1 (scoring.py)")} ↗</a>
        </div></details>
      </section>

      <section id="access" className={styles.section} aria-labelledby="access-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("04 · BEYOND THE SCORE", "04 · มากกว่าคะแนน")}</p><h2 id="access-title">{t("A dry home can still be cut off.", "บ้านไม่ท่วม ก็อาจขาดการเชื่อมต่อ")}</h2><p>{t("These definitions match the Mae Sai replay.", "นิยามเหล่านี้ตรงกับการย้อนดูแม่สาย")}</p></div>
        <div className={styles.accessGrid}>
          <article><span className={styles.topicIcon} aria-hidden="true">↝</span><h3>{t("Access", "การเข้าถึง")}</h3><p>{t("Can people reach an open, dry shelter? In the replay, a resident has access when one lies within a 2 km walk (about 30 minutes) along roads still passable; a road closes at 0.3 m of modelled water. Access is lost only by people who could reach one before the flood.", "ผู้คนไปถึงศูนย์พักพิงที่เปิดและแห้งได้หรือไม่? ในการย้อนดู ผู้อยู่อาศัยเข้าถึงได้เมื่อมีศูนย์พักพิงดังกล่าวภายในระยะเดิน 2 กม. (ประมาณ 30 นาที) ตามถนนที่ยังสัญจรได้ ถนนปิดเมื่อน้ำจำลองลึก 0.3 ม. การสูญเสียการเข้าถึงนับเฉพาะผู้ที่ไปถึงศูนย์พักพิงได้ก่อนน้ำท่วม")}</p><small>{t("A modelled route needs local verification.", "เส้นทางจากแบบจำลองต้องตรวจสอบในพื้นที่")}</small></article>
          <article><span className={styles.topicIcon} aria-hidden="true">≈</span><h3>{t("Equity", "ความเป็นธรรม")}</h3><p>{t("Evacuation Equity Gap: the rate at which the vulnerable proxy group loses access ÷ the rate for everyone else. Above 1.20 the group is more likely to lose access; below 0.80, less likely. Show the counts beside the ratio: equal rates can still mean poor access for everyone.", "ช่องว่างความเท่าเทียมในการอพยพ: อัตราการสูญเสียการเข้าถึงของกลุ่มเปราะบางตามตัวแทน ÷ อัตราของกลุ่มอื่น มากกว่า 1.20 หมายถึงกลุ่มนี้มีโอกาสสูญเสียการเข้าถึงมากกว่า ต่ำกว่า 0.80 หมายถึงน้อยกว่า แสดงจำนวนคนควบคู่กับอัตราส่วน เพราะอัตราเท่ากันอาจหมายถึงทุกกลุ่มเข้าถึงได้ไม่ดี")}</p><small>{t("“Vulnerable” here is a terrain/remoteness proxy (slopes of 8° or more, or 750 m or more from a drivable road), not age, disability or income.", "“กลุ่มเปราะบาง” ในที่นี้เป็นตัวแทนจากภูมิประเทศและความห่างไกล (ความลาดชัน 8° ขึ้นไป หรือห่างถนนที่รถวิ่งได้ 750 ม. ขึ้นไป) ไม่ใช่อายุ ความพิการ หรือรายได้")}</small></article>
          <article><span className={styles.topicIcon} aria-hidden="true">⌂</span><h3>{t("Shelters", "ศูนย์พักพิง")}</h3><p>{t("Check usable capacity, accessibility, staffing, opening status, and how people would reach the site. Shelter sets answer different questions (the sites reported in 2024 versus a ranked plan for residents whose homes flood at the peak), so compare them on several counts; no single number makes one set better.", "ตรวจความจุที่ใช้ได้จริง การเข้าถึง บุคลากร สถานะเปิดใช้งาน และวิธีเดินทางไปยังสถานที่ ชุดศูนย์พักพิงแต่ละชุดตอบคำถามต่างกัน (สถานที่ที่มีรายงานการใช้ในปี 2567 กับแผนจัดอันดับสำหรับผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด) จึงควรเปรียบเทียบหลายตัวเลข ไม่มีตัวเลขเดียวที่บอกได้ว่าชุดใดดีกว่า")}</p><small>{t("A mapped building is a candidate, not a confirmed shelter.", "อาคารบนแผนที่เป็นสถานที่ที่ต้องตรวจ ไม่ใช่ศูนย์พักพิงที่ยืนยันแล้ว")}</small></article>
        </div>
      </section>

      <section id="thailand" className={`${styles.section} ${styles.thailand}`} aria-labelledby="thailand-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("05 · FIT WITH THAI POLICY", "05 · การเชื่อมโยงกับนโยบายไทย")}</p><h2 id="thailand-title">{t("Support the people responsible.", "สนับสนุนผู้มีหน้าที่รับผิดชอบ")}</h2><p>{t("A practical starting point: local preparedness plans, exercises, and investment discussions.", "จุดเริ่มต้นที่ใช้ได้จริง: แผนเตรียมพร้อมท้องถิ่น การฝึกซ้อม และการหารือด้านการลงทุน")}</p></div>
        <div className={styles.policyRows}>
          <article><span>01</span><div><h3>{t("National direction", "ทิศทางระดับชาติ")}</h3><p>{t("The 2021–2027 disaster plan supports risk reduction, innovation, integrated response, and sustainable recovery.", "แผนสาธารณภัย พ.ศ. 2564–2570 สนับสนุนการลดความเสี่ยง นวัตกรรม การจัดการฉุกเฉินแบบบูรณาการ และการฟื้นฟูอย่างยั่งยืน")}</p></div><a href={sources[1].url} aria-label={t("Read the national plan strategies", "อ่านยุทธศาสตร์แผนแห่งชาติ")}>↗</a></article>
          <article><span>02</span><div><h3>{t("Local decisions", "การตัดสินใจในพื้นที่")}</h3><p>{t("Provincial, district, and local authorities retain their legal responsibilities. FloodGuard can supply evidence for their review.", "หน่วยงานจังหวัด อำเภอ และท้องถิ่นยังคงมีหน้าที่ตามกฎหมาย FloodGuard สามารถจัดทำหลักฐานเพื่อประกอบการทบทวน")}</p></div><a href={sources[2].url} aria-label={t("Read the disaster management Act", "อ่านกฎหมายป้องกันและบรรเทาสาธารณภัย")}>↗</a></article>
          <article><span>03</span><div><h3>{t("A Mae Sai pilot", "โครงการนำร่องแม่สาย")}</h3><p>{t("Use a tabletop exercise to compare route failures and shelter options. Record local feedback before considering wider use.", "ใช้การฝึกซ้อมบนโต๊ะเปรียบเทียบเส้นทางที่ขาดและทางเลือกศูนย์พักพิง บันทึกข้อเสนอแนะจากพื้นที่ก่อนพิจารณาขยายการใช้งาน")}</p></div><a href={sources[3].url} aria-label={t("Read Chiang Rai’s exercise announcement", "อ่านประกาศการฝึกซ้อมจังหวัดเชียงราย")}>↗</a></article>
        </div>
        <p className={styles.footnote}>{t("Proposed fit, not agency adoption. FPPS does not issue warnings, order evacuations, allocate budgets, or establish relief eligibility.", "เป็นข้อเสนอการประยุกต์ใช้ ไม่ใช่การรับรองจากหน่วยงาน FPPS ไม่ออกคำเตือน สั่งอพยพ จัดสรรงบประมาณ หรือตัดสินสิทธิรับความช่วยเหลือ")}</p>
      </section>

      <section id="responsibility" className={styles.section} aria-labelledby="responsibility-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("06 · PROPOSED GOVERNANCE", "06 · ข้อเสนอการกำกับดูแล")}</p><h2 id="responsibility-title">{t("Make every recommendation accountable.", "ทุกข้อเสนอควรมีผู้รับผิดชอบ")}</h2></div>
        <div className={styles.commitments}>
          <article><b>01</b><h3>{t("Show the evidence", "แสดงหลักฐาน")}</h3><p>{t("Source, date, version, confidence, and unknowns travel with each finding.", "แสดงแหล่งข้อมูล วันที่ รุ่น ความเชื่อมั่น และสิ่งที่ยังไม่ทราบควบคู่ทุกข้อค้นพบ")}</p></article>
          <article><b>02</b><h3>{t("Protect personal data", "คุ้มครองข้อมูลส่วนบุคคล")}</h3><p>{t("Publish aggregated needs. Define lawful purpose, access, and retention before receiving household records.", "เผยแพร่ความต้องการในภาพรวม กำหนดวัตถุประสงค์ที่ชอบด้วยกฎหมาย การเข้าถึง และการเก็บรักษาก่อนรับข้อมูลครัวเรือน")}</p></article>
          <article><b>03</b><h3>{t("Include missing voices", "รับฟังกลุ่มที่ข้อมูลยังไม่ครอบคลุม")}</h3><p>{t("Check who population data misses. Invite communities to correct assumptions and priorities.", "ตรวจว่าข้อมูลประชากรขาดกลุ่มใด เปิดให้ชุมชนช่วยแก้ไขสมมติฐานและลำดับความสำคัญ")}</p></article>
          <article><b>04</b><h3>{t("Name the next step", "ระบุขั้นตอนถัดไป")}</h3><p>{t("Record an owner, a field check, and a review date. Evaluate the quality of decisions, not just model scores.", "บันทึกผู้รับผิดชอบ การตรวจพื้นที่ และวันทบทวน ประเมินคุณภาพการตัดสินใจควบคู่คะแนนแบบจำลอง")}</p></article>
        </div>
        <div className={styles.mentorPrompt}><div><p className={styles.eyebrow}>{t("THE MENTORING QUESTION", "คำถามสำหรับการให้คำปรึกษา")}</p><h3>{t("Which local decision should we improve first?", "เราควรช่วยให้การตัดสินใจใดในพื้นที่ดีขึ้นก่อน?")}</h3><p>{t("Agree on the decision, test the assumptions, and define the evidence needed for a responsible pilot.", "ตกลงโจทย์การตัดสินใจ ทดสอบสมมติฐาน และกำหนดหลักฐานที่จำเป็นสำหรับโครงการนำร่องที่มีความรับผิดชอบ")}</p></div><span aria-hidden="true">↗</span></div>
        <details className={styles.details} id="sources"><summary>{t("Sources & reading notes", "แหล่งข้อมูลและหมายเหตุ")}<span aria-hidden="true">+</span></summary><div><p>{t("Reviewed 29 September 2026. Legal responsibilities and published policy are distinct from our proposed product rules. Local operating plans and agency acceptance still need review.", "ทบทวน 29 กันยายน 2569 หน้าที่ตามกฎหมายและนโยบายที่เผยแพร่แยกจากข้อเสนอกติกาของผลิตภัณฑ์ ยังต้องทบทวนแผนปฏิบัติงานในพื้นที่และการยอมรับจากหน่วยงาน")}</p><ul className={styles.sourceList}>{sources.map((s) => <li key={s.url}><a href={s.url}>{t(s.title, s.th)} <span aria-hidden="true">↗</span></a><small>{t(s.owner.en, s.owner.th)}</small></li>)}</ul><p>{t("The May 2026 source announces exercises; it does not establish FloodGuard participation. GISTDA’s LifeDee work is institutional context, not an integration. PDPA exceptions have conditions; a product role alone does not authorize access to personal data.", "แหล่งข้อมูลเดือนพฤษภาคม 2569 เป็นประกาศการฝึกซ้อม ไม่ได้ยืนยันการเข้าร่วมของ FloodGuard งาน LifeDee ของจิสด้าเป็นบริบทของหน่วยงาน ไม่ใช่การเชื่อมระบบ ข้อยกเว้น PDPA มีเงื่อนไข บทบาทในผลิตภัณฑ์เพียงอย่างเดียวไม่ให้อำนาจเข้าถึงข้อมูลส่วนบุคคล")}</p></div></details>
      </section>
      <footer className={styles.footer}><Link href="/" prefetch={false} className={styles.brand}>FloodGuard<span>.</span></Link><p>{t("Evidence for preparedness. Decisions with responsibility.", "หลักฐานเพื่อเตรียมพร้อม การตัดสินใจที่มีความรับผิดชอบ")}</p><a href="#main-content">{t("Back to top", "กลับด้านบน")} ↑</a></footer>
    </div>
  </main>;
}

/** Share as a one-decimal percentage, e.g. 0.963 → "96.3%". */
function percent(share: number): string {
  return `${(share * 100).toFixed(1)}%`;
}

/**
 * The historical worked example. Every score it shows sits inside this one card, after the caveat that it was
 * computed on r2 with pre-D4 anchors before protocol v1b, so no number can be read without it.
 */
function PolicyEvidence({ language }: { language: Language }) {
  const t: Translate = (en, th) => language === "th" ? th : en;
  const evidence = POLICY_EVIDENCE;
  const coverage = evidence.reconstructionCoverage;
  const share = percent(evidence.reconstructionCoverageShare);
  const km2 = `${coverage.modelledKm2} ${t("of", "จาก")} ${coverage.districtKm2} ${t("km²", "ตร.กม.")}`;
  const current = evidence.currentReplay.revision;
  const chip = t(evidence.scoreLabel.en, evidence.scoreLabel.th);
  const [superseded] = evidence.supersededLabels;
  return <article className={styles.evidenceCard} data-testid="worked-example" aria-labelledby="worked-example-title">
    <div className={styles.evidenceTop}>
      <div><p className={styles.smallLabel}>{t("PRE-D4 WORKED EXAMPLE · STUDY OF 28 SEP 2026 · r2 RECONSTRUCTION", "ตัวอย่างก่อน D4 · งานศึกษา 28 ก.ย. 2569 · การจำลองรุ่น r2")}</p><h3 id="worked-example-title">{t("Mae Sai · September 2024", "แม่สาย · กันยายน 2567")}</h3><p>{t("A fixed historical scenario: 12 September, 12:00 ICT; assumed river stage 3.5 m; shelters reported in use in 2024.", "สถานการณ์ย้อนหลังที่กำหนดไว้: 12 กันยายน เวลา 12:00 น.; สมมติระดับน้ำ 3.5 ม.; ใช้ชุดศูนย์พักพิงที่มีรายงานการใช้งานในปี 2567")}</p></div>
      <span className={styles.status}>{t("Modelled · low confidence", "จากแบบจำลอง · ความเชื่อมั่นต่ำ")}</span>
    </div>
    <div className={styles.caveat} data-testid="worked-example-caveat">
      <h4>{t("Read this before any number", "โปรดอ่านก่อนดูตัวเลข")}</h4>
      <ul>
        <li><strong>{t("r2 reconstruction.", "การจำลองรุ่น r2")}</strong> {t(
          `Computed on r2, which modelled ${share} of the district (${km2}): its elevation tile stopped at 100°E, leaving parts of Ko Chang and Si Mueang Chum out. ${current}, the current replay, covers 100%.`,
          `คำนวณบนการจำลองรุ่น r2 ซึ่งครอบคลุม ${share} ของอำเภอ (${km2}) เพราะแผ่นข้อมูลความสูงที่ใช้สิ้นสุดที่ลองจิจูด 100°E บางส่วนของตำบลเกาะช้างและศรีเมืองชุมจึงไม่ได้จำลอง การย้อนดูปัจจุบัน (${current}) ครอบคลุม 100%`,
        )}</li>
        <li><strong>{t("Pre-D4 anchors.", "จุดอ้างอิงก่อน D4")}</strong> {t(
          "Its anchors (replay_fpps_anchor_v1) differ from the signed scoring frame (D4): flood saturates at 0.25 instead of 0.20; exposure mixes a share with a 5,000-person headcount instead of using the share only; vulnerability is a terrain/remoteness proxy at 0.25 instead of national P10/P90 anchors of the dependent share. Access and road criticality are defined differently too (table below).",
          "จุดอ้างอิงของตัวอย่างนี้ (replay_fpps_anchor_v1) ต่างจากกรอบคะแนนที่ลงนามแล้ว (D4): น้ำท่วมเต็มคะแนนที่ 0.25 แทน 0.20 ความล่อแหลมผสมสัดส่วนกับจำนวนคน 5,000 คน แทนการใช้สัดส่วนอย่างเดียว ความเปราะบางใช้ตัวแทนจากภูมิประเทศและความห่างไกลที่ 0.25 แทนจุดอ้างอิง P10/P90 ระดับประเทศของสัดส่วนประชากรพึ่งพิง การเข้าถึงและความสำคัญของถนนก็นิยามต่างกัน (ดูตารางด้านล่าง)",
        )}</li>
        <li><strong>{t("Before protocol v1b.", "ก่อนโปรโตคอล v1b")}</strong> {t(
          "Computed on 28–29 September 2026, before protocol v1b was hashed. It is not a protocol result and must not be cited as the Mae Sai case score. The D4/v1 scores will come from the planning assessment after v1b.",
          "คำนวณเมื่อ 28–29 กันยายน 2569 ก่อนบันทึกค่าแฮชของโปรโตคอล v1b จึงไม่ใช่ผลตามโปรโตคอล และห้ามอ้างเป็นคะแนนของกรณีแม่สาย คะแนนตาม D4/v1 จะมาจากการประเมินเพื่อการวางแผนหลัง v1b",
        )}</li>
      </ul>
    </div>
    <dl className={styles.studyStats}>{evidence.rankings.slice(0, 3).map((row) => <div key={row.id}><dt>{t(row.name, row.nameTh)}</dt><dd><span className={styles.chip}>{chip}</span><strong>{row.score.toFixed(2)}</strong><small>/ 100</small><p>{t("Pre-D4 scenario FPPS · Class E (low confidence)", "FPPS ตามสถานการณ์ก่อน D4 · ระดับ E (ความเชื่อมั่นต่ำ)")}</p></dd></div>)}</dl>
    {/* R2: a priority score carries its tier, its method source and its anchors, in view beside the numbers. */}
    <p className={styles.provenance} data-testid="worked-example-provenance">
      <span>{t("Tier", "ระดับหลักฐาน")}: {t(evidence.tier, evidence.tierTh)}</span>
      <span>{t("Method", "วิธีการ")}: <a href={evidence.methodUrl}><code>replay-fpps.ts</code> @ {evidence.sourceCommit.slice(0, 8)} <span aria-hidden="true">↗</span></a></span>
      <span>{t("Anchors", "จุดอ้างอิง")}: <code>{evidence.scenario.anchorVersion}</code> ({t("pre-D4", "ก่อน D4")})</span>
      <span>{t("Confidence", "ความเชื่อมั่น")}: {t("low", "ต่ำ")}</span>
    </p>
    <div className={styles.evidenceBottom}><b aria-hidden="true">E</b><p><strong>{t("All eight areas: Class E, monitor and verify.", "ทั้งแปดตำบล: ระดับ E ติดตามและตรวจสอบ")} {t(E_NEVER_SAFE.en, E_NEVER_SAFE.th)}</strong><br />{t("Low confidence forces E: monitor and obtain better evidence before action. These are illustrative planning estimates, not observed impacts or operational approval.", "ความเชื่อมั่นต่ำทำให้เป็นระดับ E: ติดตามและหาหลักฐานที่ดีขึ้นก่อนดำเนินการ ตัวเลขเหล่านี้เป็นค่าประมาณเพื่ออธิบายการวางแผน ไม่ใช่ผลกระทบที่ตรวจวัดหรือการอนุมัติปฏิบัติการ")}</p></div>
    <details className={`${styles.details} ${styles.studyDetails}`}><summary>{t("All eight areas, method & source", "ทั้งแปดตำบล วิธีการ และแหล่งข้อมูล")}<span aria-hidden="true">+</span></summary><div>
      <p>{t(`Reproduced once, on 29 September 2026, from the committed 28 September method and its original r2 inputs. The current replay (${current}) computes no FPPS and assigns no class (D7), so these numbers are not refreshed from it; they will be replaced by D4/v1 planning-assessment results after protocol v1b is hashed.`, `คำนวณซ้ำครั้งเดียวเมื่อ 29 กันยายน 2569 จากวิธีที่บันทึกไว้เมื่อ 28 กันยายน และข้อมูล r2 เดิม การย้อนดูปัจจุบัน (${current}) ไม่คำนวณ FPPS และไม่กำหนดระดับ (D7) จึงไม่ได้ปรับตัวเลขเหล่านี้จาก ${current} และจะแทนที่ด้วยผลการประเมินเพื่อการวางแผนตาม D4/v1 หลังบันทึกค่าแฮชของโปรโตคอล v1b`)}</p>
      <p className={styles.rankingsCaption} data-testid="worked-example-rankings-caption"><span className={styles.chip}>{chip}</span>{t("All eight are Class E because confidence is low.", "ทั้งแปดตำบลเป็นระดับ E เพราะความเชื่อมั่นต่ำ")} {t(E_NEVER_SAFE.en, E_NEVER_SAFE.th)}</p>
      <ol className={styles.rankings} aria-label={t("Pre-D4 scenario FPPS for all eight subdistricts; all Class E", "FPPS ตามสถานการณ์ก่อน D4 ทั้งแปดตำบล ทุกตำบลระดับ E")}>{evidence.rankings.map((row) => <li key={row.id}><span>{t(row.name, row.nameTh)}</span><i aria-hidden="true"><span style={{ width: `${row.score}%` }} /></i><b>{row.score.toFixed(2)}</b><span>{row.actionClass}</span></li>)}</ol>
      <dl className={styles.metadata}>
        <div><dt>{t("Scenario time", "เวลาของสถานการณ์")}</dt><dd><time dateTime={evidence.scenario.timestamp}>{t(evidence.scenario.label, "12 กันยายน 2567 เวลา 12:00 น. (ICT)")}</time></dd></div>
        <div><dt>{t("Source imagery window", "ช่วงเวลาภาพต้นทาง")}</dt><dd>{t("5–15 September 2024 (UTC)", "5–15 กันยายน 2567 (UTC)")}</dd></div>
        <div><dt>{t("Method source recorded", "บันทึกแหล่งวิธีการ")}</dt><dd><time dateTime={evidence.sourceCommittedAt}>{t("28 September 2026 · 14:45 ICT", "28 กันยายน 2569 · 14:45 น. (ICT)")}</time></dd></div>
        <div><dt>{t("Confidence", "ความเชื่อมั่น")}</dt><dd>{t("Low", "ต่ำ")} · {t(evidence.confidenceReason, evidence.confidenceReasonTh)}</dd></div>
        <div><dt>{t("Population basis", "ฐานข้อมูลประชากร")}</dt><dd>{t("WorldPop 2020 modelled residents", "จำนวนผู้อยู่อาศัยจากแบบจำลอง WorldPop 2020")}</dd></div>
        <div><dt>{t("Anchors (pre-D4)", "จุดอ้างอิง (ก่อน D4)")}</dt><dd><code>{evidence.scenario.anchorVersion}</code></dd></div>
        <div><dt>{t("Reconstruction coverage", "ความครอบคลุมของการจำลอง")}</dt><dd>{t(`r2 · ${share} of the district (${km2})`, `r2 · ${share} ของอำเภอ (${km2})`)}</dd></div>
        <div><dt>{t("Pinned source", "แหล่งข้อมูลรุ่นที่กำหนด")}</dt><dd><a href={evidence.sourceUrl}>{evidence.sourceCommit.slice(0, 8)} · {t("r2 manifest", "รายการข้อมูล r2")} ↗</a><small className={styles.supersededNote} data-testid="superseded-label-note">{t("Superseded label: this r2 manifest gives UNOSAT 3991 the role", "ป้ายที่ถูกแทนที่แล้ว: รายการข้อมูล r2 นี้ระบุบทบาทของ UNOSAT 3991 เป็น")} <code>{superseded.sourceValue}</code>{t(".", "")} {t(`Since ${superseded.decision} (30 Sep 2026) it is calibration-informed, not independent.`, `ตั้งแต่มติ ${superseded.decision} (30 ก.ย. 2569) ถือว่ามีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ`)}</small></dd></div>
        <div><dt>{t("Source manifest SHA-256", "SHA-256 ของรายการข้อมูลต้นทาง")}</dt><dd>{evidence.sourceSha256}</dd></div>
      </dl>
      <p>{t("The example uses a scenario inundation proxy, fixed pre-D4 anchors, and a terrain/remoteness proxy for vulnerability. Access assumes an open, dry shelter of the reported 2024 set within a 2 km walk along roads still passable; it does not allocate capacity or confirm safe travel. Local scientific validation and operational acceptance are not established.", "ตัวอย่างนี้ใช้ตัวแทนขอบเขตน้ำตามสถานการณ์ จุดอ้างอิงคงที่ก่อน D4 และตัวแทนจากภูมิประเทศและความห่างไกลสำหรับความเปราะบาง การเข้าถึงสมมติศูนย์พักพิงที่เปิดและแห้งของชุดที่มีรายงานปี 2567 ภายในระยะเดิน 2 กม. ตามถนนที่ยังสัญจรได้ ไม่ได้จัดสรรความจุหรือยืนยันความปลอดภัยในการเดินทาง ยังไม่มีการยืนยันความถูกต้องในพื้นที่และการยอมรับเพื่อปฏิบัติการ")}</p>
      <a href={evidence.methodUrl}>{t("Inspect the reproduced method", "ตรวจวิธีที่ใช้คำนวณซ้ำ")} ↗</a>
    </div></details>
  </article>;
}

/** One line on the replay that is live now, which is a narrative surface (D7), not a scored case. */
function ReplayLink({ t }: { t: Translate }) {
  const { calibrationAnchor, calibrationInformedCheck, revision } = POLICY_EVIDENCE.currentReplay;
  return <div className={styles.replayLink} data-testid="replay-link">
    <p><strong>{t(`Current replay (${revision}):`, `การย้อนดูปัจจุบัน (${revision}):`)}</strong> {t(
      `T1 scenario model with 100% district coverage, shown beside observed VIIRS flood maps, rain gauges and satellite imagery. GISTDA’s 10 Sep flooded-area figure (about ${calibrationAnchor.reportedKm2} km²) sets a stage knot, so it is a calibration anchor, and the UNOSAT 3991 size check is calibration-informed, not independent (${calibrationInformedCheck.decision}). The 16 Sep Sentinel-1 radar pass was used to tune the recession, so that size comparison is calibration-informed too. It computes no FPPS and assigns no class (D7).`,
      `แบบจำลองสถานการณ์ระดับ T1 ครอบคลุมอำเภอ 100% แสดงคู่กับแผนที่น้ำท่วม VIIRS สถานีวัดฝน และภาพดาวเทียมที่สังเกตการณ์จริง ตัวเลขพื้นที่น้ำท่วมของจิสด้าวันที่ 10 ก.ย. (ประมาณ ${calibrationAnchor.reportedKm2} ตร.กม.) ใช้ปรับจุดระดับน้ำ จึงเป็นจุดอ้างอิงที่ใช้ปรับแบบจำลอง และการตรวจขนาดกับ UNOSAT 3991 มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ (${calibrationInformedCheck.decision}) ภาพเรดาร์ Sentinel-1 วันที่ 16 ก.ย. ใช้ปรับช่วงน้ำลด การเทียบขนาดกับภาพนั้นจึงมีส่วนในการปรับแบบจำลองเช่นกัน การย้อนดูนี้ไม่คำนวณ FPPS และไม่กำหนดระดับ (D7)`,
    )}</p>
    <a href={MAE_SAI_REPLAY_ROUTE}>{t("Open the Mae Sai replay", "เปิดการย้อนดูแม่สาย")} <span aria-hidden="true">↗</span></a>
  </div>;
}

/** The signed scoring frame (D4) beside what the worked example used, plus the D6/D7 rules that bind this page. */
function SignedFrame({ t }: { t: Translate }) {
  const header = { component: t("Component", "องค์ประกอบ"), weight: t("Weight", "น้ำหนัก"), signed: t("D4 definition and anchor", "นิยามและจุดอ้างอิงตาม D4"), worked: t("The worked example used instead", "สิ่งที่ตัวอย่างใช้แทน") };
  return <section id="signed-frame" className={styles.section} aria-labelledby="signed-frame-title">
    <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("02 · SIGNED 30 SEPTEMBER 2026", "02 · ลงนาม 30 กันยายน 2569")}</p><h2 id="signed-frame-title">{t("The signed scoring frame (D4)", "กรอบคะแนนที่ลงนามแล้ว (D4)")}</h2><p>{t("Recorded in the team’s decision log, docs/decision-log-d1-d16.md. Any FPPS shown after protocol v1b uses these fixed anchors and the AGENTS.md weights; the worked example above predates them.", "บันทึกไว้ในบันทึกมติของทีม docs/decision-log-d1-d16.md FPPS ที่แสดงหลังโปรโตคอล v1b จะใช้จุดอ้างอิงคงที่เหล่านี้และน้ำหนักตาม AGENTS.md ตัวอย่างด้านบนเกิดก่อนกรอบนี้")}</p></div>
    <div className={styles.frameTable}>
      <table role="table" data-testid="signed-frame-table">
        <caption>{t("Five FPPS components: weight, D4 definition, and what the worked example used instead", "องค์ประกอบ FPPS ทั้งห้า: น้ำหนัก นิยามตาม D4 และสิ่งที่ตัวอย่างใช้แทน")}</caption>
        <thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">{header.component}</th><th role="columnheader" scope="col">{header.weight}</th><th role="columnheader" scope="col">{header.signed}</th><th role="columnheader" scope="col">{header.worked}</th></tr></thead>
        <tbody role="rowgroup">{SIGNED_SCORING_FRAME.components.map((c) => <tr role="row" key={c.key}>
          <th role="rowheader" scope="row">{breakableName(t(c.name.en, c.name.th))}</th>
          <td role="cell" className={styles.weight} data-label={header.weight}>{c.weight.toFixed(2)}</td>
          <td role="cell" data-label={header.signed}>{t(c.signed.en, c.signed.th)}</td>
          <td role="cell" data-label={header.worked}>{t(c.workedExample.en, c.workedExample.th)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className={styles.frameNote}>{t("Disclosure: the 0.20 flood anchor was chosen after seeing the data, so 0.10 and 0.30 run as sensitivity checks.", "การเปิดเผย: จุดอ้างอิงน้ำท่วม 0.20 เลือกหลังจากเห็นข้อมูลแล้ว จึงตรวจความไวที่ 0.10 และ 0.30 ด้วย")}</p>
    <ul className={styles.decisions}>
      <li><b>D6</b><span>{t("The v1 class rules (scoring.py) stay binding. The v2 triggers appear only as a labelled secondary axis.", "เกณฑ์การจัดระดับ v1 (scoring.py) ยังมีผลผูกพัน เกณฑ์ v2 แสดงได้เฉพาะเป็นแกนรองที่ระบุชัดเจน")}</span></li>
      <li><b>D7</b><span>{t("The Mae Sai replay is a narrative surface, not a scored case: it computes no FPPS and assigns no class.", "การย้อนดูแม่สายเป็นพื้นที่เล่าเรื่อง ไม่ใช่กรณีที่ให้คะแนน: ไม่คำนวณ FPPS และไม่กำหนดระดับ")}</span></li>
      <li><b>v1b</b><span>{t("No FPPS, class or ensemble is computed until protocol v1b is hashed. This page computes none; it only shows the recorded example.", "ไม่มีการคำนวณ FPPS ระดับ หรือชุดการจำลองจนกว่าจะบันทึกค่าแฮชของโปรโตคอล v1b หน้านี้ไม่คำนวณสิ่งใด แสดงเพียงตัวอย่างที่บันทึกไว้")}</span></li>
    </ul>
  </section>;
}

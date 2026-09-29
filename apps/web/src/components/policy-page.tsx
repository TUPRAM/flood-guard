"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { LanguageToggle } from "./language-toggle";
import { useLanguage } from "@/lib/use-language";
import { POLICY_EVIDENCE } from "@/lib/policy-evidence";
import styles from "./policy-page.module.css";

const sources = [
  { title: "National disaster plan · 2021–2027", th: "แผนป้องกันและบรรเทาสาธารณภัยแห่งชาติ พ.ศ. 2564–2570", owner: "DDPM / ปภ.", url: "https://catalog.disaster.go.th/dataset/dpm-gd007" },
  { title: "The plan’s five strategies", th: "ยุทธศาสตร์ทั้งห้าของแผนแห่งชาติ", owner: "ONEP / สผ.", url: "https://eqmplatform.onep.go.th/public-plan/detail/1061" },
  { title: "Disaster Prevention and Mitigation Act · 2007", th: "พ.ร.บ. ป้องกันและบรรเทาสาธารณภัย พ.ศ. 2550", owner: "Government-hosted text / เอกสารจากหน่วยงานรัฐ", url: "https://www.maeyom.go.th/customers/webpage/datas/content/download/230824/e3647a8b.pdf" },
  { title: "Mae Sai preparedness exercises · May 2026", th: "การเตรียมฝึกซ้อมรับมืออุทกภัยแม่สาย พฤษภาคม 2569", owner: "Chiang Rai PRD / ประชาสัมพันธ์จังหวัดเชียงราย", url: "https://chiangrai.prd.go.th/th/content/category/detail/id/9/iid/503464" },
  { title: "Personal Data Protection Act · 2019", th: "พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562", owner: "MDES · unofficial English translation / ฉบับแปลอังกฤษอย่างไม่เป็นทางการ", url: "https://www.mdes.go.th/law/detail/3577-Personal-Data-Protection-Act-B-E--2562--2019-" },
  { title: "LifeDee: routes and safe-area research · July 2026", th: "LifeDee: การพัฒนาเส้นทางอพยพและพื้นที่ปลอดภัย กรกฎาคม 2569", owner: "GISTDA / จิสด้า", url: "https://gistda.or.th/news/evacuation-routes-and-safe-areas-for-vulnerable-groups-from-space-technology-to-strengthen-disaster-preparedness-and-to-drive-thailand-toward-resilient-city/" },
] as const;

export function PolicyPage() {
  const [language, setLanguage] = useLanguage("en");
  const [audience, setAudience] = useState(1);
  const [action, setAction] = useState(4);
  const t = (en: string, th: string) => language === "th" ? th : en;
  const chapters = [
    ["purpose", t("Purpose", "เป้าหมาย")], ["evidence", t("Latest study", "งานศึกษาล่าสุด")],
    ["priorities", t("FPPS & actions", "FPPS และการดำเนินการ")], ["access", t("Access & equity", "การเข้าถึงและความเป็นธรรม")],
    ["thailand", t("Thai policy", "นโยบายไทย")], ["responsibility", t("Responsibility", "ความรับผิดชอบ")],
  ];
  const roles = [
    { name: t("Public", "ประชาชน"), question: t("What should my household prepare?", "ครัวเรือนควรเตรียมอะไร?"), answer: t("Understand possible disruption, prepare a household plan, and find official guidance with its source and time.", "เข้าใจผลกระทบที่อาจเกิดขึ้น เตรียมแผนครัวเรือน และค้นหาคำแนะนำจากหน่วยงานทางการพร้อมแหล่งที่มาและเวลา"), output: t("Plain-language context + practical preparedness", "บริบทที่เข้าใจง่าย + การเตรียมพร้อมที่ทำได้จริง"), route: "/public/" },
    { name: t("Planning", "การวางแผน"), question: t("Where should we focus, and why?", "ควรให้ความสำคัญกับพื้นที่ใด เพราะอะไร?"), answer: t("Compare communities, disrupted connections, and shelter options. Turn the findings into field checks and a reviewed planning brief.", "เปรียบเทียบชุมชน เส้นทางที่อาจขาด และทางเลือกศูนย์พักพิง ใช้ผลวิเคราะห์กำหนดการตรวจพื้นที่และจัดทำสรุปแผนที่ผ่านการทบทวน"), output: t("Reasons + options + a responsible reviewer", "เหตุผล + ทางเลือก + ผู้รับผิดชอบทบทวน"), route: "/command/" },
    { name: t("Studio", "สตูดิโอ"), question: t("Is the evidence fit for this decision?", "หลักฐานเหมาะกับการตัดสินใจนี้หรือไม่?"), answer: t("Inspect sources, model assumptions, coverage, and validation. Show what is measured, reconstructed, and still unknown.", "ตรวจแหล่งข้อมูล สมมติฐาน ขอบเขต และการตรวจสอบความถูกต้อง แยกสิ่งที่ตรวจวัด สิ่งที่จำลอง และสิ่งที่ยังไม่ทราบ"), output: t("Traceable sources + limits + reproducible methods", "แหล่งข้อมูลที่ตรวจย้อนกลับได้ + ข้อจำกัด + วิธีที่ทำซ้ำได้"), route: "/studio/" },
  ];
  const components = [
    { weight: 30, name: t("Flood", "น้ำท่วม"), description: t("How much flooding?", "น้ำท่วมมากเพียงใด?"), color: "#087f8c" },
    { weight: 25, name: t("Exposure", "ความล่อแหลม"), description: t("Who is affected?", "ใครได้รับผลกระทบ?"), color: "#376d89" },
    { weight: 20, name: t("Access", "การเข้าถึง"), description: t("Who loses a connection?", "ใครสูญเสียการเชื่อมต่อ?"), color: "#537d5b" },
    { weight: 15, name: t("Roads", "ถนน"), description: t("Which routes matter?", "เส้นทางใดสำคัญ?"), color: "#896829" },
    { weight: 10, name: t("Vulnerability", "ความเปราะบาง"), description: t("Who faces extra barriers?", "ใครมีอุปสรรคเพิ่มเติม?"), color: "#866781" },
  ];
  const actions = [
    { letter: "A", title: t("Protect lives now", "ปกป้องชีวิต"), text: t("Review assistance, transport, shelter, and medical continuity needs with responsible emergency authorities.", "ทบทวนความต้องการช่วยเหลือ การเดินทาง ศูนย์พักพิง และบริการแพทย์ร่วมกับหน่วยงานรับผิดชอบ"), owner: t("Emergency authorities", "หน่วยงานจัดการสาธารณภัย"), when: t("Exposure ≥70 and access gap ≥70", "ความล่อแหลม ≥70 และช่องว่างการเข้าถึง ≥70") },
    { letter: "B", title: t("Keep routes open", "รักษาการเชื่อมต่อของเส้นทาง"), text: t("Prioritize road inspections and contingency connections. Road owners verify conditions and feasible alternatives.", "จัดลำดับการตรวจถนนและเส้นทางสำรอง ให้หน่วยงานเจ้าของถนนยืนยันสภาพและทางเลือกที่เป็นไปได้"), owner: t("Road owners + local coordinators", "เจ้าของถนน + ผู้ประสานงานท้องถิ่น"), when: t("Road criticality ≥75 and access gap ≥55", "ความสำคัญของถนน ≥75 และช่องว่างการเข้าถึง ≥55") },
    { letter: "C", title: t("Protect essential services", "คุ้มครองบริการจำเป็น"), text: t("Check continuity of clinics, schools, and utilities: access, staffing, supplies, and backup arrangements.", "ตรวจความต่อเนื่องของคลินิก โรงเรียน และสาธารณูปโภค ทั้งการเข้าถึง บุคลากร สิ่งของ และแผนสำรอง"), owner: t("Facility operators + local teams", "ผู้ดูแลสถานที่ + ทีมท้องถิ่น"), when: t("Exposure ≥65 and access gap ≥50", "ความล่อแหลม ≥65 และช่องว่างการเข้าถึง ≥50") },
    { letter: "D", title: t("Build resilience", "สร้างความพร้อมระยะยาว"), text: t("Compare drainage, route redundancy, accessible shelters, maintenance, and preparedness exercises.", "เปรียบเทียบการระบายน้ำ เส้นทางสำรอง ศูนย์พักพิงที่เข้าถึงได้ การบำรุงรักษา และการฝึกซ้อม"), owner: t("Local planning and budget teams", "ทีมแผนและงบประมาณท้องถิ่น"), when: t("Remaining cases after the earlier rules", "กรณีที่เหลือหลังตรวจเงื่อนไขก่อนหน้า") },
    { letter: "E", title: t("Monitor and verify", "ติดตามและตรวจสอบ"), text: t("Assign the next evidence check. Low confidence can require Class E even when possible consequences are serious.", "กำหนดการตรวจสอบหลักฐานขั้นถัดไป ความเชื่อมั่นต่ำอาจทำให้เป็นระดับ E แม้ผลกระทบที่เป็นไปได้จะรุนแรง"), owner: t("Evidence reviewers + field teams", "ผู้ทบทวนหลักฐาน + ทีมตรวจพื้นที่"), when: t("Low confidence OR FPPS <35 — checked first", "ความเชื่อมั่นต่ำ หรือ FPPS <35 — ตรวจเงื่อนไขนี้ก่อน") },
  ];
  const selectedRole = roles[audience];
  const selectedAction = actions[action];

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
          <a className={styles.primary} href="#evidence">{t("Start with the latest study", "เริ่มจากงานศึกษาล่าสุด")} <span aria-hidden="true">↓</span></a>
          <p className={styles.heroNote}>{t("Preparedness and planning support. Not an official warning system.", "สนับสนุนการเตรียมพร้อมและวางแผน ไม่ใช่ระบบเตือนภัยอย่างเป็นทางการ")}</p>
        </div>
        <div className={styles.journey} aria-label={t("Evidence to decision", "จากหลักฐานสู่การตัดสินใจ")}>
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
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("01 · CURRENT REFERENCE", "01 · ข้อมูลอ้างอิงปัจจุบัน")}</p><h2 id="evidence-title">{t("One study. A clear context.", "หนึ่งงานศึกษา บริบทชัดเจน")}</h2></div>
        <PolicyEvidence language={language} />
      </section>

      <section id="priorities" className={styles.section} aria-labelledby="priorities-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("02 · THE IMPLEMENTED METHOD", "02 · วิธีที่ใช้ในระบบ")}</p><h2 id="priorities-title">{t("A priority score, with reasons.", "คะแนนความสำคัญที่อธิบายได้")}</h2><p>{t("The Flood Preparedness Priority Score (FPPS) combines five concerns on a 0–100 scale. The weights are project choices for review, not Thai warning levels.", "คะแนนลำดับความสำคัญในการเตรียมพร้อมรับน้ำท่วม (FPPS) รวมข้อพิจารณาห้าด้านเป็นคะแนน 0–100 น้ำหนักเป็นทางเลือกของโครงการเพื่อทบทวน ไม่ใช่ระดับเตือนภัยของไทย")}</p></div>
        <div className={styles.weightBar} aria-hidden="true">{components.map((c) => <div key={c.weight} style={{ flex: c.weight, background: c.color }}>{c.weight}%</div>)}</div>
        <div className={styles.components}>{components.map((c) => <div key={c.weight} style={{ "--component-color": c.color } as CSSProperties}><span className={styles.componentWeight}>{c.weight}%</span><h3>{c.name}</h3><p>{c.description}</p></div>)}</div>
        <div className={styles.scoreNote}><strong>{t("65 / 100 ≠ 65% flood probability", "65 / 100 ≠ โอกาสน้ำท่วม 65%")}</strong><span>{t("Read the score with its evidence, assumptions, and missing information.", "อ่านคะแนนควบคู่กับหลักฐาน สมมติฐาน และข้อมูลที่ยังขาด")}</span></div>
        <details className={styles.details}><summary>{t("How are the components interpreted?", "องค์ประกอบคะแนนหมายถึงอะไร?")}<span aria-hidden="true">+</span></summary><div>
          <p>{t("The default weights are flood likelihood 30%, exposure 25%, access gap 20%, road criticality 15%, and vulnerability/context 10%. In reconstruction studies, the flood component is a scenario inundation proxy, not a calibrated probability.", "น้ำหนักมาตรฐานคือโอกาสน้ำท่วม 30% ความล่อแหลม 25% ช่องว่างการเข้าถึง 20% ความสำคัญของถนน 15% และความเปราะบางหรือบริบท 10% ในงานจำลองย้อนหลัง องค์ประกอบน้ำท่วมเป็นตัวแทนขอบเขตน้ำตามสถานการณ์ ไม่ใช่ความน่าจะเป็นที่สอบเทียบแล้ว")}</p>
          <p>{t("Normalization and group definitions belong to each study. Terrain or remoteness proxies do not establish age, disability, or care needs. Check sensitivity: correlated inputs and changing weights can change rankings.", "การปรับสเกลและนิยามกลุ่มขึ้นอยู่กับงานศึกษา ตัวแทนจากภูมิประเทศหรือความห่างไกลไม่สามารถระบุอายุ ความพิการ หรือความต้องการดูแล ควรตรวจความไว เพราะข้อมูลที่สัมพันธ์กันและน้ำหนักที่เปลี่ยนอาจเปลี่ยนลำดับความสำคัญ")}</p>
          <p>{t("Proposed rule: keep required missing inputs unavailable. Some older candidate calculations filled missing aggregates with zero; this is not evidence of zero risk.", "ข้อเสนอ: แสดงข้อมูลที่จำเป็นแต่ขาดว่าไม่พร้อมใช้งาน การคำนวณชุดเก่าบางส่วนแทนค่าที่ขาดด้วยศูนย์ ซึ่งไม่ใช่หลักฐานว่าไม่มีความเสี่ยง")}</p>
        </div></details>

        <div className={styles.actionsHeading}><h3>{t("A–E: what kind of attention?", "A–E: ควรให้ความสำคัญด้านใด?")}</h3><p>{t("Action families for review. Select one to explore.", "กลุ่มการดำเนินการเพื่อทบทวน เลือกเพื่อดูรายละเอียด")}</p></div>
        <div className={styles.actionButtons} role="group" aria-label={t("Explore action classes", "สำรวจระดับการดำเนินการ")}>{actions.map((a, i) => <button type="button" key={a.letter} aria-label={`${a.letter} · ${a.title}`} aria-pressed={action === i} aria-controls="policy-action" onClick={() => setAction(i)}><b>{a.letter}</b><span>{a.title}</span></button>)}</div>
        <div id="policy-action" className={styles.actionPanel} aria-live="polite"><span className={styles.actionLetter} aria-hidden="true">{selectedAction.letter}</span><div><h4>{selectedAction.title}</h4><p>{selectedAction.text}</p><p className={styles.actionOwner}>{t("Suggested reviewer", "ผู้ทบทวนที่เสนอ")}: {selectedAction.owner}</p></div></div>
        <p className={styles.caution}><span aria-hidden="true">↳</span> <strong>{t("Class E does not mean safe.", "ระดับ E ไม่ได้หมายความว่าปลอดภัย")}</strong> {t("Official instructions and credible immediate threats take precedence over this planning index.", "คำสั่งทางการและภัยเฉพาะหน้าที่มีหลักฐานต้องได้รับความสำคัญเหนือดัชนีวางแผนนี้")}</p>
        <details className={styles.details}><summary>{t("See the exact decision rules", "ดูเงื่อนไขการจัดระดับ")}<span aria-hidden="true">+</span></summary><div><p>{t("Evaluate in this order. A–D require confidence above low and FPPS ≥35. These are project thresholds, not official alert categories.", "พิจารณาตามลำดับนี้ A–D ต้องมีความเชื่อมั่นสูงกว่าระดับต่ำและ FPPS ≥35 เงื่อนไขเหล่านี้เป็นของโครงการ ไม่ใช่ระดับเตือนภัยทางการ")}</p><ol className={styles.rules}>{[actions[4], ...actions.slice(0, 4)].map((a) => <li key={a.letter}><b>{a.letter}</b><span>{a.when}</span></li>)}</ol><a href="https://github.com/TUPRAM/flood-guard/blob/129ff03b6fe5e4467faac165d365f8fefc5e03e0/src/floodguard/scoring.py#L187">{t("Inspect the scoring rules", "ตรวจสอบกฎการให้คะแนน")} ↗</a></div></details>
      </section>

      <section id="access" className={styles.section} aria-labelledby="access-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("03 · BEYOND THE SCORE", "03 · มากกว่าคะแนน")}</p><h2 id="access-title">{t("A dry home can still be cut off.", "บ้านไม่ท่วม ก็อาจขาดการเชื่อมต่อ")}</h2></div>
        <div className={styles.accessGrid}>
          <article><span className={styles.topicIcon} aria-hidden="true">↝</span><h3>{t("Access", "การเข้าถึง")}</h3><p>{t("Can people reach an operating service or shelter? State the travel mode, time limit, and network assumptions.", "ผู้คนไปถึงบริการหรือศูนย์พักพิงที่เปิดใช้งานได้หรือไม่? ระบุวิธีเดินทาง เวลาที่กำหนด และสมมติฐานโครงข่าย")}</p><small>{t("A modelled route needs local verification.", "เส้นทางจากแบบจำลองต้องตรวจสอบในพื้นที่")}</small></article>
          <article><span className={styles.topicIcon} aria-hidden="true">≈</span><h3>{t("Equity", "ความเป็นธรรม")}</h3><p>{t("Compare access-loss rates between clearly defined groups. Show affected counts as well as the ratio.", "เปรียบเทียบอัตราสูญเสียการเข้าถึงของกลุ่มที่นิยามชัดเจน แสดงจำนวนผู้ได้รับผลกระทบควบคู่กับอัตราส่วน")}</p><small>{t("Equal rates can still mean poor access for everyone.", "อัตราเท่ากันอาจหมายถึงทุกกลุ่มเข้าถึงได้ไม่ดี")}</small></article>
          <article><span className={styles.topicIcon} aria-hidden="true">⌂</span><h3>{t("Shelters", "ศูนย์พักพิง")}</h3><p>{t("Check usable capacity, accessibility, staffing, opening status, and how people would reach the site.", "ตรวจความจุที่ใช้ได้จริง การเข้าถึง บุคลากร สถานะเปิดใช้งาน และวิธีเดินทางไปยังสถานที่")}</p><small>{t("A mapped building is a candidate, not a confirmed shelter.", "อาคารบนแผนที่เป็นสถานที่ที่ต้องตรวจ ไม่ใช่ศูนย์พักพิงที่ยืนยันแล้ว")}</small></article>
        </div>
      </section>

      <section id="thailand" className={`${styles.section} ${styles.thailand}`} aria-labelledby="thailand-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("04 · FIT WITH THAI POLICY", "04 · การเชื่อมโยงกับนโยบายไทย")}</p><h2 id="thailand-title">{t("Support the people responsible.", "สนับสนุนผู้มีหน้าที่รับผิดชอบ")}</h2><p>{t("A practical starting point: local preparedness plans, exercises, and investment discussions.", "จุดเริ่มต้นที่ใช้ได้จริง: แผนเตรียมพร้อมท้องถิ่น การฝึกซ้อม และการหารือด้านการลงทุน")}</p></div>
        <div className={styles.policyRows}>
          <article><span>01</span><div><h3>{t("National direction", "ทิศทางระดับชาติ")}</h3><p>{t("The 2021–2027 disaster plan supports risk reduction, innovation, integrated response, and sustainable recovery.", "แผนสาธารณภัย พ.ศ. 2564–2570 สนับสนุนการลดความเสี่ยง นวัตกรรม การจัดการฉุกเฉินแบบบูรณาการ และการฟื้นฟูอย่างยั่งยืน")}</p></div><a href={sources[1].url} aria-label={t("Read the national plan strategies", "อ่านยุทธศาสตร์แผนแห่งชาติ")}>↗</a></article>
          <article><span>02</span><div><h3>{t("Local decisions", "การตัดสินใจในพื้นที่")}</h3><p>{t("Provincial, district, and local authorities retain their legal responsibilities. FloodGuard can supply evidence for their review.", "หน่วยงานจังหวัด อำเภอ และท้องถิ่นยังคงมีหน้าที่ตามกฎหมาย FloodGuard สามารถจัดทำหลักฐานเพื่อประกอบการทบทวน")}</p></div><a href={sources[2].url} aria-label={t("Read the disaster management Act", "อ่านกฎหมายป้องกันและบรรเทาสาธารณภัย")}>↗</a></article>
          <article><span>03</span><div><h3>{t("A Mae Sai pilot", "โครงการนำร่องแม่สาย")}</h3><p>{t("Use a tabletop exercise to compare route failures and shelter options. Record local feedback before considering wider use.", "ใช้การฝึกซ้อมบนโต๊ะเปรียบเทียบเส้นทางที่ขาดและทางเลือกศูนย์พักพิง บันทึกข้อเสนอแนะจากพื้นที่ก่อนพิจารณาขยายการใช้งาน")}</p></div><a href={sources[3].url} aria-label={t("Read Chiang Rai’s exercise announcement", "อ่านประกาศการฝึกซ้อมจังหวัดเชียงราย")}>↗</a></article>
        </div>
        <p className={styles.footnote}>{t("Proposed fit, not agency adoption. FPPS does not issue warnings, order evacuations, allocate budgets, or establish relief eligibility.", "เป็นข้อเสนอการประยุกต์ใช้ ไม่ใช่การรับรองจากหน่วยงาน FPPS ไม่ออกคำเตือน สั่งอพยพ จัดสรรงบประมาณ หรือตัดสินสิทธิรับความช่วยเหลือ")}</p>
      </section>

      <section id="responsibility" className={styles.section} aria-labelledby="responsibility-title">
        <div className={styles.sectionHeading}><p className={styles.eyebrow}>{t("05 · PROPOSED GOVERNANCE", "05 · ข้อเสนอการกำกับดูแล")}</p><h2 id="responsibility-title">{t("Make every recommendation accountable.", "ทุกข้อเสนอควรมีผู้รับผิดชอบ")}</h2></div>
        <div className={styles.commitments}>
          <article><b>01</b><h3>{t("Show the evidence", "แสดงหลักฐาน")}</h3><p>{t("Source, date, version, confidence, and unknowns travel with each finding.", "แสดงแหล่งข้อมูล วันที่ รุ่น ความเชื่อมั่น และสิ่งที่ยังไม่ทราบควบคู่ทุกข้อค้นพบ")}</p></article>
          <article><b>02</b><h3>{t("Protect personal data", "คุ้มครองข้อมูลส่วนบุคคล")}</h3><p>{t("Publish aggregated needs. Define lawful purpose, access, and retention before receiving household records.", "เผยแพร่ความต้องการในภาพรวม กำหนดวัตถุประสงค์ที่ชอบด้วยกฎหมาย การเข้าถึง และการเก็บรักษาก่อนรับข้อมูลครัวเรือน")}</p></article>
          <article><b>03</b><h3>{t("Include missing voices", "รับฟังกลุ่มที่ข้อมูลยังไม่ครอบคลุม")}</h3><p>{t("Check who population data misses. Invite communities to correct assumptions and priorities.", "ตรวจว่าข้อมูลประชากรขาดกลุ่มใด เปิดให้ชุมชนช่วยแก้ไขสมมติฐานและลำดับความสำคัญ")}</p></article>
          <article><b>04</b><h3>{t("Name the next step", "ระบุขั้นตอนถัดไป")}</h3><p>{t("Record an owner, a field check, and a review date. Evaluate the quality of decisions, not just model scores.", "บันทึกผู้รับผิดชอบ การตรวจพื้นที่ และวันทบทวน ประเมินคุณภาพการตัดสินใจควบคู่คะแนนแบบจำลอง")}</p></article>
        </div>
        <div className={styles.mentorPrompt}><div><p className={styles.eyebrow}>{t("THE MENTORING QUESTION", "คำถามสำหรับการให้คำปรึกษา")}</p><h3>{t("Which local decision should we improve first?", "เราควรช่วยให้การตัดสินใจใดในพื้นที่ดีขึ้นก่อน?")}</h3><p>{t("Agree on the decision, test the assumptions, and define the evidence needed for a responsible pilot.", "ตกลงโจทย์การตัดสินใจ ทดสอบสมมติฐาน และกำหนดหลักฐานที่จำเป็นสำหรับโครงการนำร่องที่มีความรับผิดชอบ")}</p></div><span aria-hidden="true">↗</span></div>
        <details className={styles.details} id="sources"><summary>{t("Sources & reading notes", "แหล่งข้อมูลและหมายเหตุ")}<span aria-hidden="true">+</span></summary><div><p>{t("Reviewed 29 September 2026. Legal responsibilities and published policy are distinct from our proposed product rules. Local operating plans and agency acceptance still need review.", "ทบทวน 29 กันยายน 2569 หน้าที่ตามกฎหมายและนโยบายที่เผยแพร่แยกจากข้อเสนอกติกาของผลิตภัณฑ์ ยังต้องทบทวนแผนปฏิบัติงานในพื้นที่และการยอมรับจากหน่วยงาน")}</p><ul className={styles.sourceList}>{sources.map((s) => <li key={s.url}><a href={s.url}>{t(s.title, s.th)} <span aria-hidden="true">↗</span></a><small>{s.owner}</small></li>)}</ul><p>{t("The May 2026 source announces exercises; it does not establish FloodGuard participation. GISTDA’s LifeDee work is institutional context, not an integration. PDPA exceptions have conditions; a product role alone does not authorize access to personal data.", "แหล่งข้อมูลเดือนพฤษภาคม 2569 เป็นประกาศการฝึกซ้อม ไม่ได้ยืนยันการเข้าร่วมของ FloodGuard งาน LifeDee ของจิสด้าเป็นบริบทของหน่วยงาน ไม่ใช่การเชื่อมระบบ ข้อยกเว้น PDPA มีเงื่อนไข บทบาทในผลิตภัณฑ์เพียงอย่างเดียวไม่ให้อำนาจเข้าถึงข้อมูลส่วนบุคคล")}</p></div></details>
      </section>
      <footer className={styles.footer}><Link href="/" prefetch={false} className={styles.brand}>FloodGuard<span>.</span></Link><p>{t("Evidence for preparedness. Decisions with responsibility.", "หลักฐานเพื่อเตรียมพร้อม การตัดสินใจที่มีความรับผิดชอบ")}</p><a href="#main-content">{t("Back to top", "กลับด้านบน")} ↑</a></footer>
    </div>
  </main>;
}

function PolicyEvidence({ language }: { language: "en" | "th" }) {
  const t = (en: string, th: string) => language === "th" ? th : en;
  const evidence = POLICY_EVIDENCE;
  return <>
    <div className={styles.evidenceCard}>
      <div className={styles.evidenceTop}>
        <div><p className={styles.smallLabel}>{t("PRIORITY STUDY · METHOD RECORDED 28 SEP 2026 · REPLAY r2", "งานศึกษาลำดับความสำคัญ · บันทึกวิธีการ 28 ก.ย. 2569 · รุ่น r2")}</p><h3>{t("Mae Sai · September 2024", "แม่สาย · กันยายน 2567")}</h3><p>{t("A fixed historical scenario: 12 September, 12:00 ICT; assumed river stage 3.5 m; shelters reported in use in 2024.", "สถานการณ์ย้อนหลังที่กำหนดไว้: 12 กันยายน เวลา 12:00 น.; สมมติระดับน้ำ 3.5 ม.; ใช้ชุดศูนย์พักพิงที่มีรายงานการใช้งานในปี 2567")}</p></div>
        <span className={styles.status}>{t("Modelled · low confidence", "จากแบบจำลอง · ความเชื่อมั่นต่ำ")}</span>
      </div>
      <dl className={styles.studyStats}>{evidence.rankings.slice(0, 3).map((row) => <div key={row.id}><dt>{t(row.name, row.nameTh)}</dt><dd><strong>{row.score.toFixed(2)}</strong><small>/ 100</small><p>{t("Scenario FPPS · Class E", "FPPS ตามสถานการณ์ · ระดับ E")}</p></dd></div>)}</dl>
      <div className={styles.evidenceBottom}><b aria-hidden="true">E</b><p><strong>{t("All eight areas: monitor and verify.", "ทั้งแปดตำบล: ติดตามและตรวจสอบ")}</strong><br />{t("Higher scores focus the review; low confidence keeps every action class at E. These are planning estimates, not observed impacts or operational approval.", "คะแนนสูงช่วยกำหนดจุดเน้นการทบทวน แต่ความเชื่อมั่นต่ำทำให้ทุกพื้นที่เป็นระดับ E เป็นค่าประมาณเพื่อวางแผน ไม่ใช่ผลกระทบที่ตรวจวัดหรือการอนุมัติปฏิบัติการ")}</p></div>
    </div>
    <details className={`${styles.details} ${styles.studyDetails}`}><summary>{t("All eight areas, method & source", "ทั้งแปดตำบล วิธีการ และแหล่งข้อมูล")}<span aria-hidden="true">+</span></summary><div>
      <p>{t("Reproduced on 29 September 2026 from the newest committed priority-study method found in the source review. The later r3 replay is a separate visualization revision and does not contain this FPPS update. This fixed example keeps its original r2 inputs.", "คำนวณซ้ำเมื่อ 29 กันยายน 2569 จากวิธีศึกษาลำดับความสำคัญฉบับบันทึกล่าสุดที่พบในการตรวจแหล่งข้อมูล รุ่นแสดงภาพ r3 เป็นงานแยกและไม่มีการปรับ FPPS นี้ ตัวอย่างนี้จึงใช้ข้อมูล r2 เดิมของงานศึกษา")}</p>
      <ol className={styles.rankings} aria-label={t("Scenario FPPS ranking; all Class E", "ลำดับ FPPS ตามสถานการณ์ ทุกพื้นที่ระดับ E")}>{evidence.rankings.map((row) => <li key={row.id}><span>{t(row.name, row.nameTh)}</span><i aria-hidden="true"><span style={{ width: `${row.score}%` }} /></i><b>{row.score.toFixed(2)}</b><span>{row.actionClass}</span></li>)}</ol>
      <dl className={styles.metadata}>
        <div><dt>{t("Scenario time", "เวลาของสถานการณ์")}</dt><dd><time dateTime={evidence.scenario.timestamp}>{t(evidence.scenario.label, "12 กันยายน 2567 เวลา 12:00 น. (ICT)")}</time></dd></div>
        <div><dt>{t("Method source recorded", "บันทึกแหล่งวิธีการ")}</dt><dd><time dateTime={evidence.sourceCommittedAt}>{t("28 September 2026 · 14:45 ICT", "28 กันยายน 2569 · 14:45 น. (ICT)")}</time></dd></div>
        <div><dt>{t("Population basis", "ฐานข้อมูลประชากร")}</dt><dd>{t("WorldPop 2020 modelled residents", "จำนวนผู้อยู่อาศัยจากแบบจำลอง WorldPop 2020")}</dd></div>
        <div><dt>{t("Normalization version", "รุ่นการปรับสเกล")}</dt><dd>{evidence.scenario.anchorVersion}</dd></div>
        <div><dt>{t("Pinned source", "แหล่งข้อมูลรุ่นที่กำหนด")}</dt><dd><a href={evidence.sourceUrl}>{evidence.sourceCommit.slice(0, 8)} · {t("r2 manifest", "รายการข้อมูล r2")} ↗</a></dd></div>
        <div><dt>{t("Source manifest SHA-256", "SHA-256 ของรายการข้อมูลต้นทาง")}</dt><dd>{evidence.sourceSha256}</dd></div>
      </dl>
      <p>{t("The study uses a scenario inundation proxy, fixed normalization anchors, and terrain/remoteness context. Access assumes a dry shelter within 2 km on modelled passable roads; it does not allocate capacity or confirm safe travel. Local scientific validation and operational acceptance are not established.", "งานศึกษาใช้ตัวแทนขอบเขตน้ำตามสถานการณ์ จุดอ้างอิงปรับสเกลคงที่ และบริบทภูมิประเทศหรือความห่างไกล การเข้าถึงสมมติศูนย์พักพิงไม่ท่วมภายใน 2 กม. ตามถนนที่แบบจำลองระบุว่าผ่านได้ ไม่ได้จัดสรรความจุหรือยืนยันความปลอดภัยในการเดินทาง ยังไม่มีการยืนยันความถูกต้องในพื้นที่และการยอมรับเพื่อปฏิบัติการ")}</p>
      <a href={evidence.methodUrl}>{t("Inspect the reproduced method", "ตรวจวิธีที่ใช้คำนวณซ้ำ")} ↗</a>
    </div></details>
  </>;
}

"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { LanguageToggle } from "./language-toggle";
import { useLanguage } from "@/lib/use-language";
import {
  POLICY_ATTENTION, POLICY_GOVERNMENT_POINTS, POLICY_GOVERNMENT_SOURCES, POLICY_GROUND_RULES, POLICY_PROPOSALS, POLICY_QUESTIONS, POLICY_READING,
} from "@/lib/policy-brief";
import { POLICY_CASE, policyCaseCount, type PolicyCaseRow } from "@/lib/policy-case";
import { SIGNED_SCORING_FRAME, type BilingualText } from "@/lib/policy-evidence";
import { POLICY_TECHNICAL_ROUTE } from "@/lib/policy-links";
import { POLICY_WEIGHT_TEST, weightTestShare } from "@/lib/policy-weight-test";
import base from "./policy-page.module.css";
import styles from "./policy-brief.module.css";

const COMPONENT_COLORS = ["#087f8c", "#376d89", "#537d5b", "#896829", "#866781"] as const;
const KO_CHANG = "TH570903";
const MAE_SAI = "TH570901";

/** What each part of the score counts, in the words of the policy document. */
const COMPONENT_PLAIN: Readonly<Record<string, BilingualText>> = {
  flood_likelihood_0_100: { en: "How much land floods", th: "พื้นที่ถูกน้ำท่วมมากเพียงใด" },
  exposure_0_100: { en: "Who lives in the flooded area", th: "ใครอาศัยอยู่ในพื้นที่น้ำท่วม" },
  access_gap_0_100: { en: "Who loses access they had to a hospital or a main road", th: "ใครสูญเสียการเข้าถึงโรงพยาบาลหรือถนนสายหลักที่เคยเข้าถึงได้" },
  road_criticality_0_100: { en: "Who loses every route", th: "ใครสูญเสียทุกเส้นทาง" },
  vulnerability_context_0_100: { en: "How many children and older people live there", th: "มีเด็กและผู้สูงอายุอาศัยอยู่มากเพียงใด" },
};

const wholePercent = (share: number): string => `${Math.round(share * 100)}%`;
const oneDecimal = (value: number): string => value.toFixed(1);

function row(unit: string): PolicyCaseRow {
  const found = POLICY_CASE.rows.find((item) => item.unit_id === unit);
  if (!found) throw new Error(`Case SE1 has no row for ${unit}.`);
  return found;
}

/**
 * The plain-language policy page, in the order of the team's policy document: what the government asks for, what we
 * propose, one example, how the score works, the five kinds of attention, the ground rules and the common questions.
 * The technical record (the signed scoring frame, the class rules, the table of the eight tambons and the earlier
 * worked example) is the page at `/policy/technical/`.
 */
export function PolicyBrief() {
  const [language, setLanguage] = useLanguage("en");
  const t = (en: string, th: string) => (language === "th" ? th : en);
  const tx = (text: BilingualText) => (language === "th" ? text.th : text.en);
  const source = (id: string) => POLICY_GOVERNMENT_SOURCES.find((item) => item.id === id)!;
  const chapters: [string, string][] = [
    ["government", t("What the government asks", "สิ่งที่ภาครัฐให้ความสำคัญ")], ["proposals", t("What we propose", "ข้อเสนอของเรา")],
    ["example", t("One example", "ตัวอย่างหนึ่งกรณี")], ["score", t("How the score works", "คะแนนทำงานอย่างไร")],
    ["attention", t("Five kinds of attention", "การให้ความสำคัญห้าแบบ")], ["rules", t("Ground rules", "หลักการพื้นฐาน")],
    ["questions", t("Common questions", "คำถามที่พบบ่อย")], ["reading", t("Sources", "แหล่งข้อมูล")],
  ];
  const koChang = row(KO_CHANG);
  const maeSai = row(MAE_SAI);
  const components = SIGNED_SCORING_FRAME.components.map((component, index) => ({
    key: component.key, weight: Math.round(component.weight * 100), plain: tx(COMPONENT_PLAIN[component.key]), color: COMPONENT_COLORS[index],
  }));
  const test = POLICY_WEIGHT_TEST;
  const equal = test.named.find((item) => item.id === "equal")!;
  const withoutAccess = test.named.find((item) => item.id === "without_access")!;
  const name = (unit: string) => (language === "th" ? test.units[unit].th : test.units[unit].en);
  const oneAtATime = {
    cases: test.one_at_a_time.length,
    firsts: test.one_at_a_time.filter((item) => item.first === KO_CHANG).length,
    same: test.one_at_a_time.filter((item) => item.same_order).length,
  };

  return <main id="main-content" className={base.page} lang={language}>
    <header className={base.header}>
      <Link href="/" prefetch={false} className={base.brand} aria-label={t("FloodGuard home", "หน้าแรก FloodGuard")}>FloodGuard<span>.</span></Link>
      <span className={base.headerLabel}>{t("Policy & public value", "นโยบายและประโยชน์ต่อสังคม")}</span>
      <LanguageToggle language={language} onChange={setLanguage} />
      <Link href="/" prefetch={false} className={base.back}>{t("Back to the story", "กลับสู่เรื่องราว")} <span aria-hidden="true">↗</span></Link>
    </header>

    <div className={base.container}>
      <section className={base.hero} id="purpose" aria-labelledby="policy-title">
        <div>
          <p className={base.eyebrow}>{t("POLICY BRIEF · A PROPOSAL, NOT A GOVERNMENT PLAN", "สรุปเชิงนโยบาย · ข้อเสนอ ไม่ใช่แผนของภาครัฐ")}</p>
          <h1 id="policy-title">{t("Flood maps show where the water goes.", "แผนที่น้ำท่วมบอกว่าน้ำไปที่ใด")}<br /><span>{t("We show who could be cut off.", "เราแสดงว่าใครอาจถูกตัดขาด")}</span></h1>
          <p className={base.lead}>{t(
            "FloodGuard helps local teams see which communities could lose their roads, hospitals and shelters in a flood, so preparation can start where it matters most.",
            "FloodGuard ช่วยให้ทีมในพื้นที่เห็นว่าชุมชนใดอาจสูญเสียถนน โรงพยาบาล และศูนย์พักพิงเมื่อเกิดน้ำท่วม เพื่อให้เริ่มเตรียมพร้อมในจุดที่สำคัญที่สุด",
          )}</p>
          <a className={base.primary} href="#government">{t("Start with what the government asks", "เริ่มจากสิ่งที่ภาครัฐให้ความสำคัญ")} <span aria-hidden="true">↓</span></a>
          <p className={base.heroNote} data-testid="policy-standing-note">{t(
            "Planning support only. Not an official warning. Local officials decide.",
            "สนับสนุนการวางแผนเท่านั้น ไม่ใช่การเตือนภัยอย่างเป็นทางการ เจ้าหน้าที่ในพื้นที่เป็นผู้ตัดสินใจ",
          )}</p>
        </div>
        <div className={base.journey} role="group" aria-label={t("Evidence to preparation", "จากหลักฐานสู่การเตรียมพร้อม")}>
          <p className={base.journeyTitle}>{t("THE QUESTION AFTER THE FLOOD MAP", "คำถามถัดจากแผนที่น้ำท่วม")}</p>
          <ol>
            <li><span aria-hidden="true">01</span><div><small>{t("EVIDENCE", "หลักฐาน")}</small><strong>{t("Where could water reach?", "น้ำอาจท่วมถึงที่ใด?")}</strong></div></li>
            <li><span aria-hidden="true">02</span><div><small>{t("CONSEQUENCE", "ผลกระทบ")}</small><strong>{t("Who could lose roads, hospitals or shelters?", "ใครอาจสูญเสียถนน โรงพยาบาล หรือศูนย์พักพิง?")}</strong></div></li>
            <li><span aria-hidden="true">03</span><div><small>{t("PREPARATION", "การเตรียมพร้อม")}</small><strong>{t("What should we check first?", "เราควรตรวจสอบอะไรก่อน?")}</strong></div></li>
          </ol>
          <p>{t("The government says → so we propose → here is one example → here is who decides.", "ภาครัฐกล่าวไว้ → เราจึงเสนอ → นี่คือตัวอย่าง → นี่คือผู้ตัดสินใจ")}</p>
        </div>
      </section>
    </div>

    <nav className={base.chapterNav} aria-label={t("On this page", "เนื้อหาในหน้านี้")}><div>{chapters.map(([id, label]) => <a href={`#${id}`} key={id}>{label}</a>)}</div></nav>

    <div className={base.container}>
      <section id="government" className={base.section} aria-labelledby="government-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("01 · WHAT THE GOVERNMENT IS FOCUSED ON", "01 · สิ่งที่ภาครัฐให้ความสำคัญ")}</p>
          <h2 id="government-title">{t("We did not invent this direction.", "เราไม่ได้คิดทิศทางนี้ขึ้นเอง")}</h2>
          <p>{t("Three government sources point the same way.", "แหล่งข้อมูลของภาครัฐสามแหล่งชี้ไปในทางเดียวกัน")}</p>
        </div>
        <div className={styles.points}>{POLICY_GOVERNMENT_POINTS.map((point, index) => <article key={point.id} data-testid={`policy-point-${point.id}`}>
          <span className={styles.number} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
          <div>
            <h3>{tx(point.title)}</h3>
            <p><b>{t("The government says:", "ภาครัฐกล่าวว่า:")}</b> {tx(point.says)}</p>
            <p className={styles.means}><b>{t("What it means:", "ความหมายสำหรับเรา:")}</b> {tx(point.means)}</p>
            <p className={styles.sourceLine}><b>{t("Sources:", "แหล่งข้อมูล:")}</b> {point.sources.map((item, i) => <span key={i}>{i > 0 && " · "}<a href={source(item.source).url}>{tx(item.label)}</a></span>)}</p>
          </div>
        </article>)}</div>
      </section>

      <section id="proposals" className={base.section} aria-labelledby="proposals-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("02 · WHAT WE PROPOSE", "02 · ข้อเสนอของเรา")}</p>
          <h2 id="proposals-title">{t("Three practical steps.", "สามขั้นตอนที่ทำได้จริง")}</h2>
          <p>{t("Based on this direction. None replaces an official plan.", "อิงจากทิศทางข้างต้น ไม่มีข้อใดใช้แทนแผนทางการ")}</p>
        </div>
        <div className={styles.proposals}>{POLICY_PROPOSALS.map((proposal, index) => <article key={proposal.id} data-testid={`policy-proposal-${proposal.id}`}>
          <span className={styles.number} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
          <h3>{tx(proposal.title)}</h3>
          <p>{tx(proposal.what)}</p>
          <dl>
            <div><dt>{t("Why now", "เหตุใดจึงควรทำตอนนี้")}</dt><dd>{tx(proposal.whyNow)}</dd></div>
            <div><dt>{t("FloodGuard supplies", "FloodGuard จัดหาให้")}</dt><dd>{tx(proposal.supplies)}</dd></div>
            <div><dt>{t("Who decides", "ผู้ตัดสินใจ")}</dt><dd>{tx(proposal.decides)}</dd></div>
          </dl>
        </article>)}</div>
      </section>

      <section id="example" className={`${base.section} ${base.evidence}`} aria-labelledby="example-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("03 · ONE EXAMPLE · A SCENARIO, NOT A REAL DAY", "03 · ตัวอย่างหนึ่งกรณี · สถานการณ์จำลอง ไม่ใช่วันที่เกิดขึ้นจริง")}</p>
          <h2 id="example-title">{t(
            "In our worst-case scenario, Ko Chang scores highest because its roads would fail, not because most of it floods.",
            "ในสถานการณ์เลวร้ายที่สุดของเรา ตำบลเกาะช้างได้คะแนนสูงสุดเพราะถนนจะใช้การไม่ได้ ไม่ใช่เพราะพื้นที่ส่วนใหญ่ถูกน้ำท่วม",
          )}</h2>
          <p>{t(
            "We tested a “worst season” scenario for eight tambons in Mae Sai district: every area mapped as flooded in 2024 is flooded at once.",
            "เราทดสอบสถานการณ์ “ฤดูที่เลวร้ายที่สุด” กับแปดตำบลในอำเภอแม่สาย โดยให้ทุกพื้นที่ที่เคยถูกบันทึกว่าน้ำท่วมในปี 2567 ท่วมพร้อมกัน",
          )}</p>
        </div>
        <div className={styles.example}>
          <article data-testid="policy-example-ko-chang">
            <p className={styles.exampleScore}><b>{oneDecimal(koChang.fpps_0_100)}</b><span>/ 100</span></p>
            <h3>{language === "th" ? koChang.name_th : koChang.name_en}</h3>
            <p>{t(
              `${wholePercent(koChang.residents_inside_the_layer / koChang.residents)} of residents live inside the flooded area, but every resident who had a road route to a hospital or main road (${policyCaseCount(koChang.residents_losing_every_route)} of ${policyCaseCount(koChang.residents_with_a_route_before)}) loses all routes.`,
              `ผู้อยู่อาศัย ${wholePercent(koChang.residents_inside_the_layer / koChang.residents)} อยู่ในพื้นที่น้ำท่วม แต่ผู้อยู่อาศัยทุกคนที่เคยมีเส้นทางถนนไปโรงพยาบาลหรือถนนสายหลัก (${policyCaseCount(koChang.residents_losing_every_route)} จาก ${policyCaseCount(koChang.residents_with_a_route_before)} คน) สูญเสียทุกเส้นทาง`,
            )}</p>
            <p className={styles.attention}>{t("Suggested attention: keep routes open.", "การให้ความสำคัญที่แนะนำ: รักษาเส้นทางให้สัญจรได้")}</p>
          </article>
          <article data-testid="policy-example-mae-sai">
            <p className={styles.exampleScore}><b>{oneDecimal(maeSai.fpps_0_100)}</b><span>/ 100</span></p>
            <h3>{t("Mae Sai town", "ตัวเมืองแม่สาย")}</h3>
            <p>{t(
              `${wholePercent(maeSai.residents_inside_the_layer / maeSai.residents)} of residents inside the flooded area, and ${wholePercent(maeSai.residents_losing_every_route / maeSai.residents_with_a_route_before)} of road-connected residents (${policyCaseCount(maeSai.residents_losing_every_route)} of ${policyCaseCount(maeSai.residents_with_a_route_before)}) lose every route. More people lose hospital access here (${policyCaseCount(maeSai.residents_losing_hospital_access)}) than anywhere else.`,
              `ผู้อยู่อาศัย ${wholePercent(maeSai.residents_inside_the_layer / maeSai.residents)} อยู่ในพื้นที่น้ำท่วม และผู้อยู่อาศัยที่เคยมีเส้นทางถนน ${wholePercent(maeSai.residents_losing_every_route / maeSai.residents_with_a_route_before)} (${policyCaseCount(maeSai.residents_losing_every_route)} จาก ${policyCaseCount(maeSai.residents_with_a_route_before)} คน) สูญเสียทุกเส้นทาง จำนวนผู้สูญเสียการเข้าถึงโรงพยาบาลที่นี่ (${policyCaseCount(maeSai.residents_losing_hospital_access)} คน) มากกว่าตำบลอื่นทุกแห่ง`,
            )}</p>
            <p className={styles.attention}>{t("Suggested attention: build resilience.", "การให้ความสำคัญที่แนะนำ: สร้างความพร้อมระยะยาว")}</p>
          </article>
        </div>
        <p className={styles.contrast}>{t(
          "A flood map alone would put Mae Sai town first. An access view shows why Ko Chang needs a separate plan.",
          "หากดูแผนที่น้ำท่วมอย่างเดียว ตัวเมืองแม่สายจะมาเป็นอันดับแรก มุมมองด้านการเข้าถึงแสดงว่าเหตุใดตำบลเกาะช้างจึงต้องมีแผนแยกต่างหาก",
        )}</p>
        <p className={base.caseNote} data-testid="policy-example-note"><strong>{t("Note:", "หมายเหตุ:")}</strong> {t(
          "this is a scenario, not a real day. Roads are modelled, not checked on the ground, and the published case does not yet say how stable each class is. Use it to decide what to check first, not what to do.",
          "นี่คือสถานการณ์จำลอง ไม่ใช่วันที่เกิดขึ้นจริง ถนนมาจากแบบจำลอง ยังไม่ได้ตรวจสอบในพื้นที่ และกรณีที่เผยแพร่ยังไม่ได้ระบุว่าระดับของแต่ละตำบลเสถียรเพียงใด ใช้เพื่อตัดสินใจว่าควรตรวจสอบอะไรก่อน ไม่ใช่เพื่อตัดสินใจว่าต้องทำอะไร",
        )} <a href={`${POLICY_TECHNICAL_ROUTE}#case`}>{t("All eight tambons, with the rules", "ทั้งแปดตำบล พร้อมกฎการจัดระดับ")} ↗</a></p>
      </section>

      <section id="score" className={base.section} aria-labelledby="score-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("04 · HOW THE SCORE WORKS", "04 · คะแนนทำงานอย่างไร")}</p>
          <h2 id="score-title">{t("The priority score compares places. It is not a probability.", "คะแนนลำดับความสำคัญใช้เปรียบเทียบพื้นที่ ไม่ใช่ความน่าจะเป็น")}</h2>
          <p>{t("A score of 65 out of 100 does not mean a 65% chance of flooding.", "คะแนน 65 จาก 100 ไม่ได้หมายถึงโอกาสน้ำท่วม 65%")}</p>
        </div>
        <div className={base.weightBar} aria-hidden="true">{components.map((c) => <div key={c.key} style={{ flex: c.weight, background: c.color }}>{c.weight}%</div>)}</div>
        <div className={base.components} data-testid="policy-five-things">{components.map((c) => <div key={c.key} style={{ "--component-color": c.color } as CSSProperties}>
          <span className={base.componentWeight}>{c.weight}%</span><h3>{c.plain}</h3>
        </div>)}</div>
        <p className={styles.plainNote}>{t(
          "These weights are our choices, open for review. They are not Thai warning levels. “People more likely to be left out” always means children under 15 and adults aged 60 or over, in the score and in the equity check alike. Shelter access is measured beside the score, not inside the published score.",
          "น้ำหนักเหล่านี้เป็นทางเลือกของเรา เปิดให้ทบทวนได้ และไม่ใช่ระดับการเตือนภัยของไทย “ผู้ที่มีแนวโน้มถูกมองข้าม” หมายถึงเด็กอายุต่ำกว่า 15 ปีและผู้ใหญ่อายุ 60 ปีขึ้นไปเสมอ ทั้งในคะแนนและในการตรวจสอบความเป็นธรรม การเข้าถึงศูนย์พักพิงวัดแยกไว้ข้างคะแนน ไม่ได้อยู่ในคะแนนที่เผยแพร่",
        )}</p>

        <div className={styles.weightTest} data-testid="policy-weight-test">
          <h3>{t("Does the result depend on these weights?", "ผลลัพธ์ขึ้นอยู่กับน้ำหนักเหล่านี้หรือไม่?")}</h3>
          <p>{t(
            "No study gives the right weights for a score like this. The guidance on composite indicators treats weights as value judgements: state them, and test what happens when they change. So we tested ours on the example above.",
            "ไม่มีงานศึกษาใดให้น้ำหนักที่ถูกต้องสำหรับคะแนนลักษณะนี้ แนวทางการสร้างดัชนีรวมถือว่าน้ำหนักเป็นการตัดสินเชิงคุณค่า จึงต้องระบุให้ชัดและทดสอบว่าเกิดอะไรขึ้นเมื่อน้ำหนักเปลี่ยน เราจึงทดสอบน้ำหนักของเรากับตัวอย่างข้างต้น",
          )}</p>
          <ul>
            <li data-testid="weight-test-equal">{t(
              `With five equal weights ${name(equal.order[0])} is still first: ${oneDecimal(equal.scores[KO_CHANG])} against ${oneDecimal(equal.scores[MAE_SAI])} for Mae Sai town.`,
              `เมื่อให้น้ำหนักเท่ากันทั้งห้าส่วน ${name(equal.order[0])}ยังเป็นอันดับแรก: ${oneDecimal(equal.scores[KO_CHANG])} เทียบกับ ${oneDecimal(equal.scores[MAE_SAI])} ของตัวเมืองแม่สาย`,
            )}</li>
            <li data-testid="weight-test-one-at-a-time">{oneAtATime.firsts === oneAtATime.cases && oneAtATime.same === oneAtATime.cases
              ? t(
                `With each weight halved or raised by half, one at a time, ${name(KO_CHANG)} stays first in all ${oneAtATime.cases} cases and the order of the eight tambons does not change.`,
                `เมื่อลดน้ำหนักแต่ละส่วนลงครึ่งหนึ่งหรือเพิ่มขึ้นครึ่งหนึ่งทีละส่วน ${name(KO_CHANG)}ยังเป็นอันดับแรกทั้ง ${oneAtATime.cases} กรณี และลำดับของทั้งแปดตำบลไม่เปลี่ยน`,
              )
              : t(
                `With each weight halved or raised by half, one at a time, ${name(KO_CHANG)} is first in ${oneAtATime.firsts} of ${oneAtATime.cases} cases and the order of the eight tambons is unchanged in ${oneAtATime.same}.`,
                `เมื่อลดน้ำหนักแต่ละส่วนลงครึ่งหนึ่งหรือเพิ่มขึ้นครึ่งหนึ่งทีละส่วน ${name(KO_CHANG)}เป็นอันดับแรกใน ${oneAtATime.firsts} จาก ${oneAtATime.cases} กรณี และลำดับของทั้งแปดตำบลไม่เปลี่ยนใน ${oneAtATime.same} กรณี`,
              )}</li>
            <li data-testid="weight-test-random">{t(
              `Across ${test.random.draws.toLocaleString("en-US")} random sets of weights, ${name(KO_CHANG)} is first in ${weightTestShare(test.random.share_first[KO_CHANG])} and the same four tambons lead in ${weightTestShare(test.random.share_same_first_four)}.`,
              `จากชุดน้ำหนักแบบสุ่ม ${test.random.draws.toLocaleString("en-US")} ชุด ${name(KO_CHANG)}เป็นอันดับแรกใน ${weightTestShare(test.random.share_first[KO_CHANG])} และสี่ตำบลแรกเป็นชุดเดิมใน ${weightTestShare(test.random.share_same_first_four)}`,
            )}</li>
            <li data-testid="weight-test-without-access">{t(
              `Only when the two access parts are left out does ${name(withoutAccess.order[0])} come first. Then the score is a flood map again.`,
              `มีเพียงเมื่อตัดองค์ประกอบการเข้าถึงทั้งสองส่วนออก ${name(withoutAccess.order[0])}จึงขึ้นเป็นอันดับแรก ซึ่งเท่ากับกลับไปดูแผนที่น้ำท่วมอย่างเดียว`,
            )}</li>
          </ul>
          <p>{t(
            "So the example does not rest on the exact weights. It rests on counting lost access at all. Two limits remain. Flood and exposure together hold 55% and move together, so the score leans towards where the water is. Age holds 10% because the open age data are a coarse model; indices that have better data on people give them more.",
            "ตัวอย่างนี้จึงไม่ได้ขึ้นกับค่าน้ำหนักที่แน่นอน แต่ขึ้นกับการนับการสูญเสียการเข้าถึงเข้าไปด้วย ยังมีข้อจำกัดสองข้อ น้ำท่วมกับการเปิดรับรวมกันมีน้ำหนัก 55% และเปลี่ยนไปด้วยกัน คะแนนจึงเอนไปทางที่ที่มีน้ำ ส่วนอายุมีน้ำหนัก 10% เพราะข้อมูลอายุแบบเปิดเป็นแบบจำลองที่หยาบ ดัชนีที่มีข้อมูลประชากรดีกว่าให้น้ำหนักกับส่วนนี้มากกว่า",
          )}</p>
          <p className={styles.sourceLine}>{t("Report only: the test changes no score, weight or class. ", "รายงานเท่านั้น: การทดสอบนี้ไม่เปลี่ยนคะแนน น้ำหนัก หรือระดับใด ")}
            <a href="#reading-index">{t("The research behind this test", "งานวิจัยเบื้องหลังการทดสอบนี้")} ↓</a> · <a href={`${POLICY_TECHNICAL_ROUTE}#signed-frame`}>{t("The exact definition of each part", "นิยามที่แน่นอนของแต่ละส่วน")} ↗</a></p>
        </div>
      </section>

      <section id="attention" className={base.section} aria-labelledby="attention-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("05 · FIVE KINDS OF ATTENTION", "05 · การให้ความสำคัญห้าแบบ")}</p>
          <h2 id="attention-title">{t("A letter says what kind of attention, not how bad.", "ตัวอักษรบอกว่าควรให้ความสำคัญด้านใด ไม่ได้บอกว่ารุนแรงเพียงใด")}</h2>
        </div>
        <ol className={styles.attentionList}>{POLICY_ATTENTION.map((item) => <li key={item.letter} data-letter={item.letter}>
          <b aria-hidden="true">{item.letter}</b><div><h3><span className={styles.srOnly}>{item.letter} · </span>{tx(item.title)}</h3><p>{tx(item.text)}</p></div>
        </li>)}</ol>
        <p className={base.caution}><span aria-hidden="true">↳</span> <strong>{t("Class E never means safe.", "ระดับ E ไม่ได้หมายความว่าปลอดภัย ไม่ว่ากรณีใด")}</strong> {t(
          "Official instructions and credible immediate threats take precedence over this planning score.",
          "คำสั่งทางการและภัยคุกคามเฉพาะหน้าที่น่าเชื่อถือมาก่อนคะแนนวางแผนนี้เสมอ",
        )}</p>
      </section>

      <section id="rules" className={base.section} aria-labelledby="rules-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("06 · GROUND RULES", "06 · หลักการพื้นฐาน")}</p>
          <h2 id="rules-title">{t("Evidence informs. Responsible people decide.", "หลักฐานช่วยพิจารณา ผู้รับผิดชอบเป็นผู้ตัดสินใจ")}</h2>
        </div>
        <div className={base.commitments}>{POLICY_GROUND_RULES.map((rule, index) => <article key={index}>
          <b>{String(index + 1).padStart(2, "0")}</b><h3>{tx(rule.title)}</h3><p>{tx(rule.text)}</p>
        </article>)}</div>
      </section>

      <section id="questions" className={base.section} aria-labelledby="questions-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("07 · COMMON QUESTIONS", "07 · คำถามที่พบบ่อย")}</p>
          <h2 id="questions-title">{t("Short answers.", "คำตอบสั้น ๆ")}</h2>
        </div>
        <dl className={styles.questions} data-testid="policy-questions">{POLICY_QUESTIONS.map((item, index) => <div key={index}>
          <dt>{tx(item.question)}</dt><dd>{tx(item.answer)}</dd>
        </div>)}</dl>
      </section>

      <section id="reading" className={base.section} aria-labelledby="reading-title">
        <div className={base.sectionHeading}>
          <p className={base.eyebrow}>{t("08 · SOURCES AND FURTHER READING", "08 · แหล่งข้อมูลและเอกสารอ่านเพิ่มเติม")}</p>
          <h2 id="reading-title">{t("Where each claim comes from.", "ข้ออ้างแต่ละข้อมาจากที่ใด")}</h2>
          <p>{t(
            "Links opened on 12 October 2026. A paper listed here supports an idea on this page; none endorses FloodGuard, and none gives our five weights.",
            "เปิดลิงก์ตรวจสอบเมื่อ 12 ตุลาคม 2569 งานวิจัยในรายการนี้สนับสนุนแนวคิดในหน้านี้ ไม่มีชิ้นใดรับรอง FloodGuard และไม่มีชิ้นใดกำหนดน้ำหนักทั้งห้าของเรา",
          )}</p>
        </div>
        <div className={styles.reading}>
          <section aria-labelledby="reading-government"><h3 id="reading-government">{t("Thai law and plans", "กฎหมายและแผนของไทย")}</h3>
            <ul data-testid="policy-government-sources">{POLICY_GOVERNMENT_SOURCES.map((item) => <li key={item.id}><a href={item.url}>{tx(item.title)}</a><span>{tx(item.owner)}</span></li>)}</ul>
          </section>
          {POLICY_READING.map((group) => <section key={group.id} aria-labelledby={`reading-${group.id}`}><h3 id={`reading-${group.id}`}>{tx(group.title)}</h3>
            <ul data-testid={`policy-reading-${group.id}`}>{group.items.map((item) => <li key={item.id}><a href={item.url} lang="en">{item.reference}</a><span>{tx(item.use)}</span></li>)}</ul>
          </section>)}
        </div>
        <p className={base.footnote}>{t(
          "The Thai text of this page was written by the project’s AI assistant and has not been reviewed by a native speaker.",
          "ข้อความภาษาไทยในหน้านี้เขียนโดยผู้ช่วย AI ของโครงการ และยังไม่ได้รับการตรวจทานโดยเจ้าของภาษา",
        )}</p>
        <div className={base.mentorPrompt}><div>
          <p className={base.eyebrow}>{t("FOR REVIEWERS", "สำหรับผู้ตรวจทาน")}</p>
          <h3>{t("The technical record", "บันทึกทางเทคนิค")}</h3>
          <p>{t(
            "The signed scoring frame, the class rules, the table of all eight tambons and the earlier worked example.",
            "กรอบการให้คะแนนที่ลงนาม กฎการจัดระดับ ตารางของทั้งแปดตำบล และตัวอย่างการคำนวณก่อนหน้า",
          )}</p>
        </div><a href={POLICY_TECHNICAL_ROUTE} data-testid="policy-technical-link">{t("Open the technical record", "เปิดบันทึกทางเทคนิค")} <span aria-hidden="true">↗</span></a></div>
      </section>
      <footer className={base.footer}><Link href="/" prefetch={false} className={base.brand}>FloodGuard<span>.</span></Link><p>{t("Evidence for preparedness. Decisions with responsibility.", "หลักฐานเพื่อเตรียมพร้อม การตัดสินใจอย่างมีความรับผิดชอบ")}</p></footer>
    </div>
  </main>;
}

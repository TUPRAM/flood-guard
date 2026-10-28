"use client";

import Link from "next/link";
import { LanguageToggle } from "./language-toggle";
import { useLanguage } from "@/lib/use-language";
import {
  JOURNAL_CHECKED, JOURNAL_DATA, JOURNAL_GROUPS, JOURNAL_REPOSITORY, JOURNAL_SOFTWARE, JOURNAL_THAI_SOURCES, type JournalResource,
} from "@/lib/journal";
import type { BilingualText } from "@/lib/policy-evidence";
import type { Language } from "@/lib/types";
import base from "./policy-page.module.css";
import styles from "./journal-page.module.css";

const MONTHS: Record<Language, readonly string[]> = {
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  th: ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."],
};

/** `2026-10-28` as "28 Oct 2026", or in Thai with the Buddhist year. */
function day(iso: string, language: Language): string {
  const [year, month, date] = iso.split("-").map(Number);
  return `${date} ${MONTHS[language][month - 1]} ${language === "th" ? year + 543 : year}`;
}

/**
 * The reference list shared with the audience by QR code: the papers in the order of the system, then Thai law and
 * plans, the data and the software. Built for a phone first. The policy page's list is read, not copied. It is
 * online-only: the `data-floodguard-references` marker keeps its chunk out of the blocking offline installation
 * (`scripts/write-offline-assets.mjs`).
 */
export function JournalPage() {
  const [language, setLanguage] = useLanguage("en");
  const t = (en: string, th: string) => (language === "th" ? th : en);
  const tx = (text: BilingualText) => (language === "th" ? text.th : text.en);
  const papers = JOURNAL_GROUPS.reduce((total, group) => total + group.items.length, 0);
  const chapters: [string, string][] = [
    ...JOURNAL_GROUPS.map((group): [string, string] => [group.id, tx(group.title)]),
    ["thai-law", t("Thai law and plans", "กฎหมายและแผนของไทย")],
    ["data", t("Data", "ข้อมูล")],
    ["software", t("Software", "ซอฟต์แวร์")],
  ];
  // Numbered straight through the groups, so a reference can be named by its number.
  const firstNumber = JOURNAL_GROUPS.map((_, index) => JOURNAL_GROUPS.slice(0, index).reduce((total, group) => total + group.items.length, 1));

  const resources = (items: readonly JournalResource[], testId: string) => <ul className={styles.resources} data-testid={testId}>
    {items.map((item) => <li key={item.id}>
      <a href={item.url} lang="en">{item.name}</a>
      <span>{tx(item.use)}</span>
      <small lang="en">{item.terms}</small>
    </li>)}
  </ul>;

  return <main id="main-content" className={base.page} lang={language} data-floodguard-references="">
    <header className={base.header}>
      <Link href="/" prefetch={false} className={base.brand} aria-label={t("FloodGuard home", "หน้าแรก FloodGuard")}>FloodGuard<span>.</span></Link>
      <span className={base.headerLabel}>{t("References", "เอกสารอ้างอิง")}</span>
      <LanguageToggle language={language} onChange={setLanguage} />
      <Link href="/" prefetch={false} className={base.back}>{t("Back to the story", "กลับสู่เรื่องราว")} <span aria-hidden="true">↗</span></Link>
    </header>

    <div className={base.container}>
      <section className={styles.hero} id="purpose" aria-labelledby="journal-title">
        <p className={base.eyebrow}>{t("REFERENCES · GEOHACKATHON 2026", "เอกสารอ้างอิง · GEOHACKATHON 2026")}</p>
        <h1 id="journal-title">{t("The papers, data and software behind FloodGuard.", "งานวิจัย ข้อมูล และซอฟต์แวร์เบื้องหลัง FloodGuard")}</h1>
        <p className={styles.lead}>{t(
          "Grouped by the step of the system each one stands behind, from radar images to the priority score. Each paper says, in one line, what we take from it.",
          "จัดกลุ่มตามขั้นตอนของระบบที่แต่ละรายการสนับสนุน ตั้งแต่ภาพเรดาร์จนถึงคะแนนลำดับความสำคัญ แต่ละรายการมีคำอธิบายหนึ่งบรรทัดว่าเรานำสิ่งใดมาใช้",
        )}</p>
        <dl className={styles.counts} data-testid="journal-counts">
          <div><dt>{t("Papers and frameworks", "งานวิจัยและกรอบการดำเนินงาน")}</dt><dd>{papers}</dd></div>
          <div><dt>{t("Datasets", "ชุดข้อมูล")}</dt><dd>{JOURNAL_DATA.length}</dd></div>
          <div><dt>{t("Software", "ซอฟต์แวร์")}</dt><dd>{JOURNAL_SOFTWARE.length}</dd></div>
        </dl>
        <p className={styles.note}>{t(
          `We read the record of each paper (authors, year, venue, DOI) on ${day(JOURNAL_CHECKED.policy, "en")} or ${day(JOURNAL_CHECKED.methods, "en")}, not always its full text. A paper supports one step of the work; none endorses FloodGuard and none validates the score. This is a working list, not a systematic review.`,
          `เราอ่านข้อมูลบรรณานุกรมของงานวิจัยแต่ละชิ้น (ผู้แต่ง ปี แหล่งตีพิมพ์ DOI) เมื่อวันที่ ${day(JOURNAL_CHECKED.policy, "th")} หรือ ${day(JOURNAL_CHECKED.methods, "th")} แต่ไม่ได้อ่านฉบับเต็มทุกชิ้น งานวิจัยแต่ละชิ้นสนับสนุนขั้นตอนหนึ่งของงาน ไม่มีชิ้นใดรับรอง FloodGuard และไม่มีชิ้นใดยืนยันความถูกต้องของคะแนน รายการนี้เป็นรายการเพื่อการทำงานที่ยังปรับปรุงได้ ไม่ใช่การทบทวนวรรณกรรมอย่างเป็นระบบ`,
        )}</p>
      </section>
    </div>

    <nav className={base.chapterNav} aria-label={t("Sections", "หมวด")}><div>
      {chapters.map(([id, label], index) => <a key={id} href={`#${id}`}><span>{String(index + 1).padStart(2, "0")}</span>{label}</a>)}
    </div></nav>

    <div className={base.container}>
      {JOURNAL_GROUPS.map((group, index) => <section key={group.id} id={group.id} className={styles.section} aria-labelledby={`${group.id}-title`}>
        <div className={styles.heading}>
          <p className={base.eyebrow}>{String(index + 1).padStart(2, "0")} · {tx(group.intro)}</p>
          <h2 id={`${group.id}-title`}>{tx(group.title)}</h2>
        </div>
        <ol className={styles.papers} data-testid={`journal-group-${group.id}`}>
          {group.items.map((item, itemIndex) => <li key={item.id} id={`ref-${item.id}`}>
              <span className={styles.number} aria-hidden="true">{firstNumber[index] + itemIndex}</span>
              <div>
                <a href={item.url} lang="en">{item.reference}</a>
                <p>{tx(item.use)}</p>
                <p className={styles.meta}>
                  <span>{t("Record checked", "ตรวจข้อมูลบรรณานุกรมเมื่อ")} {day(item.checked, language)}</span>
                  {item.code ? <a href={`${JOURNAL_REPOSITORY}${item.code}`} lang="en">{item.code.split("/").pop()}</a> : null}
                </p>
              </div>
            </li>)}
        </ol>
      </section>)}

      <section id="thai-law" className={styles.section} aria-labelledby="thai-law-title">
        <div className={styles.heading}>
          <p className={base.eyebrow}>{String(JOURNAL_GROUPS.length + 1).padStart(2, "0")} · {t("Who holds the duty to act", "ผู้มีหน้าที่ดำเนินการ")}</p>
          <h2 id="thai-law-title">{t("Thai law and plans", "กฎหมายและแผนของไทย")}</h2>
        </div>
        <ul className={styles.resources} data-testid="journal-thai-sources">
          {JOURNAL_THAI_SOURCES.map((item) => <li key={item.id}><a href={item.url}>{tx(item.title)}</a><span>{tx(item.owner)}</span></li>)}
        </ul>
      </section>

      <section id="data" className={styles.section} aria-labelledby="data-title">
        <div className={styles.heading}>
          <p className={base.eyebrow}>{String(JOURNAL_GROUPS.length + 2).padStart(2, "0")} · {t("What the results are built from", "ผลลัพธ์สร้างจากข้อมูลใด")}</p>
          <h2 id="data-title">{t("Data and its terms", "ข้อมูลและเงื่อนไขการใช้")}</h2>
        </div>
        {resources(JOURNAL_DATA, "journal-data")}
      </section>

      <section id="software" className={styles.section} aria-labelledby="software-title">
        <div className={styles.heading}>
          <p className={base.eyebrow}>{String(JOURNAL_GROUPS.length + 3).padStart(2, "0")} · {t("Open source we build on", "ซอฟต์แวร์โอเพนซอร์สที่เราใช้")}</p>
          <h2 id="software-title">{t("Software", "ซอฟต์แวร์")}</h2>
        </div>
        {resources(JOURNAL_SOFTWARE, "journal-software")}
        <p className={styles.repo}><a href="https://github.com/TUPRAM/flood-guard" lang="en">github.com/TUPRAM/flood-guard</a> · {t(
          "the whole project, with the file behind each method linked above.",
          "โครงการทั้งหมด พร้อมไฟล์ของแต่ละวิธีที่ลิงก์ไว้ด้านบน",
        )}</p>
        <p className={base.footnote}>{t(
          "FloodGuard is planning support, not an official warning. The Thai text of this page was written by the project’s AI assistant and has not been reviewed by a native speaker.",
          "FloodGuard เป็นเครื่องมือสนับสนุนการวางแผน ไม่ใช่ระบบเตือนภัยอย่างเป็นทางการ ข้อความภาษาไทยในหน้านี้เขียนโดยผู้ช่วย AI ของโครงการ และยังไม่ได้รับการตรวจทานโดยเจ้าของภาษา",
        )}</p>
      </section>
      <footer className={base.footer}><Link href="/" prefetch={false} className={base.brand}>FloodGuard<span>.</span></Link><p>{t("Evidence for preparedness. Decisions with responsibility.", "หลักฐานเพื่อเตรียมพร้อม การตัดสินใจอย่างมีความรับผิดชอบ")}</p></footer>
    </div>
  </main>;
}

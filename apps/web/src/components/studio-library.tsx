"use client";

import { useLanguage } from "@/lib/use-language";
import { WorkspaceHeader } from "./workspace-header";

import styles from "./studio-library.module.css";

export const C2S_STUDY_ROUTE = "/studio/studies/c2s-ms-20260915/";

export function StudioLibraryHeader() {
  const [language, setLanguage] = useLanguage("en");
  return <WorkspaceHeader activeSurface="studio" language={language} onLanguageChange={setLanguage} />;
}

export function StudioLibrary() {
  const [language] = useLanguage("en");
  const t = (en: string, th: string) => language === "th" ? th : en;
  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
      <StudioLibraryHeader />
      <div className={styles.container}>
        <section className={styles.hero} aria-labelledby="studio-library-title">
          <p className={styles.eyebrow}>{t("STUDIES & EVIDENCE", "งานศึกษาและหลักฐาน")}</p>
          <h1 id="studio-library-title">{t("Every result has a context.", "ทุกผลลัพธ์มีบริบทของตัวเอง")}</h1>
          <p className={styles.lead}>{t("Explore the research behind FloodGuard. Choose a study to inspect its data, methods, measured results and limitations.", "สำรวจงานวิจัยเบื้องหลัง FloodGuard เลือกงานศึกษาเพื่อดูข้อมูล วิธีการ ผลการประเมิน และข้อจำกัด")}</p>
          <div className={styles.principles}><span>{t("Public data", "ข้อมูลสาธารณะ")}</span><span>{t("Traceable evidence", "หลักฐานที่ตรวจสอบย้อนกลับได้")}</span><span>{t("Study-specific evaluation", "การประเมินแยกตามงานศึกษา")}</span></div>
        </section>

        <section aria-labelledby="research-studies-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{t("01 · RESEARCH", "01 · งานวิจัย")}</p><h2 id="research-studies-title">{t("Research studies", "งานศึกษาวิจัย")}</h2></div><p>{t("Measured benchmarks and applications of their frozen models.", "ผลการประเมินแบบจำลองและการนำแบบจำลองรุ่นที่กำหนดไว้ไปใช้งาน")}</p></div>
          <div className={styles.cards}>
            <article className={`${styles.card} ${styles.featured}`}>
              <div className={styles.cardTop}><span className={styles.kind}>{t("PUBLIC BENCHMARK", "การประเมินด้วยข้อมูลสาธารณะ")}</span><span className={styles.badge}>{t("Report only", "เพื่อรายงานเท่านั้น")}</span></div>
              <h3>{t("C2S-MS public benchmark", "การประเมิน C2S-MS ด้วยข้อมูลสาธารณะ")}</h3>
              <p>Random Forest · XGBoost · SAR U-Net</p>
              <dl><div><dt>{t("Data", "ข้อมูล")}</dt><dd>{t("900 chips · 18 events · human water labels", "ภาพย่อย 900 ภาพ · 18 เหตุการณ์ · ขอบเขตน้ำที่มนุษย์ระบุ")}</dd></div><div><dt>{t("Observations", "ช่วงเวลาของภาพ")}</dt><dd>{t("2016–2020 · multiple countries", "2016–2020 · หลายประเทศ")}</dd></div><div><dt>{t("Experiment", "การทดลอง")}</dt><dd>{t("15 September 2026 · revision 1", "15 กันยายน 2026 · ฉบับที่ 1")}</dd></div><div><dt>{t("Evaluation", "การประเมิน")}</dt><dd>{t("Entire events held apart for final testing", "แยกทั้งเหตุการณ์ไว้สำหรับการทดสอบขั้นสุดท้าย")}</dd></div></dl>
              <p className={styles.status}>{t("Benchmark completed. Inspect the original-chip evaluation and the separate matched RTC comparison.", "ประเมินเสร็จแล้ว ดูผลบนภาพย่อยต้นฉบับและผลเปรียบเทียบบนข้อมูล RTC ที่จับคู่กัน โดยแยกผลทั้งสองชุดอย่างชัดเจน")}</p>
              <a className={styles.open} href={C2S_STUDY_ROUTE}>{t("Open study ", "เปิดงานศึกษา ")}<span aria-hidden="true">↗</span></a>
            </article>
            <article className={styles.card}>
              <div className={styles.cardTop}><span className={styles.kind}>{t("MODEL APPLICATION", "การนำแบบจำลองไปใช้")}</span><span className={`${styles.badge} ${styles.amber}`}>{t("Local accuracy unmeasured", "ยังไม่ได้วัดความแม่นยำในพื้นที่")}</span></div>
              <h3>{t("Mae Sai — C2S-trained models", "แม่สาย — แบบจำลองที่ฝึกด้วย C2S")}</h3>
              <p>{t("Frozen benchmark checkpoints applied to Thailand.", "นำแบบจำลองรุ่นที่บันทึกไว้จากการประเมินมาใช้กับพื้นที่ในประเทศไทย")}</p>
              <dl><div><dt>{t("Area", "พื้นที่")}</dt><dd>{t("Mae Sai, Chiang Rai, Thailand", "แม่สาย เชียงราย ประเทศไทย")}</dd></div><div><dt>{t("Acquisitions", "วันที่บันทึกภาพ")}</dt><dd>{t("22 August / 15 September 2024 UTC", "22 สิงหาคม / 15 กันยายน 2024 UTC")}</dd></div><div><dt>{t("Outputs", "ผลลัพธ์")}</dt><dd>{t("Probability, validity, entropy and abstention", "ความน่าจะเป็น ความใช้ได้ของข้อมูล เอนโทรปี และพื้นที่ที่แบบจำลองงดตัดสิน")}</dd></div><div><dt>{t("Reference", "ข้อมูลอ้างอิง")}</dt><dd>{t("No qualified Thai reference mask", "ยังไม่มีหน้ากากอ้างอิงในไทยที่ผ่านการรับรองคุณสมบัติ")}</dd></div></dl>
              <p className={styles.status}>{t("Inference completed. The September image shows residual extent, roughly four days after the flood peak.", "ประมวลผลเสร็จแล้ว ภาพเดือนกันยายนแสดงขอบเขตน้ำที่ยังคงเหลืออยู่ ราวสี่วันหลังระดับน้ำท่วมสูงสุด")}</p>
              <a className={styles.open} href={`${C2S_STUDY_ROUTE}mae-sai/`}>{t("Open maps ", "เปิดแผนที่ ")}<span aria-hidden="true">↗</span></a>
            </article>
          </div>
        </section>

        <section aria-labelledby="planning-evidence-library-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{t("02 · GOVERNED EVIDENCE", "02 · หลักฐานที่มีการกำกับดูแล")}</p><h2 id="planning-evidence-library-title">{t("Planning evidence", "หลักฐานการวางแผน")}</h2></div><p>{t("Qualification and authorization belong to their recorded evidence context.", "การตรวจคุณสมบัติและการอนุมัติใช้หลักฐานต้องพิจารณาตามบริบทที่บันทึกไว้")}</p></div>
          <article className={`${styles.card} ${styles.wide}`}><div><span className={styles.kind}>{t("MAE SAI · SEPTEMBER 2024", "แม่สาย · กันยายน 2024")}</span><h3>{t("Current Mae Sai evidence report", "รายงานหลักฐานแม่สายฉบับปัจจุบัน")}</h3><p>{t("Source provenance, technical verification, Thai-reference qualification, model restrictions and authorization records.", "ที่มาของข้อมูล การตรวจสอบทางเทคนิค คุณสมบัติของข้อมูลอ้างอิงไทย ข้อจำกัดของแบบจำลอง และบันทึกการอนุมัติ")}</p><p className={styles.status}>{t("Open the report for the current recorded qualification and authorization states.", "เปิดรายงานเพื่อดูสถานะการตรวจคุณสมบัติและการอนุมัติที่บันทึกไว้ในปัจจุบัน")}</p></div><a className={styles.open} href="/studio/planning-evidence/">{t("Open evidence ", "เปิดหลักฐาน ")}<span aria-hidden="true">↗</span></a></article>
        </section>

        <section aria-labelledby="historical-studies-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{t("03 · ARCHIVE", "03 · คลังงานเดิม")}</p><h2 id="historical-studies-title">{t("Historical studies", "งานศึกษาในอดีต")}</h2></div><p>{t("Original evidence preserved with its original methods and limitations.", "เก็บรักษาหลักฐานเดิมพร้อมวิธีการและข้อจำกัดของงานในช่วงนั้น")}</p></div>
          <article className={`${styles.card} ${styles.wide}`}><div><span className={styles.kind}>{t("HISTORICAL RESEARCH · REPORT ONLY", "งานวิจัยในอดีต · เพื่อรายงานเท่านั้น")}</span><h3>{t("Earlier Mae Sai GeoAI analysis", "การวิเคราะห์ GeoAI แม่สายชุดก่อนหน้า")}</h3><p>{t("Optical U-Net, teacher-agreement experiments, the MNDWI label diagnosis, and earlier SAR and infrastructure research.", "U-Net จากภาพเชิงแสง การทดลองวัดความสอดคล้องกับแบบจำลองครู การตรวจสอบป้ายกำกับ MNDWI และงานวิจัย SAR กับโครงสร้างพื้นฐานชุดก่อนหน้า")}</p><p className={styles.status}>{t("30 July 2026 baseline · imagery from 2024. Historical scores have different reference labels and evaluation designs.", "ค่าฐาน 30 กรกฎาคม 2026 · ภาพจากปี 2024 คะแนนจากงานเดิมใช้ป้ายกำกับอ้างอิงและรูปแบบการประเมินที่แตกต่างกัน")}</p></div><a className={styles.open} href="/studio/archive/mae-sai-geoai/">{t("Open archive ", "เปิดคลังงานเดิม ")}<span aria-hidden="true">↗</span></a></article>
        </section>
        <footer className={styles.footer}>{t("FloodGuard supports preparedness and rapid post-event prioritisation. Research outputs here are report only and do not feed the planning decision layer.", "FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญอย่างรวดเร็วหลังเกิดเหตุ ผลงานวิจัยในหน้านี้ใช้เพื่อรายงานเท่านั้น และไม่ถูกนำไปใช้ในส่วนตัดสินใจเพื่อการวางแผน")}</footer>
      </div>
    </main>
  );
}

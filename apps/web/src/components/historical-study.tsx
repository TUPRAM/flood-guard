"use client";

import archive from "../../public/studies/mae-sai-geoai/2026-07-30-r1/manifest.json";
import { useLanguage } from "@/lib/use-language";

import { GeoaiRealPanel } from "./geoai-real-panel";
import { C2S_STUDY_ROUTE, StudioLibraryHeader } from "./studio-library";
import styles from "./studio-library.module.css";

const prefix = "/studies/mae-sai-geoai/2026-07-30-r1";

export function HistoricalStudy() {
  const [language] = useLanguage("en");
  const text = (en: string, th: string) => language === "th" ? th : en;
  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
      <StudioLibraryHeader />
      <div className={styles.container}>
        <nav className={styles.breadcrumbs} aria-label={text("Breadcrumb", "เส้นทางนำทาง")}><a href="/studio/">{text("Studio", "สตูดิโอ")}</a><span>/</span><span>{text("Historical studies", "งานศึกษาที่ผ่านมา")}</span></nav>
        <section className={`${styles.hero} ${styles.archiveHero}`} aria-labelledby="historical-study-title">
          <p className={styles.eyebrow}>{text("HISTORICAL RESEARCH · REPORT ONLY", "งานวิจัยที่ผ่านมา · ใช้เพื่อรายงานเท่านั้น")}</p>
          <h1 id="historical-study-title">{text("Earlier Mae Sai GeoAI analysis", "การวิเคราะห์ GeoAI แม่สายฉบับก่อน")}</h1>
          <p className={styles.lead}>{text("The original optical U-Net, SAR, susceptibility and infrastructure research, preserved with the evidence that explains its limitations.", "เก็บรักษางานวิจัยเดิมเกี่ยวกับ U-Net จากภาพเชิงแสง, SAR, ความไวต่อการเกิดน้ำท่วม และโครงสร้างพื้นฐาน พร้อมหลักฐานที่อธิบายข้อจำกัด")}</p>
          <div className={styles.principles}><span>{text("Baseline: 30 July 2026 · run 1", "การทดลองตั้งต้น: 30 กรกฎาคม ค.ศ. 2026 · ครั้งที่ 1")}</span><span>{text("Observations: 2024", "ภาพบันทึก: ค.ศ. 2024")}</span><span>{text("Local water accuracy unverified", "ยังไม่ยืนยันความแม่นยำของพื้นที่น้ำในท้องถิ่น")}</span></div>
        </section>
        <aside className={styles.notice} aria-labelledby="historical-score-meaning">
          <h2 id="historical-score-meaning">{text("What the old U-Net score means", "คะแนน U-Net เดิมหมายถึงอะไร")}</h2>
          {language === "th" ? <p>ค่า IoU เดิม 0.0023 และ F1 เดิม 0.0047 วัด<strong>ความสอดคล้องกับหน้ากากครูจาก OmniWaterMask</strong> ในบล็อกเชิงพื้นที่ที่กันไว้ทดสอบ ไม่ใช่ความแม่นยำเมื่อเทียบกับป้ายกำกับน้ำในประเทศไทยที่ผ่านการตรวจรับอย่างอิสระ ผลการทดลองที่บันทึกไว้มีการเรียนรู้ที่ล้มเหลว โดยมีพิกเซลน้ำในชุดฝึกเพียง 352 พิกเซล</p> : <p>The original IoU of 0.0023 and F1 of 0.0047 measure <strong>agreement with an OmniWaterMask teacher mask</strong> on held-out spatial blocks. They do not measure accuracy against independently qualified Thai water labels. The saved run records a degenerate result, with only 352 positive training pixels.</p>}
          <p>{text("The later C2S-MS study uses public human SAR labels and separate event groups. Changes in inputs, reference labels, geography and evaluation design prevent a direct old-score-to-new-score improvement claim.", "งานศึกษา C2S-MS ในภายหลังใช้ป้ายกำกับภาพ SAR โดยมนุษย์ที่เผยแพร่สาธารณะ และแยกกลุ่มเหตุการณ์ออกจากกัน ความต่างของข้อมูลเข้า ป้ายกำกับอ้างอิง ภูมิศาสตร์ และวิธีประเมิน ทำให้ไม่สามารถอ้างว่าคะแนนใหม่พัฒนาจากคะแนนเดิมโดยเปรียบเทียบตรง ๆ ได้")}</p>
        </aside>
        <div className={styles.tableScroll}>
          <table><caption className="sr-only">{text("Historical study identity and interpretation", "ข้อมูลระบุตัวงานศึกษาที่ผ่านมาและการตีความ")}</caption><thead><tr><th>{text("Evidence", "หลักฐาน")}</th><th>{text("Original context and interpretation", "บริบทเดิมและการตีความ")}</th></tr></thead><tbody>
            <tr><td>{text("Inputs and dates", "ข้อมูลเข้าและวันที่")}</td><td>{text("Sentinel-2 L2A: 18 February 2024. Sentinel-1 RTC: 22 August and 15 September 2024 UTC. The September observation records residual extent, roughly four days after the peak.", "Sentinel-2 L2A: 18 กุมภาพันธ์ ค.ศ. 2024; Sentinel-1 RTC: 22 สิงหาคม และ 15 กันยายน ค.ศ. 2024 UTC ภาพเดือนกันยายนบันทึกขอบเขตน้ำที่ยังเหลืออยู่ ประมาณสี่วันหลังระดับน้ำสูงสุด")}</td></tr>
            <tr><td>{text("Optical U-Net split", "การแบ่งข้อมูล U-Net เชิงแสง")}</td><td>{text("Runner-local spatial blocks: 5 training, 2 validation and 2 test blocks, with a 1,600 m buffer. This is distinct from the later C2S event partition.", "บล็อกเชิงพื้นที่ภายในตัวประมวลผล: ฝึก 5 บล็อก ตรวจสอบ 2 บล็อก และทดสอบ 2 บล็อก โดยมีระยะกันชน 1,600 เมตร การแบ่งนี้แยกจากการแบ่งเหตุการณ์ C2S ในภายหลัง")}</td></tr>
            <tr><td>{text("Weak-label diagnosis", "การตรวจสอบป้ายกำกับแบบอ่อน")}</td><td>{text("MNDWI > 0 labelled about 8.7 times the JRC reference area while missing about half the reference water. The module documents the registration checks and poor threshold precision. That path was superseded for flood segmentation by the SAR study.", "MNDWI > 0 ระบุพื้นที่น้ำประมาณ 8.7 เท่าของพื้นที่อ้างอิง JRC แต่กลับพลาดพื้นที่น้ำอ้างอิงประมาณครึ่งหนึ่ง โมดูลบันทึกการตรวจสอบการจัดแนวภาพและความแม่นตรงที่ต่ำของค่าเกณฑ์ งานศึกษา SAR ได้เข้ามาแทนที่วิธีนี้สำหรับการแบ่งส่วนภาพน้ำท่วมแล้ว")}</td></tr>
            <tr><td>{text("Historical SAR method", "วิธี SAR ในงานเดิม")}</td><td>{text("A fixed change ramp from 1 to 5 dB, with a binary cut at 0.5. Historical descriptions of this implementation as adaptive Otsu were inaccurate.", "ใช้ฟังก์ชันเพิ่มเชิงเส้นตามการเปลี่ยนแปลงคงที่ตั้งแต่ 1 ถึง 5 dB และตัดสินสองคลาสที่ 0.5 คำอธิบายเดิมที่เรียกวิธีนี้ว่า adaptive Otsu ไม่ถูกต้อง")}</td></tr>
            <tr><td>{text("Susceptibility and infrastructure", "ความไวต่อการเกิดน้ำท่วมและโครงสร้างพื้นฐาน")}</td><td>{text("Agreement with algorithmic SAR/JRC references and coverage-flagged building counts belong to this historical run. The displayed historical FPPS and A–E classes do not set current planning priorities.", "ความสอดคล้องกับข้อมูลอ้างอิง SAR/JRC ที่สร้างด้วยอัลกอริทึม และจำนวนอาคารที่ระบุข้อจำกัดความครอบคลุม เป็นผลของการทดลองเดิมนี้ ค่า FPPS และคลาส A–E ที่แสดงจากงานเดิมไม่ได้กำหนดลำดับความสำคัญของการวางแผนปัจจุบัน")}</td></tr>
          </tbody></table>
        </div>
        {language === "th" ? <aside className={styles.notice}>รายงาน GeoAI ต้นฉบับและไฟล์หลักฐานที่ดาวน์โหลดได้คงไว้เป็นภาษาอังกฤษ การเปลี่ยนภาษาส่วนติดต่อไม่เปลี่ยนผลลัพธ์หรือความหมายของคะแนนเดิม</aside> : null}
        <div lang="en"><GeoaiRealPanel variant="archive" archiveRecord={archive.report} /></div>
        <section className={styles.sources} aria-labelledby="historical-files-title">
          <h2 id="historical-files-title">{text("Frozen record and source evidence", "บันทึกที่ตรึงเวอร์ชันและหลักฐานต้นทาง")}</h2>
          <p>{text("Study", "งานศึกษา")} <code>{archive.study_id}</code> · {text("revision", "ฉบับ")} <code>{archive.revision}</code>. {text("The saved source timestamp is", "เวลาต้นทางที่บันทึกไว้คือ")} <time>{archive.source_timestamp}</time>{text("; this is the observation time, separate from the 30 July 2026 baseline run date.", " ซึ่งเป็นเวลาบันทึกภาพ แยกจากวันที่ทดลองตั้งต้น 30 กรกฎาคม ค.ศ. 2026")}</p>
          <p><a href={`${prefix}/manifest.json`} download>{text("Manifest and checksums", "รายการไฟล์และค่าตรวจสอบ")}</a> · <a href={archive.report.href} download>{text("Archived website report", "รายงานเว็บไซต์ฉบับเก็บถาวร")}</a> · <a href={`${prefix}/geoai_metrics.json`} download>{text("Original metrics and assumptions", "ค่าประเมินและสมมติฐานเดิม")}</a> · <a href={`${prefix}/README.md`} download>{text("Baseline run notes", "บันทึกการทดลองตั้งต้น")}</a> · <a href={`${prefix}/label-diagnosis.md`} download>{text("MNDWI diagnosis", "การตรวจสอบ MNDWI")}</a></p>
          <p>{text("Report SHA-256", "SHA-256 ของรายงาน")}: <code>{archive.report.sha256}</code>. {text("Image URLs in this archived copy point to frozen previews; the manifest retains the original report digest and every copied asset digest.", "ลิงก์ภาพในสำเนาเก็บถาวรนี้ชี้ไปยังภาพตัวอย่างที่ตรึงไว้ รายการไฟล์เก็บค่าตรวจสอบของรายงานต้นฉบับและทุกไฟล์ที่คัดลอกมา")}</p>
          <p>{text("Underlying source access", "เข้าถึงแหล่งข้อมูลต้นทาง")}: <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc">Sentinel-1 RTC</a>, <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a">Sentinel-2 L2A</a>, <a href="https://registry.opendata.aws/copernicus-dem/">Copernicus DEM</a>, <a href="https://global-surface-water.appspot.com/download">JRC surface water</a>, <a href="https://ngis.go.th/">Thai NGIS</a>, <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> {text("and", "และ")} <a href="https://hub.worldpop.org/">WorldPop</a>. {text("Each source retains its own terms. Archiving the report grants no additional training rights.", "แต่ละแหล่งยังคงมีเงื่อนไขการใช้งานของตนเอง การเก็บรายงานถาวรไม่ได้ให้สิทธิ์เพิ่มเติมในการฝึกโมเดล")}</p>
          <p><a href={C2S_STUDY_ROUTE}>{text("Explore the later C2S-MS public benchmark", "สำรวจการประเมิน C2S-MS ด้วยข้อมูลสาธารณะในงานภายหลัง")}</a> · <a href="/studio/planning-evidence/">{text("Open current planning evidence", "เปิดหลักฐานเพื่อการวางแผนปัจจุบัน")}</a></p>
        </section>
        <footer className={styles.footer}>{text("Historical research · report only · excluded from exposure, road risk, access, equity and FPPS decisions.", "งานวิจัยที่ผ่านมา · ใช้เพื่อรายงานเท่านั้น · ไม่นำไปใช้ตัดสินใจด้านการรับสัมผัสภัย ความเสี่ยงถนน การเข้าถึง ความเป็นธรรม หรือ FPPS")}</footer>
      </div>
    </main>
  );
}

import archive from "../../public/studies/mae-sai-geoai/2026-07-30-r1/manifest.json";

import { GeoaiRealPanel } from "./geoai-real-panel";
import { C2S_STUDY_ROUTE, StudioLibraryHeader } from "./studio-library";
import styles from "./studio-library.module.css";

const prefix = "/studies/mae-sai-geoai/2026-07-30-r1";

export function HistoricalStudy() {
  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang="en">
      <StudioLibraryHeader />
      <div className={styles.container}>
        <nav className={styles.breadcrumbs} aria-label="Breadcrumb"><a href="/studio/">Studio</a><span>/</span><span>Historical studies</span></nav>
        <section className={`${styles.hero} ${styles.archiveHero}`} aria-labelledby="historical-study-title">
          <p className={styles.eyebrow}>HISTORICAL RESEARCH · REPORT ONLY</p>
          <h1 id="historical-study-title">Earlier Mae Sai GeoAI analysis</h1>
          <p className={styles.lead}>The original optical U-Net, SAR, susceptibility and infrastructure research, preserved with the evidence that explains its limitations.</p>
          <div className={styles.principles}><span>Baseline: 30 July 2026 · run 1</span><span>Observations: 2024</span><span>Local water accuracy unverified</span></div>
        </section>
        <aside className={styles.notice} aria-labelledby="historical-score-meaning">
          <h2 id="historical-score-meaning">What the old U-Net score means</h2>
          <p>The original IoU of 0.0023 and F1 of 0.0047 measure <strong>agreement with an OmniWaterMask teacher mask</strong> on held-out spatial blocks. They do not measure accuracy against independently qualified Thai water labels. The saved run records a degenerate result, with only 352 positive training pixels.</p>
          <p>The later C2S-MS study uses public human SAR labels and separate event groups. Changes in inputs, reference labels, geography and evaluation design prevent a direct old-score-to-new-score improvement claim.</p>
        </aside>
        <div className={styles.tableScroll}>
          <table><caption className="sr-only">Historical study identity and interpretation</caption><thead><tr><th>Evidence</th><th>Original context and interpretation</th></tr></thead><tbody>
            <tr><td>Inputs and dates</td><td>Sentinel-2 L2A: 18 February 2024. Sentinel-1 RTC: 22 August and 15 September 2024 UTC. The September observation records residual extent, roughly four days after the peak.</td></tr>
            <tr><td>Optical U-Net split</td><td>Runner-local spatial blocks: 5 training, 2 validation and 2 test blocks, with a 1,600 m buffer. This is distinct from the later C2S event partition.</td></tr>
            <tr><td>Weak-label diagnosis</td><td>MNDWI &gt; 0 labelled about 8.7 times the JRC reference area while missing about half the reference water. The module documents the registration checks and poor threshold precision. That path was superseded for flood segmentation by the SAR study.</td></tr>
            <tr><td>Historical SAR method</td><td>A fixed change ramp from 1 to 5 dB, with a binary cut at 0.5. Historical descriptions of this implementation as adaptive Otsu were inaccurate.</td></tr>
            <tr><td>Susceptibility and infrastructure</td><td>Agreement with algorithmic SAR/JRC references and coverage-flagged building counts belong to this historical run. The displayed historical FPPS and A–E classes do not set current planning priorities.</td></tr>
          </tbody></table>
        </div>
        <GeoaiRealPanel variant="archive" archiveRecord={archive.report} />
        <section className={styles.sources} aria-labelledby="historical-files-title">
          <h2 id="historical-files-title">Frozen record and source evidence</h2>
          <p>Study <code>{archive.study_id}</code> · revision <code>{archive.revision}</code>. The saved source timestamp is <time>{archive.source_timestamp}</time>; this is the observation time, separate from the 30 July 2026 baseline run date.</p>
          <p><a href={`${prefix}/manifest.json`} download>Manifest and checksums</a> · <a href={archive.report.href} download>Archived website report</a> · <a href={`${prefix}/geoai_metrics.json`} download>Original metrics and assumptions</a> · <a href={`${prefix}/README.md`} download>Baseline run notes</a> · <a href={`${prefix}/label-diagnosis.md`} download>MNDWI diagnosis</a></p>
          <p>Report SHA-256: <code>{archive.report.sha256}</code>. Image URLs in this archived copy point to frozen previews; the manifest retains the original report digest and every copied asset digest.</p>
          <p>Underlying source access: <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc">Sentinel-1 RTC</a>, <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a">Sentinel-2 L2A</a>, <a href="https://registry.opendata.aws/copernicus-dem/">Copernicus DEM</a>, <a href="https://global-surface-water.appspot.com/download">JRC surface water</a>, <a href="https://ngis.go.th/">Thai NGIS</a>, <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> and <a href="https://hub.worldpop.org/">WorldPop</a>. Each source retains its own terms. Archiving the report grants no additional training rights.</p>
          <p><a href={C2S_STUDY_ROUTE}>Explore the later C2S-MS public benchmark</a> · <a href="/studio/planning-evidence/">Open current planning evidence</a></p>
        </section>
        <footer className={styles.footer}>Historical research · report only · excluded from exposure, road risk, access, equity and FPPS decisions.</footer>
      </div>
    </main>
  );
}

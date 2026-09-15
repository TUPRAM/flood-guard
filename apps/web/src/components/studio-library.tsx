import Image from "next/image";

import styles from "./studio-library.module.css";

export const C2S_STUDY_ROUTE = "/studio/studies/c2s-ms-20260915/";

export function StudioLibraryHeader() {
  return (
    <header className={styles.header}>
      <a className={styles.brand} href="/studio/" aria-label="FloodGuard Studio home">
        <Image src="/floodguard-logo.png" alt="" width={38} height={38} />
        <span>FloodGuard <small>STUDIO</small></span>
      </a>
      <nav aria-label="Product surfaces">
        <a href="/public/">Public</a>
        <a href="/command/">Planning</a>
        <a href="/studio/" aria-current="page">Studio</a>
      </nav>
    </header>
  );
}

export function StudioLibrary() {
  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang="en">
      <StudioLibraryHeader />
      <div className={styles.container}>
        <section className={styles.hero} aria-labelledby="studio-library-title">
          <p className={styles.eyebrow}>STUDIES & EVIDENCE</p>
          <h1 id="studio-library-title">Every result has a context.</h1>
          <p className={styles.lead}>Explore the research behind FloodGuard. Choose a study to inspect its data, methods, measured results and limitations.</p>
          <div className={styles.principles}><span>Public data</span><span>Traceable evidence</span><span>Study-specific evaluation</span></div>
        </section>

        <section aria-labelledby="research-studies-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>01 · RESEARCH</p><h2 id="research-studies-title">Research studies</h2></div><p>Measured benchmarks and applications of their frozen models.</p></div>
          <div className={styles.cards}>
            <article className={`${styles.card} ${styles.featured}`}>
              <div className={styles.cardTop}><span className={styles.kind}>PUBLIC BENCHMARK</span><span className={styles.badge}>Report only</span></div>
              <h3>C2S-MS public benchmark</h3>
              <p>Random Forest · XGBoost · SAR U-Net</p>
              <dl><div><dt>Data</dt><dd>900 chips · 18 events · human water labels</dd></div><div><dt>Observations</dt><dd>2016–2020 · multiple countries</dd></div><div><dt>Experiment</dt><dd>15 September 2026 · revision 1</dd></div><div><dt>Evaluation</dt><dd>Entire events held apart for final testing</dd></div></dl>
              <p className={styles.status}>Benchmark completed. Inspect the original-chip evaluation and the separate matched RTC comparison.</p>
              <a className={styles.open} href={C2S_STUDY_ROUTE}>Open study <span aria-hidden="true">↗</span></a>
            </article>
            <article className={styles.card}>
              <div className={styles.cardTop}><span className={styles.kind}>MODEL APPLICATION</span><span className={`${styles.badge} ${styles.amber}`}>Local accuracy unmeasured</span></div>
              <h3>Mae Sai — C2S-trained models</h3>
              <p>Frozen benchmark checkpoints applied to Thailand.</p>
              <dl><div><dt>Area</dt><dd>Mae Sai, Chiang Rai, Thailand</dd></div><div><dt>Acquisitions</dt><dd>22 August / 15 September 2024 UTC</dd></div><div><dt>Outputs</dt><dd>Probability, validity, entropy and abstention</dd></div><div><dt>Reference</dt><dd>No qualified Thai reference mask</dd></div></dl>
              <p className={styles.status}>Inference completed. The September image shows residual extent, roughly four days after the flood peak.</p>
              <a className={styles.open} href={`${C2S_STUDY_ROUTE}mae-sai/`}>Open maps <span aria-hidden="true">↗</span></a>
            </article>
          </div>
        </section>

        <section aria-labelledby="planning-evidence-library-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>02 · GOVERNED EVIDENCE</p><h2 id="planning-evidence-library-title">Planning evidence</h2></div><p>Qualification and authorization belong to their recorded evidence context.</p></div>
          <article className={`${styles.card} ${styles.wide}`}><div><span className={styles.kind}>MAE SAI · SEPTEMBER 2024</span><h3>Current Mae Sai evidence report</h3><p>Source provenance, technical verification, Thai-reference qualification, model restrictions and authorization records.</p><p className={styles.status}>Open the report for the current recorded qualification and authorization states.</p></div><a className={styles.open} href="/studio/planning-evidence/">Open evidence <span aria-hidden="true">↗</span></a></article>
        </section>

        <section aria-labelledby="historical-studies-title" className={styles.section}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>03 · ARCHIVE</p><h2 id="historical-studies-title">Historical studies</h2></div><p>Original evidence preserved with its original methods and limitations.</p></div>
          <article className={`${styles.card} ${styles.wide}`}><div><span className={styles.kind}>HISTORICAL RESEARCH · REPORT ONLY</span><h3>Earlier Mae Sai GeoAI analysis</h3><p>Optical U-Net, teacher-agreement experiments, the MNDWI label diagnosis, and earlier SAR and infrastructure research.</p><p className={styles.status}>30 July 2026 baseline · imagery from 2024. Historical scores have different reference labels and evaluation designs.</p></div><a className={styles.open} href="/studio/archive/mae-sai-geoai/">Open archive <span aria-hidden="true">↗</span></a></article>
        </section>
        <footer className={styles.footer}>FloodGuard supports preparedness and rapid post-event prioritisation. Research outputs here are report only and do not feed the planning decision layer.</footer>
      </div>
    </main>
  );
}

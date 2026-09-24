import Image from "next/image";
import { ArrowDown, ArrowRight, ArrowUpRight, CircleHelp, FileSearch, House, Map, Microscope, ShieldCheck, Waves } from "lucide-react";
import copy from "@/lib/landing/copy.en.json";
import { landingGateStatus, resolveGateCriteria } from "@/lib/landing/gate-status";
import caseRecord from "../../../public/offline-demo/mae-sai/manifest.json";
import { LandingNavigation } from "./landing-nav.client";
import { AccessComparison, ConnectionDiagram, IllustrativeFinding } from "./illustrative-finding";
import NarrativeExperience from "./narrative-experience.client";
import { PipelineDiagram } from "./pipeline-diagram";
import { PipelineDetail } from "./pipeline-detail";
import styles from "./landing.module.css";

const workspaceIcons = [House, Map, Microscope];
const gateCriteria = resolveGateCriteria(copy.pipeline.gate.criteria, landingGateStatus);
const automatedHoldoutVerified = landingGateStatus.track === "automated" && gateCriteria.some(
  criterion => criterion.id === "preregistered_holdout_evaluation" && criterion.met,
);
const automatedCandidates = [
  { id: "mae_sai_m2_gamma0_10m_otsu_candidate", label: "M2 Gamma0 Otsu (10 m, radiometrically calibrated SAR input)" },
  { id: "mae_sai_20m_amplitude_comparator", label: "Amplitude comparator (raw radar amplitude, 20 m)" },
] as const;
const automatedAgreement = automatedHoldoutVerified ? automatedCandidates.flatMap(candidate => {
  const score = landingGateStatus.candidate_agreement?.[candidate.id];
  return score ? [{ ...candidate, score }] : [];
}) : [];
const sourceTime = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false }).format(new Date(caseRecord.source_timestamp));

function ChapterDetail({ id }: { id: string }) {
  if (id === "finding") return <IllustrativeFinding />;
  if (id === "access") return <><AccessComparison /><ConnectionDiagram disrupted /></>;
  if (id === "place") return <ConnectionDiagram />;
  return <div className={styles.evidenceDistinction}><span>Flood overlap</span><ArrowRight size={18}/><strong>A question to verify</strong><small>Not a confirmed closure</small></div>;
}

function StoryOverlay() {
  return <>
    <div className={styles.sceneReadingArea}>
      {copy.story.chapters.map(chapter => <div className={styles.scenePanel} data-story-panel={chapter.id} key={chapter.id}>
        <p className={styles.eyebrow}>{chapter.number} / {chapter.label}</p>
        <h2 data-story-reading={chapter.id}>{chapter.heading}</h2>
        <p className={styles.sceneBody}>{chapter.body}</p>
        <ChapterDetail id={chapter.id}/>
        <p className={styles.sceneCaution}>{chapter.callout}</p>
      </div>)}
    </div>
    <div className={`${styles.sceneAnnotation} ${styles.homeAnnotation}`} data-scene-annotation="home"><House size={15}/><span>Homes <small>Outside footprint</small></span></div>
    <div className={`${styles.sceneAnnotation} ${styles.facilityAnnotation}`} data-scene-annotation="facility"><ShieldCheck size={15}/><span>Essential service <small>Operation unverified</small></span></div>
    <div className={`${styles.sceneAnnotation} ${styles.linkAnnotation}`} data-scene-annotation="affected-link"><span className={styles.annotationDash}/><span>Assumed disrupted link <small>Not a confirmed closure</small></span></div>
    <p className={styles.droneCredit}>Synthetic illustration / Inferred geography / Not current conditions</p>
  </>;
}

export function LandingPage() {
  return <main className={styles.landing} data-landing id="main-content" tabIndex={-1} lang="en">
    <LandingNavigation />
    <section id="story" className={styles.story} aria-labelledby="landing-title">
      <NarrativeExperience chapterIds={copy.story.chapters.map(chapter => chapter.id)} chapterLabels={copy.story.chapters.map(chapter => chapter.short_label)}
        desktopPoster={<Image src="/landing/desktop-v4/far.webp" width={1600} height={900} alt="" sizes="100vw" loading="eager" />}
        desktopOverlay={<StoryOverlay />}
        opening={<section className={styles.hero} id="hero" aria-labelledby="landing-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>{copy.hero.eyebrow}</p>
            <h1 id="landing-title" data-desktop-headline>{copy.hero.heading_lines[0]}<br/>{copy.hero.heading_lines[1]}</h1>
            <p className={styles.heroBody}>{copy.hero.body}</p>
            <div className={styles.heroActions}><a className={styles.primaryButton} href={copy.hero.primary.href}>{copy.hero.primary.label}<ArrowUpRight size={18}/></a><a className={styles.textLink} href={copy.hero.secondary.href}>{copy.hero.secondary.label}<ArrowDown size={18}/></a></div>
            <p className={styles.heroScope}>{copy.hero.scope}</p>
          </div>
        </section>}
        openingVisual={<figure className={styles.heroArt}><Image src="/landing/desktop-v4/far.webp" alt="An authored Mae Sai-inspired town with a selected home-to-service connection. Geography is inferred, not a verified reconstruction." width={1600} height={900} sizes="100vw" loading="eager"/><figcaption data-opening-provenance>{copy.hero.scene_note}</figcaption></figure>}
        poster={<div data-story-posters>{copy.story.chapters.map((chapter, index) => <Image key={chapter.id} data-poster={index} data-poster-id={chapter.id} src={`/landing/desktop-v4/${chapter.asset}.webp`} width={1600} height={900} alt="" sizes="100vw" loading="lazy"/>)}</div>}>
        {copy.story.chapters.map((chapter, index) => <section className={styles.chapter} id={chapter.id} data-chapter data-story-chapter={index} key={chapter.id} aria-labelledby={`${chapter.id}-heading`}>
          <p className={styles.chapterLabel}>{chapter.number} / {chapter.label}</p>
          <h2 id={`${chapter.id}-heading`} data-story-reading={chapter.id}>{chapter.heading}</h2>
          <figure className={styles.chapterFigure}><Image src={`/landing/desktop-v4/${chapter.asset}.webp`} width={1600} height={900} alt={chapter.poster_alt} sizes="(max-width: 680px) 100vw, 900px" loading="lazy"/><figcaption>Synthetic illustration / Same neighborhood, same registered connections</figcaption></figure>
          <p className={styles.chapterBody}>{chapter.body}</p>
          <ChapterDetail id={chapter.id}/>
          <p className={styles.callout}><CircleHelp size={17}/>{chapter.callout}</p>
        </section>)}
      </NarrativeExperience>
    </section>

    <section className={styles.method} id="method" aria-labelledby="method-heading"><div className={styles.container}>
      <div className={styles.sectionIntro}><p className={styles.eyebrow}>{copy.method.eyebrow}</p><h2 id="method-heading">{copy.method.heading}</h2><p>{copy.method.body}</p></div>
      <ol className={styles.methodSteps}>{copy.method.steps.map((step, index) => <li key={step.title}><span className={styles.stepNumber}>0{index + 1}</span><h3>{step.title}</h3><p>{step.body}</p></li>)}</ol>
      <div className={styles.methodFooter}><p>{copy.method.note}</p><a className={styles.textLink} href="/command/">Explore the planning demo<ArrowUpRight size={18}/></a></div>
    </div></section>

    <section className={styles.inputs} id="inputs" aria-labelledby="inputs-heading"><div className={styles.container}>
      <div className={styles.sectionIntro}><p className={styles.eyebrow}>{copy.inputs.eyebrow}</p><h2 id="inputs-heading">{copy.inputs.heading}</h2><p>{copy.inputs.body}</p></div>
      {copy.inputs.groups.map(group => <div className={styles.inputGroup} key={group.id}>
        <h3 className={styles.inputGroupLabel}>{group.label}</h3>
        <ul className={styles.inputList}>
          {copy.inputs.items.filter(item => item.group === group.id).map(item => <li key={item.id} className={styles.inputCard} data-input-status={item.status}>
            <span className={styles.stepNumber}>{item.number}</span>
            <div>
              <h4>{item.title}</h4>
              <p className={styles.inputLayers}>{item.layers}</p>
              <p className={styles.inputPlain}>{item.plain}</p>
              <ul className={styles.inputFigures}>
                {item.figures.map(figure => <li key={figure.src}>
                  <figure>
                    <Image src={`/landing/inputs/${figure.src}.webp`} alt={figure.alt} width={figure.w} height={figure.h} sizes="(max-width: 680px) 90vw, 300px" loading="lazy"/>
                    <figcaption>{figure.label}</figcaption>
                  </figure>
                </li>)}
              </ul>
              <p className={styles.inputSource}>{item.figure_source}</p>
              <details className={styles.inputTechnical}><summary>Role in the workflow</summary><p>{item.technical}</p></details>
            </div>
            <span className={styles.inputStatus}>{item.status_label}</span>
          </li>)}
        </ul>
      </div>)}
      <p className={styles.methodFooter}>{copy.inputs.note}</p>
      <p className={styles.inputFigureNote}>{copy.inputs.figure_note}</p>
    </div></section>

    <section className={styles.pipeline} id="pipeline" aria-labelledby="pipeline-heading"><div className={styles.container}>
      <div className={styles.sectionIntro}><p className={styles.eyebrow}>{copy.pipeline.eyebrow}</p><h2 id="pipeline-heading">{copy.pipeline.heading}</h2><p>{copy.pipeline.body}</p></div>

      <PipelineDiagram />

      <div className={styles.pipelineLanes}>
        {copy.pipeline.lanes.map(lane => <div className={styles.pipelineLane} key={lane.id}><h3>{lane.label}</h3><p>{lane.body}</p></div>)}
      </div>

      <div className={styles.pipelineBlock}>
        <h3>{copy.pipeline.models.heading}</h3>
        <p>{copy.pipeline.models.body}</p>
        <div className={styles.tableScroll}><table className={styles.modelTable}>
          <thead><tr>{copy.pipeline.models.columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead>
          <tbody>{copy.pipeline.models.rows.map(row => <tr key={row.name} data-best={row.status === "best-on-rtc" ? "rtc" : row.status === "best-on-grd" ? "grd" : undefined}>
            <td><span className={styles.modelName}>{row.name}</span></td>
            <td><span className={styles.modelWhat}>{row.note}</span></td>
            <td>{row.grd}</td>
            <td>{row.rtc}</td>
            <td>{row.mae_sai}</td>
          </tr>)}</tbody>
        </table></div>
        <p className={styles.modelNote}>{copy.pipeline.models.caption}</p>
        <p className={styles.modelNote}>{copy.pipeline.models.spread}</p>
      </div>

      <div className={styles.pipelineBlock}>
        <h3>{copy.pipeline.gate.heading}</h3>
        <p>{copy.pipeline.gate.body}</p>
        <ul className={styles.gateList}>{gateCriteria.map(criterion => <li key={criterion.label} data-criterion-id={criterion.id} data-met={String(criterion.met)} data-source={criterion.source}>
          <span className={styles.gateMark} aria-hidden="true">{criterion.met ? "✓" : "✕"}</span>
          <span><strong>{criterion.label}</strong><small>{criterion.detail}</small></span>
        </li>)}</ul>
        {landingGateStatus.track === "automated" && <>
          <p className={styles.modelNote}>Human qualification and blind review were not performed.</p>
          <p className={styles.modelNote}>Any final-holdout score is agreement with an automated optical map, not accuracy.</p>
          <p className={styles.modelNote}>Contains modified Copernicus Sentinel data 2024.</p>
          {automatedAgreement.length > 0 ? <div className={styles.automatedAgreement} aria-label="Mae Sai automated hold-out agreement">
            {automatedAgreement.map(candidate => <p key={candidate.id} data-automated-score={candidate.id}>
              <strong>{candidate.label}:</strong> {candidate.score.iou === null ? "Not evaluable" : `IoU ${(candidate.score.iou * 100).toFixed(1)}%`} — agreement with an automated optical map, not accuracy.
              {candidate.score.evaluated_coverage !== null && <> Evaluated coverage {(candidate.score.evaluated_coverage * 100).toFixed(1)}%.</>}
              {candidate.score.meets_predeclared_limits ? " Pre-registered limits met." : " Pre-registered limits failed."}
            </p>)}
          </div> : <p className={styles.modelNote}>Final-holdout agreement scores are not available from a verified result.</p>}
        </>}
        <p className={styles.gateVerdict}>{gateCriteria.every(criterion => criterion.met) ? copy.pipeline.gate.verdict_met : copy.pipeline.gate.verdict}</p>
        <p className={styles.modelNote}>{copy.pipeline.gate.status_note.replace("{generated}", landingGateStatus.generated_utc)}</p>
      </div>

      <div className={styles.pipelineBlock}>
        <h3>{copy.pipeline.outcome.heading}</h3>
        <p>{copy.pipeline.outcome.body}</p>
        <div className={styles.outcomeCard}>
          <div><p className={styles.eyebrow}>{copy.pipeline.outcome.example_label}</p><span className={styles.outcomeScore}>{copy.pipeline.outcome.example_score}</span></div>
          <ArrowRight size={20} className={styles.outcomeArrow} aria-hidden="true"/>
          <span className={styles.outcomeClass}>{copy.pipeline.outcome.example_class}</span>
          <p className={styles.outcomeNote}>{copy.pipeline.outcome.example_note}</p>
        </div>
        <p className={styles.modelNote}>{copy.pipeline.note}</p>
      </div>

      <div className={styles.pipelineBlock}>
        <h3>Look inside any stage</h3>
        <p>Each stage below opens to the diagram that explains it and the actual source lines that implement it. Nothing here is a mock-up.</p>
        <PipelineDetail />
      </div>
    </div></section>

    <section className={styles.workspaces} id="workspaces" aria-labelledby="workspace-heading">
      <div className={`${styles.container} ${styles.sectionIntro}`}><p className={styles.eyebrow}>{copy.workspaces.eyebrow}</p><h2 id="workspace-heading">{copy.workspaces.heading}</h2><p>{copy.workspaces.body}</p></div>
      {copy.workspaces.cards.map((workspace, index) => {
        const Icon = workspaceIcons[index];
        return <article className={styles.productRow} data-product-view={workspace.id} key={workspace.id}>
          <div className={styles.container}>
            <div className={styles.productCopy}><Icon size={28} strokeWidth={1.6}/><p className={styles.eyebrow}>{workspace.audience}</p><h3>{workspace.name}</h3><p>{workspace.body}</p><a className={styles.primaryButton} href={workspace.href}>{workspace.action}<ArrowUpRight size={18}/></a><p className={styles.productQualification}>{workspace.detail}</p></div>
            <figure className={styles.productCapture}><Image src={`/landing/product/${workspace.image}`} width={workspace.width} height={workspace.height} alt={workspace.alt} sizes={workspace.id === "public" ? "(max-width: 680px) 90vw, 330px" : "(max-width: 900px) 90vw, 780px"} loading="lazy"/><figcaption>Actual {workspace.id === "command" ? "Planning" : workspace.id === "studio" ? "Studio" : "Public"} workspace / Historical demonstration</figcaption></figure>
          </div>
        </article>;
      })}
    </section>

    <section className={`${styles.case} ${styles.container}`} id="case" aria-labelledby="case-heading">
      <div className={styles.caseHeading}><div><p className={styles.eyebrow}>{copy.case.eyebrow}</p><h2 id="case-heading">{copy.case.heading}</h2></div><p>{copy.case.body}</p></div>
      <div className={styles.caseGrid}>
        <figure><Image src="/geoai/scene_s2_rgb.png" alt="Sentinel-2 optical context of the Mae Sai study area, acquired 18 February 2024. Not a September flood mask." width={440} height={440} sizes="(max-width: 760px) 90vw, 400px" loading="lazy"/><figcaption>Optical context / Sentinel-2 / 18 February 2024<br/><strong>Not a September flood mask or a matched before-and-after pair.</strong></figcaption></figure>
        <div className={styles.evidenceInventory}>{copy.case.evidence.map((entry, index) => <div data-evidence-status={entry.label} key={entry.label}><span>0{index + 1}</span><div><h3>{entry.label}</h3><p>{entry.body}</p><small>{entry.note}</small></div></div>)}</div>
      </div>
      <dl className={styles.caseFacts}>{copy.case.facts.map(fact => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}<div><dt>Flood source time</dt><dd><time dateTime={caseRecord.source_timestamp}>{sourceTime} UTC</time></dd></div><div><dt>Evidence status</dt><dd>Candidate / Non-operational</dd></div></dl>
      <p className={styles.caseLimitation}>{caseRecord.reason_blocked}</p>
      <details className={styles.provenance}><summary><FileSearch size={18}/>Source records and limitations</summary><p>Sentinel-1 flood context: September 2024. Sentinel-2 optical context: February 2024. WorldPop: 2020. Reporting boundaries: 2022. OSM roads and facilities: July 2026 extract, not confirmation of September 2024 or current operation.</p><p>Evidence record: <code>{caseRecord.data_version}</code>. Prepared {caseRecord.generated_at.slice(0, 10)}. No qualified evaluation or operational authorization.</p><a href="/offline-demo/mae-sai/manifest.json">Read the historical case manifest<ArrowUpRight size={16}/></a><a href="/geoai/mae-sai-real.json">Read the separate imagery and research record<ArrowUpRight size={16}/></a><a href="/landing/product/capture-manifest.json">Read the product capture provenance<ArrowUpRight size={16}/></a></details>
      <a className={styles.primaryButton} href="/studio/">Inspect the Mae Sai evidence<ArrowUpRight size={18}/></a>
    </section>

    <section className={`${styles.questions} ${styles.container}`} id="questions" aria-labelledby="questions-heading"><div><p className={styles.eyebrow}>QUESTIONS AND LIMITATIONS</p><h2 id="questions-heading">{copy.faq.heading}</h2></div><div>{copy.faq.items.map(item => <details key={item.question}><summary>{item.question}<span aria-hidden="true">+</span></summary><p>{item.answer}</p></details>)}</div></section>
    <footer className={styles.footer}><div className={styles.container}><div className={styles.footerMain}><div><a className={styles.brand} href="#hero"><span className={styles.publicBrandMark} aria-hidden="true"/><Waves size={28}/><span>FloodGuard.</span></a><p>{copy.footer.line}</p></div><nav aria-label="Footer workspaces">{copy.footer.links.map(link => <a key={link.href} href={link.href}>{link.label}<ArrowUpRight size={16}/></a>)}</nav></div><div className={styles.footerBottom}><p>{copy.footer.scope} Check DDPM and local-authority updates for current conditions.</p><span>{copy.footer.credit}</span></div></div></footer>
  </main>;
}

import story from "@/lib/landing-v1/story.json";
import maeSaiManifest from "../../../public/offline-demo/mae-sai/manifest.json";
import styles from "./supporting-sections.module.css";

const copy = story.supportingSections;
const historicalSource = maeSaiManifest.evidence_context.source_components.find(
  (source) => source.role === "historic_flood_context",
);
const candidateEvidence = maeSaiManifest.layers.find(
  (layer) => layer.layer_id === "public_preparedness_areas",
)?.evidence_state;

export function SupportingSections() {
  const observationDate = historicalSource?.source_timestamp
    ? new Intl.DateTimeFormat("en-GB", {
      day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
    }).format(new Date(historicalSource.source_timestamp))
    : null;

  return (
    <div className={styles.support}>
      <section className={styles.section} aria-labelledby="landing-how-heading">
        <p className={styles.eyebrow}>HOW FLOODGUARD WORKS</p>
        <h2 id="landing-how-heading">{copy.howItWorks.title}</h2>
        <ol className={styles.steps}>
          {copy.howItWorks.items.map((item, index) => (
            <li key={item.title}>
              <span className={styles.stepNumber} aria-hidden="true">0{index + 1}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="evidence" className={`${styles.section} ${styles.evidence}`} aria-labelledby="landing-evidence-heading">
        <div>
          <p className={styles.eyebrow}>HISTORICAL EVIDENCE</p>
          <h2 id="landing-evidence-heading">{copy.evidence.title}</h2>
          <p className={styles.intro}>{copy.evidence.body}</p>
          <a className={styles.textLink} href={copy.evidence.href}>
            Inspect the Mae Sai evidence <span aria-hidden="true">↗</span>
          </a>
        </div>
        <div className={styles.evidenceRecord}>
          <p className={styles.recordStatus}>Historical candidate · Non-operational</p>
          <h3>Mae Sai, Thailand</h3>
          <dl>
            {observationDate && historicalSource && (
              <>
                <div>
                  <dt>Flood observation</dt>
                  <dd><time dateTime={historicalSource.source_timestamp ?? undefined}>{observationDate}</time></dd>
                </div>
                <div><dt>Source</dt><dd>{historicalSource.source_name}</dd></div>
              </>
            )}
            <div><dt>Confidence</dt><dd>{candidateEvidence?.confidence_class ?? "Not established"}</dd></div>
            <div><dt>Use</dt><dd>Historical planning review</dd></div>
          </dl>
          <p className={styles.qualification}>
            {candidateEvidence?.confidence_reason ?? "Qualified real-event validation is not established for this case. Inspect the current evidence and limitations in Studio."}
          </p>
          <p className={styles.sourceNote}>The neighborhood in this story is illustrative; it is not the Mae Sai evidence map.</p>
        </div>
      </section>

      <section id="workspaces" className={styles.section} aria-labelledby="landing-workspaces-heading" tabIndex={-1}>
        <p className={styles.eyebrow}>EXPLORE THE WORKSPACES</p>
        <h2 id="landing-workspaces-heading">Choose the view for your next step.</h2>
        <div className={styles.workspaces}>
          {copy.workspaces.map((workspace) => (
            <a className={styles.workspace} href={workspace.href} key={workspace.href}>
              <span className={styles.audience}>{workspace.audience}</span>
              <h3>{workspace.title}</h3>
              <p>{workspace.body}</p>
              <span className={styles.workspaceAction}>Open workspace <span aria-hidden="true">↗</span></span>
            </a>
          ))}
        </div>
      </section>

      <section className={`${styles.section} ${styles.faq}`} aria-labelledby="landing-faq-heading">
        <div>
          <p className={styles.eyebrow}>A LITTLE MORE CONTEXT</p>
          <h2 id="landing-faq-heading">Before you explore.</h2>
        </div>
        <div className={styles.questions}>
          {copy.faq.map((item) => (
            <details key={item.q}>
              <summary>{item.q}<span className={styles.faqIndicator} aria-hidden="true" /></summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <div>
          <a href="#main-content" className={styles.brand}>FloodGuard<span aria-hidden="true">.</span></a>
          <p>Historical planning demonstration. Not an official warning system.</p>
        </div>
        <nav aria-label="Footer workspaces">
          <a href="/public/">Public</a>
          <a href="/command/">Planning</a>
          <a href="/studio/">Studio</a>
        </nav>
      </footer>
    </div>
  );
}

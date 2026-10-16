"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { STATUS_LABEL, type StageStatus } from "@/lib/pipeline-progress";
import { AGENDA, ALL_STAGES, BLOCKERS, FOLLOW_UP_DATE, followUpTopic, PIPELINE_STEPS, type FollowUpStage } from "@/lib/technical-follow-up";

import { DetailPanel, StatusIcon } from "./pipeline-explorer";
import styles from "./technical-follow-up.module.css";

function stageCounts(): Record<StageStatus, number> {
  const counts: Record<StageStatus, number> = { done: 0, in_progress: 0, not_started: 0 };
  for (const stage of ALL_STAGES) counts[followUpTopic(stage.topic).status] += 1;
  return counts;
}

/** Mentoring Session II, 0:10 to 0:25: the technical follow-up, with every pipeline stage opening its evidence. */
export function TechnicalFollowUp() {
  const [selected, setSelected] = useState<FollowUpStage | null>(null);
  const opener = useRef<HTMLElement | null>(null);

  const open = useCallback((stage: FollowUpStage) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelected(stage);
    try {
      window.history.replaceState(null, "", `#${stage.id}`);
    } catch {
      // The address stays as it is.
    }
  }, []);

  const close = useCallback(() => {
    setSelected(null);
    try {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch {
      // The address stays as it is.
    }
    opener.current?.focus();
  }, []);

  // A link to a stage (#own-radar) opens it.
  useEffect(() => {
    let frame = 0;
    const openFromHash = () => {
      const stage = ALL_STAGES.find((item) => item.id === window.location.hash.slice(1));
      if (stage) frame = window.requestAnimationFrame(() => setSelected(stage));
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", openFromHash);
    };
  }, []);

  const counts = stageCounts();

  return (
    <main id="main-content" className={styles.page} lang="en">
      <header className={styles.head}>
        <a className={styles.back} href="/studio/">← Studio</a>
        <p className={styles.eyebrow}>TEAM BEATS · FLOODGUARD THAILAND · MENTORING SESSION II · 0:10–0:25</p>
        <h1>Follow-up on technical mentoring</h1>
        <p className={styles.lead}><strong>Since Session I:</strong> the pipeline runs end to end on eight real tambons. Every test bar was fixed before the test, and we publish the misses.</p>
        <table className={styles.agenda}>
          <caption className={styles.srOnly}>Agenda</caption>
          <thead><tr><th scope="col">Time</th><th scope="col">Part</th></tr></thead>
          <tbody>
            {AGENDA.map((item, index) => (
              <tr key={item.time}><td>{item.time}</td><td><a href={`#part-${index + 1}`}>{item.part}</a></td></tr>
            ))}
          </tbody>
        </table>
      </header>

      <section id="part-1" className={styles.part} aria-labelledby="part-1-title">
        <p className={styles.kicker}>PART 1 · 0:10–0:14</p>
        <h2 id="part-1-title">Data pipeline: {counts.done} of {ALL_STAGES.length} stages run end to end</h2>
        <p className={styles.hint}>Select a stage to see what it does, where it stands, and the documents, pages and images behind it.</p>
        <div className={styles.board}>
          {PIPELINE_STEPS.map((step) => (
            <div key={step.id} className={styles.step} data-step={step.id}>
              <h3 className={styles.stepHead} style={{ background: step.colour }}>{step.title}</h3>
              <ul className={styles.stages}>
                {step.stages.map((stage) => {
                  const status = followUpTopic(stage.topic).status;
                  return (
                    <li key={stage.id}>
                      <button
                        type="button"
                        className={styles.stage}
                        data-stage={stage.id}
                        data-status={status}
                        data-selected={selected?.id === stage.id}
                        aria-label={`${stage.title}: ${STATUS_LABEL[status]}. Open the details.`}
                        onClick={() => open(stage)}
                      >
                        <StatusIcon status={status} />
                        <span className={styles.stageText}>
                          <strong>{stage.title}</strong>
                          <span>{stage.lines[0]}</span>
                          <span>{stage.lines[1]}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <ul className={styles.legend} aria-label="Stages by status">
          <li><StatusIcon status="done" /> <strong>{counts.done}</strong> run end to end</li>
          <li><StatusIcon status="in_progress" /> <strong>{counts.in_progress}</strong> run with limits or low confidence</li>
          <li><StatusIcon status="not_started" /> <strong>{counts.not_started}</strong> not done</li>
        </ul>
        <p className={styles.note}>Every output carries its source time, confidence and assumptions. Low confidence can never raise a class.</p>
      </section>

      <section id="part-2" className={styles.part} aria-labelledby="part-2-title">
        <p className={styles.kicker}>PART 2 · 0:14–0:19</p>
        <h2 id="part-2-title">GeoAI decisions: bars fixed in advance, simple models held up</h2>
        <figure className={styles.graphic}>
          <a href="/studio-pipeline/geoai-decisions.png" target="_blank" rel="noreferrer" title="Open the graphic at full size">
            {/* eslint-disable-next-line @next/next/no-img-element -- a static graphic of this site */}
            <img src="/studio-pipeline/geoai-decisions.png" alt="Three decisions. Nan, July 2025: our radar map scored IoU 0.23 against JAXA's ALOS-2 map, under the bar of 0.40 fixed before the test; comparators scored 0.40 to 0.51. THEOS-2 tile at Sukhothai: the trained classifier scored 0.11 against 0.57 for a one-feature threshold. Flood susceptibility on three unseen districts: ROC AUC 0.923 for one terrain feature, 0.921 and 0.925 for the trees, so the one-feature model is cited." />
          </a>
          <figcaption>Decision 1 uses the Nan case of draft PR #66. IoU is the overlap of two water maps divided by their union; agreement with another map or image, not ground truth.</figcaption>
        </figure>
        <ul className={styles.related}>
          <li><button type="button" onClick={() => open(ALL_STAGES.find((stage) => stage.id === "own-radar")!)}>Details: our own radar map</button></li>
          <li><button type="button" onClick={() => open(ALL_STAGES.find((stage) => stage.id === "theos2")!)}>Details: THEOS-2 check</button></li>
          <li><button type="button" onClick={() => open(ALL_STAGES.find((stage) => stage.id === "susceptibility")!)}>Details: susceptibility model</button></li>
        </ul>
      </section>

      <section id="part-3" className={styles.part} aria-labelledby="part-3-title">
        <p className={styles.kicker}>PART 3 · 0:19–0:23</p>
        <h2 id="part-3-title">Uncertainty is measured, and it changes what the page says</h2>
        <figure className={styles.graphic}>
          <a href="/studio-pipeline/uncertainty.png" target="_blank" rel="noreferrer" title="Open the graphic at full size">
            {/* eslint-disable-next-line @next/next/no-img-element -- a static graphic of this site */}
            <img src="/studio-pipeline/uncertainty.png" alt="How often each Mae Sai tambon keeps its class over 180 runs: Mae Sai town 50%, under the 60% rule, so it reads unstable: verify; Ko Chang 78%, Pong Pha 98%, the other five 100%. Four rules: run it 180 ways; a class must hold or the page says verify; low confidence can never raise a class; say ranges where the data disagree." />
          </a>
          <figcaption>Report-only: the published page still says &quot;stability not evaluated&quot;. Class E never means safe.</figcaption>
        </figure>
        <ul className={styles.related}>
          <li><button type="button" onClick={() => open(ALL_STAGES.find((stage) => stage.id === "stability")!)}>Details: stability over 180 runs</button></li>
          <li><button type="button" onClick={() => open(ALL_STAGES.find((stage) => stage.id === "score")!)}>Details: score and class A–E</button></li>
        </ul>
      </section>

      <section id="part-4" className={styles.part} aria-labelledby="part-4-title">
        <p className={styles.kicker}>PART 4 · 0:23–0:25</p>
        <h2 id="part-4-title">Unresolved blockers</h2>
        <table className={styles.blockers}>
          <thead><tr><th scope="col">#</th><th scope="col">Blocker</th><th scope="col">What would unblock it</th></tr></thead>
          <tbody>
            {BLOCKERS.map((item, index) => (
              <tr key={item.blocker}><td>{index + 1}</td><td>{item.blocker}</td><td>{item.unblock}</td></tr>
            ))}
          </tbody>
        </table>
        <div className={styles.question}>
          <p className={styles.kicker}>OUR QUESTION</p>
          <p>Which blocker matters most to the judges, and which can we leave as &quot;stated, not solved&quot;?</p>
        </div>
      </section>

      <footer className={styles.footer}>
        <p>As of {FOLLOW_UP_DATE}. Modelled planning scenarios, not observations. Not real-time and not an official warning.</p>
        <p>All five proposal figures, box by box: <a href="/studio/pipeline/">Pipeline progress</a>.</p>
      </footer>

      {selected ? <DetailPanel topic={followUpTopic(selected.topic)} onClose={close} /> : null}
    </main>
  );
}


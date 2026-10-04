import Image from "next/image";
import detail from "@/lib/landing/pipeline-detail.json";
import styles from "./landing.module.css";

type Token = [string, string];

/**
 * The box-by-box technical detail behind the pipeline diagram: one diagram and
 * the real source lines for each stage. Collapsed by default so the public page
 * stays readable, and open to anyone who wants to check the claim.
 *
 * Diagrams and code are extracted from the pipeline walkthrough; the code is
 * tokenised at build time rather than injected as HTML.
 */
type Row = { label: string; body: string };

export function PipelineDetail() {
  const boxes = detail.filter((box) => box.viz || box.codes.length > 0 || (box.rows?.length ?? 0) > 0);

  return (
    <div className={styles.detailList}>
      {boxes.map((box) => (
        <details className={styles.detailBox} key={box.id}>
          <summary>
            <span className={styles.detailStep}>{box.step}</span>
            <span className={styles.detailTitle}>{box.title}</span>
            <span className={styles.detailMeta}>
              {box.viz ? "diagram" : null}
              {box.viz && box.codes.length > 0 ? " · " : null}
              {box.codes.length > 0 ? `${box.codes.length} code ${box.codes.length === 1 ? "extract" : "extracts"}` : null}
            </span>
          </summary>

          <div className={styles.detailBody}>
            {(box.rows?.length ?? 0) > 0 ? (
              <dl className={styles.detailRows}>
                {(box.rows as Row[]).map((row) => (
                  <div key={row.label}>
                    <dt>{row.label}</dt>
                    <dd>{row.body}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            {box.viz ? (
              <figure className={styles.detailFigure}>
                {/* unoptimized: these are hand-authored vector diagrams, and Next's
                    image optimizer refuses SVG unless dangerouslyAllowSVG is set. */}
                <Image
                  src={`/landing/pipeline/${box.viz.src}`}
                  alt={box.viz.alt}
                  width={box.viz.w}
                  height={box.viz.h}
                  sizes="(max-width: 680px) 92vw, 760px"
                  loading="lazy"
                  unoptimized
                />
                <figcaption>{box.viz.caption}</figcaption>
              </figure>
            ) : null}

            {box.codes.map((code) => (
              <figure className={styles.detailCode} key={code.caption}>
                <figcaption>{code.caption}</figcaption>
                <pre>
                  <code>
                    {(code.tokens as Token[]).map(([cls, text], index) => (
                      <span key={index} className={cls ? styles[`tok${cls.toUpperCase()}`] : undefined}>
                        {text}
                      </span>
                    ))}
                  </code>
                </pre>
              </figure>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

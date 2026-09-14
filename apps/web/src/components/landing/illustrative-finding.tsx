import { ILLUSTRATIVE_FINDING, ILLUSTRATIVE_SCENARIO } from "@/lib/landing/illustrative-scenario";
import styles from "./landing.module.css";

/** Registered plan view of exactly the links used by the illustrative reachability result. */
export function ConnectionDiagram({ disrupted = false }: { disrupted?: boolean }) {
  const scenario = ILLUSTRATIVE_SCENARIO;
  const point = (id: string) => scenario.nodes.find(node => node.id === id)!.position;
  const project = ([x, z]: readonly [number, number]) => [38 + (x + 12) * 17, 27 + (z + 4.05) * 9];
  const home = project(point(scenario.homeId));
  const facility = project(point(scenario.facilityId));
  return <figure className={styles.networkFigure} data-network-diagram={disrupted ? "assumed-disruption" : "baseline"}>
    <svg viewBox="0 0 320 155" role="img" aria-label={disrupted ? "Synthetic network: one assumed disrupted link breaks the home-to-service connection." : "Synthetic network: homes connect to the essential service through the blue links."}>
      {scenario.links.map(link => {
        const [x1, y1] = project(point(link.from)), [x2, y2] = project(point(link.to));
        const affected = disrupted && link.id === scenario.assumedDisruptedLinkId;
        return <line key={link.id} x1={x1} y1={y1} x2={x2} y2={y2} stroke={affected ? "#9a4309" : "#0f4c81"} strokeWidth={affected ? 5 : 3} strokeDasharray={affected ? "3 5" : undefined} data-link-id={link.id} />;
      })}
      <circle cx={home[0]} cy={home[1]} r="6" fill="#fff" stroke="#0f4c81" strokeWidth="3"/>
      <rect x={facility[0] - 6} y={facility[1] - 6} width="12" height="12" fill="#fff" stroke="#0f4c81" strokeWidth="3"/>
      <text x={home[0] - 10} y={home[1] - 14} fontSize="11" fill="#334155">Homes</text>
      <text x={facility[0] - 28} y={facility[1] + 23} fontSize="11" fill="#334155">Service</text>
    </svg>
    <figcaption>{disrupted ? "Same graph / one link assumed disrupted" : "Selected connections / synthetic baseline"}</figcaption>
  </figure>;
}

export function IllustrativeFinding() {
  return <div className={styles.finding} data-illustrative-finding data-scenario-id={ILLUSTRATIVE_FINDING.scenarioId}>
    <p className={styles.findingScope}>SYNTHETIC EXAMPLE / NOT A MAE SAI RESULT</p>
    <dl>
      <div data-finding-field="finding"><dt>Finding</dt><dd>{ILLUSTRATIVE_FINDING.scenario.reachable ? "A modeled connection remains." : "Potential loss of essential-service access."}</dd></div>
      <div data-finding-field="reason"><dt>Reason</dt><dd>The selected homes depend on the link assumed disrupted.</dd></div>
      <div data-finding-field="uncertainty"><dt>Uncertainty</dt><dd>Actual road status, facility operation, and other connections are unverified.</dd></div>
      <div data-finding-field="next-step"><dt>Next review</dt><dd>Verify the connection and review contingency access.</dd></div>
    </dl>
  </div>;
}

export function AccessComparison() {
  return <dl className={styles.accessComparison} data-access-comparison>
    <div><dt>Baseline</dt><dd>{ILLUSTRATIVE_FINDING.baseline.reachable ? "Connected" : "No connection"}</dd></div>
    <div><dt>Assumed disruption</dt><dd>{ILLUSTRATIVE_FINDING.scenario.reachable ? "Connection remains" : "Connection unavailable"}</dd></div>
  </dl>;
}

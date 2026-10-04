import styles from "./landing.module.css";

/**
 * The evidence-to-decision flow as one picture: three inputs converge, three
 * candidate methods compete, and a single gate decides whether the result may
 * influence anything. The travelling pulse takes the FAIL path, because that is
 * the state Mae Sai is actually in. Motion is CSS-only and is disabled under
 * prefers-reduced-motion; the diagram reads identically when still.
 */
export function PipelineDiagram() {
  return (
    <figure className={styles.pipelineFigure}>
      <svg
        viewBox="0 0 880 300"
        role="img"
        className={styles.pipelineSvg}
        aria-label="Radar, terrain and water context are aligned onto one grid, three candidate methods produce a flood probability, and a promotion gate decides whether it may enter the protected decision layer. Mae Sai currently takes the fail path to a blocked, report-only record."
      >
        <defs>
          <marker id="pipe-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <polygon points="0,0 10,5 0,10" fill="currentColor" />
          </marker>
        </defs>

        <text className={styles.pipeLane} x="16" y="20">FLOOD EVIDENCE</text>
        <text className={styles.pipeLane} x="616" y="20">DECISION LAYER</text>

        {/* three inputs */}
        {[["Radar", 44], ["Terrain", 96], ["Water context", 148]].map(([label, y]) => (
          <g key={label as string}>
            <rect x="16" y={(y as number) - 15} width="118" height="30" rx="2" className={styles.pipeBox} />
            <text className={styles.pipeText} x="75" y={(y as number) + 4} textAnchor="middle">{label}</text>
            <line x1="134" y1={y as number} x2="176" y2="96" className={styles.pipeLine} markerEnd="url(#pipe-arrow)" />
          </g>
        ))}

        {/* alignment */}
        <rect x="178" y="74" width="96" height="44" rx="2" className={styles.pipeBox} />
        <text className={styles.pipeText} x="226" y="92" textAnchor="middle">One grid</text>
        <text className={styles.pipeSmall} x="226" y="107" textAnchor="middle">aligned stack</text>
        <line x1="274" y1="96" x2="312" y2="96" className={styles.pipeLine} markerEnd="url(#pipe-arrow)" />

        {/* three candidate methods */}
        {[["Change detection", 50], ["Trees", 96], ["U-Net", 142]].map(([label, y]) => (
          <g key={label as string}>
            <rect x="314" y={(y as number) - 15} width="108" height="30" rx="2" className={styles.pipeBox} />
            <text className={styles.pipeText} x="368" y={(y as number) + 4} textAnchor="middle">{label}</text>
            <line x1="422" y1={y as number} x2="458" y2="96" className={styles.pipeLine} markerEnd="url(#pipe-arrow)" />
          </g>
        ))}

        {/* derived product */}
        <rect x="460" y="74" width="104" height="44" rx="2" className={styles.pipeDerived} />
        <text className={styles.pipeText} x="512" y="92" textAnchor="middle">Flood map</text>
        <text className={styles.pipeSmall} x="512" y="107" textAnchor="middle">+ uncertainty</text>

        {/* the gate */}
        <line x1="564" y1="96" x2="600" y2="96" className={styles.pipeLine} markerEnd="url(#pipe-arrow)" />
        <polygon points="662,52 726,96 662,140 598,96" className={styles.pipeGate} />
        <text className={styles.pipeGateText} x="662" y="92" textAnchor="middle">promotion</text>
        <text className={styles.pipeGateText} x="662" y="106" textAnchor="middle">gate</text>

        {/* pass path - not taken */}
        <path id="pipe-pass" d="M726 84 L800 52" className={styles.pipePass} markerEnd="url(#pipe-arrow)" />
        <text className={styles.pipeSmall} x="742" y="42">pass</text>
        <rect x="778" y="32" width="88" height="40" rx="2" className={styles.pipeBoxMuted} />
        <text className={styles.pipeSmall} x="822" y="50" textAnchor="middle">decision</text>
        <text className={styles.pipeSmall} x="822" y="63" textAnchor="middle">layer</text>

        {/* fail path - the one actually taken */}
        <path id="pipe-fail" d="M726 110 L800 148" className={styles.pipeFail} markerEnd="url(#pipe-arrow)" />
        <text className={styles.pipeFailLabel} x="736" y="160">fail</text>
        <rect x="778" y="128" width="88" height="42" rx="2" className={styles.pipeBlocked} />
        <text className={styles.pipeBlockedText} x="822" y="146" textAnchor="middle">BLOCKED</text>
        <text className={styles.pipeBlockedText} x="822" y="159" textAnchor="middle">report-only</text>

        {/* travelling pulse: inputs -> stack -> methods -> map -> gate -> fail */}
        <circle r="4.5" className={styles.pipePulse}>
          <animateMotion
            dur="7s"
            repeatCount="indefinite"
            keyPoints="0;0.18;0.34;0.52;0.70;0.88;1"
            keyTimes="0;0.16;0.32;0.5;0.68;0.86;1"
            calcMode="linear"
            path="M75 96 L226 96 L368 96 L512 96 L662 96 L760 128 L800 148"
          />
        </circle>

        <text className={styles.pipeSmall} x="16" y="212">Everything left of the gate is candidate evidence.</text>
        <text className={styles.pipeSmall} x="16" y="228">Everything right of it is deterministic and reproducible by hand.</text>
      </svg>
      <figcaption>
        The pulse follows the path Mae Sai actually takes today: through alignment and the candidate
        methods, into the gate, and out along the fail arrow to a blocked, report-only record.
      </figcaption>
    </figure>
  );
}

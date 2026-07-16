import type { PilotReadiness } from "@floodguard/contracts";

import { pilotReadinessCopy } from "@/lib/pilot-readiness";
import type { Language } from "@/lib/types";

interface PilotReadinessPanelProps {
  readiness: PilotReadiness;
  language: Language;
  surface: "command" | "studio";
  compact?: boolean;
}

export function PilotReadinessPanel({
  readiness,
  language,
  surface,
  compact = false,
}: PilotReadinessPanelProps) {
  const copy = pilotReadinessCopy(readiness, language);
  const titleId = `${surface}-pilot-readiness-title`;
  return (
    <section
      className={`pilot-readiness-panel ${compact ? "compact" : ""}`}
      aria-labelledby={titleId}
    >
      <div className="pilot-readiness-heading">
        <div>
          <p className="eyebrow">{language === "th" ? "ขอบเขตนำร่อง" : "Pilot boundary"}</p>
          <h2 id={titleId}>{copy.title}</h2>
        </div>
        <span className={readiness.agency_operational_allowed ? "accepted" : "blocked"}>
          {copy.status}
        </span>
      </div>
      <dl className="pilot-readiness-grid">
        <div><dt>{copy.identity}</dt><dd>{readiness.identity_state}</dd></div>
        <div><dt>{copy.acceptance}</dt><dd>{readiness.acceptance_receipt_state}</dd></div>
        <div><dt>{copy.audit}</dt><dd>{readiness.audit_state}</dd></div>
        <div><dt>{copy.retention}</dt><dd>{readiness.retention_state}</dd></div>
        <div><dt>{copy.protocol}</dt><dd>{readiness.field_validation_protocol_version}</dd></div>
        <div><dt>{language === "th" ? "สถานะ" : "Operating state"}</dt><dd>{readiness.operational_status}</dd></div>
      </dl>
      {copy.reason && <p className="pilot-blocked-reason">{copy.reason}</p>}
      <p className="pilot-auth-boundary">{copy.boundary}</p>
    </section>
  );
}

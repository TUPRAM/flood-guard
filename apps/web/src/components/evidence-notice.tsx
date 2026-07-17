import type { ReactNode } from "react";

type EvidenceNoticeTone = "info" | "caution" | "blocked" | "ready";

export function EvidenceNotice({
  children,
  title,
  tone = "info",
}: {
  children: ReactNode;
  title: string;
  tone?: EvidenceNoticeTone;
}) {
  return (
    <article className={`evidence-notice ${tone}`}>
      <span className="evidence-notice-mark" aria-hidden="true" />
      <div><b>{title}</b><p>{children}</p></div>
    </article>
  );
}

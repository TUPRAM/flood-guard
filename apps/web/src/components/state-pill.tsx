import type { ReactNode } from "react";

type StatePillTone = "info" | "caution" | "blocked" | "ready";

export function StatePill({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: StatePillTone;
}) {
  return <span className={`state-pill ${tone}`}>{children}</span>;
}

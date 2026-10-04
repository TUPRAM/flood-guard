import type { Metadata } from "next";
import { EvidenceLibrary } from "@/components/evidence-library";

export const metadata: Metadata = {
  title: "Study-area evidence library",
  description: "Read-only candidate data, coverage gaps and explicitly labelled research scenarios for FloodGuard study areas.",
};

export default function EvidenceLibraryPage() {
  return <EvidenceLibrary />;
}

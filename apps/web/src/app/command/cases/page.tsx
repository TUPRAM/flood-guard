import type { Metadata } from "next";
import { EvidenceLibrary } from "@/components/evidence-library";

export const metadata: Metadata = { title: "Case comparisons | FloodGuard Command", description: "Shared service-specific research scenarios and evidence; no operational decisions." };
export default function CommandCasesPage() { return <EvidenceLibrary view="brief" role="planning" />; }
